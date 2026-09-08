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


def upgrade() -> None:
    for name, typ in _COLS:
        try:
            op.add_column("matches", sa.Column(name, typ, nullable=True))
        except Exception:
            pass  # already exists (create_all ran first)


def downgrade() -> None:
    for name, _ in _COLS:
        try:
            op.drop_column("matches", name)
        except Exception:
            pass
