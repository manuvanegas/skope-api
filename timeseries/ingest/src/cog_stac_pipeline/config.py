import os
from dataclasses import dataclass

REQUIRED_ENV = ("INPUT_MANIFEST_PATH", "OUTPUT_DIR")


@dataclass(frozen=True)
class PipelineConfig:
    input_manifest_path: str
    output_dir: str
    dataset_metadata_dir: str = "datasets"
    max_bands_per_slice: int = 100
    require_all_variables: bool = False
    preflight_only: bool = False

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
        if missing:
            raise ValueError(
                f"Required environment variables are not set: {', '.join(missing)}"
            )
        return cls(
            input_manifest_path=os.environ["INPUT_MANIFEST_PATH"],
            output_dir=os.environ["OUTPUT_DIR"],
            dataset_metadata_dir=os.environ.get(
                "DATASET_METADATA_DIR", cls.dataset_metadata_dir
            ),
            max_bands_per_slice=int(
                os.environ.get("MAX_BANDS_PER_SLICE", cls.max_bands_per_slice)
            ),
            require_all_variables=_env_bool(
                "REQUIRE_ALL_VARIABLES", cls.require_all_variables
            ),
            preflight_only=_env_bool("PREFLIGHT_ONLY", cls.preflight_only),
        )

    def dataset_file_path(self, dataset_id: str) -> str:
        return os.path.join(self.dataset_metadata_dir, f"{dataset_id}.yml")


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}
