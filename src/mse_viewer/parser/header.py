from __future__ import annotations

from .models import ParsedSetHeader
from .tree import MseNode


def _strip_magic_prefix(name: str) -> str:
    return name[len("magic-"):] if name.startswith("magic-") else name


def parse_header(root: MseNode) -> ParsedSetHeader:
    """Read the top-level ``set_info`` and ``styling`` blocks."""
    set_info = root.first("set_info")
    set_name: str | None = None
    if set_info is not None:
        set_name = set_info.get("title") or None

    mse_version = root.get("mse_version") or None
    game = root.get("game") or None

    styling_defaults: dict[str, dict[str, str]] = {}
    styling = root.first("styling")
    if styling is not None:
        for child in styling.children:
            stylesheet = _strip_magic_prefix(child.key)
            defaults: dict[str, str] = {}
            # `magic-m15-altered:` block -> children are field/value pairs.
            for sub in child.children:
                # If a key appears multiple times (the spec mentions this happens
                # in the wild for `casting_cost_mana_symbols`), the *last* value
                # wins — that's what MSE itself does.
                defaults[sub.key] = sub.value
            styling_defaults[stylesheet] = defaults

    return ParsedSetHeader(
        set_name=set_name.strip() if set_name else None,
        mse_version=mse_version,
        game=game,
        styling_defaults=styling_defaults,
    )
