import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JobStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    EXTRACTING = "EXTRACTING"
    CURATING = "CURATING"
    ENRICHING = "ENRICHING"
    GENERATING = "GENERATING"
    VALIDATING = "VALIDATING"
    SENDING_EMAIL = "SENDING_EMAIL"
    DONE = "DONE"
    ERROR = "ERROR"


class ArtifactKind(str, enum.Enum):
    raw_file = "raw_file"
    extracted_txt = "extracted_txt"
    curated_txt = "curated_txt"
    output_md = "output_md"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="jobstatus"), nullable=False, default=JobStatus.RECEIVED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_manifest_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_manifest_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    artifacts: Mapped[list["Artifact"]] = relationship("Artifact", back_populates="job", cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship(
        "Event", back_populates="job", cascade="all, delete-orphan", order_by="Event.created_at"
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[ArtifactKind] = mapped_column(Enum(ArtifactKind, name="artifactkind"), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped["Job"] = relationship("Job", back_populates="artifacts")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    step: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped["Job"] = relationship("Job", back_populates="events")
