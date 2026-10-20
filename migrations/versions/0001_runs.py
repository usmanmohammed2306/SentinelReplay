"""Create immutable run metadata index.

Revision ID: 0001_runs
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_runs"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(length=80), primary_key=True),
        sa.Column("journal_root", sa.String(length=71), nullable=False),
        sa.Column("records", sa.Integer(), nullable=False),
        sa.Column("capsule_digest", sa.String(length=71), nullable=False),
        sa.Column("capsule_size", sa.BigInteger(), nullable=False),
        sa.Column("signer_key_id", sa.String(length=71), nullable=False),
        sa.CheckConstraint("records >= 0", name="ck_runs_records_nonnegative"),
        sa.CheckConstraint("capsule_size >= 0", name="ck_runs_capsule_size_nonnegative"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sentinel_api') THEN
                    GRANT SELECT, INSERT ON TABLE runs TO sentinel_api;
                END IF;
            END
            $$;"""
        )


def downgrade() -> None:
    op.drop_table("runs")
