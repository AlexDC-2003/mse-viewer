from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mse_viewer.db.base import Base


class DeckCard(Base):
    __tablename__ = "deck_cards"
    __table_args__ = (UniqueConstraint("deck_id", "card_id", name="uq_deck_card"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    deck_id: Mapped[int] = mapped_column(
        ForeignKey("decks.id", ondelete="CASCADE"), nullable=False
    )
    card_id: Mapped[int] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    deck = relationship("Deck", back_populates="cards")
    card = relationship("Card")
