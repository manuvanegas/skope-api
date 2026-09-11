"""Reads a dataset's description (``deploy/metadata/datasets/<dataset_id>.yml``).

The pipeline takes the described variable IDs and the declared timespan from this
file and never writes it. What the pipeline observes goes into the package's
``dataset-facts.json`` instead.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dateutil.relativedelta import relativedelta

from .datetime_utils import generate_date_range, get_iso_key

_KEY_FORMATS = {
    4: "%Y",
    7: "%Y-%m",
    10: "%Y-%m-%d",
    20: "%Y-%m-%dT%H:%M:%SZ",
}


def parse_period_key(key) -> datetime:
    """Parses 'YYYY', 'YYYY-MM', 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SSZ' as UTC."""
    key = str(key)
    key_format = _KEY_FORMATS.get(len(key))
    if key_format is None:
        raise ValueError(f"'{key}' is not an ISO-8601 timestep key.")
    return datetime.strptime(key, key_format).replace(tzinfo=timezone.utc)


def is_period_key(value) -> bool:
    try:
        parse_period_key(value)
    except ValueError:
        return False
    return True


def normalize_resolution(resolution) -> dict[str, int]:
    """Returns relativedelta keywords: 'year' and {'year': 1} both mean {'years': 1}.

    An empty value means the dataset has a single timestep.
    """
    if not resolution:
        return {}
    if isinstance(resolution, str):
        resolution = {resolution: 1}
    if not isinstance(resolution, dict):
        raise ValueError(f"Unrecognized timespan.resolution: {resolution!r}")
    return {k if k.endswith("s") else f"{k}s": v for k, v in resolution.items()}


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    variable_ids: tuple[str, ...]
    gte: str
    lte: str
    time_delta: dict[str, int]

    @property
    def start(self) -> datetime:
        return parse_period_key(self.gte)

    @property
    def step_delta(self) -> dict[str, int]:
        # A single timestep still needs a step for date arithmetic; any step works.
        return self.time_delta or {"years": 1}

    def timesteps(self) -> list[datetime]:
        if not self.time_delta:
            return [self.start]
        step = relativedelta(**self.time_delta)
        return list(generate_date_range(self.start, parse_period_key(self.lte), step))

    @property
    def expected_band_count(self) -> int:
        return len(self.timesteps())

    def key(self, moment: datetime) -> str:
        return get_iso_key(moment, self.step_delta)


def load_dataset_spec(path, dataset_id: str) -> DatasetSpec:
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Dataset file not found: {path}")

    with path.open(encoding="utf-8") as f:
        content = yaml.safe_load(f)
    if not isinstance(content, dict) or content.get("id") != dataset_id:
        raise ValueError(f"{path} must be a mapping describing dataset '{dataset_id}'.")

    variable_ids = tuple(
        str(variable["id"])
        for variable in content.get("variables") or []
        if isinstance(variable, dict) and variable.get("id")
    )
    if not variable_ids:
        raise ValueError(f"{path} describes no variables.")

    timespan = content.get("timespan") or {}
    period = timespan.get("period") or {}
    if period.get("gte") is None or period.get("lte") is None:
        raise ValueError(f"{path} must declare timespan.period.gte and lte.")

    spec = DatasetSpec(
        dataset_id=dataset_id,
        variable_ids=variable_ids,
        gte=str(period["gte"]),
        lte=str(period["lte"]),
        time_delta=normalize_resolution(timespan.get("resolution")),
    )
    _check_timespan(spec, path, timespan.get("resolution"))
    return spec


def _check_timespan(spec: DatasetSpec, path: Path, resolution) -> None:
    start = spec.start
    end = parse_period_key(spec.lte)
    if spec.key(start) != spec.gte:
        raise ValueError(
            f"{path}: timespan.period.gte '{spec.gte}' does not match the precision "
            f"of timespan.resolution {resolution!r}."
        )
    if not spec.time_delta and spec.gte != spec.lte:
        raise ValueError(
            f"{path}: an empty timespan.resolution means a single timestep, "
            f"so gte and lte must be equal (got {spec.gte} and {spec.lte})."
        )
    if end < start:
        raise ValueError(f"{path}: timespan.period.lte is before gte.")
    if spec.key(spec.timesteps()[-1]) != spec.lte:
        raise ValueError(
            f"{path}: timespan.period.lte '{spec.lte}' does not fall on a "
            f"{resolution!r} step from gte '{spec.gte}'."
        )
