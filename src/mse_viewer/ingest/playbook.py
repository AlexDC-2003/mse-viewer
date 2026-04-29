from __future__ import annotations

from sqlalchemy.orm import Session

from mse_viewer.domain.playbook import PlaybookEntry


class PlaybookStore:
    """Thin wrapper around the playbook table.

    Scopes used in Phase 1:
      - ``"design_type"`` — keys are produced by
        :func:`mse_viewer.ingest.derivations.design_type.playbook_key`.
    """

    DESIGN_TYPE = "design_type"

    def __init__(self, db: Session) -> None:
        self.db = db

    def lookup(self, scope: str, key: str) -> str | None:
        row = (
            self.db.query(PlaybookEntry)
            .filter(PlaybookEntry.scope == scope, PlaybookEntry.key == key)
            .one_or_none()
        )
        return row.value if row else None

    def remember(self, scope: str, key: str, value: str) -> None:
        existing = (
            self.db.query(PlaybookEntry)
            .filter(PlaybookEntry.scope == scope, PlaybookEntry.key == key)
            .one_or_none()
        )
        if existing:
            existing.value = value
        else:
            self.db.add(PlaybookEntry(scope=scope, key=key, value=value))
        self.db.flush()

    # Convenience for the most common scope.
    def design_type_lookup(self, key: str) -> str | None:
        return self.lookup(self.DESIGN_TYPE, key)

    def design_type_remember(self, key: str, value: str) -> None:
        self.remember(self.DESIGN_TYPE, key, value)
