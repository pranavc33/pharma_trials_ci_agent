"""Diff weekly monitor snapshots."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SNAPSHOT_FILENAME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


class SnapshotDiffError(ValueError):
    """Raised when snapshots cannot be loaded or compared."""


def load_snapshot(path: str | Path) -> dict[str, Any]:
    snapshot_path = Path(path)
    if not snapshot_path.exists():
        raise SnapshotDiffError(f"Snapshot file not found: {snapshot_path}")
    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("trials"), dict):
        raise SnapshotDiffError(f"Invalid snapshot structure: {snapshot_path}")
    return data


def _trial_name(nct_id: str, trial: dict[str, Any]) -> dict[str, Any]:
    return {
        "nct_id": nct_id,
        "drug": trial.get("drug"),
        "label": trial.get("label"),
    }


def _change_record(
    nct_id: str,
    old_trial: dict[str, Any],
    new_trial: dict[str, Any],
    field: str,
    old_value: Any,
    new_value: Any,
) -> dict[str, Any]:
    return {
        **_trial_name(nct_id, new_trial or old_trial),
        "field": field,
        "old_value": old_value,
        "new_value": new_value,
    }


def _publications_by_pmid(trial: dict[str, Any]) -> dict[str, dict[str, Any]]:
    publications = trial.get("publications") or []
    return {
        str(publication.get("pmid")): publication
        for publication in publications
        if publication.get("pmid")
    }


def diff_snapshot_data(old_snapshot: dict[str, Any], new_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a structured diff between two loaded snapshot dictionaries."""
    old_trials = old_snapshot.get("trials", {})
    new_trials = new_snapshot.get("trials", {})

    diff: dict[str, Any] = {
        "old_date": old_snapshot.get("snapshot_date"),
        "new_date": new_snapshot.get("snapshot_date"),
        "watchlist_name": new_snapshot.get("watchlist_name") or old_snapshot.get("watchlist_name"),
        "status_changes": [],
        "timeline_changes": [],
        "enrollment_changes": [],
        "new_publications": [],
    }

    for nct_id in sorted(set(old_trials) & set(new_trials)):
        old_trial = old_trials[nct_id]
        new_trial = new_trials[nct_id]

        old_status = old_trial.get("status")
        new_status = new_trial.get("status")
        if old_status != new_status:
            diff["status_changes"].append(
                _change_record(nct_id, old_trial, new_trial, "status", old_status, new_status)
            )

        old_primary_completion = old_trial.get("primary_completion_date")
        new_primary_completion = new_trial.get("primary_completion_date")
        if old_primary_completion != new_primary_completion:
            diff["timeline_changes"].append(
                _change_record(
                    nct_id,
                    old_trial,
                    new_trial,
                    "primary_completion_date",
                    old_primary_completion,
                    new_primary_completion,
                )
            )

        old_enrollment = old_trial.get("enrollment")
        new_enrollment = new_trial.get("enrollment")
        if old_enrollment != new_enrollment:
            diff["enrollment_changes"].append(
                _change_record(nct_id, old_trial, new_trial, "enrollment", old_enrollment, new_enrollment)
            )

        old_publications = _publications_by_pmid(old_trial)
        new_publications = _publications_by_pmid(new_trial)
        for pmid in sorted(set(new_publications) - set(old_publications)):
            diff["new_publications"].append(
                {
                    **_trial_name(nct_id, new_trial),
                    "publication": new_publications[pmid],
                }
            )

    return diff


def diff_snapshots(old_snapshot_path: str | Path, new_snapshot_path: str | Path) -> dict[str, Any]:
    """Load two snapshot files and return a structured diff."""
    old_snapshot = load_snapshot(old_snapshot_path)
    new_snapshot = load_snapshot(new_snapshot_path)
    return diff_snapshot_data(old_snapshot, new_snapshot)


def find_two_most_recent_snapshots(snapshot_dir: str | Path = "snapshots") -> tuple[Path, Path]:
    """Find the two most recent YYYY-MM-DD.json snapshots by filename."""
    directory = Path(snapshot_dir)
    if not directory.exists():
        raise SnapshotDiffError(f"Snapshot directory not found: {directory}")

    snapshot_paths = sorted(
        path for path in directory.iterdir() if path.is_file() and SNAPSHOT_FILENAME_PATTERN.match(path.name)
    )
    if len(snapshot_paths) < 2:
        raise SnapshotDiffError(f"Need at least two dated snapshots in {directory}")

    return snapshot_paths[-2], snapshot_paths[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Diff two weekly pharma CI snapshots.")
    parser.add_argument(
        "snapshots",
        nargs="*",
        help="Optional old and new snapshot paths. Defaults to the two most recent snapshots/ files.",
    )
    parser.add_argument(
        "--snapshot-dir",
        default="snapshots",
        help="Directory used when snapshot paths are omitted. Defaults to snapshots/.",
    )
    args = parser.parse_args()

    if len(args.snapshots) == 0:
        old_path, new_path = find_two_most_recent_snapshots(args.snapshot_dir)
    elif len(args.snapshots) == 2:
        old_path, new_path = Path(args.snapshots[0]), Path(args.snapshots[1])
    else:
        raise SnapshotDiffError("Provide either zero snapshot paths or exactly two snapshot paths")

    diff = diff_snapshots(old_path, new_path)
    print(json.dumps(diff, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
