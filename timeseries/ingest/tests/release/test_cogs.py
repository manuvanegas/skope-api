"""Writing COGs from the build plan (Section 12; COG-006, COG-010, COG-016)."""

import numpy as np
import pytest
from osgeo import gdal

from skope_release.cog_writer import cog_creation_options, conversion_parallelism, write_cogs
from skope_release.findings import Report
from skope_release.plan import Producer, StateError
from skope_release.preflight import DatasetFiles, preflight_dataset


def plan_for(directory):
    report = Report()
    plan = preflight_dataset(DatasetFiles(directory), release_id=None, mirror=None, producer=Producer("p", "0", "abc"), report=report)
    assert plan is not None, report.to_text()
    return plan


def test_writes_one_cog_per_variable_and_chunk(temporal_dataset, tmp_path):
    staging = tmp_path / "staging"
    written = write_cogs(plan_for(temporal_dataset()), staging, tmp_path / "scratch")
    assert sorted(p.relative_to(staging).as_posix() for p in written) == [
        "cogs/alpha/synth--0100--0101.tif",
        "cogs/alpha/synth--0102--0103.tif",
        "cogs/alpha/synth--0104--0104.tif",
        "cogs/beta/synth--0100--0101.tif",
        "cogs/beta/synth--0102--0103.tif",
        "cogs/beta/synth--0104--0104.tif",
    ]
    assert not (tmp_path / "scratch").exists()  # scratch is removed


def test_cogs_preserve_the_source(temporal_dataset, tmp_path):
    staging = tmp_path / "staging"
    write_cogs(plan_for(temporal_dataset()), staging, tmp_path / "scratch")
    cog = gdal.Open(str(staging / "cogs/beta/synth--0102--0103.tif"))
    source = gdal.Open(str(tmp_path / "sources" / "beta.tif"))
    band = cog.GetRasterBand(2)
    assert band.DataType == gdal.GDT_UInt32 and band.GetNoDataValue() == 4294967295
    assert band.GetDescription() == "0103" and band.GetUnitType() == "mm"
    assert np.array_equal(band.ReadAsArray(), source.GetRasterBand(4).ReadAsArray())
    assert cog.GetGeoTransform() == source.GetGeoTransform()
    structure = cog.GetMetadata("IMAGE_STRUCTURE")
    assert structure["INTERLEAVE"] == "BAND" and structure["COMPRESSION"] == "ZSTD"
    assert "STATISTICS_MEAN" in band.GetMetadata()
    assert not list(staging.rglob("*.aux.xml"))


def test_static_variable(static_dataset, tmp_path):
    staging = tmp_path / "staging"
    written = write_cogs(plan_for(static_dataset()), staging, tmp_path / "scratch")
    assert [p.relative_to(staging).as_posix() for p in written] == ["cogs/elevation.tif"]
    assert gdal.Open(str(written[0])).GetRasterBand(1).GetDescription() == "elevation"


def test_creation_options_come_from_the_declaration(temporal_dataset):
    plan = plan_for(temporal_dataset())
    options = cog_creation_options(plan, plan.variables[0])
    assert {"BLOCKSIZE=256", "COMPRESS=ZSTD", "LEVEL=9", "INTERLEAVE=BAND", "STATISTICS=YES", "SPARSE_OK=FALSE"} <= set(options)
    assert "OVERVIEW_RESAMPLING=AVERAGE" in options and "PREDICTOR=2" in options


@pytest.mark.parametrize(
    ("cpus", "override", "expected"),
    [
        (8, None, (1, 8)),  # one at a time, with every core
        (32, "", (1, 32)),
        (32, "4", (4, 8)),  # SKOPE_RELEASE_WORKERS shares the cores
        (8, "3", (3, 2)),
        (2, "4", (4, 1)),  # at least one thread each
    ],
)
def test_conversion_parallelism(cpus, override, expected):
    assert conversion_parallelism(cpus, override) == expected


def test_the_writer_takes_only_a_plan(tmp_path):
    with pytest.raises(StateError):
        write_cogs({"not": "a plan"}, tmp_path / "s", tmp_path / "x")
