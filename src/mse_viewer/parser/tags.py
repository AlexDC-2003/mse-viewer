"""MSE inline tag normalization.

Most of MSE's text fields contain XML-like tags such as ``<sym-auto>W</sym-auto>``
or ``<word-list-type>Creature</word-list-type>``.  This module exposes pure
helpers that strip the tags or convert them to canonical forms suitable for
storage / display.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Mana symbols
# ---------------------------------------------------------------------------

# Capture <sym>X</sym> and <sym-auto>X</sym-auto>.
_RE_SYM = re.compile(r"<sym(?:-auto)?>([^<]*)</sym(?:-auto)?>", re.IGNORECASE)

_HYBRID_DELIMS = re.compile(r"[/]")


def _to_scryfall_token(token: str) -> str:
    """Convert a single mana token (e.g. ``W``, ``2/W``, ``X``) to Scryfall form ``{W}``."""
    token = token.strip()
    if not token:
        return ""
    if "/" in token:
        # hybrid like "2/W" or "G/U"
        parts = [p.strip() for p in _HYBRID_DELIMS.split(token) if p.strip()]
        return "{" + "/".join(parts) + "}"
    return "{" + token + "}"


def normalize_mana_symbols(text: str) -> str:
    """Replace ``<sym>X</sym>`` / ``<sym-auto>X</sym-auto>`` with ``{X}``."""
    return _RE_SYM.sub(lambda m: _to_scryfall_token(m.group(1)), text)


# ---------------------------------------------------------------------------
# Word-list tags
# ---------------------------------------------------------------------------

_RE_WORD_LIST = re.compile(r"<word-list-[^>]+>|</word-list-[^>]+>", re.IGNORECASE)


def strip_word_lists(text: str) -> str:
    return _RE_WORD_LIST.sub("", text)


# ---------------------------------------------------------------------------
# Italics / soft / nospellcheck — strip the wrappers, keep inner text.
# ---------------------------------------------------------------------------

_RE_GENERIC_TAG = re.compile(
    r"</?(?:i-flavor|i-auto|i|b|nospellcheck|soft|atom-sep|atom-reminder|atom-reminder-custom)>",
    re.IGNORECASE,
)


def strip_simple_tags(text: str) -> str:
    return _RE_GENERIC_TAG.sub("", text)


# ---------------------------------------------------------------------------
# Keyword extraction.
# ---------------------------------------------------------------------------

# Capture everything inside <kw-N>...</kw-N>.  N is one or more digits.
_RE_KW_BLOCK = re.compile(r"<kw-(\d+)>(.*?)</kw-\1>", re.IGNORECASE | re.DOTALL)
# Inside a kw block: <key>NAME</key>
_RE_KEY = re.compile(r"<key>([^<]+)</key>", re.IGNORECASE)
# Inside a kw block: <atom-param>VALUE</atom-param>
_RE_ATOM_PARAM = re.compile(r"<atom-param>([^<]*)</atom-param>", re.IGNORECASE)


def iter_keyword_invocations(text: str) -> list[tuple[str, list[str]]]:
    """Return every ``<kw-N>...`` invocation as ``(key_text, [param_values])``.

    ``key_text`` is the literal text inside the embedded ``<key>...</key>`` tag,
    which is the keyword's display name (e.g. ``Suspend``).  This is what we use
    to look up keyword records when the card's reference is by name.
    """
    out: list[tuple[str, list[str]]] = []
    for m in _RE_KW_BLOCK.finditer(text):
        body = m.group(2)
        key_match = _RE_KEY.search(body)
        if not key_match:
            continue
        params = [p.group(1) for p in _RE_ATOM_PARAM.finditer(body)]
        out.append((key_match.group(1).strip(), params))
    return out


def strip_keyword_wrappers(text: str) -> str:
    """Remove the ``<kw-N>`` / ``</kw-N>`` and ``<key>...</key>`` wrappers, leaving the
    visible text intact.  Atom-params are kept literally."""
    text = _RE_KW_BLOCK.sub(lambda m: _kw_visible(m.group(2)), text)
    return text


def _kw_visible(body: str) -> str:
    body = _RE_KEY.sub(lambda m: m.group(1), body)
    body = _RE_ATOM_PARAM.sub(lambda m: m.group(1), body)
    return body


# ---------------------------------------------------------------------------
# All-in-one canonicalization for rule_text storage.
# ---------------------------------------------------------------------------


def canonicalize_text(text: str) -> str:
    """Apply the full normalization stack appropriate for stored ``rule_text``.

    Order matters: extract keyword invocations *before* you strip the wrappers,
    otherwise the structure is gone.  This function does **not** drop keyword
    parameters from the rendered text — use :func:`iter_keyword_invocations` if
    you need the parameter list separately.
    """
    text = normalize_mana_symbols(text)
    text = strip_word_lists(text)
    text = strip_keyword_wrappers(text)
    text = strip_simple_tags(text)
    return text


def normalize_keyword_match(match: str) -> str:
    """Normalize a keyword's ``match:`` string for identity (strict / option B).

    Per init_prompt_4 we use the literal match string verbatim — no atom-param
    label collapsing.  We still trim whitespace and collapse internal spaces so
    minor formatting differences don't create duplicates.
    """
    return re.sub(r"\s+", " ", match.strip())
