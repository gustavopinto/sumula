"""Lattes extractor — PDF via PyMuPDF with Lattes-aware section detection.

Supports:
  - PDF upload (primary): extract_lattes_pdf(path)
  - Lattes URL (fallback): fetch_lattes_url(url) via trafilatura
"""
import logging
import re
from pathlib import Path

from app.extractors._retry import with_retries

logger = logging.getLogger(__name__)

# Lattes section headers (verbatim in the PDF)
_SECTION_HEADERS = [
    "Dados Pessoais",
    "Formação Acadêmica/Titulação",
    "Formação Complementar",
    "Atuação Profissional",
    "Linhas de Pesquisa",
    "Projetos de Pesquisa",
    "Projetos de Extensão",
    "Projetos de Desenvolvimento Tecnológico",
    "Produção Bibliográfica",
    "Produção Técnica",
    "Orientações e Supervisões",
    "Prêmios e Títulos",
    "Apresentações de Trabalho",
    "Participação em Bancas",
    "Participação em Eventos",
    "Organização de Eventos",
    "Cursos Ministrados",
    "Outras Informações",
    "Idiomas",
    "Financiamentos",
]

_HEADER_RE = re.compile(
    r"^(" + "|".join(re.escape(h) for h in _SECTION_HEADERS) + r")\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def extract_lattes_pdf(path: str | Path) -> list[dict]:
    """
    Extract text from a Lattes PDF, grouping content by Lattes sections.
    Returns list of {section: str, page: int, text: str}.
    """
    import fitz  # PyMuPDF

    results = []
    doc = fitz.open(str(path))
    try:
        current_section = "Dados Gerais"
        buffer_lines: list[str] = []
        first_page = 1

        def _flush(section: str, page: int, lines: list[str]) -> None:
            text = "\n".join(lines).strip()
            if text:
                results.append({"section": section, "page": page, "text": text})

        for page_num, page in enumerate(doc, start=1):
            raw = page.get_text("text")
            for line in raw.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if _HEADER_RE.match(stripped):
                    _flush(current_section, first_page, buffer_lines)
                    current_section = stripped
                    buffer_lines = []
                    first_page = page_num
                else:
                    buffer_lines.append(stripped)

        _flush(current_section, first_page, buffer_lines)
    finally:
        doc.close()

    return results


def lattes_pdf_to_text(path: str | Path, source_id: str = "lattes_pdf") -> str:
    """Convert Lattes PDF to structured plain text."""
    sections = extract_lattes_pdf(path)
    if not sections:
        return ""
    parts = [f"SOURCE: {source_id}", f"TYPE: lattes_pdf"]
    for sec in sections:
        parts.append(f"\n[LATTES:{sec['section'].upper().replace(' ', '_')}]")
        parts.append(sec["text"])
    return "\n".join(parts)


async def fetch_lattes_url(url: str) -> str:
    """Fetch Lattes profile page.

    CNPq/Lattes has two access barriers:
      1. Legacy SSL (SSLv3) — worked around via ssl=False in httpx.
      2. reCAPTCHA on the profile page — requires Playwright (see below).

    Current behavior: fetches whatever the server returns (may be the CAPTCHA
    challenge page). Use fetch_lattes_url_playwright() for full CAPTCHA bypass.

    NOTE: For reliable Lattes data, prefer PDF/XML upload over URL.
    """
    import ssl
    import httpx
    import trafilatura

    # CNPq uses an old TLS configuration; disable strict verification
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    async def _attempt():
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            verify=False,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SumulaBot/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        text = trafilatura.extract(html, include_tables=True, no_fallback=False) or ""
        if not text.strip():
            raise ValueError("Lattes: página vazia ou apenas CAPTCHA")
        return f"SOURCE: lattes_url\nURL: {url}\n\n{text}"

    result = await with_retries(_attempt, source="lattes_url")
    if result:
        return result

    return (
        f"SOURCE: lattes_url\nURL: {url}\n"
        f"[Lattes URL não acessível — SSL legado + reCAPTCHA detectado.\n"
        f" Use upload de PDF/XML ou fetch_lattes_url_playwright() com Playwright.]"
    )


async def fetch_lattes_url_playwright(url: str) -> str:
    """Fetch Lattes via Playwright (headless Chromium), bypassing reCAPTCHA wait.

    Requires: pip install playwright && playwright install chromium

    Strategy:
      - Abre o perfil em headless Chromium.
      - Aguarda o reCAPTCHA ser resolvido automaticamente (invisible reCAPTCHA).
      - Extrai o HTML resultante com trafilatura.
    """
    try:
        from playwright.async_api import async_playwright
        import trafilatura
    except ImportError:
        return (
            f"SOURCE: lattes_url\nURL: {url}\n"
            f"[Playwright não instalado. Execute: pip install playwright && playwright install chromium]"
        )

    async def _attempt():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                ignore_https_errors=True,
            )
            page = await ctx.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)
            # Wait for profile content (not CAPTCHA) to appear
            await page.wait_for_selector("body", timeout=15000)
            html = await page.content()
            await browser.close()

        text = trafilatura.extract(html, include_tables=True, no_fallback=False) or ""
        if not text.strip():
            raise ValueError("Lattes via Playwright: ainda sem conteúdo (CAPTCHA não resolvido?)")
        return f"SOURCE: lattes_url\nURL: {url}\nTYPE: playwright\n\n{text}"

    result = await with_retries(_attempt, source="lattes_playwright")
    return result or (
        f"SOURCE: lattes_url\nURL: {url}\n"
        f"[Lattes Playwright: falhou após 3 tentativas]"
    )
