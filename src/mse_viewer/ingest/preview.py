"""Per-card preview model: pure derivations applied, no DB writes yet."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from mse_viewer.parser.card_parser import detect_frame, is_evolution_planeswalker
from mse_viewer.parser.models import ParsedCardFace, ParsedSetHeader

from .derivations import (
    DesignTypeResult,
    derive_colors,
    derive_design_type,
    is_token_route,
)
from .derivations.identity import compute_identity
from .warnings import WarningCollector, WarningKind


Route = Literal["card", "token"]


@dataclass
class FacePreview:
    """A single face after derivations, ready for review."""
    face: ParsedCardFace
    proposed_identity: str
    route: Route
    colors: list[str]
    design_type: DesignTypeResult
    warnings: WarningCollector = field(default_factory=WarningCollector)

    # Field-level user overrides (filled in by the review modal).
    overrides: dict[str, object] = field(default_factory=dict)
    rejected: bool = False
    accept_as_alternate_label: str | None = None
    collision_resolution: str | None = None  # "update" | "alternate" | "rename" | "cancel"
    route_override: Route | None = None       # Cards/Tokens picker (rarity: special)


def build_preview(
    face: ParsedCardFace,
    *,
    header: ParsedSetHeader,
    existing_card_identities: set[str],
    existing_token_identities: set[str],
    playbook_lookup=None,
) -> FacePreview:
    warnings = WarningCollector()

    # Frame detection — drives several Phase 1.6 short-circuits (silenced
    # rarity_special on Emblems, alias-driven review on Planeswalkers, etc.).
    frame = detect_frame(face.super_type or "", face.sub_type)

    # Routing first — token namespace is independent of cards. Token routing is
    # automatic (super_type contains Token) and does NOT require user
    # confirmation, so it doesn't generate a warning by itself.
    super_type_has_token = is_token_route(face)
    route: Route = "token" if super_type_has_token else "card"

    # Rarity 'special' only needs a DB choice when the super_type didn't
    # already nail routing down for us; otherwise the Token routing wins
    # silently and we just need the design_type from the modal (handled below).
    rarity = (face.rarity or "").strip().lower()
    if rarity == "special" and not super_type_has_token:
        warnings.add(
            WarningKind.rarity_special,
            "Rarity is 'special' — choose Cards or Tokens DB.",
        )

    # Frame / stylesheet typing check. We trust the type line over the
    # stylesheet, but mismatched pairs are worth a heads-up — they usually
    # mean the supertype line is wrong, the stylesheet is wrong, or the user
    # is doing something the parser hasn't seen before.
    _check_frame_type_mismatch(face, frame, warnings)

    proposed_identity = compute_identity(
        display_name=face.name,
        super_type=face.super_type or "",
    )

    # Identity collision detection (per-DB).
    pool = existing_token_identities if route == "token" else existing_card_identities
    if proposed_identity in pool:
        warnings.add(
            WarningKind.identity_conflict,
            f"A {route} named {proposed_identity!r} already exists.",
            existing_identity=proposed_identity,
        )

    # Color derivation (pure).
    colors = derive_colors(face)

    # Design type — may produce a "needs_user" result, surfaced as a warning.
    dt = derive_design_type(face, header, playbook_lookup=playbook_lookup)
    if dt.needs_user:
        warnings.add(
            WarningKind.design_type_unrecognized,
            f"Design type unrecognized ({dt.reason}).",
            stylesheet=face.stylesheet or "",
            styling_data=dict(face.styling_data),
        )

    # Planeswalker alias rule: a non-Evolution Planeswalker with a non-empty
    # alias may want a non-Normal design type — surface a modal so the user
    # can pick. Evolution Planeswalkers always have an alias, so the alias
    # signal carries no meaning there.
    if (
        frame == "planeswalker"
        and (face.alias or "").strip()
        and not is_evolution_planeswalker(face.super_type or "")
    ):
        warnings.add(
            WarningKind.planeswalker_alias,
            "Planeswalker has an alias — confirm design type.",
            alias=face.alias or "",
        )

    return FacePreview(
        face=face,
        proposed_identity=proposed_identity,
        route=route,
        colors=colors,
        design_type=dt,
        warnings=warnings,
    )


def _check_frame_type_mismatch(
    face: ParsedCardFace, frame: str, warnings: WarningCollector
) -> None:
    """Raise the ``frame_type_mismatch`` warning when the stylesheet implies
    one frame and the type line implies another. Per Phase 1.6 user direction:

    * ``m15-emblem-name-cut`` should always be an Emblem.
    * ``m15-saga`` should always be a Saga (Enchantment subtype).
    * ``future-planeswalker-horizontal`` should always be a Leyline (per the
      user's prompt — that stylesheet's typical use is Leyline framing).
    """
    stylesheet = (face.stylesheet or "").strip().lower()
    if not stylesheet:
        return
    expected: dict[str, str] = {
        "m15-emblem-name-cut": "emblem",
        "m15-saga": "saga",
        "future-planeswalker-horizontal": "leyline",
    }
    want = expected.get(stylesheet)
    if want and frame != want:
        warnings.add(
            WarningKind.frame_type_mismatch,
            f"Stylesheet {stylesheet!r} expects a {want} but type line is {frame!r}.",
            stylesheet=stylesheet,
            expected_frame=want,
            actual_frame=frame,
        )
