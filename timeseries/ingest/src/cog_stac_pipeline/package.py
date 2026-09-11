"""Reads and writes a dataset package's lookup.json and dataset-facts.json.

A run replaces only the variables it processes, so a package can be built up by
several runs over subsets of a dataset's variables.
"""

import json

from . import fs_utils
from .dataset_metadata import DatasetSpec
from .preflight import SourceInfo

PROVENANCE = (
    "Written by cog-stac-pipeline. The API image build reads this file from the "
    "release named by `release:` in deploy/metadata/<environment>.yml."
)


def read_json(path: str) -> dict | None:
    if not fs_utils.path_exists(path):
        return None
    return json.loads(fs_utils.read_text(path))


def merge_variables(existing: dict | None, updates: dict) -> dict:
    """Keeps variables from earlier runs and replaces the ones processed now."""
    merged = dict(existing or {})
    merged.update(updates)
    return merged


def _timespan(spec: DatasetSpec) -> dict:
    return {
        "resolution": dict(spec.time_delta),
        "period": {"gte": spec.gte, "lte": spec.lte},
    }


def facts_conflicts(previous: dict, spec: DatasetSpec, source: SourceInfo) -> list[str]:
    """Lists differences between an existing package and what this run would write."""
    current = {
        "crs": source.crs,
        "transform": list(source.transform),
        "timespan": _timespan(spec),
    }
    return [
        f"the existing package's dataset-facts.json has {key} {previous.get(key)!r}, but "
        f"this run would write {value!r}; use an empty OUTPUT_DIR or reprocess "
        "every variable"
        for key, value in current.items()
        if previous.get(key) != value
    ]


def build_facts(
    spec: DatasetSpec, source: SourceInfo, previous: dict | None, variables: dict
) -> dict:
    return {
        "provenance": PROVENANCE,
        "dataset_id": spec.dataset_id,
        "crs": source.crs,
        "transform": list(source.transform),
        "timespan": _timespan(spec),
        "variables": merge_variables((previous or {}).get("variables"), variables),
    }
