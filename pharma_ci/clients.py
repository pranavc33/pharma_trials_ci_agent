"""API clients for the weekly pharma CI monitor."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import requests


CTGOV_BASE_URL = "https://clinicaltrials.gov/api/v2"
NCBI_EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class ClientError(RuntimeError):
    """Raised when an upstream API response cannot be retrieved or parsed."""


def load_env_file(path: str | Path = ".env") -> None:
    """Load simple KEY=VALUE entries from a local .env file if unset."""
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as exc:
        response = exc.response
        status = response.status_code if response is not None else "unknown status"
        raise ClientError(f"Request failed for {url}: HTTP {status}") from exc
    except requests.RequestException as exc:
        raise ClientError(f"Request failed for {url}: {exc.__class__.__name__}") from exc
    except ValueError as exc:
        raise ClientError(f"Response from {url} was not valid JSON") from exc


def fetch_trial_monitor_fields(nct_id: str) -> dict[str, Any]:
    """Fetch the ClinicalTrials.gov fields used by the weekly diff.

    The returned dictionary is deliberately narrow. It captures only fields the
    monitor compares: status, primary completion date, and enrollment.
    """
    nct_id = nct_id.strip().upper()
    data = _get_json(f"{CTGOV_BASE_URL}/studies/{nct_id}")
    protocol = data.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    design = protocol.get("designModule", {})
    enrollment = design.get("enrollmentInfo", {})

    returned_nct_id = identification.get("nctId") or nct_id
    return {
        "nct_id": returned_nct_id,
        "status": status.get("overallStatus"),
        "primary_completion_date": status.get("primaryCompletionDateStruct", {}).get("date"),
        "enrollment": enrollment.get("count"),
    }


def search_pubmed_for_trial(nct_id: str, max_results: int = 10, delay_seconds: float = 0.34) -> list[dict[str, Any]]:
    """Search PubMed for publications associated with an NCT ID.

    Returns summary metadata only. The PMID is treated as the stable identifier
    for publication diffs.
    """
    nct_id = nct_id.strip().upper()
    api_key = os.environ.get("NCBI_API_KEY")

    search_params: dict[str, Any] = {
        "db": "pubmed",
        "term": nct_id,
        "retmax": max_results,
        "retmode": "json",
        "sort": "pub date",
    }
    if api_key:
        search_params["api_key"] = api_key

    search_data = _get_json(f"{NCBI_EUTILS_BASE_URL}/esearch.fcgi", params=search_params)
    pmids = search_data.get("esearchresult", {}).get("idlist", [])
    if not pmids:
        return []

    time.sleep(delay_seconds)

    summary_params: dict[str, Any] = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
    }
    if api_key:
        summary_params["api_key"] = api_key

    summary_data = _get_json(f"{NCBI_EUTILS_BASE_URL}/esummary.fcgi", params=summary_params)
    records = summary_data.get("result", {})

    publications: list[dict[str, Any]] = []
    for pmid in pmids:
        record = records.get(pmid, {})
        if not record:
            continue
        authors = [author.get("name", "") for author in record.get("authors", [])[:3]]
        pub_date = record.get("pubdate", "")
        publications.append(
            {
                "pmid": pmid,
                "title": record.get("title", ""),
                "authors": authors,
                "journal": record.get("fulljournalname") or record.get("source", ""),
                "year": pub_date.split()[0] if pub_date else "",
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            }
        )

    return publications


def fetch_trial_snapshot_fields(nct_id: str, max_pubmed_results: int = 10) -> dict[str, Any]:
    """Fetch CT.gov monitor fields plus current PubMed publications for one trial."""
    trial_fields = fetch_trial_monitor_fields(nct_id)
    trial_fields["publications"] = search_pubmed_for_trial(nct_id, max_results=max_pubmed_results)
    return trial_fields
