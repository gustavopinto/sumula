"""Web routes: form, submit, status."""
import hashlib
import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional

import magic
from arq import create_pool
from arq.connections import RedisSettings
import asyncio
import json as _json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from urllib.parse import quote
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zoneinfo import ZoneInfo

from app.config import settings
from app.database import get_db
from app.models import Artifact, ArtifactKind, Event, Job, JobStatus
from app.pipeline._helpers import get_artifact_path

logger = logging.getLogger(__name__)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
templates = Jinja2Templates(directory="app/templates")

_TZ = ZoneInfo("America/Sao_Paulo")

def _localdt(dt, fmt="%d/%m/%Y %H:%M:%S"):
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(_TZ).strftime(fmt)

templates.env.filters["localdt"] = _localdt

def _elapsed(seconds):
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

templates.env.filters["elapsed"] = _elapsed

import re as _re
_URL_RE = _re.compile(r'(https?://[^\s]+)')

def _fmtmsg(text: str) -> str:
    """Bold (**text**) + linkify URLs in event messages."""
    text = _re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = _URL_RE.sub(r'<a href="\1" target="_blank" rel="noopener">\1</a>', text)
    return text

templates.env.filters["fmtmsg"] = _fmtmsg

_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
}

_ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, error: Optional[str] = Query(default=None)):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "max_files": settings.max_files,
            "max_mb": settings.max_upload_mb,
            "error": error,
        },
    )


def _form_error(error: str):
    return RedirectResponse(url=f"/?error={quote(error)}", status_code=303)


@router.post("/submit")
@limiter.limit("5/minute")
async def submit(
    request: Request,
    email: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    lattes_url: Optional[str] = Form(default=None),
    orcid_url: Optional[str] = Form(default=None),
    dblp_url: Optional[str] = Form(default=None),
    scholar_url: Optional[str] = Form(default=None),
    wos_url: Optional[str] = Form(default=None),
    site_url: Optional[str] = Form(default=None),
    bibtex: Optional[str] = Form(default=None),
    free_text: Optional[str] = Form(default=None),
    session: AsyncSession = Depends(get_db),
):
    def form_error(msg: str):
        return _form_error(msg)

    # Validate email
    if not email or "@" not in email:
        return form_error("E-mail inválido.")

    # Validate at least one source provided
    valid_files = [f for f in files if f.filename]
    urls = [lattes_url, orcid_url, dblp_url, scholar_url, wos_url, site_url]
    if not valid_files and not any(u and u.strip() for u in urls) and not (bibtex and bibtex.strip()) and not (free_text and free_text.strip()):
        return form_error("Forneça ao menos uma fonte: arquivo, URL, BibTeX ou texto livre.")

    # Validate files count
    if len(valid_files) > settings.max_files:
        return form_error("Envie apenas 1 currículo por submissão.")

    # Create job
    job_id = str(uuid.uuid4())
    job_dir = Path(settings.workdir_path) / job_id / "raw"
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save files
    file_manifests = []
    for upload in valid_files:
        filename = upload.filename or "file"
        ext = Path(filename).suffix.lower()

        if ext not in _ALLOWED_EXTENSIONS:
            return form_error(f"Extensão não suportada: {ext}. Use: {', '.join(_ALLOWED_EXTENSIONS)}")

        content = await upload.read()

        if len(content) > settings.max_upload_bytes:
            return form_error(f"Arquivo {filename} excede o limite de {settings.max_upload_mb} MB.")

        # Validate MIME type
        try:
            detected_mime = magic.from_buffer(content, mime=True)
        except Exception:
            detected_mime = upload.content_type or "application/octet-stream"

        if detected_mime not in _ALLOWED_MIME_TYPES and not detected_mime.startswith("text/"):
            return form_error(f"Tipo de arquivo não permitido: {detected_mime}")

        sha256 = hashlib.sha256(content).hexdigest()
        source_id = f"{sha256[:8]}_{filename}"
        dest_path = job_dir / filename
        dest_path.write_bytes(content)

        file_manifests.append({
            "name": filename,
            "path": str(dest_path),
            "sha256": sha256,
            "size_bytes": len(content),
            "mime": detected_mime,
            "source_id": source_id,
        })

    # Build input manifest
    manifest = {
        "files": file_manifests,
        "urls": {
            "lattes_url": lattes_url or None,
            "orcid_url": orcid_url or None,
            "dblp_url": dblp_url or None,
            "scholar_url": scholar_url or None,
            "wos_url": wos_url or None,
            "site_url": site_url or None,
        },
        "bibtex": bibtex or None,
        "free_text": free_text or None,
        "locale": "pt-BR",
    }

    try:
        # Save raw file artifacts to DB
        job = Job(
            id=job_id,
            email=email,
            status=JobStatus.RECEIVED,
            input_manifest_json=json.dumps(manifest, ensure_ascii=False),
        )
        session.add(job)

        for fm in file_manifests:
            artifact = Artifact(
                id=str(uuid.uuid4()),
                job_id=job_id,
                kind=ArtifactKind.raw_file,
                path=fm["path"],
                sha256=fm["sha256"],
                size_bytes=fm["size_bytes"],
            )
            session.add(artifact)

        await session.commit()

        # Enqueue job in ARQ
        try:
            redis_settings = RedisSettings.from_dsn(settings.redis_url)
            pool = await create_pool(redis_settings)
            await pool.enqueue_job("process_job", job_id)
            await pool.aclose()
        except Exception as exc:
            logger.error("Failed to enqueue job %s: %s", job_id, exc)
            # Still redirect — worker can be checked manually

    except Exception as exc:
        logger.exception("Erro ao criar job %s: %s", job_id, exc)
        return form_error(f"Erro interno ao registrar o job: {exc}")

    logger.info("Job %s submitted with %d files", job_id, len(file_manifests))
    return RedirectResponse(url=f"/status/{job_id}", status_code=303)


