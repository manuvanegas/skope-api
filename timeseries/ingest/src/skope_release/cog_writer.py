"""Write COGs from a `ValidatedBuildPlan` (Section 12).

Temporal sources are read once, in horizontal swaths covering every band, and
distributed to one band-interleaved scratch GeoTIFF per chunk. Each scratch file
is then converted to a COG. This reads a pixel-interleaved source once rather
than once per chunk. Scratch files live beside the staging directory and are
removed as soon as their COG is written.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from osgeo import gdal

from . import gdalio
from .plan import PlannedVariable, ValidatedBuildPlan, require_plan

log = logging.getLogger(__name__)

SWATH_BUDGET_BYTES = 1536 * 1024 * 1024
_ITEMSIZE = {"uint8": 1, "int8": 1, "uint16": 2, "int16": 2, "uint32": 4, "int32": 4, "float32": 4, "float64": 8}


def cog_creation_options(plan: ValidatedBuildPlan, variable: PlannedVariable) -> list[str]:
    """Creation options are part of the declaration (META-004, Section 12.1)."""
    cog = plan.resolved_manifest.release.cog
    enc = variable.encoding
    options = [
        f"BLOCKSIZE={cog.blocksize}",
        f"COMPRESS={cog.compress}",
        f"PREDICTOR={enc.predictor}",
        f"INTERLEAVE={cog.interleave}",
        "OVERVIEWS=IGNORE_EXISTING",
        f"OVERVIEW_RESAMPLING={enc.overview_resampling}",
        "STATISTICS=YES",
        f"BIGTIFF={cog.bigtiff}",
        "SPARSE_OK=FALSE",
        "NUM_THREADS=ALL_CPUS",
    ]
    if cog.level is not None:
        options.append(f"LEVEL={cog.level}")
    return options


def _swath_rows(width: int, bands: int, itemsize: int, block_height: int, height: int) -> int:
    per_row = width * bands * itemsize
    rows = max(1, SWATH_BUDGET_BYTES // per_row)
    if rows >= block_height:
        rows -= rows % block_height  # whole source blocks: each tile is decoded once
    return min(rows, height)


def _prepare_scratch(path: Path, plan: ValidatedBuildPlan, variable: PlannedVariable, bands: int, rows_per_strip: int, names: list[str]):
    enc = variable.encoding
    ds = gdal.GetDriverByName("GTiff").Create(
        str(path),
        plan.grid.width,
        plan.grid.height,
        bands,
        gdalio.STAC_TO_GDAL_TYPE[enc.data_type],
        options=[
            "INTERLEAVE=BAND",
            "TILED=NO",
            f"BLOCKYSIZE={rows_per_strip}",
            "COMPRESS=ZSTD",
            "ZSTD_LEVEL=1",
            f"PREDICTOR={enc.predictor}",
            "BIGTIFF=YES",
        ],
    )
    ds.SetGeoTransform(plan.grid.geotransform)  # the canonical grid (OBS-003)
    ds.SetProjection(plan.grid.crs_wkt)
    ds.SetMetadataItem("AREA_OR_POINT", plan.grid.area_or_point)
    for i, name in enumerate(names, start=1):
        band = ds.GetRasterBand(i)
        band.SetDescription(name)  # COG-006: canonical timestep or variable identifier
        if enc.nodata is not None:
            band.SetNoDataValue(enc.nodata)
        band.SetScale(enc.scale)
        band.SetOffset(enc.offset)
        band.SetUnitType(variable.curated.unit)
    return ds


def _encode(block, variable: PlannedVariable):
    """Apply an approved narrowing (COG-016): proven-representable values keep their value; nodata maps to nodata."""
    enc = variable.encoding
    target = np.dtype(enc.data_type)
    if block.dtype == target:
        return block
    out = block.astype(target)
    if variable.source_nodata is not None and enc.nodata is not None:
        out[block == variable.source_nodata] = enc.nodata
    return out


def _to_cog(scratch: Path, target: Path, options: list[str]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    gdal.Translate(str(target), str(scratch), format="COG", creationOptions=options)


def write_temporal_variable(plan: ValidatedBuildPlan, variable: PlannedVariable, staging: Path, scratch_dir: Path) -> list[Path]:
    layout = plan.layout
    keys = plan.axis.keys()
    itemsize = _ITEMSIZE[variable.encoding.data_type]
    written: list[Path] = []
    with gdal.Open(variable.source_read_path) as src:
        block_height = src.GetRasterBand(1).GetBlockSize()[1]
        rows = _swath_rows(src.RasterXSize, src.RasterCount, itemsize, block_height, src.RasterYSize)
        scratch_paths, scratches = [], []
        for chunk in range(layout.chunk_count):
            first, last = layout.bounds(chunk)
            path = scratch_dir / f"{variable.id}--{chunk:05d}.tif"
            scratch_paths.append(path)
            scratches.append(_prepare_scratch(path, plan, variable, last - first + 1, rows, list(keys[first : last + 1])))
        log.info("%s: one pass over %d bands in swaths of %d rows", variable.id, src.RasterCount, rows)
        for y in range(0, src.RasterYSize, rows):
            height = min(rows, src.RasterYSize - y)
            swath = src.ReadAsArray(0, y, src.RasterXSize, height)
            if swath.ndim == 2:
                swath = swath[None, ...]
            for chunk, scratch in enumerate(scratches):
                first, last = layout.bounds(chunk)
                for offset, index in enumerate(range(first, last + 1), start=1):
                    scratch.GetRasterBand(offset).WriteArray(_encode(swath[index], variable), 0, y)
            del swath
        for scratch in scratches:
            scratch.Close()  # the COG step must read complete scratch files
        scratches.clear()
    options = cog_creation_options(plan, variable)
    jobs = [(path, staging / layout.cog_path(variable.id, chunk)) for chunk, path in enumerate(scratch_paths)]
    # Chunks are independent, so they convert in parallel; bytes do not depend on the order.
    with ProcessPoolExecutor(max_workers=workers(), mp_context=multiprocessing.get_context("spawn")) as pool:
        futures = {pool.submit(_convert, str(scratch), str(target), options): target for scratch, target in jobs}
        for future in as_completed(futures):
            future.result()
            log.info("wrote %s", futures[future].relative_to(staging))
    for scratch, target in jobs:
        scratch.unlink()
        written.append(target)
    return written


def workers() -> int:
    return max(1, int(os.environ.get("SKOPE_RELEASE_WORKERS", "4")))


def _convert(scratch: str, target: str, options: list[str]) -> None:
    gdalio.configure()
    _to_cog(Path(scratch), Path(target), options)


def write_static_variable(plan: ValidatedBuildPlan, variable: PlannedVariable, staging: Path, scratch_dir: Path) -> list[Path]:
    path = scratch_dir / f"{variable.id}.tif"
    with gdal.Open(variable.source_read_path) as src:
        block_height = src.GetRasterBand(variable.source_band).GetBlockSize()[1]
        rows = _swath_rows(src.RasterXSize, 1, _ITEMSIZE[variable.encoding.data_type], block_height, src.RasterYSize)
        scratch = _prepare_scratch(path, plan, variable, 1, rows, [variable.id])
        band = src.GetRasterBand(variable.source_band)
        for y in range(0, src.RasterYSize, rows):
            height = min(rows, src.RasterYSize - y)
            scratch.GetRasterBand(1).WriteArray(_encode(band.ReadAsArray(0, y, src.RasterXSize, height), variable), 0, y)
        scratch.Close()
    target = staging / "cogs" / f"{variable.id}.tif"  # ORG-009
    _to_cog(path, target, cog_creation_options(plan, variable))
    path.unlink()
    return [target]


def write_cogs(plan: object, staging: Path, scratch_dir: Path) -> list[Path]:
    """Write every COG of a release into `staging` (TXN-001 step 1)."""
    plan = require_plan(plan)
    gdalio.configure()
    scratch_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for variable in plan.variables:
        writer = write_temporal_variable if plan.temporal else write_static_variable
        written.extend(writer(plan, variable, staging, scratch_dir))
    for leftover in scratch_dir.iterdir():
        leftover.unlink()
    os.rmdir(scratch_dir)
    return written
