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
    """Render a stored text value (rule_text / flavor_text) safely with italics.

    The parser stores ``<i>...</i>`` markers verbatim; everything else is
    escaped.  Newlines are converted to ``<br>`` so multi-line rule text reads
    naturally without needing ``<pre>`` styling.
    """
    if not value:
        return Markup("")
    escaped = html.escape(value)
    rendered = _ALLOWED_TAG.sub(lambda m: f"<{m.group(1)}{m.group(2).lower()}>", escaped)
    rendered = rendered.replace("\n", "<br>")
    return Markup(rendered)


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
    t.env.filters["render_match"] = render_match
    t.env.filters["render_cost"] = render_cost
    t.env.filters["render_colors"] = render_colors
    return t


templates = get_templates()
