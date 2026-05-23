"""card starting_loyalty column

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cards", sa.Column("starting_loyalty", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("cards", "starting_loyalty")
