from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mse_viewer.domain.keyword import Keyword
from mse_viewer.parser.models import ParsedKeyword


class KeywordRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, *, include_stubs: bool = True) -> list[Keyword]:
        stmt = select(Keyword).order_by(Keyword.name)
        if not include_stubs:
            stmt = stmt.where(Keyword.is_stub.is_(False))
        return list(self.db.execute(stmt).scalars())

    def get(self, id_: int) -> Keyword | None:
        return self.db.get(Keyword, id_)

    def find_by_match(self, match: str) -> Keyword | None:
        stmt = select(Keyword).where(Keyword.name == match)
        return self.db.execute(stmt).scalar_one_or_none()

    def find_stub_by_keyword_field(self, key_text: str) -> Keyword | None:
        stmt = (
            select(Keyword)
            .where(Keyword.is_stub.is_(True))
            .where(func.lower(Keyword.source_keyword_field) == key_text.strip().lower())
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def upsert_from_parsed(self, parsed: ParsedKeyword) -> Keyword:
        existing = self.find_by_match(parsed.name)
        if existing is None:
            # Maybe a stub for the same human-readable keyword exists — merge it.
            if parsed.source_keyword_field:
                stub = self.find_stub_by_keyword_field(parsed.source_keyword_field)
                if stub is not None:
                    stub.name = parsed.name
                    stub.accepted_parameters = list(parsed.accepted_parameters)
                    stub.reminder = parsed.reminder
                    stub.rules = parsed.rules
                    stub.pseudo_keyword = parsed.pseudo_keyword
                    stub.source_keyword_field = parsed.source_keyword_field
                    stub.is_stub = False
                    self.db.flush()
                    return stub
            row = Keyword(
                name=parsed.name,
                source_keyword_field=parsed.source_keyword_field,
                accepted_parameters=list(parsed.accepted_parameters),
                reminder=parsed.reminder,
                rules=parsed.rules,
                pseudo_keyword=parsed.pseudo_keyword,
                is_stub=False,
            )
            self.db.add(row)
            self.db.flush()
            return row

        # Update in place. Keyword identity is the match string verbatim, so
        # reaching here means the user re-ingested an existing keyword — refresh
        # body fields, keep ``is_stub`` False.
        existing.source_keyword_field = parsed.source_keyword_field or existing.source_keyword_field
        existing.accepted_parameters = list(parsed.accepted_parameters)
        existing.reminder = parsed.reminder
        existing.rules = parsed.rules
        existing.pseudo_keyword = parsed.pseudo_keyword
        existing.is_stub = False
        self.db.flush()
        return existing

    def ensure_stub(self, key_text: str) -> Keyword:
        """Create or fetch a stub keyword for an undefined `<key>` reference."""
        stub = self.find_stub_by_keyword_field(key_text)
        if stub is not None:
            return stub
        # Use the same `<key>` text as match-string identity for the stub. If a
        # real definition with the same match-string later arrives, it'll merge.
        existing = self.find_by_match(key_text)
        if existing is not None:
            return existing
        row = Keyword(
            name=key_text.strip(),
            source_keyword_field=key_text.strip(),
            accepted_parameters=[],
            reminder=None,
            rules=None,
            pseudo_keyword=False,
            is_stub=True,
        )
        self.db.add(row)
        self.db.flush()
        return row
