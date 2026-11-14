"""Monotone operator trust-registry versions; not global evidence freshness."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_trust_epochs"
down_revision: str = "0003_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trust_epochs",
        sa.Column("epoch", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("digest", sa.String(71), nullable=False),
        sa.CheckConstraint("epoch >= 1", name="ck_trust_epoch_positive"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sentinel_api') THEN
                GRANT SELECT, INSERT ON trust_epochs TO sentinel_api;
            END IF;
        END $$;""")


def downgrade() -> None:
    op.drop_table("trust_epochs")
