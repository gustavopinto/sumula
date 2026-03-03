"""API routes: job events, retry."""
import logging

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import Job, JobStatus
from app.schemas import EventOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/jobs/{job_id}/events", response_model=list[EventOut])
async def get_events(job_id: str, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.events))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    events = sorted(job.events, key=lambda e: e.created_at)
    return [EventOut.model_validate(e) for e in events]


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    if job.status not in (JobStatus.ERROR, JobStatus.DONE):
        raise HTTPException(
            status_code=409,
            detail=f"Job não pode ser reprocessado no estado {job.status}"
        )

    job.status = JobStatus.RECEIVED
    job.error_code = None
    job.error_message = None
    await session.commit()

    try:
        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        pool = await create_pool(redis_settings)
        await pool.enqueue_job("process_job", job_id)
        await pool.aclose()
    except Exception as exc:
        logger.error("Failed to enqueue retry for job %s: %s", job_id, exc)
        raise HTTPException(status_code=500, detail="Falha ao enfileirar retry")

    return {"status": "queued", "job_id": job_id}
