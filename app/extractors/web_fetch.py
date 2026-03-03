"""Generic web extractor — trafilatura + httpx.
Used for: site pessoal (personal websites).
For academic sources use their specific extractors.
"""
import logging

import httpx

from app.extractors._retry import with_retries

logger = logging.getLogger(__name__)

_TIMEOUT = 20
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SumulaBot/1.0; +https://github.com/sumula)"
    )
}


async def _fetch_once(url: str) -> str:
    """Single fetch attempt — raises on any error."""
    import trafilatura

    async with httpx.AsyncClient(
        timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        html = response.text

    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
    )
    if not text or not text.strip():
        raise ValueError(f"Sem conteúdo extraível em: {url}")
    return text


async def fetch_url(url: str) -> str:
    """Fetch URL with up to 3 attempts. Returns empty string on failure."""
    async def _attempt():
        return await _fetch_once(url)

    result = await with_retries(_attempt, source=f"web:{url[:60]}")
    return result or ""
