from __future__ import annotations

import re

from .models import ParsedKeyword
from .tags import normalize_keyword_match
from .tree import MseNode


_RE_ATOM_PARAM = re.compile(r"<atom-param>([^<]*)</atom-param>", re.IGNORECASE)


def parse_keywords(root: MseNode) -> list[ParsedKeyword]:
    """Collect every top-level ``keyword:`` block."""
    out: list[ParsedKeyword] = []
    for node in root.all("keyword"):
        match_str = node.get("match")
        if not match_str:
            continue
        identity = normalize_keyword_match(match_str)
        params = _extract_param_labels(match_str)
        mode = node.get("mode")
        out.append(
            ParsedKeyword(
                name=identity,
                source_keyword_field=node.get("keyword") or None,
                accepted_parameters=params,
                reminder=node.get("reminder") or None,
                rules=node.get("rules") or None,
                pseudo_keyword=mode.strip().lower() == "pseudo" if mode else False,
            )
        )
    return out


def _extract_param_labels(match: str) -> list[str]:
    return [p.group(1) for p in _RE_ATOM_PARAM.finditer(match)]
