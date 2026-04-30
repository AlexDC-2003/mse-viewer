from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mse_viewer.domain.deck import Deck
from mse_viewer.domain.deck_card import DeckCard


class DeckRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[Deck]:
        return list(self.db.execute(select(Deck).order_by(Deck.name)).scalars())

    def get(self, id_: int) -> Deck | None:
        stmt = select(Deck).where(Deck.id == id_).options(selectinload(Deck.cards))
        return self.db.execute(stmt).scalar_one_or_none()

    def find_by_name(self, name: str) -> Deck | None:
        stmt = select(Deck).where(Deck.name == name.strip())
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, **kwargs) -> Deck:
        deck = Deck(**kwargs)
        self.db.add(deck)
        self.db.flush()
        return deck

    def add_card(self, deck: Deck, card_id: int, quantity: int = 1) -> DeckCard:
        existing = self.db.execute(
            select(DeckCard).where(
                DeckCard.deck_id == deck.id, DeckCard.card_id == card_id
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.quantity = max(existing.quantity, quantity)
            self.db.flush()
            return existing
        row = DeckCard(deck_id=deck.id, card_id=card_id, quantity=quantity)
        self.db.add(row)
        self.db.flush()
        return row
