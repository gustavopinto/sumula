from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from app.models import ArtifactKind, JobStatus


class SubmitRequest(BaseModel):
    email: str
    lattes_url: Optional[str] = None
    orcid_url: Optional[str] = None
    dblp_url: Optional[str] = None
    scholar_url: Optional[str] = None
    wos_url: Optional[str] = None
    site_url: Optional[str] = None
    bibtex: Optional[str] = None
    free_text: Optional[str] = None


class EventOut(BaseModel):
    id: str
    step: str
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactOut(BaseModel):
    id: str
    kind: ArtifactKind
    path: str
    sha256: Optional[str]
    size_bytes: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class JobStatus_(BaseModel):
    id: str
    email: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    error_code: Optional[str]
    error_message: Optional[str]
    events: list[EventOut] = []

    model_config = {"from_attributes": True}


class InputManifest(BaseModel):
    files: list[dict] = []
    urls: dict[str, Optional[str]] = {}
    bibtex: Optional[str] = None
    free_text: Optional[str] = None
    locale: str = "pt-BR"
