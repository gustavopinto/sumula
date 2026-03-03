"""initial

Revision ID: 0001
Revises:
Create Date: 2026-03-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Define PG ENUMs with create_type=False so we control creation manually
jobstatus_enum = postgresql.ENUM(
    "RECEIVED", "EXTRACTING", "CURATING", "ENRICHING",
    "GENERATING", "VALIDATING", "SENDING_EMAIL", "DONE", "ERROR",
    name="jobstatus",
    create_type=False,
)
artifactkind_enum = postgresql.ENUM(
    "raw_file", "extracted_txt", "curated_txt", "output_md",
    name="artifactkind",
    create_type=False,
)


def upgrade() -> None:
    # Create types manually (idempotent via exception handler)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE jobstatus AS ENUM (
                'RECEIVED','EXTRACTING','CURATING','ENRICHING',
                'GENERATING','VALIDATING','SENDING_EMAIL','DONE','ERROR'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE artifactkind AS ENUM (
                'raw_file','extracted_txt','curated_txt','output_md'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("status", jobstatus_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("input_manifest_json", sa.Text, nullable=True),
        sa.Column("output_manifest_json", sa.Text, nullable=True),
    )

    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", artifactkind_enum, nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("size_bytes", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step", sa.String(64), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_artifacts_job_id", "artifacts", ["job_id"])
    op.create_index("ix_events_job_id", "events", ["job_id"])
    op.create_index("ix_events_created_at", "events", ["created_at"])


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("artifacts")
    op.drop_table("jobs")
    op.execute("DROP TYPE IF EXISTS artifactkind")
    op.execute("DROP TYPE IF EXISTS jobstatus")
