# Pharma Trials CI Agent

This repo contains two pharma competitive intelligence workflows:

- `Pharma_CI.ipynb`: the original one-shot landscape report agent.
- `pharma_ci/`: a deterministic weekly change monitor for a known landscape.

The notebook uses `smolagents`, Claude via LiteLLM, ClinicalTrials.gov, PubMed,
and optional Playwright screenshots to produce broad landscape reports such as
`report_kras_g12c_inhibitors.md` and `report_parp_inhibitors.md`.

The weekly monitor is for a CI analyst who already knows the competitive set and
wants a Monday-morning digest of what changed in the last week.

## Layout

```text
Pharma_CI.ipynb                 # One-shot agent workflow
report_*.md                     # Example landscape reports
screenshots/                    # Notebook-generated screenshots
watchlist.yaml                  # Analyst-maintained monitor inputs
snapshots/                      # Dated weekly JSON snapshots
pharma_ci/                      # Weekly monitor package
tests/                          # Fixtures and tests
```

## Setup

```bash
source venv/bin/activate
python -m pip install requests pyyaml pytest
```

For the notebook workflow, also install:

```bash
python -m pip install smolagents "smolagents[litellm]" playwright
python -m playwright install chromium
```

Expected local `.env` keys:

```text
ANTHROPIC_API_KEY=...
NCBI_API_KEY=...
```

`ANTHROPIC_API_KEY` is for the notebook agent. `NCBI_API_KEY` is optional for
the weekly monitor but recommended for PubMed rate limits.

## One-Shot Landscape Agent

Use `Pharma_CI.ipynb` to discover and summarize a landscape from search terms,
known drugs, development codes, and sponsors. The notebook tools can search
ClinicalTrials.gov, fetch specific CT.gov trials, search PubMed by NCT ID, and
capture CT.gov screenshots.

This path is best for broad one-time reports and narrative analysis. It is not
the preferred weekly-monitoring path because notebook state and LLM output are
less deterministic than a scripted pipeline.

## Weekly Monitor

The analyst edits `watchlist.yaml` to list monitored NCT IDs and drug names.
The seeded watchlist tracks the KRAS G12C NSCLC Phase 3 landscape from the
existing report, including G12C-selective inhibitors and select pan-RAS
competitors.

Required trial fields are `nct_id` and `drug`; `label` is optional but useful:

```yaml
trials:
  - nct_id: NCT04303780
    drug: Sotorasib
    label: CodeBreaK 200
```

Create a live snapshot:

```bash
python -m pharma_ci.snapshot
```

By default this reads `watchlist.yaml`, writes `snapshots/YYYY-MM-DD.json`, and
stores only fields we diff: status, primary completion date, enrollment, and
PubMed publications by PMID.

Override defaults:

```bash
python -m pharma_ci.snapshot --watchlist watchlist.yaml --date 2026-07-01 --output-dir snapshots
```

Compare the two most recent dated snapshots:

```bash
python -m pharma_ci.diff
```

Compare explicit files:

```bash
python -m pharma_ci.diff snapshots/2026-06-24.json snapshots/2026-07-01.json
```

The structured diff has four buckets: `new_publications`, `status_changes`,
`timeline_changes`, and `enrollment_changes`.

Render Markdown from the two most recent snapshots:

```bash
python -m pharma_ci.report
```

Render from an existing diff JSON or write to a file:

```bash
python -m pharma_ci.report diff.json
python -m pharma_ci.report --output reports/latest_delta.md
```

Reports feature new publications first, then status, timeline, and enrollment
changes. Publications are prominent because oncology readouts and subgroup
updates often surface in PubMed before they become part of a strategic narrative.

## Design Decisions

The weekly monitor is deterministic Python rather than another notebook cell so
it is easier to schedule, test, review, and diff.

The monitor is scoped to CT.gov and PubMed. CT.gov supplies operational trial
state; PubMed supplies publication state. Screenshots are intentionally excluded:
they help one-shot evidence gathering but add noise and storage churn to weekly
change monitoring.

Snapshots store only fields we plan to diff. This keeps files readable and
avoids false churn from unrelated API fields.

## Testing

```bash
python -m pytest
```

The tests do not call external APIs. Coverage includes a unit test for
`diff_snapshot_data`, a unit test for `render_delta_report`, and an integration
test for `create_snapshot -> diff_snapshots -> render_delta_report`.

The integration test monkeypatches the snapshot fetcher and uses fixtures in
`tests/fixtures/`, so it does not depend on CT.gov or PubMed availability.
