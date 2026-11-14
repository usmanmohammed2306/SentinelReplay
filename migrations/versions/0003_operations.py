"""Append-only bounded operation jobs and compare-and-set status events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_operations"
down_revision: str = "0002_query_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operation_jobs",
        sa.Column("job_id", sa.String(32), primary_key=True),
        sa.Column("run_id", sa.String(80), sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("request_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "operation_events",
        sa.Column(
            "job_id", sa.String(32), sa.ForeignKey("operation_jobs.job_id"), primary_key=True
        ),
        sa.Column("sequence", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("sequence >= 0", name="ck_operation_event_sequence"),
    )
    op.create_index("ix_operation_run", "operation_jobs", ["run_id", "job_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sentinel_api') THEN
                GRANT SELECT, INSERT ON operation_jobs, operation_events TO sentinel_api;
            END IF;
        END $$;""")


def downgrade() -> None:
    op.drop_index("ix_operation_run", table_name="operation_jobs")
    op.drop_table("operation_events")
    op.drop_table("operation_jobs")
