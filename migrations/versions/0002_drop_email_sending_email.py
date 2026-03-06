"""drop email column and SENDING_EMAIL enum value

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make email nullable
    op.alter_column("jobs", "email", existing_type=sa.String(255), nullable=True)

    # Add new jobstatus enum without SENDING_EMAIL (Postgres requires recreating the type)
    op.execute("ALTER TYPE jobstatus RENAME TO jobstatus_old")
    op.execute("""
        CREATE TYPE jobstatus AS ENUM (
            'RECEIVED', 'EXTRACTING', 'CURATING', 'ENRICHING',
            'GENERATING', 'VALIDATING', 'DONE', 'ERROR'
        )
    """)
    op.execute("""
        ALTER TABLE jobs
            ALTER COLUMN status TYPE jobstatus
            USING status::text::jobstatus
    """)
    op.execute("DROP TYPE jobstatus_old")


def downgrade() -> None:
    op.execute("ALTER TYPE jobstatus RENAME TO jobstatus_old")
    op.execute("""
        CREATE TYPE jobstatus AS ENUM (
            'RECEIVED', 'EXTRACTING', 'CURATING', 'ENRICHING',
            'GENERATING', 'VALIDATING', 'SENDING_EMAIL', 'DONE', 'ERROR'
        )
    """)
    op.execute("""
        ALTER TABLE jobs
            ALTER COLUMN status TYPE jobstatus
            USING status::text::jobstatus
    """)
    op.execute("DROP TYPE jobstatus_old")
    op.alter_column("jobs", "email", existing_type=sa.String(255), nullable=False)
