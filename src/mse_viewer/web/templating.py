from __future__ import annotations

import html
import re
from pathlib import Path

from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from mse_viewer.parser.reminder_template import (
    evaluate_inline_templates,
    evaluate_reminder_template,
)
from mse_viewer.parser.tags import render_casting_cost, render_match_for_display


_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


# After HTML-escaping the input, re-enable a small whitelist of tags that the
# parser preserves for display (italics only — Phase 1.6 prompt 4 bug 6).
#
# We deliberately do NOT re-enable ``<b>`` here because canonicalized rule
# text never emits a real ``<b>`` tag, but rule text routinely contains
# stray ``<B>`` substrings (e.g. ``<1B>`` from malformed mana markup) that
# would otherwise be promoted into actual bold-open tags by the regex.
_ALLOWED_TAG = re.compile(r"&lt;(/?)(i|em)&gt;", re.IGNORECASE)


def render_text(value: str | None) -> Markup:
    """Render a stored text value (flavor / keyword reminder / generic prose)
    safely with italics.

    The parser stores ``<i>...</i>`` markers verbatim; everything else is
    escaped.  Newlines are converted to ``<br>`` so multi-line text reads
    naturally without needing ``<pre>`` styling.
    """
    if not value:
        return Markup("")
    escaped = html.escape(value)
    rendered = _ALLOWED_TAG.sub(lambda m: f"<{m.group(1)}{m.group(2).lower()}>", escaped)
    rendered = rendered.replace("\n", "<br>")
    return Markup(rendered)


def render_text_snippet(value: str | None, length: int = 120) -> Markup:
    """Render a *truncated* prose snippet (used for flavor previews etc.).

    Same behaviour as :func:`render_text` but caps to ``length`` characters
    (with an ellipsis appended) and balances any whitelisted tag pair that the
    truncation cut in half — otherwise an unclosed ``<i>`` would leak italics
    into the rest of the page.
    """
    if not value:
        return Markup("")
    cut = len(value) > length
    raw = value[:length] + ("…" if cut else "")
    rendered = str(render_text(raw))
    for tag in ("i",):
        opens = rendered.count(f"<{tag}>")
        closes = rendered.count(f"</{tag}>")
        if opens > closes:
            rendered += f"</{tag}>" * (opens - closes)
    return Markup(rendered)


# rule_text-specific rendering ------------------------------------------------
#
# Rule text uses ``;`` as a line separator (unlike flavor / reminder prose),
# and table-cell snippets benefit from hiding the parenthesised reminder
# clauses so the visible summary is keyword names + non-reminder abilities
# only.  We only apply these transforms to rule_text, not to flavor / reminder
# strings, which is why they live in a separate filter pair.

# A reminder clause looks like ``<i>(...)</i>`` after canonicalization (italic
# variants normalize to ``<i>``) — we also handle the rare un-italicised
# ``(...)`` form. ``[^()]*`` keeps it simple by refusing to span nested parens.
_RE_REMINDER_INLINE_ITALIC = re.compile(r"<i>\s*\([^()]*\)\s*</i>", re.IGNORECASE)
_RE_REMINDER_INLINE_PLAIN = re.compile(r"\([^()]*\)")
_RE_SEMICOLON_SEP = re.compile(r"\s*;\s*")


def _split_rule_lines(value: str) -> str:
    """Treat ``;`` as a line break for display.  Storage is unchanged so the
    canonical form remains round-trippable to MSE."""
    return _RE_SEMICOLON_SEP.sub("\n", value)


