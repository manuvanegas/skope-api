import json

import pytest
import yaml

from app.registry_build import (
    RegistryBuildError,
    build_registry,
    main,
    merge_dataset,
    normalize_resolution,
)
from app.store.index_loaders import load_registry

TRANSFORM = [0.00833, 0.0, -115.0, 0.0, -0.00833, 43.0]


def curated_dataset(**overrides):
    dataset = {
        "id": "ds",
        "title": "Dataset",
        "timespan": {
            "resolution": {"years": 1},
            "resolutionLabel": "yearly",
            "period": {"gte": "0103", "lte": "0105", "suffix": "CE"},
        },
        "variables": [
            {"id": "ppt", "name": "Precipitation", "colormap": "viridis"},
            {"id": "tmax", "name": "Maximum temperature"},
        ],
    }
    dataset.update(overrides)
    return dataset


def observed_facts(**overrides):
    facts = {
        "dataset_id": "ds",
        "crs": "EPSG:4269",
        "transform": TRANSFORM,
        "timespan": {
            "resolution": {"years": 1},
            "period": {"gte": "0103", "lte": "0105"},
        },
        "variables": {
            "ppt": {"min": 0.0, "max": 10.0, "source": "/data/ppt.tif"},
            "tmax": {"min": -5.0, "max": 40.0, "source": "/data/tmax.tif"},
        },
    }
    facts.update(overrides)
    return facts


def write_sources(root, datasets, selection, facts=None):
    """Writes dataset files and an environment file, plus the release's facts."""
    metadata_dir = root / "metadata"
    facts_dir = root / "facts"
    (metadata_dir / "datasets").mkdir(parents=True)
    facts_dir.mkdir()
    for curated in datasets:
        dataset_id = curated["id"]
        (metadata_dir / "datasets" / f"{dataset_id}.yml").write_text(
            yaml.safe_dump(curated)
        )
    for dataset_id, observed in (facts or {}).items():
        (facts_dir / f"{dataset_id}.json").write_text(json.dumps(observed))
    (metadata_dir / "dev.yml").write_text(
        yaml.safe_dump({"release": "./cog-input", "datasets": selection})
    )
    return metadata_dir, facts_dir


# ---------------------------------------------------------------------------
# merge_dataset


def test_merge_adds_observed_facts_to_selected_variables():
    entry, warnings = merge_dataset(curated_dataset(), observed_facts(), ["ppt"])

    assert warnings == []
    assert entry["title"] == "Dataset"
    assert entry["crs"] == "EPSG:4269"
    assert entry["transform"] == TRANSFORM
    assert entry["timespan"]["resolutionLabel"] == "yearly"
    assert entry["variables"] == [
        {
            "id": "ppt",
            "name": "Precipitation",
            "colormap": "viridis",
            "min": 0.0,
            "max": 10.0,
        }
    ]


def test_merge_follows_selection_order():
    entry, _ = merge_dataset(curated_dataset(), observed_facts(), ["tmax", "ppt"])

    assert [variable["id"] for variable in entry["variables"]] == ["tmax", "ppt"]


def test_merge_allows_described_variables_without_processed_data_if_unselected():
    curated = curated_dataset(variables=[{"id": "ppt"}, {"id": "not_processed_yet"}])

    entry, _ = merge_dataset(curated, observed_facts(), ["ppt"])

    assert [variable["id"] for variable in entry["variables"]] == ["ppt"]


def test_merge_rejects_selected_variable_without_processed_data():
    curated = curated_dataset(variables=[{"id": "ppt"}, {"id": "missing"}])

    with pytest.raises(RegistryBuildError, match="'missing' is selected but has no"):
        merge_dataset(curated, observed_facts(), ["ppt", "missing"])


def test_merge_can_skip_selected_variables_without_processed_data():
    curated = curated_dataset(variables=[{"id": "ppt"}, {"id": "missing"}])

    entry, warnings = merge_dataset(
        curated, observed_facts(), ["ppt", "missing"], allow_missing_facts=True
    )

    assert [variable["id"] for variable in entry["variables"]] == ["ppt"]
    assert warnings == [
        "ds: variable 'missing' is selected but has no processed data "
        "in the release; skipped"
    ]


