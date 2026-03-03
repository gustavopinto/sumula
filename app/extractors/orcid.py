"""ORCID extractor — uses the ORCID Public REST API v3.0.

No authentication required for public profiles.
API docs: https://pub.orcid.org/v3.0/
"""
import logging
import re

import httpx

from app.extractors._retry import with_retries

logger = logging.getLogger(__name__)

_API_BASE = "https://pub.orcid.org/v3.0"
_ORCID_RE = re.compile(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])")
_TIMEOUT = 20
_HEADERS = {"Accept": "application/json"}


def _extract_orcid_id(url: str) -> str:
    m = _ORCID_RE.search(url)
    if not m:
        raise ValueError(f"ORCID ID não encontrado na URL: {url}")
    return m.group(1)


def _fmt_names(items: list) -> str:
    return "; ".join(
        i.get("value", "") for i in items if i.get("value")
    )


def _format_record(data: dict) -> str:
    parts = ["SOURCE: orcid", f"TYPE: orcid_api"]

    # Basic info
    person = data.get("person", {})
    name_data = person.get("name", {})
    given = (name_data.get("given-names") or {}).get("value", "")
    family = (name_data.get("family-name") or {}).get("value", "")
    parts.append(f"\n[ORCID:NOME]\n{given} {family}".strip())

    # Biography
    bio = (person.get("biography") or {}).get("content", "")
    if bio:
        parts.append(f"\n[ORCID:BIOGRAFIA]\n{bio}")

    # Keywords
    kws = [k.get("content", "") for k in person.get("keywords", {}).get("keyword", [])]
    if kws:
        parts.append(f"\n[ORCID:PALAVRAS_CHAVE]\n{', '.join(kws)}")

    activities = data.get("activities-summary", {})

    # Education
    edu_groups = (activities.get("educations") or {}).get("affiliation-group", [])
    edu_items = []
    for group in edu_groups:
        for summary in group.get("summaries", []):
            s = summary.get("education-summary", {})
            org = (s.get("organization") or {}).get("name", "")
            dept = (s.get("department-name") or "")
            role = (s.get("role-title") or "")
            start = _fmt_date(s.get("start-date"))
            end = _fmt_date(s.get("end-date")) or "atual"
            edu_items.append(f"- {role} | {dept} | {org} | {start}–{end}")
    if edu_items:
        parts.append(f"\n[ORCID:FORMACAO]\n" + "\n".join(edu_items))

    # Employment
    emp_groups = (activities.get("employments") or {}).get("affiliation-group", [])
    emp_items = []
    for group in emp_groups:
        for summary in group.get("summaries", []):
            s = summary.get("employment-summary", {})
            org = (s.get("organization") or {}).get("name", "")
            dept = (s.get("department-name") or "")
            role = (s.get("role-title") or "")
            start = _fmt_date(s.get("start-date"))
            end = _fmt_date(s.get("end-date")) or "atual"
            emp_items.append(f"- {role} | {dept} | {org} | {start}–{end}")
    if emp_items:
        parts.append(f"\n[ORCID:HISTORICO_PROFISSIONAL]\n" + "\n".join(emp_items))

    # Fundings
    fund_groups = (activities.get("fundings") or {}).get("group", [])
    fund_items = []
    for group in fund_groups:
        for summary in group.get("funding-summary", []):
            title = (summary.get("title") or {}).get("title", {}).get("value", "")
            ftype = summary.get("type", "")
            org = (summary.get("organization") or {}).get("name", "")
            start = _fmt_date(summary.get("start-date"))
            end = _fmt_date(summary.get("end-date")) or "atual"
            fund_items.append(f"- {title} | {ftype} | {org} | {start}–{end}")
    if fund_items:
        parts.append(f"\n[ORCID:FINANCIAMENTOS]\n" + "\n".join(fund_items))

    # Works
    work_groups = (activities.get("works") or {}).get("group", [])
    work_items = []
    for group in work_groups:
        for summary in group.get("work-summary", [])[:1]:  # first (canonical) per group
            title = (summary.get("title") or {}).get("title", {}).get("value", "")
            wtype = summary.get("type", "")
            year = _fmt_date(summary.get("publication-date"))
            journal = (summary.get("journal-title") or {}).get("value", "")
            doi = _get_doi(summary.get("external-ids", {}).get("external-id", []))
            work_items.append(
                f"- {title} | {wtype} | {journal} | {year}" + (f" | doi:{doi}" if doi else "")
            )
    if work_items:
        parts.append(f"\n[ORCID:PRODUCAO]\n" + "\n".join(work_items))

    return "\n".join(parts)


def _fmt_date(d: dict | None) -> str:
    if not d:
        return ""
    year = (d.get("year") or {}).get("value", "")
    month = (d.get("month") or {}).get("value", "")
    return f"{month}/{year}" if month else year


def _get_doi(ext_ids: list) -> str:
    for eid in ext_ids:
        if eid.get("external-id-type") == "doi":
            return eid.get("external-id-value", "")
    return ""


async def fetch_orcid(orcid_url: str) -> str:
    """Fetch full ORCID record. Returns formatted text. 3 attempts."""
    orcid_id = _extract_orcid_id(orcid_url)
    api_url = f"{_API_BASE}/{orcid_id}/record"

    async def _attempt():
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
            resp = await client.get(api_url)
            resp.raise_for_status()
            data = resp.json()
        return _format_record(data)

    result = await with_retries(_attempt, source=f"orcid:{orcid_id}")
    return result or f"SOURCE: orcid\nORCID: {orcid_id}\n[ORCID não acessível após 3 tentativas]"
