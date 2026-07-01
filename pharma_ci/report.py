"""Render weekly monitor diffs as Markdown reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pharma_ci.diff import diff_snapshots, find_two_most_recent_snapshots


def _display_trial(change: dict[str, Any]) -> str:
    nct_id = change.get("nct_id", "")
    drug = change.get("drug") or "Unknown drug"
    label = change.get("label")
    if label:
        return f"{drug} ({label}, {nct_id})"
    return f"{drug} ({nct_id})"


def _format_value(value: Any) -> str:
    if value is None or value == "":
        return "not reported"
    return str(value)


def _format_authors(authors: list[str] | None) -> str:
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    return f"{authors[0]} et al."


def _render_new_publications(changes: list[dict[str, Any]]) -> list[str]:
    lines = ["## New Publications", ""]
    if not changes:
        lines.extend(["No new PubMed publications detected.", ""])
        return lines

    for change in changes:
        publication = change.get("publication", {})
        authors = _format_authors(publication.get("authors"))
        title = publication.get("title") or "Untitled publication"
        journal = publication.get("journal") or "Journal not reported"
        year = publication.get("year") or "Year not reported"
        pmid = publication.get("pmid") or "PMID not reported"
        url = publication.get("pubmed_url") or f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        citation_prefix = f"{authors}. " if authors else ""
        lines.append(f"- **{_display_trial(change)}**")
        lines.append(f"  - {citation_prefix}{title} {journal}. {year}. [PMID: {pmid}]({url})")
    lines.append("")
    return lines


def _render_change_section(title: str, changes: list[dict[str, Any]]) -> list[str]:
    lines = [f"## {title}", ""]
    if not changes:
        lines.extend([f"No {title.lower()} detected.", ""])
        return lines

    for change in changes:
        old_value = _format_value(change.get("old_value"))
        new_value = _format_value(change.get("new_value"))
        lines.append(f"- **{_display_trial(change)}**: {old_value} -> {new_value}")
    lines.append("")
    return lines


def _has_any_changes(diff: dict[str, Any]) -> bool:
    return any(
        diff.get(bucket)
        for bucket in [
            "new_publications",
            "status_changes",
            "timeline_changes",
            "enrollment_changes",
        ]
    )


def render_delta_report(diff: dict[str, Any]) -> str:
    """Render a structured snapshot diff as Markdown."""
    watchlist_name = diff.get("watchlist_name") or "pharma_ci_watchlist"
    old_date = _format_value(diff.get("old_date"))
    new_date = _format_value(diff.get("new_date"))

    lines = [
        f"# Weekly CI Change Digest: {watchlist_name}",
        "",
        f"Snapshot comparison: {old_date} -> {new_date}",
        "",
    ]
    lines.extend(_render_new_publications(diff.get("new_publications", [])))
    lines.extend(_render_change_section("Trial Status Changes", diff.get("status_changes", [])))
    lines.extend(_render_change_section("Timeline Changes", diff.get("timeline_changes", [])))
    lines.extend(_render_change_section("Enrollment Changes", diff.get("enrollment_changes", [])))

    if not _has_any_changes(diff):
        lines.extend(["## No Changes", "", "No monitored changes detected in this snapshot comparison.", ""])

    return "\n".join(lines).rstrip() + "\n"


def load_diff(path: str | Path) -> dict[str, Any]:
    diff_path = Path(path)
    data = json.loads(diff_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Diff file must contain a JSON object: {diff_path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a weekly pharma CI delta report.")
    parser.add_argument(
        "diff_json",
        nargs="?",
        help="Optional diff JSON path. Defaults to diffing the two most recent snapshots.",
    )
    parser.add_argument(
        "--snapshot-dir",
        default="snapshots",
        help="Directory used when diff_json is omitted. Defaults to snapshots/.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional Markdown output path. Defaults to stdout.",
    )
    args = parser.parse_args()

    if args.diff_json:
        diff = load_diff(args.diff_json)
    else:
        old_path, new_path = find_two_most_recent_snapshots(args.snapshot_dir)
        diff = diff_snapshots(old_path, new_path)

    markdown = render_delta_report(diff)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        print(f"Delta report saved to {output_path}")
    else:
        print(markdown, end="")


if __name__ == "__main__":
    main()
