from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class CardCoreMixin:
    """Columns shared by Card and Token tables."""

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    card_type: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    card_subtype: Mapped[str | None] = mapped_column(String(255), nullable=True)

    @declared_attr
    def colors(cls) -> Mapped[list[str]]:
        return mapped_column(JSONB, nullable=False, default=list)

    casting_cost: Mapped[str | None] = mapped_column(String(255), nullable=True)
    power: Mapped[str | None] = mapped_column(String(32), nullable=True)
    toughness: Mapped[str | None] = mapped_column(String(32), nullable=True)
    flavor_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    abilities: Mapped[str | None] = mapped_column(Text, nullable=True)

    @declared_attr
    def keyword_ids(cls) -> Mapped[list[int]]:
        return mapped_column(JSONB, nullable=False, default=list)

    @declared_attr
    def related_cards(cls) -> Mapped[list[str]]:
        return mapped_column(JSONB, nullable=False, default=list)

    @declared_attr
    def sets(cls) -> Mapped[list[str]]:
        return mapped_column(JSONB, nullable=False, default=list)

    @declared_attr
    def alt_arts(cls) -> Mapped[list[str]]:
        return mapped_column(JSONB, nullable=False, default=list)

    design_type: Mapped[str] = mapped_column(String(64), nullable=False, default="Normal")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    printed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
