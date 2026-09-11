"""Runs the whole pipeline on small synthetic rasters."""

import json

import numpy as np
import pystac
import pytest
import rasterio
import yaml
from osgeo import gdal, osr

from cog_stac_pipeline.config import PipelineConfig
from cog_stac_pipeline.main import PreflightError, run_pipeline

GEOTRANSFORM = (
    -114.995833333457,
    0.008333333332949996,
    0.0,
    42.9958333336016,
    0.0,
    -0.008333333333010806,
)
NODATA = 4294967295


def write_source(path, bands, first_year=103, geotransform=GEOTRANSFORM, describe=True):
    """One band per timestep; band i holds 10 * i, with one nodata pixel."""
    ds = gdal.GetDriverByName("GTiff").Create(str(path), 8, 6, bands, gdal.GDT_UInt32)
    ds.SetGeoTransform(geotransform)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4269)
    ds.SetProjection(srs.ExportToWkt())
    for index in range(1, bands + 1):
        band = ds.GetRasterBand(index)
        values = np.full((6, 8), index * 10, dtype=np.uint32)
        values[0, 0] = NODATA
        band.WriteArray(values)
        band.SetNoDataValue(NODATA)
        if describe:
            band.SetDescription(f"{first_year + index - 1:04d}")
    ds = None
    return str(path)


class Workspace:
    def __init__(self, root):
        self.root = root
        self.datasets = root / "datasets"
        self.datasets.mkdir()
        self.sources = root / "sources"
        self.sources.mkdir()
        self.output = root / "out" / "testds"

    def describe(self, variables=("a", "b", "c"), resolution=None, gte="0103", lte="0352"):
        content = {
            "id": "testds",
            "title": "Test dataset",
            "timespan": {
                "resolution": {"years": 1} if resolution is None else resolution,
                "period": {"gte": gte, "lte": lte},
            },
            "variables": [{"id": variable} for variable in variables],
        }
        (self.datasets / "testds.yml").write_text(yaml.safe_dump(content))

    def manifest(self, uris, trunc=True):
        path = self.root / f"manifest-{'-'.join(uris)}.yml"
        path.write_text(
            yaml.safe_dump(
                {
                    "dataset_id": "testds",
                    "trunc_to_uint16": trunc,
                    "variables": [{"id": i, "uri": u} for i, u in uris.items()],
                }
            )
        )
        return str(path)

    def config(self, manifest_path, output=None, **overrides):
        return PipelineConfig(
            input_manifest_path=manifest_path,
            output_dir=str(output or self.output),
            dataset_metadata_dir=str(self.datasets),
            max_bands_per_slice=100,
            **overrides,
        )

    def read(self, name):
        return json.loads((self.output / name).read_text())


@pytest.fixture
def ws(tmp_path):
    workspace = Workspace(tmp_path)
    workspace.describe()
    return workspace


def test_subset_runs_accumulate_variables_in_one_package(ws):
    a = write_source(ws.sources / "a.tif", 250)
    b = write_source(ws.sources / "b.tif", 250)

    run_pipeline(ws.config(ws.manifest({"a": a})))
    run_pipeline(ws.config(ws.manifest({"b": b})))

    lookup = ws.read("lookup.json")
    assert list(lookup) == ["a", "b"]
    assert list(lookup["a"])[0] == "0103"
    assert list(lookup["a"])[-1] == "0352"
    assert lookup["a"]["0103"] == {"file": "testds/cogs/a/a_1.tif", "bidx": 1}
    assert lookup["b"]["0352"] == {"file": "testds/cogs/b/b_3.tif", "bidx": 50}

    facts = ws.read("dataset-facts.json")
    assert facts["crs"] == "EPSG:4269"
    assert facts["transform"] == [
        GEOTRANSFORM[1],
        GEOTRANSFORM[2],
        GEOTRANSFORM[0],
        GEOTRANSFORM[4],
        GEOTRANSFORM[5],
        GEOTRANSFORM[3],
        0.0,
        0.0,
        1.0,
    ]
    assert facts["timespan"] == {
        "resolution": {"years": 1},
        "period": {"gte": "0103", "lte": "0352"},
    }
    assert {k: (v["min"], v["max"]) for k, v in facts["variables"].items()} == {
        "a": (10.0, 2500.0),
        "b": (10.0, 2500.0),
    }
    assert facts["variables"]["b"]["source"] == b

    catalog = pystac.Catalog.from_file(str(ws.output / "stac" / "catalog.json"))
    assert sorted(child.id for child in catalog.get_children()) == ["a", "b"]

    with rasterio.open(ws.output / "cogs" / "a" / "a_1.tif") as cog:
        assert cog.count == 100
        assert cog.dtypes[0] == "uint16"
        assert cog.nodata == 65535
        first_band = cog.read(1)
        assert first_band[0, 0] == 65535
        assert first_band[1, 1] == 10


