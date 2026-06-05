from dotenv import load_dotenv
load_dotenv()

import sys
sys.stdout.reconfigure(line_buffering=True)

import requests
from typing import List
from smolagents import ToolCallingAgent, LiteLLMModel, tool


# ---------- Tools ----------

@tool       
def search_clinical_trials(
    query: str,
    sponsor: str = None,
    phase: str = None,
    statuses: List[str] = None,
    max_results: int = 10,
) -> list:
    """Search ClinicalTrials.gov for trials matching the given criteria.

    Returns a list of trials with summary information. Use this to find candidate
    trials, then call get_clinical_trial on specific NCT IDs for full details.

    IMPORTANT - SEARCH STRATEGY:
    A single search rarely gives comprehensive coverage of a drug class or 
    therapeutic area. Trials are registered with inconsistent terminology — 
    some use the generic class name, some use specific drug names, some use 
    development codes, some use sponsor names.

    For thorough coverage, run multiple searches and combine results:
      - The drug class or mechanism (e.g., 'KRAS G12C inhibitor')
      - Specific approved/known drug names (e.g., 'sotorasib', 'adagrasib', 
        'divarasib', 'olomorasib')
      - Development codes when known (e.g., 'AMG 510', 'MRTX849', 'JDQ443')
      - Sponsor names for major players (e.g., sponsor='Amgen', sponsor='Mirati')

    A trial may appear in only one of these searches. Deduplicate by NCT ID 
    after combining.

    Args:
        query: Search terms describing the condition, intervention, or topic
            (e.g., 'KRAS G12C inhibitor', 'sotorasib', 'AMG 510'). Required.
        sponsor: Optional lead sponsor name to filter by (e.g., 'Amgen', 'Merck').
        phase: Optional phase filter. One of 'PHASE1', 'PHASE2', 'PHASE3', 'PHASE4'.
        statuses: Optional list of recruitment statuses to include. Common values:
            'RECRUITING' (actively enrolling new patients),
            'ACTIVE_NOT_RECRUITING' (ongoing but enrollment closed - many pivotal
            late-stage trials are in this status),
            'COMPLETED', 'TERMINATED', 'NOT_YET_RECRUITING'.
            To find all 'active' or 'ongoing' trials, pass
            ['RECRUITING', 'ACTIVE_NOT_RECRUITING'].
        max_results: Maximum number of results to return (default 10, max 50).

    Returns:
        A list of dictionaries with nct_id, title, status, phase, lead_sponsor,
        conditions, and start_date for each matching trial.
    """
    url = "https://clinicaltrials.gov/api/v2/studies"

    params = {
        "query.term": query,
        "pageSize": min(max_results, 50),
        "format": "json",
    }

    if sponsor:
        params["query.lead"] = sponsor

    advanced_filters = []
    if phase:
        advanced_filters.append(f"AREA[Phase]{phase}")
    if statuses:
        status_or = " OR ".join(f"AREA[OverallStatus]{s}" for s in statuses)
        advanced_filters.append(f"({status_or})" if len(statuses) > 1 else status_or)
    if advanced_filters:
        params["filter.advanced"] = " AND ".join(advanced_filters)

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    results = []
    for study in data.get("studies", []):
        protocol = study.get("protocolSection", {})
        identification = protocol.get("identificationModule", {})
        status_mod = protocol.get("statusModule", {})
        sponsor_mod = protocol.get("sponsorCollaboratorsModule", {})
        conditions_mod = protocol.get("conditionsModule", {})
        design_mod = protocol.get("designModule", {})

        results.append({
            "nct_id": identification.get("nctId"),
            "title": identification.get("briefTitle"),
            "status": status_mod.get("overallStatus"),
            "phase": design_mod.get("phases", []),
            "lead_sponsor": sponsor_mod.get("leadSponsor", {}).get("name"),
            "conditions": conditions_mod.get("conditions", []),
            "start_date": status_mod.get("startDateStruct", {}).get("date"),
        })

    return results


