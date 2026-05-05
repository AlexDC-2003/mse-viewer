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
    existing_lookup=None,  # callable: (name, route) -> snapshot-dict | None
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
        # If we can resolve the existing row, compute a per-field diff so the
        # modal can render side-by-side. ``modifies_printed`` warns on top of
        # ``identity_conflict`` when the existing row was marked printed —
        # those edits are the dangerous ones.
        snap = existing_lookup(proposed_identity, route) if existing_lookup else None
        if snap is not None:
            new_snap = _face_snapshot(face, colors=[], design_type="(pending)")
            diff = _compute_field_diff(snap, new_snap)
            if snap.get("printed"):
                warnings.add(
                    WarningKind.modifies_printed,
                    f"This will modify printed {route} {proposed_identity!r}.",
                    diff=diff,
                    existing=snap,
                )
            else:
                # Attach diff payload to the identity_conflict warning so the
                # modal can show the comparison even when the existing row
                # isn't marked printed.
                warnings.warnings[-1].payload["diff"] = diff
                warnings.warnings[-1].payload["existing"] = snap

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


def _face_snapshot(face: ParsedCardFace, *, colors, design_type) -> dict:
    """Capture the fields a card-vs-incoming diff cares about. Mirrors the
    column set in ``CardCoreMixin`` plus Card-only ``rarity`` /
    ``starting_loyalty``. Used to feed the diff renderer in the review modal.
    """
    return {
        "card_type": face.super_type or "",
        "card_subtype": face.sub_type,
        "colors": list(colors),
        "casting_cost": face.casting_cost,
        "power": face.power,
        "toughness": face.toughness,
        "flavor_text": face.flavor_text,
        "rule_text": face.rule_text,
        "abilities": face.abilities,
        "design_type": design_type,
        "rarity": face.rarity,
        "alias": face.alias,
        "starting_loyalty": face.starting_loyalty,
        "related_cards": list(face.related_from_notes),
    }


def _compute_field_diff(old: dict, new: dict) -> list[dict]:
    """Per-field diff used in the review modal. Returns an ordered list of
    ``{field, old, new}`` entries for the fields that actually changed.

    deepdiff's structured output is used internally but flattened here for
    template ergonomics — the modal just needs an at-a-glance comparison.
    """
    try:
        from deepdiff import DeepDiff
    except ImportError:  # pragma: no cover - dependency declared in requirements
        DeepDiff = None
    out: list[dict] = []
    keys = sorted(set(old) | set(new))
    keys = [k for k in keys if k != "printed"]  # internal, never shown in diff
    for k in keys:
        ov, nv = old.get(k), new.get(k)
        if ov == nv:
            continue
        out.append({"field": k, "old": ov, "new": nv})
    if DeepDiff is not None and out:
        # Stable, side-effect-free invocation — populates payload metadata
        # other UI surfaces could consume; we don't render it directly here.
        DeepDiff(old, new, ignore_order=False)
    return out


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
