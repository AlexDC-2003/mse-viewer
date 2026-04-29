"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


CARD_KIND = sa.Enum("card", "token", name="card_kind")
LOG_KIND = sa.Enum("action", "notice", name="log_kind")
LOG_STATE = sa.Enum(
    "open", "resolved",
    "unread", "standby", "issued", "completed",
    name="log_state",
)


def _card_columns(include_rarity_pwl: bool) -> list[sa.Column]:
    cols = [
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("card_type", sa.String(255), nullable=False, server_default=""),
        sa.Column("card_subtype", sa.String(255), nullable=True),
        sa.Column("colors", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("casting_cost", sa.String(255), nullable=True),
        sa.Column("power", sa.String(32), nullable=True),
        sa.Column("toughness", sa.String(32), nullable=True),
        sa.Column("flavor_text", sa.Text, nullable=True),
        sa.Column("rule_text", sa.Text, nullable=True),
        sa.Column("abilities", sa.Text, nullable=True),
        sa.Column("keyword_ids", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("related_cards", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("sets", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("alt_arts", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("design_type", sa.String(64), nullable=False, server_default="Normal"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("printed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]
    if include_rarity_pwl:
        cols.append(sa.Column("rarity", sa.String(32), nullable=False, server_default="common"))
        cols.append(sa.Column("power_level", sa.Integer, nullable=True))
    return cols


def upgrade() -> None:
    op.create_table("cards", *_card_columns(include_rarity_pwl=True))
    op.create_index("ix_cards_name_lower", "cards", [sa.text("lower(name)")], unique=False)
    op.create_index("ix_cards_colors_gin", "cards", ["colors"], postgresql_using="gin")
    op.create_index("ix_cards_keyword_ids_gin", "cards", ["keyword_ids"], postgresql_using="gin")
    op.create_index("ix_cards_sets_gin", "cards", ["sets"], postgresql_using="gin")

    op.create_table("tokens", *_card_columns(include_rarity_pwl=False))
    op.create_index("ix_tokens_name_lower", "tokens", [sa.text("lower(name)")], unique=False)
    op.create_index("ix_tokens_colors_gin", "tokens", ["colors"], postgresql_using="gin")
    op.create_index("ix_tokens_keyword_ids_gin", "tokens", ["keyword_ids"], postgresql_using="gin")

    op.create_table(
        "keywords",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(512), nullable=False, unique=True),
        sa.Column("source_keyword_field", sa.String(255), nullable=True),
        sa.Column("accepted_parameters", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("reminder", sa.Text, nullable=True),
        sa.Column("rules", sa.Text, nullable=True),
        sa.Column("pseudo_keyword", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_stub", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "decks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("format", sa.String(32), nullable=False, server_default="1v1"),
        sa.Column("theme", sa.String(255), nullable=True),
        sa.Column("archetype", sa.String(255), nullable=True),
        sa.Column("owners", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("colors", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("size", sa.Integer, nullable=False, server_default="60"),
        sa.Column("commander_card_id", sa.Integer, sa.ForeignKey("cards.id"), nullable=True),
        sa.Column("package", sa.String(32), nullable=True),
        sa.Column("related_decks", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "deck_cards",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("deck_id", sa.Integer, sa.ForeignKey("decks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("card_id", sa.Integer, sa.ForeignKey("cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.UniqueConstraint("deck_id", "card_id", name="uq_deck_card"),
    )
    op.create_index("ix_deck_cards_card", "deck_cards", ["card_id"])
    op.create_index("ix_deck_cards_deck", "deck_cards", ["deck_id"])

    op.create_table(
        "log_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", LOG_KIND, nullable=False),
        sa.Column("state", LOG_STATE, nullable=False, server_default="open"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("card_id", sa.Integer, sa.ForeignKey("cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("token_id", sa.Integer, sa.ForeignKey("tokens.id", ondelete="SET NULL"), nullable=True),
        sa.Column("keyword_id", sa.Integer, sa.ForeignKey("keywords.id", ondelete="SET NULL"), nullable=True),
        sa.Column("storage_location", sa.Text, nullable=True),
        sa.Column("affected_deck_ids", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_log_kind_state", "log_entries", ["kind", "state"])

    op.create_table(
        "playbook_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("scope", sa.String(64), nullable=False),  # e.g. "design_type"
        sa.Column("key", sa.String(512), nullable=False),
        sa.Column("value", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("scope", "key", name="uq_playbook_scope_key"),
    )


def downgrade() -> None:
    op.drop_table("playbook_entries")
    op.drop_index("ix_log_kind_state", table_name="log_entries")
    op.drop_table("log_entries")
    op.drop_index("ix_deck_cards_deck", table_name="deck_cards")
    op.drop_index("ix_deck_cards_card", table_name="deck_cards")
    op.drop_table("deck_cards")
    op.drop_table("decks")
    op.drop_table("keywords")
    op.drop_index("ix_tokens_keyword_ids_gin", table_name="tokens")
    op.drop_index("ix_tokens_colors_gin", table_name="tokens")
    op.drop_index("ix_tokens_name_lower", table_name="tokens")
    op.drop_table("tokens")
    op.drop_index("ix_cards_sets_gin", table_name="cards")
    op.drop_index("ix_cards_keyword_ids_gin", table_name="cards")
    op.drop_index("ix_cards_colors_gin", table_name="cards")
    op.drop_index("ix_cards_name_lower", table_name="cards")
    op.drop_table("cards")
    op.execute("DROP TYPE IF EXISTS log_state")
    op.execute("DROP TYPE IF EXISTS log_kind")
    op.execute("DROP TYPE IF EXISTS card_kind")
