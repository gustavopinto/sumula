"""Google Scholar extractor.

Primary:  SerpAPI (google_scholar_author engine) — requires SERPAPI_API_KEY.
Fallback: scholarly library (scraping) — used when SerpAPI has no credits or key is absent.
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


# ── SerpAPI ────────────────────────────────────────────────────────────────────

def _format_serpapi(results: dict) -> str:
    parts = ["SOURCE: scholar", "TYPE: google_scholar"]

    author = results.get("author", {})
    name = author.get("name", "")
    affiliation = author.get("affiliations", "")
    interests = ", ".join(i.get("title", "") for i in author.get("interests", []))

    parts.append(f"\n[SCHOLAR:PERFIL]")
    parts.append(f"Nome: {name}")
    if affiliation:
        parts.append(f"Afiliação: {affiliation}")
    if interests:
        parts.append(f"Áreas: {interests}")

    table = results.get("cited_by", {}).get("table", [])
    citedby = hindex = i10 = ""
    for row in table:
        if "citations" in row:
            citedby = row["citations"].get("all", "")
        if "h_index" in row:
            hindex = row["h_index"].get("all", "")
        if "i10_index" in row:
            i10 = row["i10_index"].get("all", "")

    parts.append(f"\n[SCHOLAR:INDICADORES]")
    parts.append(f"Citações totais: {citedby}")
    parts.append(f"h-index: {hindex}")
    parts.append(f"i10-index: {i10}")

    co_authors = results.get("co_authors", [])
    if co_authors:
        parts.append(f"\n[SCHOLAR:COAUTORES]")
        for c in co_authors:
            parts.append(f"- {c.get('name', '')} | {c.get('affiliations', '')}")

    articles = results.get("articles", [])
    if articles:
        parts.append(f"\n[SCHOLAR:PUBLICACOES] ({len(articles)} registros, ordenado por citações)")
        for a in articles:
            title = a.get("title", "")
            pub = a.get("publication", "").split("-")[0].strip()
            year = a.get("year", "")
            cited = a.get("cited_by", {}).get("value", "")
            parts.append(f"- {title} | {pub} | {year} | citações: {cited}")

    return "\n".join(parts)


def _sync_fetch_serpapi(user_id: str, api_key: str) -> str:
    from serpapi import GoogleSearch

    all_articles = []
    start = 0
    base_results = None

    while True:
        params = {
            "engine": "google_scholar_author",
            "author_id": user_id,
            "api_key": api_key,
            "start": start,
            "sort": "citedby",
        }
        results = GoogleSearch(params).get_dict()

        # Detect missing credits: response has no author data
        if not results.get("author"):
            raise RuntimeError("SerpAPI sem créditos ou sem dados de autor")

        if base_results is None:
            base_results = results

        articles = results.get("articles", [])
        all_articles.extend(articles)

        if len(articles) < 100:
            break
        start += 100

    base_results["articles"] = all_articles
    return _format_serpapi(base_results)


# ── scholarly fallback ─────────────────────────────────────────────────────────

def _format_scholarly(author: dict) -> str:
    parts = ["SOURCE: scholar", "TYPE: google_scholar"]

    name = author.get("name", "")
    affiliation = author.get("affiliation", "")
    interests = ", ".join(author.get("interests", []))

    parts.append(f"\n[SCHOLAR:PERFIL]")
    parts.append(f"Nome: {name}")
    if affiliation:
        parts.append(f"Afiliação: {affiliation}")
    if interests:
        parts.append(f"Áreas: {interests}")

    parts.append(f"\n[SCHOLAR:INDICADORES]")
    parts.append(f"Citações totais: {author.get('citedby', '')}")
    parts.append(f"h-index: {author.get('hindex', '')}")
    parts.append(f"i10-index: {author.get('i10index', '')}")

    pubs = author.get("publications", [])
    if pubs:
        parts.append(f"\n[SCHOLAR:PUBLICACOES] ({len(pubs)} registros)")
        for pub in pubs:
            bib = pub.get("bib", {})
            title = bib.get("title", "")
            venue = bib.get("venue", "")
            year = bib.get("pub_year", "")
            cited = pub.get("num_citations", "")
            parts.append(f"- {title} | {venue} | {year} | citações: {cited}")

    return "\n".join(parts)


def _sync_fetch_scholarly(user_id: str) -> str:
    from scholarly import scholarly as _scholarly

    author = _scholarly.search_author_id(user_id)
    author = _scholarly.fill(author, sections=["basics", "publications", "indices"])
    return _format_scholarly(author)


# ── public API ─────────────────────────────────────────────────────────────────

async def fetch_scholar(scholar_url: str) -> str:
    """Fetch Google Scholar profile. Tries SerpAPI first, falls back to scholarly."""
    from app.config import settings

    user_id = _extract_user_id(scholar_url)
    if not user_id:
        logger.warning("Scholar: não foi possível extrair user ID de: %s", scholar_url)
        return f"SOURCE: scholar\nURL: {scholar_url}\n[Scholar: URL inválida ou sem user ID]"

    loop = asyncio.get_event_loop()

    # ── 1. SerpAPI (3 tentativas) ───────────────────────────────────────────────
    if settings.serpapi_api_key:
        async def _serpapi_attempt():
            return await loop.run_in_executor(
                None, _sync_fetch_serpapi, user_id, settings.serpapi_api_key
            )

        result = await with_retries(_serpapi_attempt, source=f"scholar_serpapi:{user_id}")
        if result:
            return result
        logger.warning("SerpAPI falhou após 3 tentativas, tentando scholarly como fallback")

    # ── 2. scholarly fallback ───────────────────────────────────────────────────
    logger.info("Scholar: usando scholarly como fallback para user_id=%s", user_id)

    async def _attempt():
        return await loop.run_in_executor(None, _sync_fetch_scholarly, user_id)

    result = await with_retries(_attempt, source=f"scholar_scholarly:{user_id}")
    if result:
        return result

    return (
        f"SOURCE: scholar\nURL: {scholar_url}\n"
        f"[Scholar não acessível via SerpAPI nem scholarly — use BibTeX colado como alternativa]"
    )
