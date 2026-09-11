from datetime import datetime, timezone

import pytest
import yaml

from cog_stac_pipeline.dataset_metadata import (
    is_period_key,
    load_dataset_spec,
    parse_period_key,
)


def write_dataset(tmp_path, resolution, gte, lte, dataset_id="ds"):
    path = tmp_path / f"{dataset_id}.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "id": dataset_id,
                "title": "Dataset",
                "timespan": {
                    "resolution": resolution,
                    "period": {"gte": gte, "lte": lte},
                },
                "variables": [{"id": "ppt"}, {"id": "tmax"}],
            }
        )
    )
    return path


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("0103", datetime(103, 1, 1, tzinfo=timezone.utc)),
        ("1895-07", datetime(1895, 7, 1, tzinfo=timezone.utc)),
        ("2000-01-02", datetime(2000, 1, 2, tzinfo=timezone.utc)),
        ("2000-01-02T03:04:05Z", datetime(2000, 1, 2, 3, 4, 5, tzinfo=timezone.utc)),
    ],
)
def test_parse_period_key(key, expected):
    assert parse_period_key(key) == expected


@pytest.mark.parametrize("value", ["", "Band 1", "103", "1895-13"])
def test_is_period_key_rejects_non_keys(value):
    assert is_period_key(value) is False


def test_yearly_dataset_counts_timesteps(tmp_path):
    spec = load_dataset_spec(write_dataset(tmp_path, "year", "0103", "2000"), "ds")

    assert spec.variable_ids == ("ppt", "tmax")
    assert spec.time_delta == {"years": 1}
    assert spec.start == datetime(103, 1, 1, tzinfo=timezone.utc)
    assert spec.expected_band_count == 1898


def test_monthly_dataset_counts_timesteps(tmp_path):
    path = write_dataset(tmp_path, {"months": 1}, "1895-01", "2013-07")

    spec = load_dataset_spec(path, "ds")

    assert spec.expected_band_count == (2013 - 1895) * 12 + 7


def test_single_timestep_dataset(tmp_path):
    spec = load_dataset_spec(write_dataset(tmp_path, "", "2009", "2009"), "ds")

    assert spec.time_delta == {}
    assert spec.expected_band_count == 1
    assert spec.key(spec.start) == "2009"


@pytest.mark.parametrize(
    ("resolution", "gte", "lte", "message"),
    [
        ({"months": 1}, "0103", "0200", "does not match the precision"),
        ({"months": 1}, "1895-01", "2013", "does not fall on"),
        ("", "2009", "2010", "single timestep"),
        ("year", "2000", "1999", "before gte"),
    ],
)
def test_inconsistent_timespans_are_rejected(tmp_path, resolution, gte, lte, message):
    path = write_dataset(tmp_path, resolution, gte, lte)

    with pytest.raises(ValueError, match=message):
        load_dataset_spec(path, "ds")


def test_dataset_file_must_describe_the_requested_dataset(tmp_path):
    path = write_dataset(tmp_path, "year", "0103", "2000", dataset_id="other")

    with pytest.raises(ValueError, match="describing dataset 'ds'"):
        load_dataset_spec(path, "ds")