def test_merge_returns_no_entry_when_every_selected_variable_is_skipped():
    curated = curated_dataset(variables=[{"id": "missing"}])

    entry, warnings = merge_dataset(
        curated, observed_facts(), ["missing"], allow_missing_facts=True
    )

    assert entry is None
    assert len(warnings) == 1


def test_merge_rejects_selected_variable_that_is_not_described():
    with pytest.raises(
        RegistryBuildError, match="'tmin' is selected but not described"
    ):
        merge_dataset(
            curated_dataset(),
            observed_facts(variables={"tmin": {"min": 0, "max": 1}}),
            ["tmin"],
        )


def test_merge_rejects_observed_fields_in_dataset_file():
    curated = curated_dataset(
        crs="EPSG:4326", variables=[{"id": "ppt", "min": 0, "max": 5}]
    )

    with pytest.raises(RegistryBuildError) as error:
        merge_dataset(curated, observed_facts(), ["ppt"])

    message = str(error.value)
    assert "'crs' is observed in the data" in message
    assert "variable 'ppt': 'min' is observed in the data" in message
    assert "variable 'ppt': 'max' is observed in the data" in message


def test_merge_rejects_timespan_disagreement_naming_both_sources():
    facts = observed_facts(
        timespan={"resolution": {"years": 1}, "period": {"gte": "0001", "lte": "0105"}}
    )

    with pytest.raises(RegistryBuildError) as error:
        merge_dataset(curated_dataset(), facts, ["ppt"])

    message = str(error.value)
    assert "datasets/ds.yml, ds/dataset-facts.json in the release" in message
    assert "timespan.period.gte is '0103' in the dataset file" in message
    assert "'0001' in the processed data" in message


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("year", {"years": 1}),
        ({"year": 1}, {"years": 1}),
        ("", None),
        ("month", {"months": 1}),
    ],
)
def test_normalize_resolution_equivalent_spellings(left, right):
    assert normalize_resolution(left) == normalize_resolution(right)


def test_normalize_resolution_distinguishes_steps():
    assert normalize_resolution("year") != normalize_resolution({"months": 1})


# ---------------------------------------------------------------------------
# build_registry / main


def test_build_registry_follows_environment_selection(tmp_path):
    metadata_dir, facts_dir = write_sources(
        tmp_path,
        [curated_dataset(), curated_dataset(id="second")],
        selection=[
            {"id": "second", "variables": ["tmax"]},
            {"id": "ds", "variables": ["ppt", "tmax"]},
        ],
        facts={"ds": observed_facts(), "second": observed_facts(dataset_id="second")},
    )

    registry, warnings = build_registry(metadata_dir, facts_dir, "dev")

    assert warnings == []
    assert [entry["id"] for entry in registry] == ["second", "ds"]
    assert [v["id"] for v in registry[0]["variables"]] == ["tmax"]
    assert [v["id"] for v in registry[1]["variables"]] == ["ppt", "tmax"]


@pytest.mark.parametrize(
    ("selection", "message"),
    [
        ([{"id": "ds"}], "ds must list the variables it publishes"),
        (["ds"], "dataset entry 0 has no id"),
        (
            [{"id": "ds", "variables": ["ppt"]}, {"id": "ds", "variables": ["ppt"]}],
            "lists ds twice",
        ),
        ([{"id": "ds", "variables": ["ppt", "ppt"]}], "ds lists ppt twice"),
    ],
)
def test_build_registry_rejects_malformed_selection(tmp_path, selection, message):
    metadata_dir, facts_dir = write_sources(
        tmp_path, [curated_dataset()], selection, facts={"ds": observed_facts()}
    )

    with pytest.raises(RegistryBuildError, match=message):
        build_registry(metadata_dir, facts_dir, "dev")


