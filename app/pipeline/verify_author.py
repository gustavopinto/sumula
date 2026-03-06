"""verify_author pipeline step.

Após a extração, usa o LLM para identificar o nome do autor principal em cada
fonte. Se fontes distintas apontarem para autores diferentes, levanta um erro
descritivo antes de prosseguir para curadoria/geração.
"""
import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Artifact, ArtifactKind
from app.pipeline._helpers import add_event, get_job
from app.pipeline.prompts import VERIFY_AUTHOR_SYSTEM

logger = logging.getLogger(__name__)

_MAX_CHARS = 2000  # primeiros N chars de cada fonte para identificação


async def _identify_author(text: str) -> str | None:
    """Ask the LLM to identify the main author in a text snippet."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    snippet = text[:_MAX_CHARS]
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": VERIFY_AUTHOR_SYSTEM},
            {"role": "user", "content": snippet},
        ],
        max_tokens=64,
        temperature=0,
    )
    raw = response.choices[0].message.content or ""
    try:
        data = json.loads(raw)
        return data.get("nome") or None
    except Exception:
        return None


def _normalize_name(name: str) -> str:
    """Lowercase + strip for fuzzy comparison."""
    return " ".join(name.lower().split())


def _names_conflict(names: list[str]) -> bool:
    """Return True if the identified names are clearly from different people."""
    normalized = [_normalize_name(n) for n in names]
    unique = set(normalized)
    if len(unique) <= 1:
        return False

    # Allow partial matches: "gustavo pinto" vs "gustavo henrique lima pinto"
    for a in unique:
        for b in unique:
            if a == b:
                continue
            parts_a = set(a.split())
            parts_b = set(b.split())
            # If they share at least 2 name tokens, consider them the same person
            if len(parts_a & parts_b) >= 2:
                return False

    return True


async def run(job_id: str, session: AsyncSession) -> None:
    """Identify authors in each extracted source and flag conflicts."""
    await get_job(session, job_id)
    await add_event(session, job_id, "EXTRACTING", "Verificando consistência de autoria entre as fontes")

    result = await session.execute(
        select(Artifact).where(
            Artifact.job_id == job_id,
            Artifact.kind == ArtifactKind.extracted_txt,
        )
    )
    artifacts = result.scalars().all()

    if len(artifacts) < 2:
        # Só uma fonte — nada para comparar
        await add_event(session, job_id, "EXTRACTING", "Verificação de autoria: fonte única, sem conflito")
        return

    source_authors: dict[str, str] = {}  # source_id → nome identificado

    for artifact in artifacts:
        try:
            text = Path(artifact.path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        source_id = Path(artifact.path).stem
        nome = await _identify_author(text)
        if nome:
            source_authors[source_id] = nome
            logger.info("[%s] verify_author: %s → %s", job_id, source_id, nome)

    if len(source_authors) < 2:
        await add_event(session, job_id, "EXTRACTING", "Verificação de autoria: autores não identificáveis nas fontes")
        return

    names = list(source_authors.values())
    if _names_conflict(names):
        details = "\n".join(f"  • {src}: {nome}" for src, nome in source_authors.items())
        raise ValueError(
            f"As fontes fornecidas parecem pertencer a autores diferentes:\n{details}\n\n"
            "Verifique se todos os documentos e URLs são do mesmo pesquisador."
        )

    unique_names = list({_normalize_name(n) for n in names})
    await add_event(
        session, job_id, "EXTRACTING",
        f"Autoria consistente entre as fontes: {', '.join(unique_names)}"
    )
