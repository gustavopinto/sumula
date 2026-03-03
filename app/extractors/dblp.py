"""DBLP extractor — uses DBLP public API and BibTeX export.

No authentication required.
APIs:
  - Person JSON: https://dblp.org/pid/{pid}.json
  - BibTeX export: https://dblp.org/pid/{pid}.bib
  - Author search: https://dblp.org/search/author/api?q={name}&format=json
"""
import logging
import re

import httpx

from app.extractors._retry import with_retries

logger = logging.getLogger(__name__)

_TIMEOUT = 20
_HEADERS = {"Accept": "application/json", "User-Agent": "SumulaBot/1.0"}

# Matches: /pid/XX/XXXX or /pers/hd/x/Name or homepages/X/Name
_PID_RE = re.compile(r"/pid/([^.?#]+)")
_PERS_RE = re.compile(r"dblp\.(?:org|uni-trier\.de)/(?:pers/hd|homepages)/[^/]+/([^/?#]+)")


def _extract_pid(url: str) -> str | None:
    """Extract the DBLP person ID from various URL formats."""
    m = _PID_RE.search(url)
    if m:
        return m.group(1).rstrip("/")
    return None


def _person_name_from_url(url: str) -> str | None:
    """Extract author name from old-style DBLP URLs."""
    m = _PERS_RE.search(url)
    if m:
        return m.group(1).replace("_", " ").replace("=", " ")
    return None


def _format_dblp_json(data: dict) -> str:
    """Convert DBLP person JSON to readable text."""
    result = data.get("result", {})
    hits = result.get("hits", {}).get("hit", [])

    parts = ["SOURCE: dblp", "TYPE: dblp_api"]
    parts.append(f"\n[DBLP:PUBLICACOES] ({len(hits)} registros)")

    for hit in hits:
        info = hit.get("info", {})
        title = info.get("title", "")
        year = info.get("year", "")
        venue = info.get("venue", "")
        pub_type = info.get("type", "")
        authors_raw = info.get("authors", {}).get("author", [])
        if isinstance(authors_raw, dict):
            authors_raw = [authors_raw]
        authors = "; ".join(
            a.get("text", a) if isinstance(a, dict) else str(a)
            for a in authors_raw
        )
        doi = info.get("doi", "")
        line = f"- {title} | {pub_type} | {venue} | {year} | {authors}"
        if doi:
            line += f" | doi:{doi}"
        parts.append(line)

    return "\n".join(parts)


async def fetch_dblp(dblp_url: str) -> str:
    """Fetch DBLP profile: tries JSON API first, then BibTeX. 3 attempts each."""
    pid = _extract_pid(dblp_url)

    # Strategy 1: if we have a PID, use the JSON + BibTeX endpoints
    if pid:
        return await _fetch_by_pid(pid)

    # Strategy 2: try to find person via author search (old URL formats)
    name = _person_name_from_url(dblp_url)
    if name:
        return await _fetch_by_search(name)

    # Strategy 3: generic trafilatura scrape
    logger.warning("DBLP: formato de URL não reconhecido, usando scraper genérico: %s", dblp_url)
    from app.extractors.web_fetch import _fetch_once
    result = await with_retries(lambda: _fetch_once(dblp_url), source="dblp_generic")
    return f"SOURCE: dblp\nURL: {dblp_url}\n\n{result or '[DBLP não acessível]'}"


async def _fetch_by_pid(pid: str) -> str:
    """Fetch publications via BibTeX export endpoint (primary for person profiles).

    Note: dblp.org/pid/{pid}.json returns 404 for person profiles — it only
    works for search results. BibTeX export is the correct endpoint for profiles.
    """
    bib_url = f"https://dblp.org/pid/{pid}.bib"

    async def _attempt_bib():
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(bib_url)
            resp.raise_for_status()
            bibtex_text = resp.text
        if not bibtex_text.strip():
            raise ValueError(f"DBLP BibTeX vazio para PID {pid}")
        from app.extractors.bibtex import parse_bibtex
        parsed = parse_bibtex(bibtex_text)
        return f"SOURCE: dblp\nTYPE: dblp_bibtex\nPID: {pid}\n\n{parsed}"

    result = await with_retries(_attempt_bib, source=f"dblp_bib:{pid}")
    return result or f"SOURCE: dblp\nPID: {pid}\n[DBLP não acessível após 3 tentativas]"


async def _fetch_by_search(name: str) -> str:
    """Search DBLP by author name and fetch their publications."""
    search_url = "https://dblp.org/search/author/api"

    async def _attempt():
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
            resp = await client.get(search_url, params={"q": name, "format": "json", "h": 5})
            resp.raise_for_status()
            hits = resp.json().get("result", {}).get("hits", {}).get("hit", [])
            if not hits:
                raise ValueError(f"DBLP: nenhum autor encontrado para '{name}'")
            # Take the first hit and fetch their publications
            first_pid = hits[0].get("info", {}).get("url", "")
            pid = _extract_pid(first_pid)
            if not pid:
                raise ValueError(f"DBLP: não foi possível extrair PID de '{first_pid}'")
            return pid

    pid = await with_retries(_attempt, source=f"dblp_search:{name}")
    if pid:
        return await _fetch_by_pid(pid)
    return f"SOURCE: dblp\nNAME: {name}\n[DBLP: autor não encontrado após 3 tentativas]"
