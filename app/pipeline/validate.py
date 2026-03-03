"""Validation pipeline step: verify FAPESP structure, repair if needed."""
import logging
import re
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ArtifactKind
from app.pipeline._helpers import add_event, get_artifact_path, get_job, save_artifact

logger = logging.getLogger(__name__)

_REQUIRED_SECTIONS = [
    (1, r"##\s*1\.\s*Forma[çc][aã]o"),
    (2, r"##\s*2\.\s*Hist[oó]rico Profissional"),
    (3, r"##\s*3\.\s*Contribui[çc][oõ]es"),
    (4, r"##\s*4\.\s*Financiamentos"),
    (5, r"##\s*5\.\s*Indicadores"),
    (6, r"##\s*6\.\s*Outras Informa[çc][oõ]es"),
]

_REQUIRED_SUBITEMS = [
    ("1.1", r"###\s*1\.1"),
    ("6.a", r"###\s*6\.a"),
    ("6.b", r"###\s*6\.b"),
    ("6.c", r"###\s*6\.c"),
]

_HEADER_FIELDS = [
    ("ORCID", r"\*\*ORCID"),
    ("Lattes", r"\*\*Curr[íi]culo Lattes"),
]


def validate_markdown(markdown: str) -> list[str]:
    """Return list of validation error messages (empty = valid)."""
    errors = []

    # Check 6 sections in order
    last_pos = -1
    for num, pattern in _REQUIRED_SECTIONS:
        match = re.search(pattern, markdown, re.IGNORECASE)
        if not match:
            errors.append(f"Seção {num} ausente")
            continue
        if match.start() <= last_pos:
            errors.append(f"Seção {num} fora de ordem")
        last_pos = match.start()

        # Check section is not empty
        section_text = _extract_section_content(markdown, match.end())
        if not section_text.strip() or section_text.strip() == "":
            errors.append(f"Seção {num} vazia")

    # Check required subitems
    for name, pattern in _REQUIRED_SUBITEMS:
        if not re.search(pattern, markdown, re.IGNORECASE):
            errors.append(f"Subitem {name} ausente")

    # Check header fields
    for name, pattern in _HEADER_FIELDS:
        if not re.search(pattern, markdown, re.IGNORECASE):
            errors.append(f"Campo de cabeçalho ausente: {name}")

    return errors


def _extract_section_content(markdown: str, start: int) -> str:
    """Extract content between current section header and next ## header."""
    rest = markdown[start:]
    next_section = re.search(r"\n##\s", rest)
    if next_section:
        return rest[: next_section.start()]
    return rest


_REPAIR_SYSTEM = """Você é um especialista em Súmulas Curriculares FAPESP.
Corrija o Markdown abaixo para que satisfaça os requisitos listados.
Retorne apenas o Markdown corrigido, sem explicações.
Regras: não invente dados; use "NADA A DECLARAR" onde não houver informação;
mantenha todas as 6 seções na ordem correta e os subitens 1.1, 6.a, 6.b, 6.c."""


async def run(job_id: str, session: AsyncSession) -> None:
    """Validate generated markdown and repair if needed."""
    await get_job(session, job_id)
    await add_event(session, job_id, "VALIDATING", "Iniciando validação da súmula")

    md_path = await get_artifact_path(session, job_id, ArtifactKind.output_md)
    if md_path is None or not md_path.exists():
        raise RuntimeError("Arquivo sumula.md não encontrado para validação")

    markdown = md_path.read_text(encoding="utf-8")
    errors = validate_markdown(markdown)

    if not errors:
        await add_event(session, job_id, "VALIDATING", "Validação passou sem erros")
        return

    error_list = "\n".join(f"- {e}" for e in errors)
    await add_event(
        session, job_id, "VALIDATING",
        f"Validação encontrou {len(errors)} problema(s):\n{error_list}"
    )

    # Repair: call LLM with markdown + error list only
    await add_event(session, job_id, "VALIDATING", "Iniciando reparo via LLM")

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    repair_prompt = (
        f"O Markdown abaixo da Súmula Curricular FAPESP tem os seguintes problemas:\n"
        f"{error_list}\n\n"
        f"Corrija o Markdown para resolver todos os problemas listados.\n\n"
        f"MARKDOWN:\n{markdown}"
    )

    response = await client.chat.completions.create(
        model=settings.openai_model,
        max_tokens=settings.openai_max_tokens,
        messages=[
            {"role": "system", "content": _REPAIR_SYSTEM},
            {"role": "user", "content": repair_prompt},
        ],
        temperature=0.1,
    )

    repaired = response.choices[0].message.content or markdown

    # Validate once more
    remaining_errors = validate_markdown(repaired)
    if remaining_errors:
        await add_event(
            session, job_id, "VALIDATING",
            f"Reparo parcial; {len(remaining_errors)} problema(s) remanescente(s): "
            + "; ".join(remaining_errors)
        )
    else:
        await add_event(session, job_id, "VALIDATING", "Reparo bem-sucedido")

    out_path = Path(settings.workdir_path) / job_id / "sumula.md"
    await save_artifact(session, job_id, ArtifactKind.output_md, out_path, repaired)