def test_preflight_rejects_band_count_before_writing_anything(ws):
    short = write_source(ws.sources / "a.tif", 249)

    with pytest.raises(PreflightError, match="249 bands.*needs 250"):
        run_pipeline(ws.config(ws.manifest({"a": short})))

    assert not ws.output.exists()


def test_preflight_rejects_band_descriptions_that_disagree_with_timespan(ws):
    shifted = write_source(ws.sources / "a.tif", 250, first_year=1)

    with pytest.raises(PreflightError, match="band descriptions run 0001 to 0250"):
        run_pipeline(ws.config(ws.manifest({"a": shifted})))


def test_preflight_only_checks_without_writing(ws):
    a = write_source(ws.sources / "a.tif", 250)

    run_pipeline(ws.config(ws.manifest({"a": a}), preflight_only=True))

    assert not ws.output.exists()


def test_require_all_variables_rejects_partial_manifest(ws):
    a = write_source(ws.sources / "a.tif", 250)

    with pytest.raises(PreflightError, match="missing from the input manifest.*b, c"):
        run_pipeline(ws.config(ws.manifest({"a": a}), require_all_variables=True))


def test_rejects_manifest_variable_that_is_not_described(ws):
    z = write_source(ws.sources / "z.tif", 250)

    with pytest.raises(PreflightError, match="not described in the dataset file: z"):
        run_pipeline(ws.config(ws.manifest({"z": z})))


def test_output_dir_must_end_in_dataset_id(ws):
    a = write_source(ws.sources / "a.tif", 250)

    with pytest.raises(PreflightError, match="OUTPUT_DIR must end in the dataset ID"):
        run_pipeline(
            ws.config(ws.manifest({"a": a}), output=ws.root / "out" / "elsewhere")
        )


def test_rejects_grid_that_differs_from_existing_package(ws):
    a = write_source(ws.sources / "a.tif", 250)
    moved = (GEOTRANSFORM[0] + 1.0, *GEOTRANSFORM[1:])
    b = write_source(ws.sources / "b.tif", 250, geotransform=moved)
    run_pipeline(ws.config(ws.manifest({"a": a})))

    with pytest.raises(PreflightError, match="existing package's dataset-facts.json has transform"):
        run_pipeline(ws.config(ws.manifest({"b": b})))


def test_single_timestep_dataset(ws):
    ws.describe(variables=("elev",), resolution="", gte="2009", lte="2009")
    elev = write_source(ws.sources / "elev.tif", 1, first_year=2009)

    run_pipeline(ws.config(ws.manifest({"elev": elev})))

    assert ws.read("lookup.json") == {
        "elev": {"2009": {"file": "testds/cogs/elev/elev_1.tif", "bidx": 1}}
    }
    assert ws.read("dataset-facts.json")["timespan"] == {
        "resolution": {},
        "period": {"gte": "2009", "lte": "2009"},
    }


def test_monthly_dataset_without_band_descriptions(ws):
    ws.describe(variables=("ppt",), resolution={"months": 1}, gte="1895-01", lte="1895-12")
    ppt = write_source(ws.sources / "ppt.tif", 12, describe=False)

    run_pipeline(ws.config(ws.manifest({"ppt": ppt}, trunc=False)))

    lookup = ws.read("lookup.json")["ppt"]
    assert list(lookup)[0] == "1895-01"
    assert list(lookup)[-1] == "1895-12"
    assert lookup["1895-12"] == {"file": "testds/cogs/ppt/ppt_1.tif", "bidx": 12}
    with rasterio.open(ws.output / "cogs" / "ppt" / "ppt_1.tif") as cog:
        assert cog.dtypes[0] == "uint32"