def render_rule_text(
    value: str | None,
    keyword_reminders=None,
    card_facts=None,
) -> Markup:
    """Render rule_text for the detail page.

    ``;`` becomes a line break, then italic-preservation as :func:`render_text`.

    ``keyword_reminders`` may be either a callable ``ref → reminder | None`` or
    a plain ``lower(name) → reminder`` dict (legacy).  When provided we also:

    * split lines that are a comma-separated list of *only* known keywords
      (``First strike, reach, splash 2 (...)``) into one line per keyword;
    * for any line whose entire body is a single known keyword (with or
      without an inline ``(...)`` reminder), capitalize the first letter so
      ``reach`` reads as ``Reach``;
    * append ``<i>(reminder)</i>`` to any resulting line that is a single
      bare keyword without an inline parenthesised reminder.

    Comma-splitting respects parens depth so an internal comma inside a
    reminder body (``... (when this deals damage, it deals ...)``) doesn't
    break the line; ability sentences that contain commas are left alone
    because they don't fully resolve to keywords.
    """
    if not value:
        return Markup("")
    text = _split_rule_lines(value)
    # Evaluate inline ``{if … then … else …}`` templates against the
    # invoking card's facts so e.g. ``{if has_pt() then "creature"}`` shows
    # up as ``creature`` on a P/T row. Bare ``{B}`` mana symbols are left
    # alone (no ``{paramN}`` substitution at this layer).
    text = evaluate_inline_templates(text, card_facts=card_facts)
    if keyword_reminders:
        resolver = (
            keyword_reminders if callable(keyword_reminders)
            else (lambda r, _d=keyword_reminders: _d.get((r or "").strip().rstrip(".,").lower()))
        )
        text = _split_keyword_comma_lines(text, resolver)
        text = _process_keyword_lines(text, resolver)
    return render_text(text)


_RE_INLINE_ITALIC = re.compile(r"</?i>", re.IGNORECASE)


_SENTENCE_WORDS = frozenset(
    {
        "this", "that", "these", "those",
        "when", "whenever", "if", "until", "as", "while",
        "you", "your", "yours",
        "it", "its", "they", "their", "theirs",
        "the", "a", "an", "of", "to", "from", "in", "on", "at", "by", "for",
        "with", "into", "onto", "without",
        "each", "all", "any", "no", "every",
        "may", "must", "can", "could", "should", "would", "will",
        "is", "are", "was", "were", "be", "been", "being",
        "and", "or", "but", "than", "then", "also",
        "draw", "gain", "deal", "deals", "dealt", "lose", "loses", "lost",
        "create", "creates", "created", "make", "makes",
        "enter", "enters", "entered", "leave", "leaves",
        "attack", "attacks", "attacking", "block", "blocks", "blocking",
        "cast", "casts", "casting", "play", "plays", "playing",
    }
)

# A keyword "head word" — alpha + optional hyphen / apostrophe. Phase 1.6
# prompt 5 bug 4: the splitter heuristic decides whether a comma-segment
# looks like a keyword (vs. a sentence fragment) on the head shape.
_RE_KW_HEAD_WORD = re.compile(r"^[A-Za-z][A-Za-z'\-]*$")
# A keyword parameter slot — short numeric / single-letter / token.
_RE_KW_HEAD_PARAM = re.compile(r"^(?:[0-9]+|[A-Za-z]|\{[^}]+\})$")


def _is_keyword_shaped(head: str) -> bool:
    """Heuristic: does ``head`` look like a keyword name?

    Accept 1–3-word phrases where every word is alpha (with optional hyphen
    / apostrophe) or a short parameter slot (digits, single letter, brace
    expression). Reject if any word is a common sentence-internal English
    word — those are very likely sentence fragments rather than keywords.
    """
    words = (head or "").split()
    if not words or len(words) > 3:
        return False
    for w in words:
        if w.lower() in _SENTENCE_WORDS:
            return False
    if not _RE_KW_HEAD_WORD.match(words[0]):
        return False
    for w in words[1:]:
        if not (_RE_KW_HEAD_WORD.match(w) or _RE_KW_HEAD_PARAM.match(w)):
            return False
    return True


