from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mse_viewer.domain.card import Card
from mse_viewer.domain.keyword import Keyword
from mse_viewer.domain.token import Token
from mse_viewer.parser.models import ParsedKeyword


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RE_ATOM_PARAM = re.compile(r"<atom-param>[^<]*</atom-param>", re.IGNORECASE)


def _kw_match_pattern(match_string: str) -> re.Pattern[str]:
    """Convert a keyword's ``match:`` string into a regex that captures any
    card-side reference (``<key>...</key>`` body) referring to that keyword.

    Each ``<atom-param>X</atom-param>`` slot becomes a non-greedy capture
    group ``(.+?)``; the surrounding literals are escaped.  The pattern is
    anchored and case-insensitive, so ``Cleave 1RR``, ``cleave 4BB`` and
    ``Cleave X`` all match a definition with match-string
    ``Cleave <atom-param>cost</atom-param>``.
    """
    parts = _RE_ATOM_PARAM.split(match_string)
    pattern = "(.+?)".join(re.escape(p) for p in parts)
    return re.compile(rf"^\s*{pattern}\s*$", re.IGNORECASE | re.DOTALL)


def _has_atom_params(s: str) -> bool:
    return bool(_RE_ATOM_PARAM.search(s or ""))


def _is_self_defining(name: str) -> bool:
    """A keyword whose captured reminder body counts as a full definition.

    Any non-empty name without an ``<atom-param>`` slot qualifies — both
    single-word (Haste, Trample) and multi-word (Triple strike, Ward 3) forms.
    Names that already contain an ``<atom-param>`` slot still need an
    explicit ``keyword:`` block because parameterisation is the source of
    truth for which slots accept which kinds of value.

    Trade-off (decision 2026-05-04): a multi-word stub name like ``Ward 3``
    is now auto-promoted on first import. If the user later imports a
    formal ``Ward <atom-param>cost</atom-param>`` block, the existing
    absorption logic only merges ``is_stub=True`` rows, so the auto-
    promoted ``Ward 3`` / ``Ward 2`` rows stay as separate non-stub
    keywords alongside the parameterised one. The user accepted this in
    exchange for not having to manually fill in reminders that the parser
    already captured correctly.
    """
    n = (name or "").strip()
    if not n:
        return False
    return not _has_atom_params(n)


def _strip_inline_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def _singularize(s: str) -> str:
    """Naive English-plural normalization for stub names: drop a single
    trailing ``s`` unless the word ends in ``ss`` (e.g. *Class*).  Returns the
    original string when no transform applies.
    """
    s = s.strip()
    if len(s) <= 2:
        return s
    lower = s.lower()
    if lower.endswith("ss") or lower.endswith("us") or lower.endswith("is"):
        return s
    if lower.endswith("s"):
        return s[:-1]
    return s


