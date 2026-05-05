"""MSE inline tag normalization.

Most of MSE's text fields contain XML-like tags such as ``<sym-auto>W</sym-auto>``
or ``<word-list-type>Creature</word-list-type>``.  This module exposes pure
helpers that strip the tags or convert them to canonical forms suitable for
storage / display.

Storage policy (Phase 1):
  - mana symbols  → Scryfall braces, one ``{...}`` per atomic slot.
  - keyword wrappers (``<kw-N>``, ``<key>``, ``<atom-param>``, ``<param-*>``) →
    inner text preserved, wrappers stripped.
  - word lists, ``<nospellcheck>``, ``<atom-sep>``, ``<soft>``,
    ``<atom-reminder*>`` → wrappers stripped, inner text kept.
  - italics (``<i>``, ``<i-auto>``, ``<i-flavor>``) → normalized to a single
    ``<i>...</i>`` tag, preserved in the DB and re-rendered in the UI.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Mana symbols
# ---------------------------------------------------------------------------

_RE_SYM = re.compile(r"<sym(?:-auto)?>([^<]*)</sym(?:-auto)?>", re.IGNORECASE)

# Letters MSE uses for mana colors (incl. the brewer/extended palette from
# init_prompt_2 §3.1) plus generic markers (X, Y, Z), tap (T), phyrexian (P).
_MANA_LETTERS = set("WUBRGOKPELN" + "WUBRG" + "XYZTSP")


def _tokenize_mana_string(s: str) -> list[str]:
    """Split a raw MSE mana token string into atomic Scryfall slots.

    Examples:
        ``"RW"`` → ``["R", "W"]``
        ``"2WU"`` → ``["2", "W", "U"]``
        ``"2/W"`` → ``["2/W"]`` (hybrid kept together)
        ``"2/W2/U"`` → ``["2/W", "2/U"]`` (two hybrid slots)
        ``"3"`` → ``["3"]``
        ``"X"`` → ``["X"]``
    """
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        # Read one atomic part: a digit run OR a single letter.
        if ch.isdigit():
            j = i
            while j < n and s[j].isdigit():
                j += 1
            part = s[i:j]
            i = j
        elif ch.isalpha():
            part = ch.upper()
            i += 1
        else:
            # Skip punctuation we don't recognize.
            i += 1
            continue
        # Check for hybrid extensions (slash-separated).
        parts = [part]
        while i < n and s[i] == "/":
            i += 1
            if i >= n:
                break
            if s[i].isdigit():
                j = i
                while j < n and s[j].isdigit():
                    j += 1
                parts.append(s[i:j])
                i = j
            elif s[i].isalpha():
                parts.append(s[i].upper())
                i += 1
            else:
                break
        out.append("/".join(parts))
    return out


def normalize_mana_symbols(text: str) -> str:
    """Replace ``<sym>X</sym>`` / ``<sym-auto>X</sym-auto>`` with ``{X}{Y}...``.

    Each atomic mana slot becomes its own ``{...}`` (init_prompt_3 #12).
    """
    def _repl(m: re.Match[str]) -> str:
        tokens = _tokenize_mana_string(m.group(1))
        return "".join(f"{{{t}}}" for t in tokens) if tokens else ""
    return _RE_SYM.sub(_repl, text)


# ---------------------------------------------------------------------------
# Word-list tags  →  strip wrapper, keep inner.
# ---------------------------------------------------------------------------

_RE_WORD_LIST = re.compile(r"</?word-list-[^>]*>", re.IGNORECASE)


def strip_word_lists(text: str) -> str:
    return _RE_WORD_LIST.sub("", text)


# ---------------------------------------------------------------------------
# Italic tags  →  normalize all variants to <i>...</i>.
# ---------------------------------------------------------------------------

_RE_ITALIC_OPEN = re.compile(r"<(i-flavor|i-auto|i)>", re.IGNORECASE)
_RE_ITALIC_CLOSE = re.compile(r"</(i-flavor|i-auto|i)>", re.IGNORECASE)


def normalize_italics(text: str) -> str:
    text = _RE_ITALIC_OPEN.sub("<i>", text)
    text = _RE_ITALIC_CLOSE.sub("</i>", text)
    # Drop empty `<i></i>` pairs (MSE often emits them for missing flavor).
    return re.sub(r"<i>\s*</i>", "", text)


# ---------------------------------------------------------------------------
# "Wrapper" tags whose content we keep verbatim.
#
#   <nospellcheck>   <atom-sep>   <atom-reminder>   <atom-reminder-custom>
#   <soft>           <b>          <key>             <atom-param>
#   <param-name>     <param-cost> <param-number>    <param-text>
#
# Note: <kw-N>...</kw-N> is handled separately because we extract the keyword
# reference before discarding the wrapper.
# ---------------------------------------------------------------------------

# Plain-name wrappers we discard (keep inner text).
_WRAPPER_TAGS_FIXED = (
    "nospellcheck", "soft", "soft-line", "b",
    "key", "atom-param", "param-name", "param-cost", "param-number", "param-text",
)
_RE_WRAPPER_FIXED = re.compile(
    r"</?(?:" + "|".join(_WRAPPER_TAGS_FIXED) + r")(?:\s[^>]*)?>",
    re.IGNORECASE,
)
# Wildcard families:
#   <atom-sep>, <atom-sep-XYZ>
#   <atom-reminder>, <atom-reminder-core>, <atom-reminder-expert>, <atom-reminder-custom>
#   <param-*s>, <param-*es>, <param-something-else> (plurality/inflection markers)
_RE_ATOM_SEP_FAMILY = re.compile(r"</?atom-sep(?:-[^>\s]+)?(?:\s[^>]*)?>", re.IGNORECASE)
_RE_ATOM_REMINDER_FAMILY = re.compile(r"</?atom-reminder(?:-[^>\s]+)?(?:\s[^>]*)?>", re.IGNORECASE)
_RE_PARAM_FAMILY = re.compile(r"</?param-[^>\s]+(?:\s[^>]*)?>", re.IGNORECASE)
# Anything else that survived (and isn't an italic / bold we explicitly preserve).
_RE_STRAY_SYM = re.compile(r"</?sym(?:-[^>\s]+)?(?:\s[^>]*)?>", re.IGNORECASE)
# Stray, unpaired <kw-N> / </kw-N> tags that didn't match _RE_KW_BLOCK because
# the file had a malformed pair (e.g. ``M<kw-1>ulti-strike 3 (...)`` from the
# user's report).  Run as a final cleanup so we never leak ``<kw-…>`` to users.
_RE_STRAY_KW = re.compile(r"</?kw-[a-zA-Z0-9]+(?:\s[^>]*)?>", re.IGNORECASE)


def strip_wrapper_tags(text: str) -> str:
    text = _RE_WRAPPER_FIXED.sub("", text)
    text = _RE_ATOM_SEP_FAMILY.sub("", text)
    text = _RE_ATOM_REMINDER_FAMILY.sub("", text)
    text = _RE_PARAM_FAMILY.sub("", text)
    return text


# ---------------------------------------------------------------------------
# Keyword extraction.
#
# kw IDs in the wild include digits AND letters (e.g. ``<kw-A>``, ``<kw-a>``,
# ``<kw-0>``).  The backreference + IGNORECASE flag handles ``<kw-A>...</kw-a>``
# correctly.
# ---------------------------------------------------------------------------

_RE_KW_BLOCK = re.compile(
    r"<kw-([a-zA-Z0-9]+)>(.*?)</kw-\1>",
    re.IGNORECASE | re.DOTALL,
)
_RE_KEY = re.compile(r"<key>(.*?)</key>", re.IGNORECASE | re.DOTALL)
_RE_ATOM_PARAM = re.compile(r"<atom-param>([^<]*)</atom-param>", re.IGNORECASE)


_RE_REMINDER = re.compile(
    r"<atom-reminder(?:-[^>\s]+)?(?:\s[^>]*)?>(.*?)</atom-reminder(?:-[^>\s]+)?>",
    re.IGNORECASE | re.DOTALL,
)


# Bare ``<key>X</key>`` references whose body is one of these verb forms are
# *not* real keyword invocations — MSE wraps them in ``<kw-N>`` for spell-check
# styling, but the surrounding sentence treats them as plain English (e.g.
# ``When you <key>evolve</key> Foo into Bar, …``).  We only suppress when there
# is no ``<atom-param>`` and no ``<atom-reminder…>`` — those signal a real
# parameterised invocation that we must keep.
_VERB_FORM_BLOCKLIST = frozenset({"evolve", "evolves", "evolved", "evolving"})


def iter_keyword_invocations(text: str) -> list[tuple[str, list[str], str | None]]:
    """Return every keyword invocation as ``(key_text, [param_values], reminder_text|None)``.

    Captures both ``<kw-N>...<key>X</key>...</kw-N>`` blocks AND standalone
    ``<key>X</key>`` references.  Reminder text is recognised in two positions
    (real MSE files use both):

      1. **Inside the ``<kw-N>`` body**, e.g.
         ``<kw-A><nospellcheck><key>Amphibious</key></nospellcheck><atom-reminder-custom>(...)</atom-reminder-custom></kw-A>``
      2. **Immediately after the ``<kw-N>`` close** (or after a standalone ``<key>``),
         allowing leading whitespace.

    The first match wins; the body is cleaned (italic / wrapper / mana
    normalization) and returned so callers can attach it to a stub.
    """
    out: list[tuple[str, list[str], str | None]] = []
    seen_spans: list[tuple[int, int]] = []

    for m in _RE_KW_BLOCK.finditer(text):
        body = m.group(2)
        key_match = _RE_KEY.search(body)
        if not key_match:
            continue
        params = [p.group(1) for p in _RE_ATOM_PARAM.finditer(body)]
        reminder = _capture_reminder_inside(body) or _capture_reminder_after(text, m.end())
        key_text = _clean_key_text(key_match.group(1))
        if _is_verb_form_noise(key_text, params, reminder):
            seen_spans.append(m.span())  # still suppress the standalone-loop dup
            continue
        out.append((key_text, params, reminder))
        seen_spans.append(m.span())

    for m in _RE_KEY.finditer(text):
        if any(s <= m.start() < e for s, e in seen_spans):
            continue
        reminder = _capture_reminder_after(text, m.end())
        key_text = _clean_key_text(m.group(1))
        if _is_verb_form_noise(key_text, [], reminder):
            continue
        out.append((key_text, [], reminder))

    return out


def _is_verb_form_noise(key_text: str, params: list[str], reminder: str | None) -> bool:
    """True when a ``<key>X</key>`` reference is a sentence-internal verb, not
    a real keyword invocation. Triggers only on a bare reference (no params,
    no reminder) whose key text is in :data:`_VERB_FORM_BLOCKLIST`.
    """
    if params or reminder:
        return False
    return key_text.strip().lower() in _VERB_FORM_BLOCKLIST


def _capture_reminder_inside(body: str) -> str | None:
    """Find an ``<atom-reminder…>`` element anywhere inside a ``<kw-N>`` body."""
    m = _RE_REMINDER.search(body)
    return _clean_reminder(m.group(1)) if m else None


def _capture_reminder_after(text: str, idx: int) -> str | None:
    """If the substring starting at ``idx`` (after optional whitespace) is an
    ``<atom-reminder…>`` block, return its cleaned visible text."""
    j = idx
    while j < len(text) and text[j].isspace():
        j += 1
    m = _RE_REMINDER.match(text, j)
    return _clean_reminder(m.group(1)) if m else None


def _clean_reminder(inner: str) -> str | None:
    inner = strip_word_lists(inner)
    inner = strip_wrapper_tags(inner)
    inner = normalize_mana_symbols(inner)
    inner = _RE_STRAY_SYM.sub("", inner)
    inner = _RE_STRAY_KW.sub("", inner)
    inner = re.sub(r"</?(?:i|i-auto|i-flavor|b)>", "", inner)
    cleaned = _collapse_inline_whitespace(inner).strip()
    # MSE wraps reminders in parens for rendering — the parens belong to the
    # display layer, so peel them off before storing. Only strip when both
    # ends are present so we don't mangle text that happens to start or end
    # with a single bracket for other reasons.
    if cleaned.startswith("(") and cleaned.endswith(")") and len(cleaned) >= 2:
        cleaned = cleaned[1:-1].strip()
    return cleaned or None


def _clean_key_text(s: str) -> str:
    """The ``<key>`` body sometimes contains ``<param-*>`` children — discard
    those for the *reference name* (it's just the keyword name)."""
    s = re.sub(r"<[^>]+>", "", s)
    return s.strip()


def strip_keyword_wrappers(text: str) -> str:
    """Replace ``<kw-N>...</kw-N>`` with the body's visible text."""
    return _RE_KW_BLOCK.sub(lambda m: m.group(2), text)


# ---------------------------------------------------------------------------
# All-in-one canonicalization for stored ``rule_text`` / ``flavor_text``.
# ---------------------------------------------------------------------------


def canonicalize_text(text: str) -> str:
    """Apply the full normalization stack.  Order matters:

      1. Extract keyword invocations *before* we discard the wrappers (callers
         that need the refs use :func:`iter_keyword_invocations`).
      2. Strip ``<kw-N>`` wrappers (keep body).
      3. Strip word-list / wrapper tags (``<key>``, ``<atom-param>``, ``<param-*>``,
         ``<nospellcheck>``, ``<soft>``, ``<atom-sep…>``, ``<atom-reminder…>`` …).
      4. Convert ``<sym...>`` → ``{X}`` per slot, then drop any malformed
         leftovers (e.g. swapped ``</sym>1<sym>``).
      5. Normalize italic variants to ``<i>``.
      6. Collapse runs of whitespace introduced by tag removal.
    """
    text = strip_keyword_wrappers(text)
    text = strip_word_lists(text)
    text = strip_wrapper_tags(text)
    text = normalize_mana_symbols(text)
    text = _RE_STRAY_SYM.sub("", text)
    text = _RE_STRAY_KW.sub("", text)
    text = normalize_italics(text)
    text = _collapse_inline_whitespace(text)
    return text


def canonicalize_flavor(text: str) -> str:
    """Aggressive cleaning for ``flavor_text`` — strip *all* tags (including
    italic variants).  Per init_prompt_4 #11, flavor doesn't need any markup
    survival in Phase 1.
    """
    text = re.sub(r"<[^>]+>", "", text or "")
    text = _collapse_inline_whitespace(text).strip()
    return text


def strip_all_tags(text: str) -> str:
    """Aggressive stripper for fields that are pure plaintext (sub_type, etc.).

    Removes *every* ``<…>`` tag and trims trailing whitespace runs.
    """
    text = re.sub(r"<[^>]+>", "", text)
    return _collapse_inline_whitespace(text).strip()


_RE_MULTI_SPACE = re.compile(r"[ \t]+")
_RE_TRAILING_WS = re.compile(r"[ \t]+(?=\n|$)")


def _collapse_inline_whitespace(text: str) -> str:
    text = _RE_MULTI_SPACE.sub(" ", text)
    text = _RE_TRAILING_WS.sub("", text)
    return text


def normalize_keyword_match(match: str) -> str:
    """Normalize a keyword's ``match:`` for storage (strict B identity).

    We trim and collapse internal whitespace but *keep* ``<atom-param>label</atom-param>``
    verbatim — labels are part of the identity per init_prompt_4 #2.
    """
    return re.sub(r"\s+", " ", match.strip())


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def render_casting_cost(value: str | None) -> str:
    """Render a raw MSE casting_cost field for human reading.

    Each atomic mana slot is emitted in turn; hybrid slots (containing ``/``)
    are wrapped in parentheses so ``G/UG/U`` displays as ``(G/U)(G/U)``
    (init_prompt_4 #5).  Non-hybrid slots are emitted as-is, so plain costs
    like ``2WU`` stay readable as ``2WU``.
    """
    if not value:
        return ""
    tokens = _tokenize_mana_string(value)
    return "".join(f"({t})" if "/" in t else t for t in tokens)


_RE_ATOM_PARAM_DISPLAY = re.compile(r"<atom-param>([^<]*)</atom-param>", re.IGNORECASE)


def render_match_for_display(match: str | None) -> str:
    """Convert a stored keyword ``match:`` for human display.

    Per init_prompt_4 #10/#94 the ``<atom-param>X</atom-param>`` wrapper is
    replaced with ``<X>`` (literal angle brackets).  The result is plain text
    that the template will HTML-escape — escaping turns ``<`` into ``&lt;``
    so the brackets render visually.
    """
    if not match:
        return ""
    return _RE_ATOM_PARAM_DISPLAY.sub(lambda m: f"<{m.group(1)}>", match)
