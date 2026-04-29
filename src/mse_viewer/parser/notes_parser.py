from __future__ import annotations

import re

from .models import ParsedNotes


_RE_PWL = re.compile(r"^\s*PWL\s*:\s*(\d+)\s*$", re.IGNORECASE)
_RE_RELATED = re.compile(r"^\s*Related(?:\s+Cards)?\s*:\s*(.+)$", re.IGNORECASE)
_RE_STATUS_PRINTED = re.compile(r"^\s*Status\s*:\s*Printed\s*$", re.IGNORECASE)
_RE_DO_NOT_READ = re.compile(r"^\s*Do\s+Not\s+Read\s*$", re.IGNORECASE)


def parse_notes(raw: str | None) -> ParsedNotes:
    """Pull structured fields out of an MSE ``notes:`` block.

    Recognised line prefixes (case-insensitive):
        - ``PWL: <int>`` — overrides set-default power level for this card
        - ``Related: a, b, c`` (or ``Related Cards: ...``) — comma-separated names
        - ``Status: Printed`` — sets the ``printed`` flag
        - ``Do Not Read`` — short-circuit: skip this card during ingest

    Whatever lines are left form ``remainder``.
    """
    if not raw:
        return ParsedNotes()

    pwl: int | None = None
    related: list[str] = []
    status_printed = False
    do_not_read = False
    remainder_lines: list[str] = []

    for line in raw.splitlines():
        if (m := _RE_PWL.match(line)):
            pwl = int(m.group(1))
            continue
        if (m := _RE_RELATED.match(line)):
            related.extend(_split_related(m.group(1)))
            continue
        if _RE_STATUS_PRINTED.match(line):
            status_printed = True
            continue
        if _RE_DO_NOT_READ.match(line):
            do_not_read = True
            continue
        remainder_lines.append(line)

    return ParsedNotes(
        pwl=pwl,
        related=related,
        status_printed=status_printed,
        do_not_read=do_not_read,
        remainder="\n".join(remainder_lines).strip("\n"),
    )


def _split_related(value: str) -> list[str]:
    return [s.strip() for s in value.split(",") if s.strip()]
