"""Web of Science extractor.

Web of Science API requires institutional subscription (Expanded API).
WoS Starter API (free tier) requires API key from developer.clarivate.com.

This extractor:
  1. If WOS_API_KEY env var is set → uses WoS Starter REST API
  2. Otherwise → scrapes the public ResearcherID/WoS profile page via trafilatura

3 attempts with exponential backoff.
"""
import logging
import re

import httpx

from app.extractors._retry import with_retries

logger = logging.getLogger(__name__)

_TIMEOUT = 20
_RESEARCHER_ID_RE = re.compile(r"AAA-\d{4}-\d{4}|[A-Z]-\d{4}-\d{4}")


def _extract_researcher_id(url: str) -> str | None:
    m = _RESEARCHER_ID_RE.search(url)
    return m.group(0) if m else None


def _format_wos_api(data: dict) -> str:
    """Format WoS Starter API response."""
    hits = data.get("hits", [])
    parts = ["SOURCE: wos", "TYPE: wos_api", f"\n[WOS:PUBLICACOES] ({len(hits)} registros)"]
    for doc in hits:
        title = (doc.get("title") or {}).get("value", "")
        source = (doc.get("source") or {}).get("sourceTitle", "")
        pub_year = doc.get("publishYear", "")
        doc_type = doc.get("docType", "")
        times_cited = doc.get("timesCited", "")
        authors_raw = (doc.get("names") or {}).get("authors", [])
        authors = "; ".join(a.get("displayName", "") for a in authors_raw[:5])
        doi = ""
        for uid in doc.get("uids", []):
            if uid.startswith("DOI:"):
                doi = uid[4:]
        line = f"- {title} | {doc_type} | {source} | {pub_year} | citações: {times_cited} | {authors}"
        if doi:
            line += f" | doi:{doi}"
        parts.append(line)
    return "\n".join(parts)


async def _fetch_via_api(wos_url: str) -> str:
    """Use WoS Starter REST API if WOS_API_KEY is configured."""
    from app.config import settings

    api_key = getattr(settings, "wos_api_key", "")
    if not api_key:
        raise ValueError("WOS_API_KEY não configurada")

    # Try to extract a ResearcherID or query by URL
    rid = _extract_researcher_id(wos_url)
    if not rid:
        raise ValueError(f"ResearcherID não encontrado em: {wos_url}")

    api_url = "https://api.clarivate.com/apis/wos-starter/v1/documents"
    headers = {"X-ApiKey": api_key}
    params = {"q": f"AI={rid}", "limit": 50, "page": 1}

    async def _attempt():
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=headers, follow_redirects=True) as client:
            resp = await client.get(api_url, params=params)
            resp.raise_for_status()
            return _format_wos_api(resp.json())

    result = await with_retries(_attempt, source=f"wos_api:{rid}")
    if not result:
        raise RuntimeError("WoS API falhou após 3 tentativas")
    return result


async def _fetch_via_scraper(wos_url: str) -> str:
    """Scrape WoS public profile page with trafilatura."""
    from app.extractors.web_fetch import _fetch_once

    async def _attempt():
        text = await _fetch_once(wos_url)
        if not text.strip():
            raise ValueError("Página WoS vazia ou bloqueada")
        return f"SOURCE: wos\nTYPE: wos_scraper\nURL: {wos_url}\n\n{text}"

    result = await with_retries(_attempt, source="wos_scraper")
    return result or f"SOURCE: wos\nURL: {wos_url}\n[WoS não acessível após 3 tentativas]"


async def fetch_wos(wos_url: str) -> str:
    """Fetch WoS profile. Tries API key first, falls back to scraper."""
    from app.config import settings

    api_key = getattr(settings, "wos_api_key", "")
    if api_key:
        try:
            return await _fetch_via_api(wos_url)
        except Exception as exc:
            logger.warning("WoS API falhou (%s), usando scraper", exc)

    return await _fetch_via_scraper(wos_url)
