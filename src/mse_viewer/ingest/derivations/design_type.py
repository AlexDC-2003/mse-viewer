"""design_type derivation, per the rule table in init_prompt_2 §3.2."""
from __future__ import annotations

from dataclasses import dataclass

from mse_viewer.parser.models import ParsedCardFace, ParsedSetHeader


@dataclass
class DesignTypeResult:
    value: str | None  # None means "ask the user"
    needs_user: bool
    reason: str = ""


def derive_design_type(
    face: ParsedCardFace,
    header: ParsedSetHeader,
    *,
    playbook_lookup=None,  # callable: (stylesheet, styling_data_key) -> str | None
) -> DesignTypeResult:
    """Apply the rule table, layering set-header styling defaults first."""
    stylesheet = (face.stylesheet or "").strip()
    styling_data = dict(face.styling_data)

    # Apply set-header styling defaults: a card with no styling_data inherits the
    # header's styling_data for its stylesheet.
    if stylesheet and not styling_data:
        styling_data = dict(header.styling_defaults.get(stylesheet, {}))

    super_type = (face.super_type or "").lower()
    frames = _frames_without_snow(styling_data.get("frames"))

    # ---- m15-altered ----
    if stylesheet == "m15-altered":
        if frames == "fnm promo":
            return DesignTypeResult("Colorpushed", False)
        if frames == "":
            return DesignTypeResult("Normal", False)
        return _ask(face, stylesheet, styling_data, playbook_lookup, "altered styling combination not in rule table")

    if stylesheet in ("m15-mainframe-planeswalker", "m15-mainframe-tokens"):
        return DesignTypeResult("Normal", False)

    if stylesheet == "m15-altered-beyond":
        # init_prompt_3 → phase1_prompt_2 ruling: Evolution/Hero are not an
        # exception; both default to "Normal" (no prompt).
        if "evolution" in super_type or "hero" in super_type:
            return DesignTypeResult("Normal", False)
        return DesignTypeResult("Unique", False)

    if stylesheet == "m15-extra-udelude":
        return DesignTypeResult("Additional Color", False)

    if stylesheet == "m15-extra-udelude-beyond":
        return DesignTypeResult("Additional Color - Unique", False)

    if not stylesheet:
        return DesignTypeResult("Normal", False)

    return _ask(face, stylesheet, styling_data, playbook_lookup, "stylesheet not in rule table")


def _frames_without_snow(value: str | None) -> str:
    """Return the ``frames`` field with ``snow`` filtered out, comma-separated.

    Per init_prompt_3 #5: ``snow`` is treated as cosmetic for *every* stylesheet
    and never participates in design-type derivation.  Empty string means "no
    meaningful frames".
    """
    if not value:
        return ""
    parts = [p.strip().lower() for p in value.split(",")]
    parts = [p for p in parts if p and p != "snow"]
    return ", ".join(parts)


def _ask(
    face: ParsedCardFace,
    stylesheet: str,
    styling_data: dict[str, str],
    playbook_lookup,
    reason: str,
) -> DesignTypeResult:
    if playbook_lookup is not None:
        key = playbook_key(stylesheet, styling_data)
        remembered = playbook_lookup(key)
        if remembered:
            return DesignTypeResult(remembered, False, reason=f"playbook:{reason}")
    return DesignTypeResult(None, True, reason=reason)


def playbook_key(stylesheet: str, styling_data: dict[str, str]) -> str:
    """Stable key for the warning playbook keyed by (stylesheet, styling_data)."""
    items = sorted((k, v) for k, v in styling_data.items())
    encoded = ";".join(f"{k}={v}" for k, v in items)
    return f"{stylesheet}|{encoded}"