def _classify_kw_segment(stripped: str, head: str, resolver) -> str:
    """Return ``"strong"`` (resolves or carries an inline reminder),
    ``"shaped"`` (looks like a bare keyword name), or ``"reject"``."""
    if not head:
        return "reject"
    if resolver(head) is not None:
        return "strong"
    # Tolerate trailing sentence punctuation (``).``) on the reminder shape.
    tail_check = stripped.rstrip(".,;:").rstrip()
    if tail_check.endswith(")") and len(head.split()) <= 4:
        return "strong"
    if _is_keyword_shaped(head):
        return "shaped"
    return "reject"


def _split_keyword_comma_lines(text: str, resolver) -> str:
    """For each line: if every top-level comma-segment looks like a keyword
    invocation, split into one segment per line. Otherwise leave the line.

    A segment is treated as a keyword if it ``"strong"``-classifies (resolves
    against the keyword DB OR carries an inline ``(reminder)`` body) or
    ``"shaped"``-classifies (1–3 words, alphabetic, no English sentence
    words — looks like a bare keyword name even when the card never linked
    it via ``keyword_ids``).

    The line is split iff every segment classifies non-``reject`` AND at
    least one segment is ``"strong"``. The "at least one strong" gate is what
    keeps a free-text sentence like ``Apples, oranges, pears`` from being
    over-split into three lines.

    Phase 1.6 prompt 5 bug 4: previous attempts required resolver hits or
    inline reminders on every segment; the user's actual rule_text had
    bare ``Haste, vigilance, reach`` heads that the card hadn't linked,
    so the splitter bailed even though the last segment was clearly a
    keyword with its own reminder.
    """
    out: list[str] = []
    for line in text.split("\n"):
        if "," not in line:
            out.append(line)
            continue
        segments = _tokenize_top_level_commas(line)
        if len(segments) < 2:
            out.append(line)
            continue
        kinds: list[str] = []
        for seg in segments:
            stripped = seg.strip()
            head = _strip_trailing_parens(stripped).strip()
            kinds.append(_classify_kw_segment(stripped, head, resolver))
        if "reject" not in kinds and "strong" in kinds:
            out.extend(s.strip() for s in segments if s.strip())
        else:
            out.append(line)
    return "\n".join(out)


def _tokenize_top_level_commas(s: str) -> list[str]:
    """Split on commas that are *not* inside parentheses."""
    out: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            out.append(s[start:i])
            start = i + 1
    out.append(s[start:])
    return out


def _strip_trailing_parens(s: str) -> str:
    """Drop a trailing balanced parenthesised body so ``Splash 2 (...)``
    becomes ``Splash 2`` for keyword lookup. Tolerates trailing punctuation
    (``).``) — the comma-splitter needs to handle sentences that wrap a
    keyword reminder before a sentence-ending dot."""
    s = s.rstrip().rstrip(".,;:")
    s = s.rstrip()
    if not s.endswith(")"):
        return s
    depth = 0
    for i in range(len(s) - 1, -1, -1):
        if s[i] == ")":
            depth += 1
        elif s[i] == "(":
            depth -= 1
            if depth == 0:
                return s[:i].rstrip()
    return s


def _process_keyword_lines(text: str, resolver) -> str:
    """Per-line transform for known-keyword lines:

    * Capitalize the first letter so ``reach`` reads as ``Reach`` (only the
      first letter — ``First strike`` stays as written, no title-case).
    * Append ``<i>(reminder)</i>`` when the line is a single bare keyword
      (no inline parens).

    Lines that don't resolve to a known keyword are left untouched.  The
    resolver evaluates ``if/then/else`` templates and substitutes captured
    parameters before returning, so ``Toxic 2`` produces
    ``2 poison counters.`` rather than leaking the raw template.
    """
    out: list[str] = []
    for line in text.split("\n"):
        bare = line.strip()
        if not bare:
            out.append(line)
            continue
        head = _strip_trailing_parens(bare).strip()
        if not head:
            out.append(line)
            continue
        reminder = resolver(head)
        if reminder is None:
            out.append(line)
            continue
        rendered = _capitalize_first(line)
        # Append the reminder ONLY when we have a non-empty body and the
        # line doesn't already carry one. An empty-string reminder marks a
        # keyword that's known but has no definition yet (Phase 1.6 prompt 4
        # bug 1) — capitalize the head, but don't render ``<i>()</i>``.
        if reminder and "(" not in bare:
            # Strip pre-existing italic tags from the reminder body to avoid
            # nested ``<i>`` (browsers can render nested italics as upright).
            body = _RE_INLINE_ITALIC.sub("", reminder)
            rendered = f"{rendered} <i>({body})</i>"
        out.append(rendered)
    return "\n".join(out)


