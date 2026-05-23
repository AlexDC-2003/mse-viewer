"""drop abilities column (cards, tokens) and tokens.sets

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-05

Phase 1.6 prompt 3:
- bug 3: ``abilities`` always equalled ``rule_text`` after canonicalization;
  carrying both was confusing the manual edit form.
- bug 6: Tokens never need a per-set provenance list.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("cards", "abilities")
    op.drop_column("tokens", "abilities")
    op.drop_column("tokens", "sets")


def downgrade() -> None:
    op.add_column("tokens", sa.Column("sets", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("tokens", sa.Column("abilities", sa.Text, nullable=True))
    op.add_column("cards", sa.Column("abilities", sa.Text, nullable=True))
