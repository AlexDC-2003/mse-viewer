from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mse_viewer.db.base import Base


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Identity = literal match string (strict, per init_prompt_4 decision B).
    name: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    source_keyword_field: Mapped[str | None] = mapped_column(String(255), nullable=True)
    accepted_parameters: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    reminder: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    pseudo_keyword: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_stub: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Keyword id={self.id} name={self.name!r}>"
