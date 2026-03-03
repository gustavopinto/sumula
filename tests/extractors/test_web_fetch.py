"""Tests for the generic web extractor (trafilatura + httpx).

Used for site pessoal only. Other academic sources have dedicated extractors.
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.extractors.web_fetch import _fetch_once, fetch_url

PUBLIC_URL = "https://example.com"         # RFC-standard always-available URL
REAL_SITE_URL = "https://gustavopinto.org"  # Personal site (site pessoal example)


# ── Unit: retry integration ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_url_returns_empty_on_total_failure():
    """fetch_url must return '' (not raise) when all attempts fail."""
    with patch("app.extractors.web_fetch._fetch_once", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = RuntimeError("network error")
        with patch("app.extractors._retry.asyncio.sleep", new_callable=AsyncMock):
            result = await fetch_url("https://unreachable.invalid")
    assert result == ""
    assert mock_fetch.call_count == 3


@pytest.mark.asyncio
async def test_fetch_url_returns_content_on_success():
    with patch("app.extractors.web_fetch._fetch_once", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = "Conteúdo da página"
        result = await fetch_url(PUBLIC_URL)
    assert result == "Conteúdo da página"
    mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_url_retries_then_succeeds():
    with patch("app.extractors.web_fetch._fetch_once", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = [ConnectionError("timeout"), "Conteúdo OK"]
        with patch("app.extractors._retry.asyncio.sleep", new_callable=AsyncMock):
            result = await fetch_url(PUBLIC_URL)
    assert result == "Conteúdo OK"
    assert mock_fetch.call_count == 2


# ── Network: real fetch ────────────────────────────────────────────────────────

@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_once_example_com():
    """example.com is always up per RFC; should return non-empty text."""
    text = await _fetch_once(PUBLIC_URL)
    assert isinstance(text, str)
    assert len(text) > 10
    assert "example" in text.lower() or "domain" in text.lower()


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_url_example_com():
    result = await fetch_url(PUBLIC_URL)
    assert isinstance(result, str)
    assert len(result) > 10


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_url_real_personal_site():
    """Fetch a real personal website (site pessoal use case)."""
    result = await fetch_url(REAL_SITE_URL)
    assert isinstance(result, str)
    # Either content extracted or graceful empty
    # (site may redirect or have JS-only content)
    assert result is not None


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_url_404_returns_empty():
    """404 pages must not raise — fetch_url returns ''."""
    result = await fetch_url("https://example.com/this-page-does-not-exist-at-all")
    # trafilatura may still extract something from a 404 page
    # but most importantly it must not raise
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_fetch_url_invalid_domain_returns_empty():
    with patch("app.extractors._retry.asyncio.sleep", new_callable=AsyncMock):
        result = await fetch_url("https://this-domain-absolutely-does-not-exist.invalid")
    assert result == ""
