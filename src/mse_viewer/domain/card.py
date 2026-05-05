from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from mse_viewer.db.base import Base
from mse_viewer.domain._card_mixin import CardCoreMixin


class Card(Base, CardCoreMixin):
    __tablename__ = "cards"

    rarity: Mapped[str] = mapped_column(String(32), nullable=False, default="common")
    power_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Planeswalkers only — null on every other card type.
    starting_loyalty: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover -- debug only
        return f"<Card id={self.id} name={self.name!r}>"
