from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mse_viewer.db.base import Base


class DeckCard(Base):
    """A single member of a deck — either a Card or a Token, with quantity.

    Phase 1.6 prompt 5 bug/change 3: decks can now hold tokens too. Exactly
    one of ``card_id`` / ``token_id`` is non-null per row, enforced by a
    DB-level CHECK constraint and a pair of partial-unique indexes
    (created in the migration). The model carries optional relationships
    to both sides; the UI picks the link target based on which FK is set.
    """

    __tablename__ = "deck_cards"
    __table_args__ = (
        CheckConstraint(
            "(card_id IS NOT NULL) <> (token_id IS NOT NULL)",
            name="ck_deck_card_xor_token",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    deck_id: Mapped[int] = mapped_column(
        ForeignKey("decks.id", ondelete="CASCADE"), nullable=False
    )
    card_id: Mapped[int | None] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE"), nullable=True
    )
    token_id: Mapped[int | None] = mapped_column(
        ForeignKey("tokens.id", ondelete="CASCADE"), nullable=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    deck = relationship("Deck", back_populates="cards")
    card = relationship("Card")
    token = relationship("Token")

    @property
    def member(self):
        """Return the Card or Token row this member references."""
        return self.card if self.card_id is not None else self.token

    @property
    def member_kind(self) -> str:
        return "card" if self.card_id is not None else "token"
