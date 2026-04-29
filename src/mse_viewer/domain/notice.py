from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mse_viewer.db.base import Base


class LogKind(StrEnum):
    action = "action"
    notice = "notice"


class LogState(StrEnum):
    # actions
    open = "open"
    resolved = "resolved"
    # notices (Phase 2)
    unread = "unread"
    standby = "standby"
    issued = "issued"
    completed = "completed"


class LogEntry(Base):
    """Unified action / notice log.

    Phase 1 only writes ``kind=action`` rows; ``kind=notice`` rows belong to Phase 2
    but the schema is shared so we can roll forward without a migration.
    """

    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[LogKind] = mapped_column(
        SAEnum(LogKind, name="log_kind", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    state: Mapped[LogState] = mapped_column(
        SAEnum(LogState, name="log_state", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=LogState.open,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    card_id: Mapped[int | None] = mapped_column(
        ForeignKey("cards.id", ondelete="SET NULL"), nullable=True
    )
    token_id: Mapped[int | None] = mapped_column(
        ForeignKey("tokens.id", ondelete="SET NULL"), nullable=True
    )
    keyword_id: Mapped[int | None] = mapped_column(
        ForeignKey("keywords.id", ondelete="SET NULL"), nullable=True
    )

    storage_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_deck_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
