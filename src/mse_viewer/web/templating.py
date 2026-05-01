from __future__ import annotations

import html
import re
from pathlib import Path

from fastapi.templating import Jinja2Templates
from markupsafe import Markup

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


def render_rule_text(value: str | None) -> Markup:
    """Render rule_text for the detail page: ``;`` becomes a line break, then
    the same italic-preservation as :func:`render_text`."""
    if not value:
        return Markup("")
    return render_text(_split_rule_lines(value))


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


def get_templates() -> Jinja2Templates:
    t = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    t.env.filters["render_text"] = render_text
    t.env.filters["render_text_snippet"] = render_text_snippet
    t.env.filters["render_rule_text"] = render_rule_text
    t.env.filters["render_rule_text_snippet"] = render_rule_text_snippet
    t.env.filters["render_match"] = render_match
    t.env.filters["render_cost"] = render_cost
    t.env.filters["render_colors"] = render_colors
    return t


templates = get_templates()
