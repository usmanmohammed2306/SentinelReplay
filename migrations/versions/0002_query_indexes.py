"""Add root-bound immutable investigation indexes.

Revision ID:0002_query_indexes
Revises:0001_runs
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_query_indexes"
down_revision = "0001_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_indexes",
        sa.Column("index_id", sa.String(71), primary_key=True),
        sa.Column("run_id", sa.String(80), sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("view_id", sa.String(20), nullable=False),
        sa.Column("producer_digest", sa.String(71), nullable=False),
        sa.Column("capsule_digest", sa.String(71), nullable=False),
        sa.Column("journal_root", sa.String(71), nullable=False),
        sa.Column("records", sa.Integer(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("phases", sa.JSON(), nullable=True),
        sa.Column("incidents", sa.JSON(), nullable=False),
        sa.Column("graph_supported", sa.Integer(), nullable=False),
    )
    op.create_table(
        "event_pages",
        sa.Column(
            "index_id", sa.String(71), sa.ForeignKey("run_indexes.index_id"), primary_key=True
        ),
        sa.Column("first_step", sa.Integer(), primary_key=True),
        sa.Column("records", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(71), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "first_step >= 0 AND records > 0 AND records <= 500", name="ck_event_page_bounds"
        ),
    )
    op.create_table(
        "dependency_edges",
        sa.Column(
            "index_id", sa.String(71), sa.ForeignKey("run_indexes.index_id"), primary_key=True
        ),
        sa.Column("source", sa.Integer(), primary_key=True),
        sa.Column("target", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(32), primary_key=True),
        sa.Column("rationale", sa.String(240), nullable=False),
        sa.CheckConstraint("source >= 0 AND target > source", name="ck_dependency_forward"),
    )
    op.create_index("ix_dependency_target", "dependency_edges", ["index_id", "target"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sentinel_api') THEN
          GRANT SELECT, INSERT ON run_indexes, event_pages, dependency_edges TO sentinel_api;
        END IF; END $$;""")


def downgrade() -> None:
    for table in ("dependency_edges", "event_pages", "run_indexes"):
        op.drop_table(table)
