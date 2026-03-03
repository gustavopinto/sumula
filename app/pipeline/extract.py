"""Extraction pipeline step.

Routes each source to its dedicated extractor:
  - Lattes PDF/XML upload → extractors.lattes
  - Other PDFs           → extractors.pdf (generic)
  - XLSX                 → extractors.xlsx
  - TXT/MD               → read directly
  - lattes_url           → extractors.lattes.fetch_lattes_url
  - orcid_url            → extractors.orcid.fetch_orcid
  - dblp_url             → extractors.dblp.fetch_dblp
  - scholar_url          → extractors.scholar.fetch_scholar
  - wos_url              → extractors.wos.fetch_wos
  - site_url             → extractors.web_fetch.fetch_url  (generic)
  - bibtex               → extractors.bibtex.parse_bibtex
  - free_text            → stored as-is
"""
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.extractors.bibtex import parse_bibtex
from app.extractors.dblp import fetch_dblp
from app.extractors.lattes import fetch_lattes_url, lattes_pdf_to_text
from app.extractors.orcid import fetch_orcid
from app.extractors.pdf import extract_pdf
from app.extractors.scholar import fetch_scholar
from app.extractors.web_fetch import fetch_url
from app.extractors.wos import fetch_wos
from app.extractors.xlsx import extract_xlsx
from app.models import ArtifactKind
from app.pipeline._helpers import add_event, get_job, load_manifest, save_artifact

logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".txt", ".md"}

# Maps manifest URL field → (extractor coroutine, friendly label)
_URL_EXTRACTORS = {
    "lattes_url":  (fetch_lattes_url,  "Lattes (URL)"),
    "orcid_url":   (fetch_orcid,       "ORCID"),
    "dblp_url":    (fetch_dblp,        "DBLP"),
    "scholar_url": (fetch_scholar,     "Google Scholar"),
    "wos_url":     (fetch_wos,         "Web of Science"),
    "site_url":    (fetch_url,         "Site pessoal"),
}

# Heuristic: if filename contains these keywords, treat as Lattes PDF
_LATTES_HINTS = ("lattes", "curriculo", "currículo", "cnpq")


def _is_lattes_pdf(name: str) -> bool:
    return any(hint in name.lower() for hint in _LATTES_HINTS)


async def run(job_id: str, session: AsyncSession) -> None:
    job = await get_job(session, job_id)
    manifest = load_manifest(job)

    await add_event(session, job_id, "EXTRACTING", "Iniciando extração de fontes")
    base_dir = _job_dir(job_id)

    # ── Files ──────────────────────────────────────────────────────────────────
    for file_info in manifest.get("files", []):
        path = Path(file_info["path"])
        name = file_info.get("name", path.name)
        ext = path.suffix.lower()
        source_id = file_info.get("source_id", path.stem)

        try:
            if ext == ".pdf":
                if _is_lattes_pdf(name):
                    text = lattes_pdf_to_text(path, source_id=source_id)
                    await add_event(session, job_id, "EXTRACTING", f"Lattes PDF extraído: {name}")
                else:
                    pages = extract_pdf(path)
                    text = _pages_to_text(pages, source_id)
                    await add_event(session, job_id, "EXTRACTING", f"PDF extraído: {name} ({len(pages)} páginas)")

            elif ext in {".xlsx", ".xls"}:
                rows = extract_xlsx(path)
                text = _rows_to_text(rows, source_id)
                await add_event(session, job_id, "EXTRACTING", f"XLSX extraído: {name} ({len(rows)} linhas)")

            elif ext in {".txt", ".md"}:
                text = f"SOURCE: {source_id}\n\n" + path.read_text(encoding="utf-8", errors="replace")
                await add_event(session, job_id, "EXTRACTING", f"Texto lido: {name}")

            else:
                await add_event(session, job_id, "EXTRACTING", f"Tipo não suportado, ignorado: {name}")
                continue

            out_path = base_dir / "extracted" / f"{source_id}.txt"
            await save_artifact(session, job_id, ArtifactKind.extracted_txt, out_path, text)

        except Exception as exc:
            logger.exception("Erro ao extrair arquivo %s", name)
            await add_event(session, job_id, "EXTRACTING", f"Erro ao extrair {name}: {exc}")

    # ── URLs ───────────────────────────────────────────────────────────────────
    urls: dict = manifest.get("urls", {})

    for field, (extractor_fn, label) in _URL_EXTRACTORS.items():
        url = urls.get(field)
        if not url:
            continue
        try:
            await add_event(session, job_id, "EXTRACTING", f"Buscando {label}: {url}")
            text = await extractor_fn(url)

            if text.strip():
                out_path = base_dir / "extracted" / f"{field}.txt"
                await save_artifact(session, job_id, ArtifactKind.extracted_txt, out_path, text)
                lines = len(text.splitlines())
                await add_event(session, job_id, "EXTRACTING", f"{label} extraído ({lines} linhas)")
            else:
                await add_event(session, job_id, "EXTRACTING", f"{label}: sem conteúdo retornado")

        except Exception as exc:
            logger.exception("Erro ao extrair %s (%s)", label, url)
            await add_event(session, job_id, "EXTRACTING", f"Erro ao extrair {label}: {exc}")

    # ── BibTeX ─────────────────────────────────────────────────────────────────
    bibtex = manifest.get("bibtex", "") or ""
    if bibtex.strip():
        try:
            text = parse_bibtex(bibtex)
            out_path = base_dir / "extracted" / "bibtex.txt"
            content = f"SOURCE: bibtex\nTYPE: bibtex_pasted\n\n{text}"
            await save_artifact(session, job_id, ArtifactKind.extracted_txt, out_path, content)
            await add_event(session, job_id, "EXTRACTING", "BibTeX processado")
        except Exception as exc:
            await add_event(session, job_id, "EXTRACTING", f"Erro ao processar BibTeX: {exc}")

    # ── Texto livre ────────────────────────────────────────────────────────────
    free_text = manifest.get("free_text", "") or ""
    if free_text.strip():
        out_path = base_dir / "extracted" / "free_text.txt"
        content = f"SOURCE: free_text\nTYPE: user_input\n\n{free_text}"
        await save_artifact(session, job_id, ArtifactKind.extracted_txt, out_path, content)
        await add_event(session, job_id, "EXTRACTING", "Texto livre registrado")

    await add_event(session, job_id, "EXTRACTING", "Extração concluída")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _job_dir(job_id: str) -> Path:
    from app.config import settings
    return Path(settings.workdir_path) / job_id


def _pages_to_text(pages: list[dict], source_id: str) -> str:
    parts = [f"SOURCE: {source_id}", "TYPE: pdf_generic"]
    for p in pages:
        parts.append(f"\n--- Página {p['page']} ---\n{p['text']}")
    return "\n".join(parts)


def _rows_to_text(rows: list[dict], source_id: str) -> str:
    parts = [f"SOURCE: {source_id}", "TYPE: xlsx"]
    for r in rows:
        parts.append(f"[Aba: {r['sheet']} | Linha {r['row']}] {r['text']}")
    return "\n".join(parts)
