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


def upgrade() -> None:
    try:
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
        op.create_index("idx_presence_job", "presence_observations", ["job_id"])
        op.create_index("idx_presence_record", "presence_observations", ["record_ref"])
    except Exception:
        pass  # already exists (create_all ran first)


def downgrade() -> None:
    try:
        op.drop_index("idx_presence_record", table_name="presence_observations")
        op.drop_index("idx_presence_job", table_name="presence_observations")
        op.drop_table("presence_observations")
    except Exception:
        pass
