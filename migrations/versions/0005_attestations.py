"""Retain the original verified detached capsule statement in encrypted CAS."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_attestations"
down_revision: str = "0004_trust_epochs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "run_attestations",
        sa.Column("run_id", sa.String(80), sa.ForeignKey("runs.run_id"), primary_key=True),
        sa.Column("digest", sa.String(71), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.CheckConstraint("size > 0 AND size <= 8192", name="ck_run_attestation_size"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sentinel_api') THEN
                GRANT SELECT, INSERT ON run_attestations TO sentinel_api;
            END IF;
        END $$;""")


def downgrade() -> None:
    op.drop_table("run_attestations")
