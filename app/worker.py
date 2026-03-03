"""ARQ worker: job queue processing."""
import logging
import traceback

from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import JobStatus
from app.pipeline import email_send, enrich, extract, generate, validate
from app.pipeline import curate as curate_step
from app.pipeline._helpers import add_event, set_status

logger = logging.getLogger(__name__)


async def process_job(ctx: dict, job_id: str) -> str:
    """Main pipeline function: runs all steps for a job."""
    session_factory: async_sessionmaker = ctx["session_factory"]

    async with session_factory() as session:
        try:
            # Step 1: Extract
            await set_status(session, job_id, JobStatus.EXTRACTING)
            await extract.run(job_id, session)

            # Step 2: Curate
            await set_status(session, job_id, JobStatus.CURATING)
            await curate_step.run(job_id, session)

            # Step 3: Enrich
            await set_status(session, job_id, JobStatus.ENRICHING)
            await enrich.run(job_id, session)

            # Step 4: Generate
            await set_status(session, job_id, JobStatus.GENERATING)
            await generate.run(job_id, session)

            # Step 5: Validate
            await set_status(session, job_id, JobStatus.VALIDATING)
            await validate.run(job_id, session)

            # Step 6: Send email
            await set_status(session, job_id, JobStatus.SENDING_EMAIL)
            await email_send.run(job_id, session)

            # Done
            await set_status(session, job_id, JobStatus.DONE)
            await add_event(session, job_id, "DONE", "Processamento concluído com sucesso")
            logger.info("Job %s completed successfully", job_id)
            return "done"

        except Exception as exc:
            tb = traceback.format_exc()
            logger.exception("Job %s failed: %s", job_id, exc)
            try:
                from app.models import Job
                from sqlalchemy import select

                result = await session.execute(select(Job).where(Job.id == job_id))
                job = result.scalar_one_or_none()
                if job:
                    job.status = JobStatus.ERROR
                    job.error_code = type(exc).__name__
                    job.error_message = str(exc)[:2000]
                    await session.commit()
                await add_event(session, job_id, "ERROR", f"Erro: {exc}")
            except Exception as inner:
                logger.error("Failed to record error for job %s: %s", job_id, inner)
            raise


async def on_startup(ctx: dict) -> None:
    """Initialize DB connection pool in worker context."""
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )
    ctx["engine"] = engine
    ctx["session_factory"] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    logger.info("Worker started, DB pool initialized")


async def on_shutdown(ctx: dict) -> None:
    """Dispose DB engine on shutdown."""
    engine = ctx.get("engine")
    if engine:
        await engine.dispose()
    logger.info("Worker shutdown, DB pool disposed")


class WorkerSettings:
    functions = [process_job]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 5
    job_timeout = 600  # 10 minutes per job
    keep_result = 3600  # Keep results 1 hour
