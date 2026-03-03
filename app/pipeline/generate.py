"""Generation pipeline step: call OpenAI GPT-4o to produce the FAPESP sumula."""
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ArtifactKind
from app.pipeline._helpers import add_event, get_artifact_path, get_job, save_artifact

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Você é um assistente especialista em elaboração de Súmulas Curriculares no formato FAPESP.

Regras absolutas:
1. Você gera somente Markdown estrito, sem HTML.
2. Você usa somente o TXT curado fornecido pelo usuário. Não invente dados.
3. Se não houver evidência suficiente para uma seção, escreva exatamente "NADA A DECLARAR".
4. Preserve a estrutura FAPESP com exatamente 6 seções na ordem correta e os subitens obrigatórios.
5. Não inclua links não informados no TXT curado.
6. Não invente números de indicadores bibliométricos.
7. Não crie seções fora do template FAPESP.
"""

_TEMPLATE = """# Súmula Curricular FAPESP

**Nome:** [nome completo]
**ORCID:** [link orcid]
**Currículo Lattes:** [link lattes]
**Web of Science:** [link wos]
**Google Scholar:** [link scholar]

---

## 1. Formação

[Descrever formação acadêmica em ordem cronológica inversa]

### 1.1 Formação — Informações Adicionais

[Informações adicionais de formação, certificações, etc.]

---

## 2. Histórico Profissional Acadêmico

[Descrever cargos, instituições e períodos em ordem cronológica inversa]

---

## 3. Contribuições à Ciência

[Descrever principais contribuições científicas com evidências]

---

## 4. Financiamentos à Pesquisa

[Listar projetos financiados, agências, período e papel]

---

## 5. Indicadores Quantitativos

[Listar indicadores bibliométricos disponíveis]

---

## 6. Outras Informações Relevantes

### 6.a Informações biográficas dos últimos dez anos

[Informações biográficas relevantes]

### 6.b Experiência internacional após doutorado

[Experiências internacionais pós-doutorado]

### 6.c Prêmios, distinções e honrarias

[Prêmios e reconhecimentos]
"""


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
        f"TEMPLATE ALVO:\n{_TEMPLATE}\n\n"
        f"TXT CURADO:\n{curated_content}"
    )

    await add_event(session, job_id, "GENERATING", f"Chamando {settings.openai_model}...")

    response = await client.chat.completions.create(
        model=settings.openai_model,
        max_tokens=settings.openai_max_tokens,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
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
