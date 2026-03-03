"""Tests for the Google Scholar extractor.

Uses the `scholarly` library (web scraping — no official API).
Real profile: https://scholar.google.com.br/citations?user=dOeggYMAAAAJ&hl=en

Warnings:
  - Google Scholar rate-limits aggressively. Tests may fail if IP is blocked.
  - On CI, Scholar tests are slow (~10–30s) and may be flaky.
  - Mark with `@pytest.mark.slow` and `@pytest.mark.network`.
  - If blocked, the extractor returns a graceful fallback (no exception).
"""
import pytest

from app.extractors.scholar import _extract_user_id, fetch_scholar

SCHOLAR_URL = "https://scholar.google.com.br/citations?user=dOeggYMAAAAJ&hl=en"
EXPECTED_USER_ID = "dOeggYMAAAAJ"


# ── Unit: user ID extraction ───────────────────────────────────────────────────

def test_extract_user_id_standard():
    uid = _extract_user_id(
        "https://scholar.google.com/citations?user=dOeggYMAAAAJ&hl=en"
    )
    assert uid == "dOeggYMAAAAJ"


def test_extract_user_id_br_domain():
    uid = _extract_user_id(
        "https://scholar.google.com.br/citations?user=dOeggYMAAAAJ&hl=en"
    )
    assert uid == "dOeggYMAAAAJ"


def test_extract_user_id_with_extra_params():
    uid = _extract_user_id(
        "https://scholar.google.com/citations?hl=pt-BR&user=ABCD1234&sortby=pubdate"
    )
    assert uid == "ABCD1234"


def test_extract_user_id_missing_returns_none():
    assert _extract_user_id("https://scholar.google.com/scholar?q=python") is None


# ── Network: real Scholar fetch ────────────────────────────────────────────────

@pytest.mark.network
@pytest.mark.slow
@pytest.mark.asyncio
async def test_fetch_scholar_does_not_raise():
    """Scholar must never raise — returns string (content or fallback)."""
    result = await fetch_scholar(SCHOLAR_URL)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.network
@pytest.mark.slow
@pytest.mark.asyncio
async def test_fetch_scholar_has_source_marker():
    result = await fetch_scholar(SCHOLAR_URL)
    assert "SOURCE: scholar" in result


@pytest.mark.network
@pytest.mark.slow
@pytest.mark.asyncio
async def test_fetch_scholar_content_or_graceful_fallback():
    """
    Either we get rich profile data (name, publications, indicators)
    or a clear fallback message when Google blocks the request.
    Both are valid outcomes.
    """
    result = await fetch_scholar(SCHOLAR_URL)
    has_profile = "[SCHOLAR:PERFIL]" in result or "[SCHOLAR:PUBLICACOES]" in result
    has_fallback = "não acessível" in result or "BibTeX" in result or "bloqueado" in result.lower()
    assert has_profile or has_fallback, (
        f"Resultado inesperado (nem perfil nem fallback):\n{result[:300]}"
    )


@pytest.mark.network
@pytest.mark.slow
@pytest.mark.asyncio
async def test_fetch_scholar_indicators_when_available():
    """If Scholar returns data, the indicators section must be present."""
    result = await fetch_scholar(SCHOLAR_URL)
    if "[SCHOLAR:PERFIL]" in result:
        assert "[SCHOLAR:INDICADORES]" in result
        assert "h-index" in result
        assert "Citações totais" in result


@pytest.mark.asyncio
async def test_fetch_scholar_invalid_url_graceful():
    """URL without user ID returns a clear fallback (no exception)."""
    result = await fetch_scholar("https://scholar.google.com/scholar?q=test")
    assert isinstance(result, str)
    assert "inválida" in result or "user ID" in result
