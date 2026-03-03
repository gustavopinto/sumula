"""Lattes extractor — Lattes sempre via URL (lattes.cnpq.br).

  - fetch_lattes_url(url) via trafilatura
  - fetch_lattes_url_playwright(url) para contornar reCAPTCHA
"""
import logging

from app.extractors._retry import with_retries

logger = logging.getLogger(__name__)


async def fetch_lattes_url(url: str) -> str:
    """Fetch Lattes profile page.

    CNPq/Lattes has two access barriers:
      1. Legacy SSL (SSLv3) — worked around via ssl=False in httpx.
      2. reCAPTCHA on the profile page — requires Playwright (see below).

    Current behavior: fetches whatever the server returns (may be the CAPTCHA
    challenge page). Use fetch_lattes_url_playwright() for full CAPTCHA bypass.
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
        f" Use fetch_lattes_url_playwright() com Playwright.]"
    )


async def fetch_lattes_url_playwright(url: str) -> str:
    """Fetch Lattes via Playwright (headless Chromium) com bypass do reCAPTCHA.

    Requer: pip install playwright playwright-stealth && playwright install chromium

    Estratégia:
      1. Carrega a página com modo stealth (remove sinais de automação).
      2. Aguarda o widget reCAPTCHA v2 carregar.
      3. Clica no checkbox — Google pode aprovar automaticamente dependendo do
         score de confiança da sessão (fingerprint limpo via stealth).
      4. Se aprovado, clica em "Visualizar" e extrai o perfil com trafilatura.
      5. Se o challenge visual aparecer (imagens), retorna fallback gracioso.
    """
    try:
        from playwright.async_api import async_playwright
        import trafilatura
    except ImportError:
        return (
            f"SOURCE: lattes_url\nURL: {url}\n"
            f"[Playwright não instalado. Execute: pip install playwright && playwright install chromium]"
        )

    import asyncio

    async def _attempt():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                ignore_https_errors=True,
                viewport={"width": 1280, "height": 720},
                locale="pt-BR",
            )
            page = await ctx.new_page()

            # Stealth: remove navigator.webdriver e outros sinais de automação
            try:
                from playwright_stealth import Stealth
                await Stealth().apply_stealth_async(page)
            except ImportError:
                await page.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
                )

            await page.goto(url, wait_until="networkidle", timeout=40000)
            await asyncio.sleep(2)

            # ── Tenta aprovar reCAPTCHA via clique ────────────────────────────
            anchor_frame = next(
                (f for f in page.frames if "recaptcha/api2/anchor" in f.url), None
            )
            if anchor_frame:
                try:
                    cb = await anchor_frame.wait_for_selector(
                        ".recaptcha-checkbox", timeout=5000
                    )
                    await cb.click()
                    await asyncio.sleep(4)
                    checked = await anchor_frame.query_selector(
                        ".recaptcha-checkbox-checked"
                    )
                except Exception:
                    checked = None

                if not checked:
                    await browser.close()
                    raise ValueError(
                        "Lattes: reCAPTCHA não aprovado automaticamente "
                        "(challenge visual bloqueou)"
                    )

            # ── Submete o formulário ───────────────────────────────────────────
            submit = await page.query_selector("#submitBtn:not([disabled])")
            if submit:
                await submit.click()
                await page.wait_for_load_state("networkidle", timeout=30000)

            html = await page.content()
            await browser.close()

        # Se ainda está na página do captcha, não houve conteúdo
        if "tokenCaptchar" in html:
            raise ValueError("Lattes: ainda na página do CAPTCHA após submissão")

        text = trafilatura.extract(html, include_tables=True, no_fallback=False) or ""
        if not text.strip():
            raise ValueError("Lattes via Playwright: conteúdo vazio após CAPTCHA")
        return f"SOURCE: lattes_url\nURL: {url}\nTYPE: playwright\n\n{text}"

    result = await with_retries(_attempt, source="lattes_playwright")
    return result or (
        f"SOURCE: lattes_url\nURL: {url}\n"
        f"[Lattes Playwright: reCAPTCHA não resolvido após 3 tentativas]"
    )
