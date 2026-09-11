import pytest

from cog_stac_pipeline.config import PipelineConfig

OPTIONAL_ENV = (
    "DATASET_METADATA_DIR",
    "MAX_BANDS_PER_SLICE",
    "REQUIRE_ALL_VARIABLES",
    "PREFLIGHT_ONLY",
)


def test_pipeline_config_from_env(monkeypatch):
    monkeypatch.setenv("INPUT_MANIFEST_PATH", "/manifests/input.yml")
    monkeypatch.setenv("OUTPUT_DIR", "/output/test-dataset")
    monkeypatch.setenv("DATASET_METADATA_DIR", "/datasets")
    monkeypatch.setenv("MAX_BANDS_PER_SLICE", "25")
    monkeypatch.setenv("REQUIRE_ALL_VARIABLES", "true")
    monkeypatch.setenv("PREFLIGHT_ONLY", "yes")

    config = PipelineConfig.from_env()

    assert config.input_manifest_path == "/manifests/input.yml"
    assert config.output_dir == "/output/test-dataset"
    assert config.dataset_metadata_dir == "/datasets"
    assert config.max_bands_per_slice == 25
    assert config.require_all_variables is True
    assert config.preflight_only is True
    assert config.dataset_file_path("test-dataset") == "/datasets/test-dataset.yml"


def test_pipeline_config_defaults(monkeypatch):
    for name in OPTIONAL_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("INPUT_MANIFEST_PATH", "/manifests/input.yml")
    monkeypatch.setenv("OUTPUT_DIR", "/output/test-dataset")

    config = PipelineConfig.from_env()

    assert config.dataset_metadata_dir == "datasets"
    assert config.max_bands_per_slice == 100
    assert config.require_all_variables is False
    assert config.preflight_only is False


def test_pipeline_config_requires_manifest_and_output(monkeypatch):
    monkeypatch.delenv("INPUT_MANIFEST_PATH", raising=False)
    monkeypatch.delenv("OUTPUT_DIR", raising=False)

    with pytest.raises(ValueError, match="INPUT_MANIFEST_PATH, OUTPUT_DIR"):
        PipelineConfig.from_env()
