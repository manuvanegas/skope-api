"""Checks source rasters against the dataset description before any output is written.

Only raster headers are read, so a preflight over remote sources takes seconds.
"""

from dataclasses import dataclass

from osgeo import gdal

from . import fs_utils
from .dataset_metadata import DatasetSpec, is_period_key
from .manifest import ManifestVariable


@dataclass(frozen=True)
class SourceInfo:
    variable_id: str
    uri: str
    band_count: int
    crs: str | None
    # rasterio/STAC order (a, b, c, d, e, f, 0, 0, 1), as the registry stores it
    transform: tuple[float, ...]
    shape: tuple[int, int]
    first_description: str
    last_description: str


def inspect_source(variable: ManifestVariable) -> SourceInfo:
    with gdal.Open(fs_utils.to_vsi(variable.uri)) as ds:
        band_count = ds.RasterCount
        gt = ds.GetGeoTransform()
        first = ds.GetRasterBand(1).GetDescription() if band_count else ""
        last = ds.GetRasterBand(band_count).GetDescription() if band_count else ""
        return SourceInfo(
            variable_id=variable.id,
            uri=variable.uri,
            band_count=band_count,
            crs=_epsg_code(ds.GetSpatialRef()),
            transform=(gt[1], gt[2], gt[0], gt[4], gt[5], gt[3], 0.0, 0.0, 1.0),
            shape=(ds.RasterYSize, ds.RasterXSize),
            first_description=first,
            last_description=last,
        )


def _epsg_code(srs) -> str | None:
    if srs is None:
        return None
    if srs.GetAuthorityName(None) != "EPSG":
        try:
            srs.AutoIdentifyEPSG()
        except RuntimeError:
            return None
    code = srs.GetAuthorityCode(None)
    if srs.GetAuthorityName(None) == "EPSG" and code:
        return f"EPSG:{code}"
    return None


def validate_sources(spec: DatasetSpec, sources: list[SourceInfo]) -> list[str]:
    errors = []
    expected = spec.expected_band_count
    for source in sources:
        if source.band_count != expected:
            errors.append(
                f"{source.variable_id}: the source has {source.band_count} bands, but "
                f"the dataset file's timespan {spec.gte} to {spec.lte} needs "
                f"{expected} ({source.uri})"
            )
        first, last = source.first_description, source.last_description
        if (
            is_period_key(first)
            and is_period_key(last)
            and (first, last) != (spec.gte, spec.lte)
        ):
            errors.append(
                f"{source.variable_id}: band descriptions run {first} to {last}, but "
                f"the dataset file declares {spec.gte} to {spec.lte}"
            )
        if source.crs is None:
            errors.append(
                f"{source.variable_id}: the source has no EPSG code ({source.uri})"
            )

    if sources:
        reference = sources[0]
        for source in sources[1:]:
            if (source.crs, source.transform, source.shape) != (
                reference.crs,
                reference.transform,
                reference.shape,
            ):
                errors.append(
                    f"{source.variable_id}: grid (CRS, transform or size) differs "
                    f"from {reference.variable_id}"
                )
    return errors
