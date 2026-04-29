"""Per-card preview model: pure derivations applied, no DB writes yet."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

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


def build_preview(
    face: ParsedCardFace,
    *,
    header: ParsedSetHeader,
    existing_card_identities: set[str],
    existing_token_identities: set[str],
    playbook_lookup=None,
) -> FacePreview:
    warnings = WarningCollector()

    # Routing first — token namespace is independent of cards.
    super_type_has_token = is_token_route(face)

    # Rarity: special is asked-about (warning), but defaults to Cards DB.
    rarity = (face.rarity or "").strip().lower()
    if rarity == "special":
        warnings.add(
            WarningKind.rarity_special,
            "Rarity is 'special' — choose Cards or Tokens DB and a Design Type.",
        )

    if super_type_has_token:
        warnings.add(
            WarningKind.token_routing,
            "super_type contains 'Token' — confirm token routing & related cards.",
        )

    route: Route = "token" if super_type_has_token else "card"

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

    # Notes-driven short-circuit.
    if face.notes.do_not_read:
        warnings.add(
            WarningKind.do_not_read,
            "'Do Not Read' marker — card will be skipped and logged.",
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

    return FacePreview(
        face=face,
        proposed_identity=proposed_identity,
        route=route,
        colors=colors,
        design_type=dt,
        warnings=warnings,
    )
