"""Tests for the Lattes extractor.

Lattes URL (https://lattes.cnpq.br/...) has two access barriers:
  1. Legacy SSL/TLS configuration (SSLv3 alert) on CNPq servers.
  2. reCAPTCHA on the profile page.

Strategy:
  - PDF extraction: tested with a synthetic in-memory PDF (no network).
  - URL extraction: tested for graceful failure (no exception raised).
  - Playwright path: documented but not run in CI (requires browser install).
"""
import pytest

from app.extractors.lattes import (
    _HEADER_RE,
    _is_lattes_pdf,
    extract_lattes_pdf,
    fetch_lattes_url,
    lattes_pdf_to_text,
)

LATTES_URL = "https://lattes.cnpq.br/1631238943341152"

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_lattes_pdf(tmp_path, content: str) -> str:
    """Create a minimal PDF with the given text content via PyMuPDF."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), content)
    path = tmp_path / "lattes_test.pdf"
    doc.save(str(path))
    doc.close()
    return str(path)


FAKE_LATTES_TEXT = """\
Dados Pessoais
Nome: Armando Solar-Lezama
Nascimento: 01/01/1980

Formação Acadêmica/Titulação
Doutorado em Ciência da Computação
Massachusetts Institute of Technology, 2008

Atuação Profissional
Professor Titular
MIT CSAIL, 2008 - atual

Produção Bibliográfica
Sketch-based program synthesis
PLDI 2006

Prêmios e Títulos
ACM SIGPLAN Distinguished Paper Award, 2010
"""


# ── Unit: section header regex ─────────────────────────────────────────────────

def test_header_re_matches_known_sections():
    assert _HEADER_RE.search("Dados Pessoais")
    assert _HEADER_RE.search("Formação Acadêmica/Titulação")
    assert _HEADER_RE.search("Produção Bibliográfica")
    assert _HEADER_RE.search("Prêmios e Títulos")
    assert _HEADER_RE.search("Atuação Profissional")


def test_header_re_no_false_positives():
    assert not _HEADER_RE.search("Universidade de São Paulo")
    assert not _HEADER_RE.search("2024")
    assert not _HEADER_RE.search("doi:10.1145/12345")


# ── Unit: Lattes PDF filename detection ────────────────────────────────────────

def test_is_lattes_pdf_detects_lattes_filenames():
    assert _is_lattes_pdf("curriculo.pdf")
    assert _is_lattes_pdf("Lattes_João_Silva.pdf")
    assert _is_lattes_pdf("cnpq_export.pdf")
    assert _is_lattes_pdf("currículo_lattes.pdf")


def test_is_lattes_pdf_ignores_generic_pdfs():
    assert not _is_lattes_pdf("paper_2024.pdf")
    assert not _is_lattes_pdf("thesis.pdf")
    assert not _is_lattes_pdf("artigo.pdf")


# ── PDF extraction ─────────────────────────────────────────────────────────────

def test_extract_lattes_pdf_returns_sections(tmp_path):
    path = _make_lattes_pdf(tmp_path, FAKE_LATTES_TEXT)
    sections = extract_lattes_pdf(path)
    assert isinstance(sections, list)
    assert len(sections) > 0
    section_names = {s["section"] for s in sections}
    # At least one known Lattes section should be detected
    assert section_names & {
        "Dados Pessoais",
        "Formação Acadêmica/Titulação",
        "Produção Bibliográfica",
        "Atuação Profissional",
        "Prêmios e Títulos",
    }


def test_extract_lattes_pdf_each_section_has_text(tmp_path):
    path = _make_lattes_pdf(tmp_path, FAKE_LATTES_TEXT)
    sections = extract_lattes_pdf(path)
    for sec in sections:
        assert sec["text"].strip(), f"Seção '{sec['section']}' está vazia"
        assert isinstance(sec["page"], int)
        assert sec["page"] >= 1


def test_lattes_pdf_to_text_format(tmp_path):
    path = _make_lattes_pdf(tmp_path, FAKE_LATTES_TEXT)
    text = lattes_pdf_to_text(path, source_id="lattes_test")
    assert "SOURCE: lattes_test" in text
    assert "TYPE: lattes_pdf" in text
    assert "[LATTES:" in text
    assert len(text) > 50


def test_extract_lattes_pdf_empty_pdf(tmp_path):
    import fitz
    doc = fitz.open()
    doc.new_page()  # blank page
    path = tmp_path / "blank.pdf"
    doc.save(str(path))
    doc.close()
    sections = extract_lattes_pdf(str(path))
    assert isinstance(sections, list)
    # Blank PDF → no content sections
    assert all(not s["text"].strip() for s in sections) or len(sections) == 0


# ── URL extraction: graceful failure ──────────────────────────────────────────

@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_lattes_url_does_not_raise():
    """
    Lattes URL has legacy SSL + reCAPTCHA.
    The extractor must NEVER raise — it returns a fallback string.
    For real data, use PDF upload or fetch_lattes_url_playwright().
    """
    result = await fetch_lattes_url(LATTES_URL)
    assert isinstance(result, str)
    assert len(result) > 0
    # Must always contain the source marker
    assert "SOURCE: lattes_url" in result


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_lattes_url_fallback_message_on_captcha():
    """
    If CAPTCHA/SSL blocks the request, the result must contain a
    clear fallback message pointing to alternatives.
    """
    result = await fetch_lattes_url(LATTES_URL)
    # Either we got real content OR a clear fallback message
    has_content = len(result.splitlines()) > 5
    has_fallback = "PDF" in result or "Playwright" in result or "CAPTCHA" in result or "não acessível" in result
    assert has_content or has_fallback, f"Resultado inesperado: {result[:200]}"
