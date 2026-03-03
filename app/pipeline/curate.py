"""Curation pipeline step: dedup, normalize, structure into curated TXT."""
import hashlib
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Artifact, ArtifactKind
from app.pipeline._helpers import add_event, get_job, load_manifest, save_artifact

logger = logging.getLogger(__name__)

# Section keyword patterns for routing text blocks
_SECTION_PATTERNS = {
    "FORMACAO_RAW": re.compile(
        r"forma[çc][aã]o|gradua[çc][aã]o|mestrado|doutorado|p[oó]s.doc|bacharel|licencia",
        re.IGNORECASE,
    ),
    "HISTORICO_RAW": re.compile(
        r"hist[oó]rico|cargo|institui[çc][aã]o|docente|professor|pesquisador|emprego|atua[çc][aã]o",
        re.IGNORECASE,
    ),
    "CONTRIBUICOES_RAW": re.compile(
        r"contribui[çc][oõ]|publica[çc][aã]o|artigo|livro|cap[íi]tulo|patente|software|produ[çc][aã]o",
        re.IGNORECASE,
    ),
    "FINANCIAMENTOS_RAW": re.compile(
        r"financiamento|projeto|bolsa|edital|fapesp|cnpq|capes|fundo|grant",
        re.IGNORECASE,
    ),
    "INDICADORES_RAW": re.compile(
        r"indicador|cita[çc][oõ]|h.index|impact|fator|qualis|scopus|web of science|wos",
        re.IGNORECASE,
    ),
    "OUTRAS_RAW": re.compile(
        r"prêmio|honraria|distin|biogr[aá]f|internacional|p[oó]s.dout|award|prize",
        re.IGNORECASE,
    ),
}

_DATE_PATTERN = re.compile(
    r"\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b"
)


def _normalize_date(match: re.Match) -> str:
    day, month, year = match.group(1), match.group(2), match.group(3)
    months = ["jan", "fev", "mar", "abr", "mai", "jun",
               "jul", "ago", "set", "out", "nov", "dez"]
    try:
        m_name = months[int(month) - 1]
    except (ValueError, IndexError):
        m_name = month
    return f"{m_name}/{year}"


def _sentence_hash(sentence: str) -> str:
    normalized = re.sub(r"\s+", " ", sentence.strip().lower())
    return hashlib.md5(normalized.encode()).hexdigest()


def _classify_text(text: str) -> dict[str, list[str]]:
    """Route text lines to appropriate RAW_BLOCK sections."""
    blocks: dict[str, list[str]] = {k: [] for k in _SECTION_PATTERNS}
    blocks["CONTRIBUICOES_RAW"] = []  # default catch-all

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        matched = False
        for section, pattern in _SECTION_PATTERNS.items():
            if pattern.search(line):
                blocks[section].append(line)
                matched = True
                break
        if not matched:
            blocks["CONTRIBUICOES_RAW"].append(line)

    return blocks


async def run(job_id: str, session: AsyncSession) -> None:
    """Curate all extracted artifacts into a structured curated TXT."""
    job = await get_job(session, job_id)
    manifest = load_manifest(job)

    await add_event(session, job_id, "CURATING", "Iniciando curadoria")

    # Load all extracted_txt artifacts
    result = await session.execute(
        select(Artifact).where(
            Artifact.job_id == job_id,
            Artifact.kind == ArtifactKind.extracted_txt,
        )
    )
    artifacts = result.scalars().all()

    if not artifacts:
        await add_event(session, job_id, "CURATING", "Nenhum texto extraído disponível")

    # Aggregate all text, dedup sentences
    seen_hashes: set[str] = set()
    evidence_lines: list[str] = []
    evid_counter = 0
    all_text_by_source: dict[str, str] = {}

    for artifact in artifacts:
        try:
            raw = Path(artifact.path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        source_id = Path(artifact.path).stem
        all_text_by_source[source_id] = raw

    # Build blocks and evidence
    aggregated_blocks: dict[str, list[str]] = {k: [] for k in _SECTION_PATTERNS}

    for source_id, raw in all_text_by_source.items():
        # Normalize dates
        raw = _DATE_PATTERN.sub(_normalize_date, raw)
        # Remove artificial line breaks (short lines)
        raw = _clean_text(raw)

        classified = _classify_text(raw)

        for section, lines in classified.items():
            for line in lines:
                h = _sentence_hash(line)
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                aggregated_blocks[section].append(line)

                evid_counter += 1
                snippet = line[:120].replace("|", "│")
                evidence_lines.append(
                    f"EVID {evid_counter:04d} | SRC={source_id} | LOC=auto | TEXT={snippet}"
                )

    # Build identifiers from manifest
    urls = manifest.get("urls", {})
    identifiers = "\n".join([
        f"nome: {manifest.get('nome', '')}",
        f"orcid: {urls.get('orcid_url', '')}",
        f"lattes_url: {urls.get('lattes_url', '')}",
        f"dblp_url: {urls.get('dblp_url', '')}",
        f"scholar_url: {urls.get('scholar_url', '')}",
        f"wos_url: {urls.get('wos_url', '')}",
        f"site_url: {urls.get('site_url', '')}",
    ])

    # Build curated TXT
    now = datetime.utcnow().isoformat()
    sections = []
    for section_name, lines in aggregated_blocks.items():
        content = "\n".join(lines) if lines else "NADA A DECLARAR"
        sections.append(f"[{section_name}]\n{content}")

    curated = "\n\n".join([
        f"[META]\njob_id: {job_id}\ncreated_at: {now}\nlocale: {manifest.get('locale', 'pt-BR')}",
        f"[IDENTIFIERS]\n{identifiers}",
        *sections,
        f"[EVIDENCE]\n" + "\n".join(evidence_lines),
    ])

    from app.config import settings
    out_path = Path(settings.workdir_path) / job_id / "curated.txt"
    await save_artifact(session, job_id, ArtifactKind.curated_txt, out_path, curated)
    await add_event(
        session, job_id, "CURATING",
        f"Curadoria concluída: {len(seen_hashes)} sentenças únicas, {evid_counter} evidências"
    )


def _clean_text(text: str) -> str:
    """Remove repeated headers/footers, normalize spaces and bullets."""
    lines = text.splitlines()
    # Count line frequencies (potential headers/footers appear many times)
    from collections import Counter
    freq = Counter(line.strip() for line in lines if line.strip())

    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        # Remove lines that appear more than 5 times (likely headers/footers)
        if freq[stripped] > 5:
            continue
        # Normalize bullets
        stripped = re.sub(r"^[•·▪▸►‣◦]\s*", "- ", stripped)
        # Normalize multiple spaces
        stripped = re.sub(r" {2,}", " ", stripped)
        cleaned.append(stripped)

    return "\n".join(cleaned)