def _capitalize_first(s: str) -> str:
    """Uppercase the first ASCII letter and leave everything else alone, so
    ``reach`` becomes ``Reach`` while ``First strike`` is unchanged."""
    if not s:
        return s
    for i, ch in enumerate(s):
        if ch.isalpha():
            if ch.isupper():
                return s
            return s[:i] + ch.upper() + s[i + 1 :]
        if not ch.isspace():
            # First non-whitespace is non-alpha (e.g. a digit) — nothing to do.
            return s
    return s


def render_rule_text_snippet(value: str | None, length: int = 120) -> Markup:
    """Truncated rule_text for table rows.

    Strips parenthesised reminder clauses (``<i>(...)</i>`` and bare ``(...)``)
    before truncating so the snippet shows keywords / non-reminder abilities
    only — keeps the table cell readable on cards with three big reminder
    bodies in a row (e.g. Doom-Bringer's Haste / Omni-strike / Voidsnare).
    """
    if not value:
        return Markup("")
    stripped = _RE_REMINDER_INLINE_ITALIC.sub("", value)
    stripped = _RE_REMINDER_INLINE_PLAIN.sub("", stripped)
    stripped = _split_rule_lines(stripped)
    # Collapse runs of whitespace / blank lines that the strips left behind.
    stripped = re.sub(r"\n[ \t]*\n+", "\n", stripped)
    stripped = re.sub(r"[ \t]+", " ", stripped).strip(" \t\n")
    return render_text_snippet(stripped, length=length)


def render_match(value: str | None) -> Markup:
    """Render a stored keyword ``match:`` for display.

    ``<atom-param>X</atom-param>`` is converted to ``<X>`` (literal angle
    brackets); everything else is HTML-escaped, so the brackets render as
    ``&lt;X&gt;`` → visible ``<X>`` chip-style text.
    """
    if not value:
        return Markup("")
    return Markup(html.escape(render_match_for_display(value)))


def render_cost(value: str | None) -> Markup:
    """Render a casting_cost field with hybrid slots in parens."""
    if not value:
        return Markup("")
    return Markup(html.escape(render_casting_cost(value)))


def render_colors(values: list[str] | None) -> Markup:
    """Render a colors list, falling back to 'colorless' when empty."""
    if not values:
        return Markup("colorless")
    return Markup(html.escape(", ".join(values)))


def render_reminder(value: str | None) -> Markup:
    """Render a stored ``keyword.reminder`` for display.

    Evaluates MSE template expressions before the usual italic-preservation
    pass — so ``{ if n.value=="1" then "counter." else "counters." }`` shows
    as ``counters.`` (the plural fallback) and ``{paramN}`` slots become
    ``<paramN>`` rather than leaking the raw template to the user.
    """
    if not value:
        return Markup("")
    return render_text(evaluate_reminder_template(value))


def get_templates() -> Jinja2Templates:
    t = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    t.env.filters["render_text"] = render_text
    t.env.filters["render_text_snippet"] = render_text_snippet
    t.env.filters["render_rule_text"] = render_rule_text
    t.env.filters["render_rule_text_snippet"] = render_rule_text_snippet
    t.env.filters["render_match"] = render_match
    t.env.filters["render_cost"] = render_cost
    t.env.filters["render_colors"] = render_colors
    t.env.filters["render_reminder"] = render_reminder
    return t


templates = get_templates()