def test_build_registry_reports_every_problem_at_once(tmp_path):
    metadata_dir, facts_dir = write_sources(
        tmp_path,
        [curated_dataset(), curated_dataset(id="unprocessed")],
        selection=[
            {"id": "ds", "variables": ["nope"]},
            {"id": "absent", "variables": ["ppt"]},
            {"id": "unprocessed", "variables": ["ppt"]},
        ],
        facts={"ds": observed_facts()},
    )

    with pytest.raises(RegistryBuildError) as error:
        build_registry(metadata_dir, facts_dir, "dev")

    message = str(error.value)
    assert "'nope' is selected but not described" in message
    assert "absent: missing datasets/absent.yml" in message
    assert "unprocessed: the release has no unprocessed/dataset-facts.json" in message


def test_build_registry_can_skip_datasets_without_processed_data(tmp_path):
    metadata_dir, facts_dir = write_sources(
        tmp_path,
        [curated_dataset(), curated_dataset(id="unprocessed")],
        selection=[
            {"id": "ds", "variables": ["ppt"]},
            {"id": "unprocessed", "variables": ["ppt"]},
        ],
        facts={"ds": observed_facts()},
    )

    registry, warnings = build_registry(
        metadata_dir, facts_dir, "dev", allow_missing_facts=True
    )

    assert [entry["id"] for entry in registry] == ["ds"]
    assert warnings == [
        "unprocessed: the release has no unprocessed/dataset-facts.json; skipped"
    ]


def test_build_registry_rejects_facts_for_another_dataset(tmp_path):
    metadata_dir, facts_dir = write_sources(
        tmp_path,
        [curated_dataset()],
        [{"id": "ds", "variables": ["ppt"]}],
        facts={"ds": observed_facts(dataset_id="other")},
    )

    with pytest.raises(
        RegistryBuildError, match="dataset-facts.json describes 'other'"
    ):
        build_registry(metadata_dir, facts_dir, "dev")


def test_build_registry_rejects_dataset_id_that_does_not_match_filename(tmp_path):
    metadata_dir, facts_dir = write_sources(
        tmp_path,
        [curated_dataset()],
        [{"id": "ds", "variables": ["ppt"]}],
        facts={"ds": observed_facts()},
    )
    (metadata_dir / "datasets" / "ds.yml").write_text(
        yaml.safe_dump(curated_dataset(id="other"))
    )

    with pytest.raises(RegistryBuildError, match="must be a mapping with id 'ds'"):
        build_registry(metadata_dir, facts_dir, "dev")


def run_main(metadata_dir, facts_dir, output, *extra):
    return main(
        [
            "--metadata-dir",
            str(metadata_dir),
            "--facts-dir",
            str(facts_dir),
            "--environment",
            "dev",
            "--output",
            str(output),
            *extra,
        ]
    )


def test_main_writes_a_registry_the_api_can_load(tmp_path):
    metadata_dir, facts_dir = write_sources(
        tmp_path,
        [curated_dataset()],
        [{"id": "ds", "variables": ["ppt"]}],
        facts={"ds": observed_facts()},
    )
    output = tmp_path / "metadata.yml"

    assert run_main(metadata_dir, facts_dir, output) == 0

    assert output.read_text().startswith("# Generated by app.registry_build")
    registry = load_registry(output)
    assert registry["ds"]["crs"] == "EPSG:4269"
    assert registry["ds"]["variables"] == [
        {
            "id": "ppt",
            "name": "Precipitation",
            "colormap": "viridis",
            "min": 0.0,
            "max": 10.0,
        }
    ]


def test_main_fails_without_writing_output(tmp_path, capsys):
    metadata_dir, facts_dir = write_sources(
        tmp_path, [curated_dataset()], [{"id": "ds", "variables": ["ppt"]}]
    )
    output = tmp_path / "metadata.yml"

    assert run_main(metadata_dir, facts_dir, output) == 1

    assert not output.exists()
    assert "Registry build failed for 'dev'" in capsys.readouterr().err


def test_main_reports_skipped_data_as_warnings(tmp_path, capsys):
    metadata_dir, facts_dir = write_sources(
        tmp_path, [curated_dataset()], [{"id": "ds", "variables": ["ppt"]}]
    )
    output = tmp_path / "metadata.yml"

    assert run_main(metadata_dir, facts_dir, output, "--allow-missing-facts") == 0

    assert load_registry(output) == {}
    assert (
        "warning: ds: the release has no ds/dataset-facts.json"
        in capsys.readouterr().err
    )
