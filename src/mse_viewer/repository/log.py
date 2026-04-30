from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mse_viewer.domain.notice import LogEntry, LogKind, LogState


class LogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        kind: LogKind | None = None,
        state: LogState | None = None,
        limit: int = 200,
    ) -> list[LogEntry]:
        stmt = select(LogEntry).order_by(LogEntry.created_at.desc())
        if kind is not None:
            stmt = stmt.where(LogEntry.kind == kind)
        if state is not None:
            stmt = stmt.where(LogEntry.state == state)
        return list(self.db.execute(stmt.limit(limit)).scalars())

    def get(self, id_: int) -> LogEntry | None:
        return self.db.get(LogEntry, id_)

    def create_action(
        self,
        *,
        title: str,
        body: str | None = None,
        payload: dict | None = None,
        card_id: int | None = None,
        token_id: int | None = None,
        keyword_id: int | None = None,
    ) -> LogEntry:
        row = LogEntry(
            kind=LogKind.action,
            state=LogState.open,
            title=title,
            body=body,
            payload=payload or {},
            card_id=card_id,
            token_id=token_id,
            keyword_id=keyword_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def transition(self, entry: LogEntry, new_state: LogState) -> LogEntry:
        entry.state = new_state
        self.db.flush()
        return entry
