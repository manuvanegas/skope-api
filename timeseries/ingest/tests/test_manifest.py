from pathlib import Path

import pytest

from cog_stac_pipeline.dataset_metadata import load_dataset_spec
from cog_stac_pipeline.manifest import (
    InputManifest,
    ManifestVariable,
    load_input_manifest,
    validate_manifest_variables,
)


def write_manifest(tmp_path, content):
    path = tmp_path / "manifest.yml"
    path.write_text(content, encoding="utf-8")
    return str(path)


def manifest_of(*variable_ids):
    return InputManifest(
        dataset_id="ds",
        trunc_to_uint16=False,
        variables=tuple(ManifestVariable(id=i, uri=f"/data/{i}.tif") for i in variable_ids),
    )


def test_load_input_manifest_maps_ids_to_arbitrary_tiff_uris(tmp_path):
    manifest_path = write_manifest(
        tmp_path,
        """
dataset_id: paleocar_v3
trunc_to_uint16: true
variables:
  - id: ppt_annual
    uri: s3://skope/paleocar_v3/ppt_annual/prediction_scaled.tif
  - id: local_variable
    uri: /data/source/cube.tiff
""",
    )

    manifest = load_input_manifest(manifest_path)

    assert manifest.dataset_id == "paleocar_v3"
    assert manifest.trunc_to_uint16 is True
    assert [(variable.id, variable.uri) for variable in manifest.variables] == [
        (
            "ppt_annual",
            "s3://skope/paleocar_v3/ppt_annual/prediction_scaled.tif",
        ),
        ("local_variable", "/data/source/cube.tiff"),
    ]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("trunc_to_uint16: true\nvariables: []\n", "must set dataset_id"),
        (
            "dataset_id: paleocar_v3\ntrunc_to_uint16: true\nvariables: []\n",
            "non-empty",
        ),
        (
            """
dataset_id: paleocar_v3
variables:
  - id: ppt
    uri: /data/ppt.tif
""",
            "trunc_to_uint16",
        ),
        (
            """
dataset_id: paleocar_v3
trunc_to_uint16: false
variables:
  - id: ppt
    uri: /data/ppt.tif
  - id: ppt
    uri: /data/other.tif
""",
            "Duplicate variable id",
        ),
        (
            """
dataset_id: paleocar_v3
trunc_to_uint16: false
variables:
  - id: ppt
    uri: /data/ppt.nc
""",
            "must reference a TIFF",
        ),
    ],
)
def test_load_input_manifest_rejects_invalid_contract(tmp_path, content, message):
    manifest_path = write_manifest(tmp_path, content)

    with pytest.raises(ValueError, match=message):
        load_input_manifest(manifest_path)


def test_subset_of_described_variables_is_accepted():
    errors = validate_manifest_variables(
        manifest_of("ppt"), ("ppt", "gdd"), require_all=False
    )

    assert errors == []


def test_undescribed_manifest_variable_is_rejected():
    errors = validate_manifest_variables(
        manifest_of("ppt", "extra"), ("ppt",), require_all=False
    )

    assert errors == ["not described in the dataset file: extra"]


def test_require_all_reports_described_variables_missing_from_manifest():
    errors = validate_manifest_variables(
        manifest_of("ppt"), ("ppt", "gdd", "tmax"), require_all=True
    )

    assert len(errors) == 1
    assert "missing from the input manifest" in errors[0]
    assert errors[0].endswith("gdd, tmax")


@pytest.mark.parametrize(
    "manifest_path", sorted(str(path) for path in Path("manifests").rglob("*.yml"))
)
def test_checked_in_manifests_cover_their_dataset_files(manifest_path):
    manifest = load_input_manifest(manifest_path)
    spec = load_dataset_spec(
        f"datasets/{manifest.dataset_id}.yml", manifest.dataset_id
    )

    assert validate_manifest_variables(manifest, spec.variable_ids, require_all=True) == []