def _stub_canonical(ref_text: str) -> str:
    """Canonical form for a stub-keyword name.

    Strip inline tags (``<param-*>`` etc.), trim, singularize trailing 's',
    and capitalize the first character so that
    ``"food tokens"`` / ``"Food Tokens"`` both become ``"Food Token"``
    (init_prompt_4 #95).
    """
    s = _strip_inline_tags(ref_text)
    s = _singularize(s)
    if not s:
        return ""
    return s[0].upper() + s[1:]


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class KeywordRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- queries ----------------------------------------------------------

    def list(self, *, include_stubs: bool = True) -> list[Keyword]:
        stmt = select(Keyword).order_by(Keyword.name)
        if not include_stubs:
            stmt = stmt.where(Keyword.is_stub.is_(False))
        return list(self.db.execute(stmt).scalars())

    def list_stubs(self) -> list[Keyword]:
        """Stub-only listing for the dashboard."""
        stmt = select(Keyword).where(Keyword.is_stub.is_(True)).order_by(Keyword.name)
        return list(self.db.execute(stmt).scalars())

    def search(self, query: str, *, limit: int = 200) -> list[Keyword]:
        """Match ``query`` against keyword name, reminder, and rules text;
        whitelist tags (``<i>``/``<b>``/``<em>``) are stripped from the body
        columns the same way :meth:`CardRepository.search` does it."""
        q = f"%{query.strip().lower()}%"
        tag_re = r"</?(i|b|em)>"
        reminder_clean = func.regexp_replace(
            func.coalesce(func.lower(Keyword.reminder), ""), tag_re, "", "gi"
        )
        rules_clean = func.regexp_replace(
            func.coalesce(func.lower(Keyword.rules), ""), tag_re, "", "gi"
        )
        stmt = (
            select(Keyword)
            .where(
                func.lower(Keyword.name).like(q)
                | reminder_clean.like(q)
                | rules_clean.like(q)
            )
            .order_by(Keyword.name)
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())

    def get(self, id_: int) -> Keyword | None:
        return self.db.get(Keyword, id_)

    def find_by_match(self, match: str) -> Keyword | None:
        """Exact case-sensitive match (legacy callers)."""
        stmt = select(Keyword).where(Keyword.name == match)
        return self.db.execute(stmt).scalar_one_or_none()

    def find_by_match_ci(self, match: str) -> Keyword | None:
        """Case-insensitive exact match on the literal match-string."""
        stmt = select(Keyword).where(func.lower(Keyword.name) == match.strip().lower())
        return self.db.execute(stmt).scalar_one_or_none()

    def find_for_card_ref(self, ref_text: str) -> Keyword | None:
        """Resolve a card-side ``<key>...</key>`` reference to a keyword row.

        Resolution order:
          1. Exact case-insensitive match on ``keyword.name``.
          2. Structural CI match: each parameterized keyword's match string is
             compiled to a regex (``<atom-param>X</atom-param>`` → ``(.+?)``);
             real definitions are tried before stubs.  This is what makes
             ``Cleave 1RR`` resolve to ``Cleave <atom-param>cost</atom-param>``.
          3. Singularized retry on the same two passes (so plural references
             like ``Food tokens`` find the singular keyword).
        """
        candidates = self.list(include_stubs=True)
        return (
            self._resolve_one(ref_text, candidates)
            or self._resolve_one(_singularize(_strip_inline_tags(ref_text)), candidates)
        )

    def _resolve_one(self, ref: str, candidates: list[Keyword]) -> Keyword | None:
        ref_n = (ref or "").strip()
        if not ref_n:
            return None
        # 1) exact CI hit on stored name.
        for kw in candidates:
            if kw.name.lower() == ref_n.lower():
                return kw
        # 2) structural — prefer real definitions.
        for kw in (k for k in candidates if not k.is_stub and _has_atom_params(k.name)):
            if _kw_match_pattern(kw.name).match(ref_n):
                return kw
        # 3) structural — stubs (rare; stubs don't carry atom-params unless a
        # weird situation injected them).
        for kw in (k for k in candidates if k.is_stub and _has_atom_params(k.name)):
            if _kw_match_pattern(kw.name).match(ref_n):
                return kw
        return None

    # ---- writes -----------------------------------------------------------

    def upsert_from_parsed(self, parsed: ParsedKeyword) -> Keyword:
        """Upsert a keyword definition; absorb any matching stubs afterwards."""
        existing = self.find_by_match_ci(parsed.name)
        if existing is None:
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
        else:
            existing.name = parsed.name  # promote casing if it was different
            existing.source_keyword_field = parsed.source_keyword_field or existing.source_keyword_field
            existing.accepted_parameters = list(parsed.accepted_parameters)
            # Don't clobber a card-captured reminder/rules with None; the
            # definition file may simply not include those fields.
            if parsed.reminder is not None:
                existing.reminder = parsed.reminder
            if parsed.rules is not None:
                existing.rules = parsed.rules
            existing.pseudo_keyword = parsed.pseudo_keyword
            existing.is_stub = False
            self.db.flush()
            row = existing

        self._absorb_matching_stubs(row)
        return row

    def ensure_stub(self, ref_text: str, *, reminder: str | None = None) -> Keyword:
        """Get-or-create a stub keyword for an unresolved card reference.

        First try to find an existing real or stub keyword that matches the
        reference (structurally or by name).  Only if nothing matches do we
        create a new stub, and the stub's name is the *canonical* form
        (singular, leading-capital).  ``reminder`` (if provided) is captured
        from the trailing ``<atom-reminder>`` block that followed the
        invocation in rule text — gives the stub a useful body so the
        Keywords list isn't a wall of empty rows (init_prompt_5 #5).

        For single-word keywords (no whitespace, no ``<atom-param>``) the
        captured reminder *is* the definition: when one shows up the row is
        auto-promoted to ``is_stub=False`` so it stops appearing as a TODO.
        """
        existing = self.find_for_card_ref(ref_text)
        if existing is not None:
            self.maybe_backfill_reminder(existing, reminder)
            return existing
        canonical = _stub_canonical(ref_text)
        if not canonical:
            canonical = ref_text.strip() or "?"
        existing_ci = self.find_by_match_ci(canonical)
        if existing_ci is not None:
            self.maybe_backfill_reminder(existing_ci, reminder)
            return existing_ci
        # Brand-new row: if it's single-word and we have a reminder, the
        # reminder is enough — promote straight to a real definition.
        promote = bool(reminder) and _is_self_defining(canonical)
        row = Keyword(
            name=canonical,
            source_keyword_field=canonical,
            accepted_parameters=[],
            reminder=reminder,
            rules=None,
            pseudo_keyword=False,
            is_stub=not promote,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def maybe_backfill_reminder(self, kw: Keyword, reminder: str | None) -> None:
        """Fill in a missing reminder on an existing stub and, if the keyword
        is single-word, promote it out of stub state.  Never clobbers an
        already-populated reminder.  Public so the ingest path can call it
        when ``find_for_card_ref`` already returned a row (in which case
        ``ensure_stub`` is *not* invoked and the reminder would otherwise be
        dropped)."""
        if not kw.is_stub or not reminder:
            return
        if not kw.reminder:
            kw.reminder = reminder
        if _is_self_defining(kw.name):
            kw.is_stub = False
        self.db.flush()

    # ---- stub absorption --------------------------------------------------

    def _absorb_matching_stubs(self, kw: Keyword) -> int:
        """When a real keyword is upserted, any stubs whose names match its
        structural pattern (or its literal name) are merged into it: cards /
        tokens referencing the stub are repointed at the real row, then the
        stub is deleted."""
        stubs = list(
            self.db.execute(
                select(Keyword).where(Keyword.is_stub.is_(True)).where(Keyword.id != kw.id)
            ).scalars()
        )
        if not stubs:
            return 0

        pattern = _kw_match_pattern(kw.name) if _has_atom_params(kw.name) else None
        merged = 0
        for stub in stubs:
            absorb = False
            if pattern is not None and pattern.match(stub.name):
                absorb = True
            elif stub.name.lower() == kw.name.lower():
                absorb = True
            if absorb:
                self._reassign_keyword_id(stub.id, kw.id)
                self.db.delete(stub)
                merged += 1
        if merged:
            self.db.flush()
        return merged

    def _reassign_keyword_id(self, old_id: int, new_id: int) -> None:
        """Replace ``old_id`` with ``new_id`` in every Card / Token's
        ``keyword_ids`` JSONB list, preserving order and de-duplicating."""
        for Model in (Card, Token):
            stmt = select(Model).where(Model.keyword_ids.contains([old_id]))
            for row in self.db.execute(stmt).scalars():
                new_ids: list[int] = []
                seen: set[int] = set()
                for kid in row.keyword_ids or []:
                    resolved = new_id if kid == old_id else kid
                    if resolved not in seen:
                        new_ids.append(resolved)
                        seen.add(resolved)
                row.keyword_ids = new_ids  # reassign so SA flushes the change

    def propagate_change(
        self,
        kw_id: int,
        *,
        old_name: str | None,
        new_name: str | None,
        old_reminder: str | None,
        new_reminder: str | None,
    ) -> int:
        """Update card / token rule_text bodies when a keyword is renamed
        or its reminder changes (Phase 1.6 prompt 4 item 4 / Bug 10).

        Best-effort find-and-replace:
          * The old name (case-insensitive, word-boundary) is replaced with
            the new name across rule_text on every Card / Token whose
            ``keyword_ids`` mentions ``kw_id``.
          * If both old and new reminders are non-empty and differ, the
            literal substring ``"(<old reminder>)"`` is replaced with
            ``"(<new reminder>)"`` in the same set of rows.

        Returns the number of rows touched. The substitutions are
        intentionally simple — for edge cases (reminder body that's a
        substring of another, or names that share a stem with a different
        keyword) the user can fix manually via the edit form.
        """
        old_name = (old_name or "").strip()
        new_name = (new_name or "").strip()
        name_changed = bool(old_name and new_name and old_name != new_name)
        reminder_changed = bool(
            old_reminder and new_reminder and old_reminder != new_reminder
        )
        if not name_changed and not reminder_changed:
            return 0
        name_pattern = (
            re.compile(r"\b" + re.escape(old_name) + r"\b", re.IGNORECASE)
            if name_changed
            else None
        )

        affected = 0
        for Model in (Card, Token):
            stmt = select(Model).where(Model.keyword_ids.contains([kw_id]))
            for row in self.db.execute(stmt).scalars():
                text = row.rule_text or ""
                if not text:
                    continue
                new_text = text
                if name_pattern is not None:
                    new_text = name_pattern.sub(new_name, new_text)
                if reminder_changed:
                    new_text = new_text.replace(
                        f"({old_reminder})", f"({new_reminder})"
                    )
                if new_text != text:
                    row.rule_text = new_text
                    affected += 1
        if affected:
            self.db.flush()
        return affected