@router.get("/status/{job_id}/stream")
async def status_stream(job_id: str, session: AsyncSession = Depends(get_db)):
    """SSE stream: pushes job status + events until job is terminal."""
    TERMINAL = {"DONE", "ERROR"}

    async def generate():
        seen_event_ids: set[str] = set()
        start_ts = None

        while True:
            session.expire_all()
            result = await session.execute(
                select(Job).where(Job.id == job_id).options(selectinload(Job.events))
            )
            job = result.scalar_one_or_none()
            if job is None:
                yield f"data: {_json.dumps({'error': 'job not found'})}\n\n"
                return

            events = sorted(job.events, key=lambda e: e.created_at)
            if events and start_ts is None:
                start_ts = events[0].created_at

            new_events = []
            for ev in events:
                if ev.id not in seen_event_ids:
                    seen_event_ids.add(ev.id)
                    delta = int((ev.created_at - start_ts).total_seconds()) if start_ts else 0
                    m, s = divmod(delta, 60)
                    h, m2 = divmod(m, 60)
                    elapsed = f"{h:02d}:{m2:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
                    new_events.append({
                        "step": ev.step,
                        "elapsed": elapsed,
                        "message": ev.message,
                    })

            payload = {
                "status": job.status.value,
                "new_events": new_events,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            }
            yield f"data: {_json.dumps(payload)}\n\n"

            if job.status.value in TERMINAL:
                return

            await asyncio.sleep(2)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


async def _render_sumula(request: Request, job_id: str, session: AsyncSession, **extra):
    import markdown as md_lib
    md_path = await get_artifact_path(session, job_id, ArtifactKind.output_md)
    if md_path is None or not md_path.exists():
        raise HTTPException(status_code=404, detail="Súmula não encontrada")
    result = await session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    content_md = md_path.read_text(encoding="utf-8")
    content_html = md_lib.markdown(content_md, extensions=["tables", "fenced_code", "nl2br"])
    return templates.TemplateResponse(
        "sumula.html",
        {"request": request, "job_id": job_id, "content": content_html, "job_email": job.email if job else None, **extra},
    )


@router.get("/status/{job_id}/sumula", response_class=HTMLResponse)
async def sumula_view(request: Request, job_id: str, session: AsyncSession = Depends(get_db)):
    return await _render_sumula(request, job_id, session)


@router.post("/status/{job_id}/send-email", response_class=HTMLResponse)
async def sumula_send_email(
    request: Request,
    job_id: str,
    session: AsyncSession = Depends(get_db),
):
    from app.pipeline.email_send import _send_smtp
    import asyncio as _asyncio

    result = await session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job or not job.email:
        return await _render_sumula(request, job_id, session, email_error="E-mail não cadastrado para este job.")

    md_path = await get_artifact_path(session, job_id, ArtifactKind.output_md)
    if md_path is None or not md_path.exists():
        return await _render_sumula(request, job_id, session, email_error="Súmula não encontrada.")

    try:
        await _asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _send_smtp(
                to=job.email,
                subject="Súmula Curricular FAPESP",
                body_text="Sua Súmula Curricular FAPESP está em anexo.",
                body_html="<p>Sua Súmula Curricular FAPESP está em anexo.</p>",
                attachment_path=md_path,
                attachment_name="sumula.md",
            ),
        )
        return await _render_sumula(request, job_id, session, email_sent=job.email)
    except Exception as exc:
        logger.error("Erro ao enviar e-mail para %s: %s", job.email, exc)
        return await _render_sumula(request, job_id, session, email_error=f"Erro ao enviar: {exc}")


@router.get("/status/{job_id}", response_class=HTMLResponse)
async def status(request: Request, job_id: str, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.events))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    return templates.TemplateResponse(
        "status.html",
        {
            "request": request,
            "job": job,
            "events": sorted(job.events, key=lambda e: e.created_at),
        },
    )
