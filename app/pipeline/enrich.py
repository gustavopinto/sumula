"""Enrichment pipeline step: consolidate publications, compute indicators."""
import logging
import re
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ArtifactKind
from app.pipeline._helpers import (
    add_event,
    get_artifact_path,
    get_job,
    save_artifact,
)

logger = logging.getLogger(__name__)

_PUB_BLOCK = re.compile(r"\[CONTRIBUICOES_RAW\](.*?)(?=\[|\Z)", re.DOTALL)
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")


def _normalize_title(text: str) -> str:
    """Normalize a publication title for dedup."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _consolidate_publications(block_text: str) -> tuple[str, dict]:
    """Dedup publications by normalized title+year, return consolidated text and counts."""
    lines = [l.strip() for l in block_text.splitlines() if l.strip()]
    seen: dict[str, str] = {}
    counts: dict[str, int] = {"artigos": 0, "livros": 0, "capitulos": 0, "outros": 0}

    consolidated = []
    for line in lines:
        year_match = _YEAR_PATTERN.search(line)
        year = year_match.group(0) if year_match else "s/d"
        key = _normalize_title(line[:80]) + "|" + year

        if key in seen:
            continue
        seen[key] = line

        lower = line.lower()
        if any(w in lower for w in ["journal", "revista", "artigo", "article", "doi"]):
            counts["artigos"] += 1
        elif any(w in lower for w in ["livro", "book", "editora"]):
            counts["livros"] += 1
        elif any(w in lower for w in ["capítulo", "capitulo", "chapter"]):
            counts["capitulos"] += 1
        else:
            counts["outros"] += 1

        consolidated.append(line)

    return "\n".join(consolidated), counts


async def run(job_id: str, session: AsyncSession) -> None:
    """Enrich curated TXT: consolidate pubs, update indicators."""
    await get_job(session, job_id)
    await add_event(session, job_id, "ENRICHING", "Iniciando enriquecimento")

    curated_path = await get_artifact_path(session, job_id, ArtifactKind.curated_txt)
    if curated_path is None or not curated_path.exists():
        await add_event(session, job_id, "ENRICHING", "Curated TXT não encontrado, pulando enriquecimento")
        return

    curated = curated_path.read_text(encoding="utf-8")

    # Find CONTRIBUICOES_RAW block
    match = _PUB_BLOCK.search(curated)
    if match:
        block_text = match.group(1)
        consolidated_text, counts = _consolidate_publications(block_text)

        # Replace block content
        curated = curated.replace(match.group(1), "\n" + consolidated_text + "\n")

        # Update INDICADORES_RAW with computed counts
        indicator_summary = (
            f"Artigos: {counts['artigos']}\n"
            f"Livros: {counts['livros']}\n"
            f"Capítulos: {counts['capitulos']}\n"
            f"Outros: {counts['outros']}"
        )
        indic_block = re.compile(r"(\[INDICADORES_RAW\]\n)(.*?)(?=\[|\Z)", re.DOTALL)
        indic_match = indic_block.search(curated)
        if indic_match:
            existing = indic_match.group(2).strip()
            updated = existing + "\n\n[Contagens automáticas]\n" + indicator_summary if existing and existing != "NADA A DECLARAR" else indicator_summary
            curated = curated[:indic_match.start(2)] + updated + "\n" + curated[indic_match.end(2):]
        else:
            curated += f"\n\n[INDICADORES_RAW]\n{indicator_summary}"

        await add_event(
            session, job_id, "ENRICHING",
            f"Publicações consolidadas: {counts['artigos']} artigos, {counts['livros']} livros, "
            f"{counts['capitulos']} capítulos, {counts['outros']} outros"
        )
    else:
        await add_event(session, job_id, "ENRICHING", "Bloco de contribuições não encontrado")

    # Overwrite curated artifact
    from app.config import settings
    out_path = Path(settings.workdir_path) / job_id / "curated.txt"
    await save_artifact(session, job_id, ArtifactKind.curated_txt, out_path, curated)
    await add_event(session, job_id, "ENRICHING", "Enriquecimento concluído")
