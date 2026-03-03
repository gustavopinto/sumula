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
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import Artifact, ArtifactKind, Event, Job, JobStatus

logger = logging.getLogger(__name__)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
templates = Jinja2Templates(directory="app/templates")

_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
}

_ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".txt", ".md"}


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "max_files": settings.max_files,
            "max_mb": settings.max_upload_mb,
        },
    )


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
    # Validate email
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="E-mail inválido")

    # Validate files count
    valid_files = [f for f in files if f.filename]
    if len(valid_files) > settings.max_files:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo de {settings.max_files} arquivos por submissão"
        )

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
            raise HTTPException(
                status_code=400,
                detail=f"Extensão não suportada: {ext}. Use: {', '.join(_ALLOWED_EXTENSIONS)}"
            )

        content = await upload.read()

        if len(content) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"Arquivo {filename} excede o limite de {settings.max_upload_mb} MB"
            )

        # Validate MIME type
        try:
            detected_mime = magic.from_buffer(content, mime=True)
        except Exception:
            detected_mime = upload.content_type or "application/octet-stream"

        if detected_mime not in _ALLOWED_MIME_TYPES and not detected_mime.startswith("text/"):
            raise HTTPException(
                status_code=400,
                detail=f"Tipo de arquivo não permitido: {detected_mime}"
            )

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
        from urllib.parse import urlparse
        parsed = urlparse(settings.redis_url)
        redis_settings = RedisSettings(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            password=parsed.password or None,
            database=int(parsed.path.lstrip("/") or 0),
        )
        pool = await create_pool(redis_settings)
        await pool.enqueue_job("process_job", job_id)
        await pool.aclose()
    except Exception as exc:
        logger.error("Failed to enqueue job %s: %s", job_id, exc)
        # Still redirect — worker can be checked manually

    logger.info("Job %s submitted by %s with %d files", job_id, email, len(file_manifests))
    return RedirectResponse(url=f"/status/{job_id}", status_code=303)


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
