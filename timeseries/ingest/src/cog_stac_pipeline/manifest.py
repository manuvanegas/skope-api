from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ManifestVariable:
    id: str
    uri: str


@dataclass(frozen=True)
class InputManifest:
    dataset_id: str
    trunc_to_uint16: bool
    variables: tuple[ManifestVariable, ...]


def load_input_manifest(manifest_path: str) -> InputManifest:
    path = Path(manifest_path)
    if not path.is_file():
        raise ValueError(f"Input manifest not found at: {manifest_path}")

    with path.open(encoding="utf-8") as manifest_file:
        content = yaml.safe_load(manifest_file)

    if not isinstance(content, dict):
        raise ValueError("Input manifest must be a YAML mapping.")

    dataset_id = content.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ValueError("Input manifest must set dataset_id.")

    trunc_to_uint16 = content.get("trunc_to_uint16")
    if not isinstance(trunc_to_uint16, bool):
        raise ValueError("Input manifest must set trunc_to_uint16 to true or false.")

    variables = content.get("variables")
    if not isinstance(variables, list) or not variables:
        raise ValueError("Input manifest must contain a non-empty variables list.")

    parsed: list[ManifestVariable] = []
    seen_ids: set[str] = set()
    for index, variable in enumerate(variables):
        if not isinstance(variable, dict):
            raise ValueError(f"Manifest variable at index {index} must be a mapping.")

        variable_id = variable.get("id")
        uri = variable.get("uri")
        if not isinstance(variable_id, str) or not variable_id.strip():
            raise ValueError(f"Manifest variable at index {index} has no valid id.")
        if variable_id in seen_ids:
            raise ValueError(f"Duplicate variable id in input manifest: {variable_id}")
        if not isinstance(uri, str) or not uri.strip():
            raise ValueError(f"Manifest variable '{variable_id}' has no valid uri.")
        if not uri.lower().endswith((".tif", ".tiff")):
            raise ValueError(
                f"Manifest variable '{variable_id}' must reference a TIFF: {uri}"
            )

        seen_ids.add(variable_id)
        parsed.append(ManifestVariable(id=variable_id, uri=uri))

    return InputManifest(
        dataset_id=dataset_id,
        trunc_to_uint16=trunc_to_uint16,
        variables=tuple(parsed),
    )


def validate_manifest_variables(
    manifest: InputManifest, described_ids: tuple[str, ...], require_all: bool
) -> list[str]:
    """Checks the manifest against the variables the dataset file describes.

    A manifest may process a subset of the described variables; with require_all it
    must process every one of them.
    """
    manifest_ids = [variable.id for variable in manifest.variables]
    errors = []

    undescribed = [i for i in manifest_ids if i not in described_ids]
    if undescribed:
        errors.append(f"not described in the dataset file: {', '.join(undescribed)}")

    if require_all:
        missing = [i for i in described_ids if i not in manifest_ids]
        if missing:
            errors.append(
                "described in the dataset file but missing from the input manifest "
                f"(REQUIRE_ALL_VARIABLES is set): {', '.join(missing)}"
            )
    return errors
