"""deck_cards can reference tokens too

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-06

Phase 1.6 prompt 5 bug/change 3: a deck row can be either a Card or a
Token (one of the two — enforced by CHECK constraint + partial-unique
indexes on (deck_id, card_id) and (deck_id, token_id)).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_deck_card", "deck_cards", type_="unique")
    op.alter_column("deck_cards", "card_id", existing_type=sa.Integer(), nullable=True)
    op.add_column(
        "deck_cards",
        sa.Column(
            "token_id",
            sa.Integer(),
            sa.ForeignKey("tokens.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_deck_card_xor_token",
        "deck_cards",
        "(card_id IS NOT NULL) <> (token_id IS NOT NULL)",
    )
    # Partial-unique indexes: one row per (deck, card) and one per (deck, token).
    op.create_index(
        "uq_deck_card",
        "deck_cards",
        ["deck_id", "card_id"],
        unique=True,
        postgresql_where=sa.text("card_id IS NOT NULL"),
    )
    op.create_index(
        "uq_deck_token",
        "deck_cards",
        ["deck_id", "token_id"],
        unique=True,
        postgresql_where=sa.text("token_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_deck_token", table_name="deck_cards")
    op.drop_index("uq_deck_card", table_name="deck_cards")
    op.drop_constraint("ck_deck_card_xor_token", "deck_cards", type_="check")
    # Tokens that were in any deck have to be removed before re-tightening
    # ``card_id NOT NULL`` — leave that to a manual fix if it ever matters.
    op.drop_column("deck_cards", "token_id")
    op.alter_column("deck_cards", "card_id", existing_type=sa.Integer(), nullable=False)
    op.create_unique_constraint("uq_deck_card", "deck_cards", ["deck_id", "card_id"])
