from __future__ import annotations

import sqlalchemy as sa
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
        # ``sets`` only lives on Card (Phase 1.6 prompt 3 bug 6); silently
        # no-op for any model without the column so legacy callers don't fail.
        if not hasattr(row, "sets"):
            return
        row.sets = append_unique(row.sets, set_name)

    def append_alt_art(self, row, label: str) -> None:
        if not label.strip():
            return
        row.alt_arts = append_unique(row.alt_arts, label.strip())

    def append_related(self, row, names: list[str]) -> None:
        row.related_cards = merge_unique(row.related_cards, [n for n in names if n])

    def search(self, query: str, *, limit: int = 200) -> list:
        """Match ``query`` (case-insensitive substring) across the
        Phase-1.6 search field set: name, rule_text, flavor_text, alias,
        card_type, card_subtype, and related_cards (JSONB list cast to text).

        Whitelist tags (``<i>``, ``</i>``, ``<b>``, ``</b>``, ``<em>``,
        ``</em>``) are stripped from the prose columns before matching so
        a query for ``first-strike`` matches text stored as ``<i>first-strike</i>``.
        """
        q = f"%{query.strip().lower()}%"
        tag_re = r"</?(i|b|em)>"

        def _stripped(col):
            return func.regexp_replace(
                func.coalesce(func.lower(col), ""), tag_re, "", "gi"
            )

        rule_clean = _stripped(self.model.rule_text)
        flavor_clean = _stripped(self.model.flavor_text)
        related_clean = func.lower(
            func.coalesce(func.cast(self.model.related_cards, sa.Text), "")
        )
        stmt = (
            select(self.model)
            .where(
                func.lower(self.model.name).like(q)
                | rule_clean.like(q)
                | flavor_clean.like(q)
                | func.coalesce(func.lower(self.model.alias), "").like(q)
                | func.coalesce(func.lower(self.model.card_type), "").like(q)
                | func.coalesce(func.lower(self.model.card_subtype), "").like(q)
                | related_clean.like(q)
            )
            .order_by(self.model.name)
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())

    def distinct_design_types(self) -> list[str]:
        # Token model has no ``design_type`` column (Phase 1.6 prompt 4 item 2).
        if not hasattr(self.model, "design_type"):
            return []
        stmt = select(self.model.design_type).distinct()
        return sorted({v for v in self.db.execute(stmt).scalars() if v})

    def distinct_colors(self) -> list[str]:
        # ``colors`` is a JSONB list column — flatten in Python; the dataset is
        # small enough that this is cheaper than a set-returning Postgres
        # function and avoids the awkward SA ergonomics around it.
        seen: set[str] = set()
        for row in self.db.execute(select(self.model.colors)).scalars():
            for c in row or []:
                if c:
                    seen.add(c)
        return sorted(seen)


class CardRepository(_BaseCardRepo):
    model = Card

    def create(self, **kwargs) -> Card:
        row = Card(**kwargs)
        self.db.add(row)
        self.db.flush()
        return row

    def distinct_rarities(self) -> list[str]:
        stmt = select(Card.rarity).distinct()
        return sorted({v for v in self.db.execute(stmt).scalars() if v})


class TokenRepository(_BaseCardRepo):
    model = Token

    def create(self, **kwargs) -> Token:
        row = Token(**kwargs)
        self.db.add(row)
        self.db.flush()
        return row