@tool
def get_clinical_trial(nct_id: str) -> dict:
    """Fetch detailed information about a specific clinical trial from
    ClinicalTrials.gov.

    Use this after search_clinical_trials to get full details on trials of
    interest. Pay close attention to the primary_outcomes and brief_summary
    fields — these reveal the true study population (e.g. a trial may mention
    a drug class broadly but actually enroll a specific subset).

    DATE INTERPRETATION (IMPORTANT for CI work):
    - 'primary_completion_date' = when the primary analysis is expected. This 
      is the date that matters for competitive readout timing. Pivotal data 
      readouts typically happen near this date.
    - 'completion_date' = when the entire study (including long-term follow-up) 
      ends. This is often years after the primary readout. Don't confuse the 
      two — using 'completion_date' as the readout date overstates how far 
      out the data is.

    Args:
        nct_id: The NCT identifier of the trial (e.g., 'NCT04267848').

    Returns:
        A dictionary containing trial details including title, status, phase,
        sponsor, conditions, interventions, primary outcomes, dates, and URL.
    """
    url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()

    protocol = data.get("protocolSection", {})

    identification = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    sponsor = protocol.get("sponsorCollaboratorsModule", {})
    description = protocol.get("descriptionModule", {})
    conditions = protocol.get("conditionsModule", {})
    design = protocol.get("designModule", {})
    arms = protocol.get("armsInterventionsModule", {})
    outcomes = protocol.get("outcomesModule", {})

    return {
        "nct_id": nct_id,
        "title": identification.get("officialTitle") or identification.get("briefTitle"),
        "status": status.get("overallStatus"),
        "phase": design.get("phases", []),
        "study_type": design.get("studyType"),
        "lead_sponsor": sponsor.get("leadSponsor", {}).get("name"),
        "conditions": conditions.get("conditions", []),
        "brief_summary": description.get("briefSummary"),
        "interventions": [
            {"type": i.get("type"), "name": i.get("name")}
            for i in arms.get("interventions", [])
        ],
        "primary_outcomes": [
            {"measure": o.get("measure"), "timeframe": o.get("timeFrame")}
            for o in outcomes.get("primaryOutcomes", [])
        ],
        "start_date": status.get("startDateStruct", {}).get("date"),
        "primary_completion_date": status.get("primaryCompletionDateStruct", {}).get("date"),
        "completion_date": status.get("completionDateStruct", {}).get("date"),
        "url": f"https://clinicaltrials.gov/study/{nct_id}",
    }


# ---------- Model & Agent ----------

model = LiteLLMModel(
    model_id="gemini/gemini-2.5-flash",
    api_key=None,
    max_tokens=8000,
)

agent = ToolCallingAgent(
    tools=[search_clinical_trials, get_clinical_trial],
    model=model,
    max_steps=15,  # bumped to allow multiple searches
)


# ---------- Run ----------

if __name__ == "__main__":
    prompt = """Produce a competitive intelligence report on currently active 
Phase 3 trials of KRAS G12C inhibitors in non-small cell lung cancer (NSCLC).

DEFINITIONS AND SCOPE:
- "Active" means trials that are either RECRUITING or ACTIVE_NOT_RECRUITING. 
  Both represent ongoing trials.
- A trial qualifies as a "KRAS G12C inhibitor trial" only if its enrolled 
  population is specifically KRAS G12C-mutated patients AND the investigational 
  drug is targeting KRAS G12C (directly or as part of a combination). 

SEARCH STRATEGY (CRITICAL):
A single search query will NOT give complete coverage. Trials are registered 
with inconsistent terminology. You MUST run multiple searches and combine 
the results before writing the report. At minimum, search for:
  1. The drug class: 'KRAS G12C inhibitor NSCLC'
  2. Each known drug by name: sotorasib, adagrasib, divarasib, olomorasib, 
     daraxonrasib, opnurasib (JDQ443), D-1553
  3. Each known development code where the drug name search may miss: 
     'AMG 510', 'MRTX849'
  4. By major sponsor: Amgen, Bristol-Myers Squibb (or Mirati), Hoffmann-La 
     Roche, Eli Lilly, Novartis, Revolution Medicines

After running these searches, deduplicate by NCT ID, then fetch full details 
on each unique trial that meets the scope criteria.

WHEN INTERPRETING DATES:
Use 'primary_completion_date' (not 'completion_date') as the expected 
readout date for competitive timing analysis. The completion_date often 
extends years past the primary readout for long-term follow-up.

DELIVERABLE - your report MUST contain exactly these three sections in 
this order:

## Section 1: Summary Table
A table with columns: Sponsor | Drug | NCT ID | Status | Line of Therapy 
(1L vs 2L+) | Comparator | Primary Endpoint | Primary Completion Date 
(expected readout).

## Section 2: Competitive Analysis  
Concrete strategic analysis. Avoid generic phrases like "highly competitive 
landscape." Address: who is targeting first-line vs later-line; who is 
monotherapy vs combination; what clinically differentiates each program 
(e.g., head-to-head vs vs-chemo, biomarker stratification, novel mechanism); 
which readouts are timed to land first.

## Section 3: Limitations and Caveats
This section is REQUIRED and must contain at least three bullet points:
  - Trials you considered but excluded, with the specific reason for each.
  - Data fields where ClinicalTrials.gov did not provide enough detail to 
    answer the question definitively.
  - Trials you suspect may exist but did not surface in your searches, 
    or where you'd want to verify with another source (press releases, 
    company pipelines, conference abstracts).

FORMAT: Clean Markdown. Cite each trial's URL. Be concise — quality over 
length. If uncertain about a fact, state the uncertainty rather than guessing."""

    result = agent.run(prompt)

    output_path = "kras_g12c_landscape_v3.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(str(result))

    print(f"\nReport saved to {output_path}")
    print("\n" + "="*60)
    print(result)