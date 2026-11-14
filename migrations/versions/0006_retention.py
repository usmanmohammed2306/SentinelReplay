"""Logical retirements and future receipt references; no mutable run metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_retention"
down_revision: str = "0005_attestations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "run_retirements",
        sa.Column("run_id", sa.String(80), sa.ForeignKey("runs.run_id"), primary_key=True),
        sa.Column("retired_at", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
    )
    op.create_table(
        "future_receipts",
        sa.Column("digest", sa.String(71), primary_key=True),
        sa.Column("run_id", sa.String(80), sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.CheckConstraint("size > 0 AND size <= 1048576", name="ck_future_receipt_size"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sentinel_api') THEN
                GRANT SELECT, INSERT ON run_retirements, future_receipts TO sentinel_api;
            END IF;
        END $$;""")


def downgrade() -> None:
    op.drop_table("future_receipts")
    op.drop_table("run_retirements")
