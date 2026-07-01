"""Create weekly monitor snapshots from a watchlist."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from pharma_ci.clients import fetch_trial_snapshot_fields, load_env_file
from pharma_ci.watchlist import Watchlist, load_watchlist


def build_snapshot(watchlist: Watchlist, snapshot_date: date | None = None) -> dict[str, Any]:
    """Fetch current monitored fields for every trial in a watchlist."""
    effective_date = snapshot_date or date.today()
    snapshot: dict[str, Any] = {
        "snapshot_date": effective_date.isoformat(),
        "watchlist_name": watchlist.name,
        "watchlist_description": watchlist.description,
        "drug_names": watchlist.drug_names,
        "trials": {},
    }

    metadata_by_nct_id = watchlist.trial_metadata_by_nct_id()
    for trial in watchlist.trials:
        fetched_fields = fetch_trial_snapshot_fields(trial.nct_id)
        snapshot["trials"][trial.nct_id] = {
            **metadata_by_nct_id[trial.nct_id],
            "status": fetched_fields.get("status"),
            "primary_completion_date": fetched_fields.get("primary_completion_date"),
            "enrollment": fetched_fields.get("enrollment"),
            "publications": fetched_fields.get("publications", []),
        }

    return snapshot


def save_snapshot(snapshot: dict[str, Any], output_dir: str | Path = "snapshots") -> Path:
    """Save a snapshot to snapshots/YYYY-MM-DD.json by default."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    snapshot_date = snapshot["snapshot_date"]
    snapshot_file = output_path / f"{snapshot_date}.json"
    snapshot_file.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return snapshot_file


def create_snapshot(
    watchlist_path: str | Path = "watchlist.yaml",
    snapshot_date: date | None = None,
    output_dir: str | Path = "snapshots",
) -> Path:
    """Load a watchlist, fetch current state, and save a dated snapshot file."""
    load_env_file()
    watchlist = load_watchlist(watchlist_path)
    snapshot = build_snapshot(watchlist, snapshot_date=snapshot_date)
    return save_snapshot(snapshot, output_dir=output_dir)


def _parse_snapshot_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a weekly pharma CI snapshot.")
    parser.add_argument(
        "--watchlist",
        default="watchlist.yaml",
        help="Path to watchlist YAML. Defaults to watchlist.yaml.",
    )
    parser.add_argument(
        "--date",
        dest="snapshot_date",
        default=None,
        help="Snapshot date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--output-dir",
        default="snapshots",
        help="Directory where snapshot JSON is written. Defaults to snapshots/.",
    )
    args = parser.parse_args()

    output_path = create_snapshot(
        watchlist_path=args.watchlist,
        snapshot_date=_parse_snapshot_date(args.snapshot_date),
        output_dir=args.output_dir,
    )
    print(f"Snapshot saved to {output_path}")


if __name__ == "__main__":
    main()
