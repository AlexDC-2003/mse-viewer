"""card/token alias column

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cards", sa.Column("alias", sa.Text, nullable=True))
    op.add_column("tokens", sa.Column("alias", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("tokens", "alias")
    op.drop_column("cards", "alias")
