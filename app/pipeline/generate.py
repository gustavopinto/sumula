"""Generation pipeline step: call OpenAI GPT-4o to produce the FAPESP sumula."""
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ArtifactKind
from app.pipeline._helpers import add_event, get_artifact_path, get_job, save_artifact
from app.pipeline.prompts import GENERATE_SYSTEM, GENERATE_TEMPLATE

logger = logging.getLogger(__name__)


async def run(job_id: str, session: AsyncSession) -> None:
    """Generate the FAPESP sumula Markdown using GPT-4o."""
    await get_job(session, job_id)
    await add_event(session, job_id, "GENERATING", "Iniciando geração via LLM")

    curated_path = await get_artifact_path(session, job_id, ArtifactKind.curated_txt)
    if curated_path is None or not curated_path.exists():
        raise RuntimeError("Curated TXT não encontrado para geração")

    curated_content = curated_path.read_text(encoding="utf-8")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    user_message = (
        f"Use o TXT curado abaixo para preencher o template da Súmula Curricular FAPESP.\n\n"
        f"TEMPLATE ALVO:\n{GENERATE_TEMPLATE}\n\n"
        f"TXT CURADO:\n{curated_content}"
    )

    await add_event(session, job_id, "GENERATING", f"Chamando {settings.openai_model}...")

    response = await client.chat.completions.create(
        model=settings.openai_model,
        max_tokens=settings.openai_max_tokens,
        messages=[
            {"role": "system", "content": GENERATE_SYSTEM},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
    )

    markdown = response.choices[0].message.content or ""

    out_path = Path(settings.workdir_path) / job_id / "sumula.md"
    await save_artifact(session, job_id, ArtifactKind.output_md, out_path, markdown)
    await add_event(
        session, job_id, "GENERATING",
        f"Sumula gerada: {len(markdown)} caracteres"
    )
