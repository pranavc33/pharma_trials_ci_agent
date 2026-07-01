from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pharma_ci.snapshot as snapshot_module
from pharma_ci.diff import diff_snapshot_data, diff_snapshots
from pharma_ci.report import render_delta_report
from pharma_ci.snapshot import create_snapshot


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_diff_snapshot_data_returns_structured_seeded_changes() -> None:
    old_snapshot = _load_fixture("snapshot_old.json")
    new_snapshot = _load_fixture("snapshot_new.json")

    diff = diff_snapshot_data(old_snapshot, new_snapshot)

    assert diff["old_date"] == "2026-06-22"
    assert diff["new_date"] == "2026-06-29"
    assert diff["watchlist_name"] == "seeded_monitor"

    assert diff["status_changes"] == [
        {
            "nct_id": "NCT00000001",
            "drug": "Sotorasib",
            "label": "Status seed",
            "field": "status",
            "old_value": "RECRUITING",
            "new_value": "ACTIVE_NOT_RECRUITING",
        }
    ]
    assert diff["timeline_changes"] == [
        {
            "nct_id": "NCT00000002",
            "drug": "Adagrasib",
            "label": "Timeline seed",
            "field": "primary_completion_date",
            "old_value": "2029-09-07",
            "new_value": "2029-12-15",
        }
    ]
    assert diff["enrollment_changes"] == [
        {
            "nct_id": "NCT00000003",
            "drug": "Divarasib",
            "label": "Enrollment seed",
            "field": "enrollment",
            "old_value": 220,
            "new_value": 275,
        }
    ]
    assert diff["new_publications"] == [
        {
            "nct_id": "NCT00000004",
            "drug": "Olomorasib",
            "label": "Publication seed",
            "publication": {
                "authors": ["Investigator One", "Investigator Two"],
                "journal": "Oncology Fixture Reports",
                "pmid": "20000002",
                "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/20000002/",
                "title": "Seeded new readout publication.",
                "year": "2026",
            },
        }
    ]


def test_render_delta_report_groups_markdown_by_change_type() -> None:
    diff = {
        "old_date": "2026-06-22",
        "new_date": "2026-06-29",
        "watchlist_name": "seeded_monitor",
        "new_publications": [
            {
                "nct_id": "NCT00000004",
                "drug": "Olomorasib",
                "label": "Publication seed",
                "publication": {
                    "authors": ["Investigator One", "Investigator Two"],
                    "journal": "Oncology Fixture Reports",
                    "pmid": "20000002",
                    "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/20000002/",
                    "title": "Seeded new readout publication.",
                    "year": "2026",
                },
            }
        ],
        "status_changes": [
            {
                "nct_id": "NCT00000001",
                "drug": "Sotorasib",
                "label": "Status seed",
                "field": "status",
                "old_value": "RECRUITING",
                "new_value": "ACTIVE_NOT_RECRUITING",
            }
        ],
        "timeline_changes": [
            {
                "nct_id": "NCT00000002",
                "drug": "Adagrasib",
                "label": "Timeline seed",
                "field": "primary_completion_date",
                "old_value": "2029-09-07",
                "new_value": "2029-12-15",
            }
        ],
        "enrollment_changes": [
            {
                "nct_id": "NCT00000003",
                "drug": "Divarasib",
                "label": "Enrollment seed",
                "field": "enrollment",
                "old_value": 220,
                "new_value": 275,
            }
        ],
    }

    markdown = render_delta_report(diff)

    assert markdown.startswith("# Weekly CI Change Digest: seeded_monitor")
    assert "Snapshot comparison: 2026-06-22 -> 2026-06-29" in markdown
    assert "## New Publications" in markdown
    assert "## Trial Status Changes" in markdown
    assert "## Timeline Changes" in markdown
    assert "## Enrollment Changes" in markdown
    assert markdown.index("## New Publications") < markdown.index("## Trial Status Changes")
    assert "Seeded new readout publication." in markdown
    assert "[PMID: 20000002](https://pubmed.ncbi.nlm.nih.gov/20000002/)" in markdown
    assert "Sotorasib (Status seed, NCT00000001)**: RECRUITING -> ACTIVE_NOT_RECRUITING" in markdown
    assert "Adagrasib (Timeline seed, NCT00000002)**: 2029-09-07 -> 2029-12-15" in markdown
    assert "Divarasib (Enrollment seed, NCT00000003)**: 220 -> 275" in markdown
    assert "## No Changes" not in markdown


def test_snapshot_diff_report_integration_with_seeded_fixtures(tmp_path, monkeypatch) -> None:
    old_snapshot = _load_fixture("snapshot_old.json")
    new_snapshot = _load_fixture("snapshot_new.json")

    watchlist_path = tmp_path / "watchlist.yaml"
    watchlist_path.write_text(
        "\n".join(
            [
                "name: seeded_monitor",
                "description: Seeded test watchlist.",
                "trials:",
                "  - nct_id: NCT00000001",
                "    drug: Sotorasib",
                "    label: Status seed",
                "  - nct_id: NCT00000002",
                "    drug: Adagrasib",
                "    label: Timeline seed",
                "  - nct_id: NCT00000003",
                "    drug: Divarasib",
                "    label: Enrollment seed",
                "  - nct_id: NCT00000004",
                "    drug: Olomorasib",
                "    label: Publication seed",
                "drug_names:",
                "  - sotorasib",
                "  - adagrasib",
                "  - divarasib",
                "  - olomorasib",
                "",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "snapshots"

    active_fixture = {"data": old_snapshot}

    def fake_fetch_trial_snapshot_fields(nct_id: str) -> dict:
        return active_fixture["data"]["trials"][nct_id]

    monkeypatch.setattr(snapshot_module, "fetch_trial_snapshot_fields", fake_fetch_trial_snapshot_fields)

    old_path = create_snapshot(
        watchlist_path=watchlist_path,
        snapshot_date=date(2026, 6, 22),
        output_dir=output_dir,
    )
    active_fixture["data"] = new_snapshot
    new_path = create_snapshot(
        watchlist_path=watchlist_path,
        snapshot_date=date(2026, 6, 29),
        output_dir=output_dir,
    )

    diff = diff_snapshots(old_path, new_path)
    markdown = render_delta_report(diff)

    assert old_path == output_dir / "2026-06-22.json"
    assert new_path == output_dir / "2026-06-29.json"
    assert diff["new_publications"][0]["publication"]["pmid"] == "20000002"
    assert diff["status_changes"][0]["new_value"] == "ACTIVE_NOT_RECRUITING"
    assert diff["timeline_changes"][0]["new_value"] == "2029-12-15"
    assert diff["enrollment_changes"][0]["new_value"] == 275
    assert "## New Publications" in markdown
    assert "Seeded new readout publication." in markdown
    assert "RECRUITING -> ACTIVE_NOT_RECRUITING" in markdown
    assert "2029-09-07 -> 2029-12-15" in markdown
    assert "220 -> 275" in markdown
