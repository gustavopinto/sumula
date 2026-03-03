"""Tests for the ORCID extractor.

Uses the ORCID Public REST API v3.0 — no authentication required.
Test profile: Josiah Carberry (0000-0002-1825-0097), maintained by ORCID
as a canonical public test account with rich data.
"""
import pytest

from app.extractors.orcid import (
    _extract_orcid_id,
    _fmt_date,
    _get_doi,
    fetch_orcid,
)

ORCID_URL = "https://orcid.org/0000-0002-1825-0097"
ORCID_ID = "0000-0002-1825-0097"


# ── Unit: ID extraction ────────────────────────────────────────────────────────

def test_extract_orcid_id_standard_url():
    assert _extract_orcid_id("https://orcid.org/0000-0002-1825-0097") == "0000-0002-1825-0097"


def test_extract_orcid_id_with_trailing_path():
    assert _extract_orcid_id("https://orcid.org/0000-0002-1825-0097/works") == "0000-0002-1825-0097"


def test_extract_orcid_id_http():
    assert _extract_orcid_id("http://orcid.org/0000-0001-9876-5432") == "0000-0001-9876-5432"


def test_extract_orcid_id_invalid_raises():
    with pytest.raises(ValueError, match="ORCID ID não encontrado"):
        _extract_orcid_id("https://example.com/profile/john")


# ── Unit: date formatting ──────────────────────────────────────────────────────

def test_fmt_date_with_year_and_month():
    d = {"year": {"value": "2023"}, "month": {"value": "06"}}
    assert _fmt_date(d) == "06/2023"


def test_fmt_date_year_only():
    d = {"year": {"value": "2020"}, "month": None}
    assert _fmt_date(d) == "2020"


def test_fmt_date_none():
    assert _fmt_date(None) == ""


# ── Unit: DOI extraction ───────────────────────────────────────────────────────

def test_get_doi_finds_doi():
    ext_ids = [
        {"external-id-type": "wosuid", "external-id-value": "WOS:xxx"},
        {"external-id-type": "doi", "external-id-value": "10.1234/test"},
    ]
    assert _get_doi(ext_ids) == "10.1234/test"


def test_get_doi_empty_list():
    assert _get_doi([]) == ""


def test_get_doi_no_doi_type():
    ext_ids = [{"external-id-type": "pmid", "external-id-value": "12345"}]
    assert _get_doi(ext_ids) == ""


# ── Network: real API call ─────────────────────────────────────────────────────

@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_orcid_returns_string():
    result = await fetch_orcid(ORCID_URL)
    assert isinstance(result, str)
    assert len(result) > 100


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_orcid_has_source_marker():
    result = await fetch_orcid(ORCID_URL)
    assert "SOURCE: orcid" in result


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_orcid_has_name_section():
    result = await fetch_orcid(ORCID_URL)
    # Josiah Carberry's name should appear
    assert "[ORCID:NOME]" in result
    assert "Carberry" in result or "Josiah" in result


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_orcid_has_works_section():
    result = await fetch_orcid(ORCID_URL)
    assert "[ORCID:PRODUCAO]" in result


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_orcid_graceful_on_nonexistent():
    """Non-existent ORCID must not raise — returns fallback string."""
    result = await fetch_orcid("https://orcid.org/0000-0000-0000-0000")
    assert isinstance(result, str)
    assert "orcid" in result.lower()
