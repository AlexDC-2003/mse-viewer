"""Per-card commit step: take a FacePreview (post-modal) and write it to the DB."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from mse_viewer.parser.models import ParsedCardFace, ParsedKeyword
from mse_viewer.repository import (
    CardRepository,
    KeywordRepository,
    LogRepository,
    TokenRepository,
)
from mse_viewer.repository._helpers import append_unique, normalize_set_name

from .derivations.design_type import playbook_key
from .derivations.identity import next_collision_suffix
from .playbook import PlaybookStore
from .preview import FacePreview, Route
from .warnings import WarningKind


@dataclass
class CommitResult:
    route: Route
    record_id: int | None
    skipped: bool = False
    reason: str | None = None
    log_entry_id: int | None = None


class IngestRepos:
    """Bag of repositories, passed to the pipeline so callers don't import each."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.cards = CardRepository(db)
        self.tokens = TokenRepository(db)
        self.keywords = KeywordRepository(db)
        self.log = LogRepository(db)
        self.playbook = PlaybookStore(db)


# ---------------------------------------------------------------------------
# Keyword pre-pass (called once before per-card commits)
# ---------------------------------------------------------------------------


def commit_keywords(parsed: list[ParsedKeyword], repos: IngestRepos) -> dict[str, int]:
    """Upsert all keyword definitions; returns ``match-string → keyword.id``."""
    out: dict[str, int] = {}
    for p in parsed:
        kw = repos.keywords.upsert_from_parsed(p)
        out[p.name] = kw.id
    return out


def resolve_keyword_refs_for_face(
    face: ParsedCardFace,
    repos: IngestRepos,
) -> tuple[list[int], list[str]]:
    """For every ``<key>`` reference on the face, return ``(keyword_ids,
    stub_names_created)``.

    Resolution uses :meth:`KeywordRepository.find_for_card_ref` so that
    parameterized references like ``Cleave 1RR`` link to a single
    ``Cleave <atom-param>cost</atom-param>`` definition rather than
    creating one stub per concrete value (init_prompt_4 #9/#10).
    """
    ids: list[int] = []
    stubs_created: list[str] = []
    for ref in face.keyword_refs:
        existing = repos.keywords.find_for_card_ref(ref)
        if existing is None:
            stub = repos.keywords.ensure_stub(ref)
            stubs_created.append(stub.name)
            kid = stub.id
        else:
            kid = existing.id
        if kid not in ids:
            ids.append(kid)
    return ids, stubs_created


# ---------------------------------------------------------------------------
# Per-face commit
# ---------------------------------------------------------------------------


def commit_face(
    preview: FacePreview,
    *,
    set_name: str,
    pwl_default_for_rarity: dict[str, int] | None,
    repos: IngestRepos,
) -> CommitResult:
    """Persist a face after the user has resolved its review modal."""
    face = preview.face

    # 1) "Do Not Read": skip and log.
    if face.notes.do_not_read:
        entry = repos.log.create_action(
            title=f"Skipped (Do Not Read): {face.name}",
            body=face.raw_notes or None,
            payload={"raw_block_excerpt": preview.face.model_dump(mode="json")},
        )
        return CommitResult(
            route=preview.route,
            record_id=None,
            skipped=True,
            reason="do_not_read",
            log_entry_id=entry.id,
        )

    # 2) User explicitly rejected the card from the modal.
    if preview.rejected:
        entry = repos.log.create_action(
            title=f"Rejected from review: {face.name}",
            body=preview.warnings.warnings[0].message if preview.warnings else None,
            payload={"face": preview.face.model_dump(mode="json")},
        )
        return CommitResult(
            route=preview.route,
            record_id=None,
            skipped=True,
            reason="rejected",
            log_entry_id=entry.id,
        )

    # 3) Resolve final identity. ``route_override`` (set by the rarity:special
    #    DB picker in the modal) wins over the auto-derived route.
    effective_route = preview.route_override or preview.route
    repo = repos.tokens if effective_route == "token" else repos.cards
    existing_identities = repo.existing_identities()
    proposed = preview.proposed_identity

    resolution = preview.collision_resolution or ("update" if proposed in existing_identities else "fresh")

    if resolution == "rename":
        proposed = next_collision_suffix(proposed, existing_identities)
        existing = None
    elif resolution in ("update", "alternate"):
        existing = repo.find_by_identity(proposed)
    else:  # "fresh"
        existing = None

    # 4) Resolve keyword references → ids + stub log entries.
    keyword_ids, stub_names = resolve_keyword_refs_for_face(face, repos)
    for stub in stub_names:
        repos.log.create_action(
            title=f"Define keyword: {stub}",
            body=f"Auto-created stub keyword from card {face.name!r}.",
            payload={"keyword_ref": stub, "card_name": face.name},
        )

    # 5) Compute concrete fields, applying any overrides from the modal.
    o = preview.overrides
    design_type_value = (
        o.get("design_type")
        or preview.design_type.value
        or "Custom"
    )

    # If the modal answered an unrecognized-design-type warning, remember it.
    if preview.warnings.has(WarningKind.design_type_unrecognized) and o.get("design_type"):
        key = playbook_key(face.stylesheet or "", face.styling_data or {})
        repos.playbook.design_type_remember(key, str(o["design_type"]))

    rarity = (o.get("rarity") or face.rarity or "common").strip().lower()
    pwl = face.notes.pwl
    if pwl is None and pwl_default_for_rarity:
        pwl = pwl_default_for_rarity.get(rarity)

    colors = list(o.get("colors") or preview.colors)
    notes_body = face.notes.remainder or None

    common_kwargs = dict(
        display_name=face.name,
        card_type=face.super_type or "",
        card_subtype=face.sub_type,
        colors=colors,
        casting_cost=face.casting_cost,
        power=face.power,
        toughness=face.toughness,
        flavor_text=face.flavor_text,
        rule_text=face.rule_text,
        abilities=face.abilities,
        keyword_ids=keyword_ids,
        related_cards=list(face.related_from_notes),
        design_type=design_type_value,
        notes=notes_body,
        printed=face.notes.status_printed,
    )

    set_name_n = normalize_set_name(set_name)
    alt_art_label = preview.accept_as_alternate_label

    if existing is not None and resolution in ("update", "alternate"):
        # Update in place.
        for attr, value in common_kwargs.items():
            # Don't squash existing values with empty-on-import; only overwrite
            # when the import provides something.
            if value not in (None, "", []):
                setattr(existing, attr, value)
        repo.append_set(existing, set_name_n)
        if alt_art_label or resolution == "alternate":
            label = alt_art_label or "alternate"
            repo.append_alt_art(existing, label)
        repo.append_related(existing, list(face.related_from_notes))
        repos.db.flush()
        return CommitResult(route=preview.route, record_id=existing.id)

    # Fresh create.
    new_kwargs = {"name": proposed, **common_kwargs}
    if preview.route == "card":
        new_kwargs["rarity"] = rarity
        new_kwargs["power_level"] = pwl
        row = repos.cards.create(**new_kwargs)
    else:
        row = repos.tokens.create(**new_kwargs)

    repo.append_set(row, set_name_n)
    if alt_art_label:
        repo.append_alt_art(row, alt_art_label)

    return CommitResult(route=preview.route, record_id=row.id)
