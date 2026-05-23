"""drop tokens.design_type

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-06

Phase 1.6 prompt 4 item 2: Tokens don't carry a design taxonomy.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("tokens", "design_type")


def downgrade() -> None:
    op.add_column(
        "tokens",
        sa.Column(
            "design_type",
            sa.String(64),
            nullable=False,
            server_default="Normal",
        ),
    )
