from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mse_viewer.domain.card import Card
from mse_viewer.domain.token import Token
from ._helpers import append_unique, merge_unique


class _BaseCardRepo:
    model: type

    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, *, limit: int | None = None, offset: int = 0) -> list:
        stmt = select(self.model).order_by(self.model.name)
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars())

    def get(self, id_: int):
        return self.db.get(self.model, id_)

    def find_by_identity(self, identity: str):
        stmt = select(self.model).where(self.model.name == identity)
        return self.db.execute(stmt).scalar_one_or_none()

    def find_by_name_ci(self, name: str):
        stmt = select(self.model).where(func.lower(self.model.name) == name.strip().lower())
        return self.db.execute(stmt).scalars().all()

    def existing_identities(self) -> set[str]:
        return set(self.db.execute(select(self.model.name)).scalars())

    def append_set(self, row, set_name: str) -> None:
        row.sets = append_unique(row.sets, set_name)

    def append_alt_art(self, row, label: str) -> None:
        if not label.strip():
            return
        row.alt_arts = append_unique(row.alt_arts, label.strip())

    def append_related(self, row, names: list[str]) -> None:
        row.related_cards = merge_unique(row.related_cards, [n for n in names if n])

    def search(self, query: str, *, limit: int = 200) -> list:
        q = f"%{query.strip().lower()}%"
        stmt = (
            select(self.model)
            .where(func.lower(self.model.name).like(q))
            .order_by(self.model.name)
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())


class CardRepository(_BaseCardRepo):
    model = Card

    def create(self, **kwargs) -> Card:
        row = Card(**kwargs)
        self.db.add(row)
        self.db.flush()
        return row


class TokenRepository(_BaseCardRepo):
    model = Token

    def create(self, **kwargs) -> Token:
        row = Token(**kwargs)
        self.db.add(row)
        self.db.flush()
        return row
