"""Shared helpers for pipeline steps."""
import hashlib
import json
import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Artifact, ArtifactKind, Event, Job, JobStatus

logger = logging.getLogger(__name__)


async def get_job(session: AsyncSession, job_id: str) -> Job:
    result = await session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise ValueError(f"Job {job_id} not found")
    return job


async def set_status(session: AsyncSession, job_id: str, status: JobStatus) -> None:
    job = await get_job(session, job_id)
    job.status = status
    await session.commit()


async def add_event(session: AsyncSession, job_id: str, step: str, message: str) -> None:
    event = Event(
        id=str(uuid.uuid4()),
        job_id=job_id,
        step=step,
        message=message,
    )
    session.add(event)
    await session.commit()
    logger.info("[%s] %s: %s", job_id, step, message)


async def save_artifact(
    session: AsyncSession,
    job_id: str,
    kind: ArtifactKind,
    path: Path,
    content: str | bytes,
) -> Artifact:
    if isinstance(content, str):
        data = content.encode("utf-8")
    else:
        data = content

    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(data)

    sha256 = hashlib.sha256(data).hexdigest()
    artifact = Artifact(
        id=str(uuid.uuid4()),
        job_id=job_id,
        kind=kind,
        path=str(path),
        sha256=sha256,
        size_bytes=len(data),
    )
    session.add(artifact)
    await session.commit()
    return artifact


async def get_artifact_path(session: AsyncSession, job_id: str, kind: ArtifactKind) -> Path | None:
    result = await session.execute(
        select(Artifact)
        .where(Artifact.job_id == job_id, Artifact.kind == kind)
        .order_by(Artifact.created_at.desc())
    )
    artifact = result.scalars().first()
    if artifact is None:
        return None
    return Path(artifact.path)


def load_manifest(job: Job) -> dict:
    if job.input_manifest_json:
        return json.loads(job.input_manifest_json)
    return {}
