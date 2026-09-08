"""phase4.5 decision columns on matches (nullable, historical rows untouched)

Revision ID: 003_phase45_decision
Revises: 002_phase3_sync
Create Date: 2026-09-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '003_phase45_decision'
down_revision: Union[str, None] = '002_phase3_sync'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLS = [
    ("final_confidence", sa.Float()),
    ("risk", sa.String(20)),
    ("auto_resolvable", sa.Boolean()),
    ("recommendation", sa.String(50)),
]


def _existing_columns(table: str) -> set:
    try:
        return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return set()


def upgrade() -> None:
    # Check-then-add (not try/except): on PostgreSQL a failed DDL statement
    # aborts the whole revision transaction, which broke fresh-database
    # upgrades (Phase 8B finding). Safe to re-run after create_all.
    existing = _existing_columns("matches")
    for name, typ in _COLS:
        if name not in existing:
            op.add_column("matches", sa.Column(name, typ, nullable=True))


def downgrade() -> None:
    existing = _existing_columns("matches")
    for name, _ in _COLS:
        if name in existing:
            op.drop_column("matches", name)
