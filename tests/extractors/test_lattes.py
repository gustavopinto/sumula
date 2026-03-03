"""Tests for the Lattes extractor.

Lattes é sempre via URL (https://lattes.cnpq.br/...). Dois obstáculos de acesso:
  1. SSL/TLS legado nos servidores CNPq.
  2. reCAPTCHA v2 (checkbox) na página do perfil.

Estratégia nos testes:
  - URL httpx: testa falha graciosa (retorna fallback, nunca levanta exceção).
  - Playwright: clica no checkbox do reCAPTCHA; se Google aprovar
    automaticamente pelo score de stealth, obtém o perfil real.
    Se challenge visual bloquear, o teste é marcado como skip.

Perfil real: https://lattes.cnpq.br/1631238943341152
"""
import pytest

from app.extractors.lattes import fetch_lattes_url, fetch_lattes_url_playwright

LATTES_URL = "https://lattes.cnpq.br/1631238943341152"

# Palavras que indicam que o acesso foi bloqueado pelo reCAPTCHA
_CAPTCHA_SIGNALS = ("reCAPTCHA", "challenge", "tokenCaptchar", "não resolvido")


def _is_captcha_blocked(result: str) -> bool:
    return any(s.lower() in result.lower() for s in _CAPTCHA_SIGNALS)


# ── httpx: falha graciosa ──────────────────────────────────────────────────────

@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_lattes_url_does_not_raise():
    """httpx nunca deve levantar exceção — retorna string com fallback."""
    result = await fetch_lattes_url(LATTES_URL)
    assert isinstance(result, str)
    assert len(result) > 0
    assert "SOURCE: lattes_url" in result


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_lattes_url_fallback_message_on_captcha():
    """Se CAPTCHA/SSL bloquear, deve haver mensagem clara de fallback."""
    result = await fetch_lattes_url(LATTES_URL)
    has_content = len(result.splitlines()) > 5
    has_fallback = "Playwright" in result or "CAPTCHA" in result or "não acessível" in result
    assert has_content or has_fallback, f"Resultado inesperado: {result[:200]}"


# ── Playwright: clique no reCAPTCHA ───────────────────────────────────────────

@pytest.mark.network
@pytest.mark.slow
@pytest.mark.asyncio
async def test_fetch_lattes_playwright_bypasses_captcha():
    """Acessa o perfil real via Playwright com stealth + clique no reCAPTCHA.

    O extrator clica no checkbox do reCAPTCHA v2. O Google pode aprovar
    automaticamente se o score de confiança da sessão for alto o suficiente
    (fingerprint limpo, comportamento humano simulado via stealth).

    - Se aprovado: verifica que o resultado contém dados reais do Lattes.
    - Se challenge visual bloquear: skip (não é possível resolver sem serviço
      externo de CAPTCHA).
    """
    result = await fetch_lattes_url_playwright(LATTES_URL)

    assert isinstance(result, str), "Deve retornar str, não exceção"
    assert len(result) > 0, "Resultado não pode ser vazio"

    if _is_captcha_blocked(result):
        pytest.skip(
            "reCAPTCHA v2 não aprovado automaticamente — "
            "challenge visual bloqueou o acesso headless.\n"
            f"Retorno: {result[:300]}"
        )

    # ── Verificações de conteúdo real ──────────────────────────────────────
    assert "SOURCE: lattes_url" in result
    assert "TYPE: playwright" in result

    # O perfil deve conter pelo menos uma dessas marcas de currículo Lattes
    lattes_markers = [
        "Produção",          # Produção Bibliográfica / Produção Técnica
        "Formação",          # Formação Acadêmica
        "Orientações",       # Orientações e Supervisões
        "Atuação",           # Atuação Profissional
        "pesquisa",          # Linhas de pesquisa / projetos
    ]
    found = [m for m in lattes_markers if m.lower() in result.lower()]
    assert found, (
        f"Nenhuma seção Lattes encontrada no conteúdo.\n"
        f"Marcadores esperados: {lattes_markers}\n"
        f"Primeiras 500 chars: {result[:500]}"
    )
