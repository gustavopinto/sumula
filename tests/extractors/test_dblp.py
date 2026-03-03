"""Tests for the DBLP extractor.

Real profile: Armando Solar-Lezama — https://dblp.org/pid/95/6919.html
DBLP public API, no authentication required.

Notes:
  - The /pid/{pid}.json endpoint returns empty for person profiles.
    The extractor falls back to /pid/{pid}.bib (BibTeX), which works.
  - The BibTeX is then parsed via bibtexparser.
"""
import pytest

from app.extractors.dblp import (
    _extract_pid,
    _person_name_from_url,
    fetch_dblp,
)

DBLP_URL = "https://dblp.org/pid/95/6919.html"
EXPECTED_PID = "95/6919"
EXPECTED_AUTHOR = "Solar-Lezama"


# ── Unit: PID extraction ───────────────────────────────────────────────────────

def test_extract_pid_standard_url():
    assert _extract_pid("https://dblp.org/pid/95/6919.html") == "95/6919"


def test_extract_pid_without_extension():
    assert _extract_pid("https://dblp.org/pid/75/10060") == "75/10060"


def test_extract_pid_three_segments():
    assert _extract_pid("https://dblp.org/pid/12/3456-7.html") == "12/3456-7"


def test_extract_pid_returns_none_for_unrecognized():
    assert _extract_pid("https://dblp.org/search?q=solar+lezama") is None


def test_extract_pid_old_pers_url_returns_none():
    # Old /pers/hd/ URLs don't contain /pid/ → None, falls back to name search
    assert _extract_pid("https://dblp.uni-trier.de/pers/hd/s/Solar=Lezama:Armando") is None


def test_person_name_from_old_url():
    name = _person_name_from_url(
        "https://dblp.uni-trier.de/pers/hd/s/Solar=Lezama:Armando"
    )
    assert name is not None
    assert "Armando" in name


# ── Network: real BibTeX fetch ─────────────────────────────────────────────────

@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_dblp_returns_string():
    result = await fetch_dblp(DBLP_URL)
    assert isinstance(result, str)
    assert len(result) > 100


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_dblp_has_source_marker():
    result = await fetch_dblp(DBLP_URL)
    assert "SOURCE: dblp" in result


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_dblp_contains_author_name():
    result = await fetch_dblp(DBLP_URL)
    assert EXPECTED_AUTHOR in result, (
        f"Nome '{EXPECTED_AUTHOR}' não encontrado no resultado DBLP.\n"
        f"Primeiras 500 chars: {result[:500]}"
    )


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_dblp_contains_publications():
    result = await fetch_dblp(DBLP_URL)
    # Should have at least one publication entry (dash-separated format)
    lines_with_pubs = [l for l in result.splitlines() if l.startswith("- ")]
    assert len(lines_with_pubs) > 5, (
        f"Esperado >5 publicações, encontradas {len(lines_with_pubs)}"
    )


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_dblp_graceful_on_invalid_url():
    """Invalid DBLP URL must not raise — returns a fallback string."""
    result = await fetch_dblp("https://dblp.org/search?q=naoexiste12345xyzabc")
    assert isinstance(result, str)
    assert "dblp" in result.lower()
