from __future__ import annotations

from mse_viewer.db.base import Base
from mse_viewer.domain._card_mixin import CardCoreMixin


class Token(Base, CardCoreMixin):
    __tablename__ = "tokens"

    def __repr__(self) -> str:  # pragma: no cover -- debug only
        return f"<Token id={self.id} name={self.name!r}>"
