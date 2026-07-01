"""Watchlist loading and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


NCT_ID_PATTERN = re.compile(r"^NCT\d{8}$")


class WatchlistError(ValueError):
    """Raised when watchlist.yaml is missing required fields or is malformed."""


@dataclass(frozen=True)
class WatchlistTrial:
    nct_id: str
    drug: str
    label: str | None = None

    @classmethod
    def from_mapping(cls, item: dict[str, Any], index: int) -> "WatchlistTrial":
        nct_id = str(item.get("nct_id", "")).strip().upper()
        drug = str(item.get("drug", "")).strip()
        label = item.get("label")

        if not nct_id:
            raise WatchlistError(f"Trial entry {index} is missing nct_id")
        if not NCT_ID_PATTERN.match(nct_id):
            raise WatchlistError(f"Trial entry {index} has invalid nct_id: {nct_id}")
        if not drug:
            raise WatchlistError(f"Trial entry {index} is missing drug")
        if label is not None:
            label = str(label).strip() or None

        return cls(nct_id=nct_id, drug=drug, label=label)

    def to_snapshot_metadata(self) -> dict[str, Any]:
        return {
            "drug": self.drug,
            "label": self.label,
        }


@dataclass(frozen=True)
class Watchlist:
    name: str
    description: str | None
    trials: list[WatchlistTrial]
    drug_names: list[str]

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "Watchlist":
        name = str(data.get("name", "")).strip()
        description = data.get("description")
        raw_trials = data.get("trials")
        raw_drug_names = data.get("drug_names", [])

        if not name:
            raise WatchlistError("Watchlist is missing name")
        if description is not None:
            description = str(description).strip() or None
        if not isinstance(raw_trials, list) or not raw_trials:
            raise WatchlistError("Watchlist must include at least one trial")
        if not isinstance(raw_drug_names, list):
            raise WatchlistError("drug_names must be a list when provided")

        trials: list[WatchlistTrial] = []
        seen_nct_ids: set[str] = set()
        for index, item in enumerate(raw_trials, start=1):
            if not isinstance(item, dict):
                raise WatchlistError(f"Trial entry {index} must be a mapping")
            trial = WatchlistTrial.from_mapping(item, index)
            if trial.nct_id in seen_nct_ids:
                raise WatchlistError(f"Duplicate nct_id in watchlist: {trial.nct_id}")
            seen_nct_ids.add(trial.nct_id)
            trials.append(trial)

        drug_names = [str(name).strip() for name in raw_drug_names if str(name).strip()]

        return cls(
            name=name,
            description=description,
            trials=trials,
            drug_names=drug_names,
        )

    def trial_metadata_by_nct_id(self) -> dict[str, dict[str, Any]]:
        return {trial.nct_id: trial.to_snapshot_metadata() for trial in self.trials}


def load_watchlist(path: str | Path = "watchlist.yaml") -> Watchlist:
    watchlist_path = Path(path)
    if not watchlist_path.exists():
        raise WatchlistError(f"Watchlist file not found: {watchlist_path}")

    data = yaml.safe_load(watchlist_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise WatchlistError(f"Watchlist file must contain a YAML mapping: {watchlist_path}")

    return Watchlist.from_mapping(data)
