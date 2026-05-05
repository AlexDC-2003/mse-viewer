from __future__ import annotations

import html
import re
from pathlib import Path

from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from mse_viewer.parser.reminder_template import evaluate_reminder_template
from mse_viewer.parser.tags import render_casting_cost, render_match_for_display


_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


# After HTML-escaping the input, re-enable a small whitelist of tags that the
# parser preserves for display (italic + bold).  Everything else stays escaped.
_ALLOWED_TAG = re.compile(r"&lt;(/?)(i|em|b)&gt;", re.IGNORECASE)


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
    for tag in ("i", "b"):
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
    if keyword_reminders:
        resolver = (
            keyword_reminders if callable(keyword_reminders)
            else (lambda r, _d=keyword_reminders: _d.get((r or "").strip().rstrip(".,").lower()))
        )
        text = _split_keyword_comma_lines(text, resolver)
        text = _process_keyword_lines(text, resolver)
    return render_text(text)


_RE_INLINE_ITALIC = re.compile(r"</?i>", re.IGNORECASE)


def _split_keyword_comma_lines(text: str, resolver) -> str:
    """For each line: if every top-level comma-segment resolves to a known
    keyword (allowing a trailing parenthesised reminder body on at most one
    of them), split into one segment per line.  Otherwise leave the line.
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
        all_keywords = True
        for seg in segments:
            head = _strip_trailing_parens(seg).strip()
            if not head or resolver(head) is None:
                all_keywords = False
                break
        if all_keywords:
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
    becomes ``Splash 2`` for keyword lookup."""
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
        if "(" not in bare:
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
