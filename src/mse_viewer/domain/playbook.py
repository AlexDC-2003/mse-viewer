from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from mse_viewer.db.base import Base


class PlaybookEntry(Base):
    """Remembered overrides — e.g. (stylesheet, styling_data) → design_type."""

    __tablename__ = "playbook_entries"
    __table_args__ = (UniqueConstraint("scope", "key", name="uq_playbook_scope_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(512), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
