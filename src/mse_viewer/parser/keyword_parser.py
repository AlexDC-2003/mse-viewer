from __future__ import annotations

import re

from .keyword_rejects import is_rejected_match
from .models import ParsedKeyword
from .tags import canonicalize_text, normalize_keyword_match
from .tree import MseNode


_RE_ATOM_PARAM = re.compile(r"<atom-param>([^<]*)</atom-param>", re.IGNORECASE)


def parse_keywords(root: MseNode) -> tuple[list[ParsedKeyword], list[str]]:
    """Collect every top-level ``keyword:`` block.

    Returns ``(accepted, rejected_match_strings)``. Rejected entries are
    those matching the explicit reject-list (see :mod:`keyword_rejects`);
    callers can pass the names through to the action log so the user can
    audit deletions.
    """
    out: list[ParsedKeyword] = []
    rejected: list[str] = []
    for node in root.all("keyword"):
        match_str = node.get("match")
        if not match_str:
            continue
        identity = normalize_keyword_match(match_str)
        if is_rejected_match(identity):
            rejected.append(identity)
            continue
        params = _extract_param_labels(match_str)
        mode = node.get("mode")
        reminder_raw = node.get("reminder") or ""
        rules_raw = node.get("rules") or ""
        out.append(
            ParsedKeyword(
                name=identity,
                source_keyword_field=node.get("keyword") or None,
                accepted_parameters=params,
                reminder=canonicalize_text(reminder_raw) or None,
                rules=canonicalize_text(rules_raw) or None,
                pseudo_keyword=mode.strip().lower() == "pseudo" if mode else False,
            )
        )
    return out, rejected


def _extract_param_labels(match: str) -> list[str]:
    return [p.group(1) for p in _RE_ATOM_PARAM.finditer(match)]
