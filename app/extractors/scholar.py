"""Google Scholar extractor — uses the `scholarly` library.

scholarly scrapes Google Scholar (no official API).
Runs in a thread executor since scholarly is synchronous.
3 attempts with exponential backoff; silent failure if all blocked.

Docs: https://scholarly.readthedocs.io
"""
import asyncio
import logging
import re

from app.extractors._retry import with_retries

logger = logging.getLogger(__name__)

_USER_RE = re.compile(r"[?&]user=([^&]+)")


def _extract_user_id(url: str) -> str | None:
    m = _USER_RE.search(url)
    return m.group(1) if m else None


def _format_author(author: dict) -> str:
    parts = ["SOURCE: scholar", "TYPE: google_scholar"]

    name = author.get("name", "")
    affiliation = author.get("affiliation", "")
    interests = ", ".join(author.get("interests", []))
    citedby = author.get("citedby", "")
    hindex = author.get("hindex", "")
    i10index = author.get("i10index", "")

    parts.append(f"\n[SCHOLAR:PERFIL]")
    parts.append(f"Nome: {name}")
    if affiliation:
        parts.append(f"Afiliação: {affiliation}")
    if interests:
        parts.append(f"Áreas: {interests}")

    parts.append(f"\n[SCHOLAR:INDICADORES]")
    parts.append(f"Citações totais: {citedby}")
    parts.append(f"h-index: {hindex}")
    parts.append(f"i10-index: {i10index}")

    pubs = author.get("publications", [])
    if pubs:
        parts.append(f"\n[SCHOLAR:PUBLICACOES] ({len(pubs)} registros)")
        for pub in pubs:
            bib = pub.get("bib", {})
            title = bib.get("title", "")
            year = bib.get("pub_year", "")
            venue = bib.get("venue", "")
            cited = pub.get("num_citations", "")
            parts.append(f"- {title} | {venue} | {year} | citações: {cited}")

    return "\n".join(parts)


def _sync_fetch_author(user_id: str) -> str:
    """Synchronous scholarly fetch — runs in executor."""
    from scholarly import scholarly as _scholarly

    author = _scholarly.search_author_id(user_id)
    author = _scholarly.fill(author, sections=["basics", "publications", "indices"])
    return _format_author(author)


async def fetch_scholar(scholar_url: str) -> str:
    """Fetch Google Scholar profile. 3 attempts. Silent failure if blocked."""
    user_id = _extract_user_id(scholar_url)
    if not user_id:
        logger.warning("Scholar: não foi possível extrair user ID de: %s", scholar_url)
        return f"SOURCE: scholar\nURL: {scholar_url}\n[Scholar: URL inválida ou sem user ID]"

    loop = asyncio.get_event_loop()

    async def _attempt():
        return await loop.run_in_executor(None, _sync_fetch_author, user_id)

    result = await with_retries(_attempt, source=f"scholar:{user_id}")
    return result or (
        f"SOURCE: scholar\nURL: {scholar_url}\n"
        f"[Scholar não acessível após 3 tentativas — use BibTeX colado como alternativa]"
    )
