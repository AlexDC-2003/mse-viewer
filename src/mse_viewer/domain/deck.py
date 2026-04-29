from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mse_viewer.db.base import Base


class Deck(Base):
    __tablename__ = "decks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    format: Mapped[str] = mapped_column(String(32), nullable=False, default="1v1")
    theme: Mapped[str | None] = mapped_column(String(255), nullable=True)
    archetype: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owners: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    colors: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    commander_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("cards.id"), nullable=True
    )
    package: Mapped[str | None] = mapped_column(String(32), nullable=True)
    related_decks: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    cards: Mapped[list["DeckCard"]] = relationship(  # noqa: F821
        back_populates="deck", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Deck id={self.id} name={self.name!r}>"


from mse_viewer.domain.deck_card import DeckCard  # noqa: E402,F401  -- relationship resolution
