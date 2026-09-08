"""phase5c presence observations table (read-only semantics; no directives)

Revision ID: 004_phase5c_presence
Revises: 003_phase45_decision
Create Date: 2026-09-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '004_phase5c_presence'
down_revision: Union[str, None] = '003_phase45_decision'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    try:
        return sa.inspect(op.get_bind()).has_table(name)
    except Exception:
        return False


def _existing_indexes(table: str) -> set:
    try:
        return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}
    except Exception:
        return set()


def upgrade() -> None:
    # Check-then-create (not try/except): on PostgreSQL a failed DDL
    # statement aborts the whole revision transaction, which broke
    # fresh-database upgrades (Phase 8B finding). Safe to re-run.
    if _has_table("presence_observations"):
        return
    op.create_table(
        "presence_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("reconciliation_jobs.id"), nullable=True),
        sa.Column("snapshot_a_ref", sa.String(200), nullable=True),
        sa.Column("snapshot_b_ref", sa.String(200), nullable=True),
        sa.Column("scope", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("record_ref", sa.String(200), nullable=False),
        sa.Column("record_presence", sa.String(20), nullable=False),
        sa.Column("entity_presence", sa.String(20), nullable=True),
        sa.Column("basis", sa.String(40), nullable=False),
        sa.Column("entity_links", sa.JSON(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("pipeline_version", sa.String(20), nullable=True),
    )
    existing = _existing_indexes("presence_observations")
    if "idx_presence_job" not in existing:
        op.create_index("idx_presence_job", "presence_observations", ["job_id"])
    if "idx_presence_record" not in existing:
        op.create_index("idx_presence_record", "presence_observations", ["record_ref"])


def downgrade() -> None:
    if not _has_table("presence_observations"):
        return
    existing = _existing_indexes("presence_observations")
    if "idx_presence_record" in existing:
        op.drop_index("idx_presence_record", table_name="presence_observations")
    if "idx_presence_job" in existing:
        op.drop_index("idx_presence_job", table_name="presence_observations")
    op.drop_table("presence_observations")
