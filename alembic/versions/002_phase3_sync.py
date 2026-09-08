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


def upgrade() -> None:
    table, cols = _cols()
    for name, typ in cols:
        try:
            op.add_column(table, sa.Column(name, typ, nullable=True))
        except Exception:
            pass  # column already exists (e.g. create_all ran first)


def downgrade() -> None:
    table, cols = _cols()
    for name, _ in cols:
        try:
            op.drop_column(table, name)
        except Exception:
            pass
