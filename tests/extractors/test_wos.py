"""Tests for the Web of Science extractor.

WoS API requires institutional subscription (Expanded) or API key (Starter).
Without WOS_API_KEY, the extractor falls back to trafilatura scraping of
the public profile page.

Real URL tested: public WoS ResearcherID profile page.
Note: WoS may block scraping or require login — graceful failure is expected.
"""
import pytest

from app.extractors.wos import _extract_researcher_id, fetch_wos

# Public WoS author profile (ResearcherID format)
WOS_URL = "https://www.webofscience.com/wos/author/record/AAA-1234-2021"

# A well-known researcher's public WoS page
WOS_REAL_URL = "https://www.webofscience.com/wos/author/rid/AAA-1234-2021"


# ── Unit: ResearcherID extraction ─────────────────────────────────────────────

def test_extract_researcher_id_standard():
    rid = _extract_researcher_id(
        "https://www.webofscience.com/wos/author/record/AAA-1234-2021"
    )
    assert rid == "AAA-1234-2021"


def test_extract_researcher_id_single_letter_format():
    rid = _extract_researcher_id(
        "https://www.webofscience.com/wos/author/record/B-9876-2015"
    )
    assert rid == "B-9876-2015"


def test_extract_researcher_id_in_query_param():
    rid = _extract_researcher_id(
        "https://publons.com/researcher/1234567/john-doe/?utm_rid=AAA-5678-2019"
    )
    assert rid == "AAA-5678-2019"


def test_extract_researcher_id_not_found():
    assert _extract_researcher_id("https://www.webofscience.com/wos/") is None


# ── Network: scraper fallback ──────────────────────────────────────────────────

@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_wos_does_not_raise():
    """WoS extractor must never raise regardless of access restrictions."""
    result = await fetch_wos(WOS_URL)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_wos_has_source_marker():
    result = await fetch_wos(WOS_URL)
    assert "SOURCE: wos" in result


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_wos_content_or_graceful_fallback():
    """
    Either WoS is scraped (some content) or a fallback message is returned.
    WoS typically requires login, so fallback is the expected outcome.
    """
    result = await fetch_wos(WOS_URL)
    has_content = len(result.splitlines()) > 5
    has_fallback = "não acessível" in result or "WoS" in result
    assert has_content or has_fallback


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_wos_no_api_key_uses_scraper(monkeypatch):
    """Without WOS_API_KEY, the scraper path is used."""
    from app import config as cfg_module
    monkeypatch.setattr(cfg_module.settings, "wos_api_key", "")
    result = await fetch_wos(WOS_URL)
    assert isinstance(result, str)
    assert "SOURCE: wos" in result
