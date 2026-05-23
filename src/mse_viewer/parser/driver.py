from __future__ import annotations

from .card_parser import parse_cards
from .header import parse_header
from .keyword_parser import parse_keywords
from .lexer import lex
from .models import ParsedSet
from .tree import build_tree


def parse_set_text(text: str) -> ParsedSet:
    """Full pipeline: raw MSE plaintext → :class:`ParsedSet`.

    Order:
        1. Lex (tabs / colons / continuation lines).
        2. Build tree.
        3. Parse header (set_info + styling defaults).
        4. Parse keywords *before* cards so they exist for cross-reference.
        5. Parse cards (DFC split happens here).
    """
    lines = lex(text)
    root = build_tree(lines)
    header = parse_header(root)
    keywords, rejected_keywords = parse_keywords(root)
    cards = parse_cards(root)
    return ParsedSet(
        header=header,
        keywords=keywords,
        cards=cards,
        rejected_keywords=rejected_keywords,
    )
