"""Inspecting written COGs (AT-010, AT-011; COG-001 to COG-009, OBS-007)."""

import numpy as np
import pytest
from osgeo import gdal

from skope_release.cog_writer import write_cogs
from skope_release.findings import Report
from skope_release.inspect_bytes import inspect_asset, observe
from skope_release.plan import Producer
from skope_release.preflight import DatasetFiles, preflight_dataset


@pytest.fixture
def staged(temporal_dataset, tmp_path):
    report = Report()
    plan = preflight_dataset(DatasetFiles(temporal_dataset()), release_id="synth-r-2026.10.07", mirror=None, producer=Producer("p", "0", "abc"), report=report)
    staging = tmp_path / "staging"
    write_cogs(plan, staging, tmp_path / "scratch")
    return plan, staging


def test_observation_of_valid_cogs(staged):
    plan, staging = staged
    report = Report()
    obs = observe(plan, staging, report)
    assert obs is not None, report.to_text()
    assert [a.path for a in obs.assets][:3] == [
        "cogs/alpha/synth--0100--0101.tif", "cogs/alpha/synth--0102--0103.tif", "cogs/alpha/synth--0104--0104.tif",
    ]
    asset = obs.asset("alpha", 1)
    assert [b.name for b in asset.bands] == ["0102", "0103"]
    assert asset.checksum.startswith("1220") and asset.crs_code == "EPSG:4269"
    assert obs.bbox_wgs84 == (-115.0, 42.7, -114.6, 43.0)


def test_statistics_match_the_pixels(staged, tmp_path):
    """AT-011: embedded statistics equal statistics recomputed from the source."""
    plan, staging = staged
    obs = observe(plan, staging, Report())
    source = gdal.Open(str(tmp_path / "sources" / "alpha.tif"))
    for i, band in enumerate(obs.asset("alpha", 0).bands, start=1):
        values = source.GetRasterBand(i).ReadAsArray().astype(np.float64)
        values = values[values != 4294967295]
        assert (band.minimum, band.maximum) == (values.min(), values.max())
        assert band.mean == pytest.approx(values.mean(), rel=1e-10)
        assert band.stddev == pytest.approx(values.std(), rel=1e-10)
        assert band.valid_percent == pytest.approx(100 * values.size / (30 * 40), abs=0.005)


def reinspect(plan, staging, rel):
    report = Report()
    inspect_asset(staging / rel, rel, plan=plan, variable=plan.variables[0], chunk=0,
                  expected_names=["0100", "0101"], report=report)
    return {f.requirement for f in report.errors}


def test_missing_statistics_are_detected(staged):
    plan, staging = staged
    rel = "cogs/alpha/synth--0100--0101.tif"
    path = staging / rel
    gdal.Translate(str(path) + ".tmp.tif", str(path), format="COG", creationOptions=["STATISTICS=NO", "COMPRESS=ZSTD", "BLOCKSIZE=256", "INTERLEAVE=BAND"])
    copy = gdal.Open(str(path) + ".tmp.tif")
    has_stats = "STATISTICS_MEAN" in copy.GetRasterBand(1).GetMetadata()
    copy = None
    if has_stats:
        pytest.skip("GDAL copied the source statistics")
    (staging / (rel + ".tmp.tif")).replace(path)
    assert "COG-004" in reinspect(plan, staging, rel)


def test_wrong_band_description_is_detected(staged):
    plan, staging = staged
    rel = "cogs/alpha/synth--0100--0101.tif"
    report = Report()
    inspect_asset(staging / rel, rel, plan=plan, variable=plan.variables[0], chunk=0,
                  expected_names=["0100", "0102"], report=report)
    assert "COG-006" in {f.requirement for f in report.errors}


def test_sidecars_are_rejected(staged):
    plan, staging = staged
    rel = "cogs/alpha/synth--0100--0101.tif"
    (staging / (rel + ".aux.xml")).write_text("<PAMDataset/>")
    assert "COG-005" in reinspect(plan, staging, rel)


def test_non_cog_is_rejected(staged):
    plan, staging = staged
    rel = "cogs/alpha/synth--0100--0101.tif"
    path = staging / rel
    gdal.Translate(str(path) + ".gtiff", str(path), format="GTiff", creationOptions=["TILED=NO", "COMPRESS=NONE"])
    (staging / (rel + ".gtiff")).replace(path)
    assert {"COG-001", "COG-003"} & reinspect(plan, staging, rel)
