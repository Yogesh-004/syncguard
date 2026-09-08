"""phase3 sync columns (nullable, existing rows untouched)

Revision ID: 002_phase3_sync
Revises: 001_initial
Create Date: 2026-09-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '002_phase3_sync'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(table: str = "sync_jobs"):
    cols = [
        ("resolution_id", sa.Integer()),
        ("destination", sa.String(200)),
        ("operation", sa.String(50)),
        ("field_name", sa.String(100)),
        ("resolved_value", sa.JSON()),
        ("attempt_count", sa.Integer()),
        ("response_metadata", sa.JSON()),
    ]
    return table, cols


def _existing_columns(table: str) -> set:
    try:
        return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return set()


def upgrade() -> None:
    # Check-then-add (not try/except): on PostgreSQL a failed DDL statement
    # aborts the whole revision transaction, which broke fresh-database
    # upgrades (Phase 8B finding). Safe to re-run after create_all.
    table, cols = _cols()
    existing = _existing_columns(table)
    for name, typ in cols:
        if name not in existing:
            op.add_column(table, sa.Column(name, typ, nullable=True))


def downgrade() -> None:
    table, cols = _cols()
    existing = _existing_columns(table)
    for name, _ in cols:
        if name in existing:
            op.drop_column(table, name)
