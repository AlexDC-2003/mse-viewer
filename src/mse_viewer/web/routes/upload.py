from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from mse_viewer.db.session import get_db
from mse_viewer.ingest.deck import DeckIngestPlan, collapse_deck
from mse_viewer.ingest.pipeline import IngestRepos
from mse_viewer.parser import parse_set_text
from mse_viewer.repository import CardRepository
from mse_viewer.services.ingest_session import IngestSessionStore, get_session_store
from mse_viewer.web.templating import templates

router = APIRouter(prefix="/upload", tags=["upload"])


@router.get("")
def upload_form(
    request: Request,
    mode: str = "set",
    db: Session = Depends(get_db),
):
    cards = CardRepository(db).list() if mode == "deck" else []
    return templates.TemplateResponse(
        request,
        "upload.html",
        {"request": request, "mode": mode, "cards": cards},
    )


@router.post("")
async def upload_submit(
    request: Request,
    mode: str = Form("set"),
    file: UploadFile | None = None,
    pasted_text: str = Form(""),
    set_name: str = Form(""),
    pwl_common: str = Form(""),
    pwl_uncommon: str = Form(""),
    pwl_rare: str = Form(""),
    pwl_mythic: str = Form(""),
    deck_name: str = Form(""),
    deck_format: str = Form("1v1"),
    deck_size: str = Form("60"),
    deck_commander_card_id: str = Form(""),
    deck_package: str = Form(""),
    deck_theme: str = Form(""),
    deck_archetype: str = Form(""),
    deck_owners: str = Form(""),
    deck_colors: str = Form(""),
    deck_related: str = Form(""),
    db: Session = Depends(get_db),
    store: IngestSessionStore = Depends(get_session_store),
):
    raw = pasted_text or ""
    if file is not None and file.filename:
        body = await file.read()
        try:
            raw = body.decode("utf-8")
        except UnicodeDecodeError:
            raw = body.decode("latin-1", errors="replace")

    if not raw.strip():
        return _render_error(
            request, db, mode, "No file uploaded and no text pasted.", status_code=400
        )

    parsed = parse_set_text(raw)

    if mode == "deck":
        if not deck_name.strip():
            return _render_error(request, db, mode, "Deck name is required.", status_code=400)
        repos = IngestRepos(db)
        existing_card_names = repos.cards.existing_identities()
        deduped, quantities = collapse_deck(
            parsed, existing_card_names=existing_card_names
        )
        meta = _deck_meta_from_form(
            deck_name=deck_name,
            deck_format=deck_format,
            deck_size=deck_size,
            deck_commander_card_id=deck_commander_card_id,
            deck_package=deck_package,
            deck_theme=deck_theme,
            deck_archetype=deck_archetype,
            deck_owners=deck_owners,
            deck_colors=deck_colors,
            deck_related=deck_related,
        )
        plan = DeckIngestPlan(
            meta=meta,
            quantities=quantities,
            missing=set(quantities) - {n for n in existing_card_names},
        )
        # Use deck_name as the "set_name" for any per-card sets[] entries
        # (the deck file's cards are tagged as belonging to this deck).
        session = store.create(
            parsed=deduped,
            set_name=deck_name.strip(),
            pwl_defaults={},
            repos=repos,
            deck_plan=plan,
        )
        return RedirectResponse(url=f"/review/{session.id}", status_code=303)

    # ---- set mode (existing flow) ----
    if parsed.header.set_name and not set_name.strip():
        set_name = parsed.header.set_name
    if not set_name.strip():
        return _render_error(request, db, mode, "Set name is required.", status_code=400)

    pwl_inputs = (
        ("common", pwl_common),
        ("uncommon", pwl_uncommon),
        ("rare", pwl_rare),
        ("mythic", pwl_mythic),
    )
    pwl_defaults: dict[str, int] = {}
    bad: list[str] = []
    for key, raw_value in pwl_inputs:
        v = (raw_value or "").strip()
        if not v:
            continue
        try:
            pwl_defaults[key] = int(v)
        except ValueError:
            bad.append(key)
    if bad:
        return _render_error(
            request,
            db,
            mode,
            f"Power-level field(s) must be integers (or left blank): {', '.join(bad)}.",
            status_code=400,
        )

    repos = IngestRepos(db)
    session = store.create(
        parsed=parsed,
        set_name=set_name.strip(),
        pwl_defaults=pwl_defaults,
        repos=repos,
    )
    return RedirectResponse(url=f"/review/{session.id}", status_code=303)


def _deck_meta_from_form(
    *,
    deck_name: str,
    deck_format: str,
    deck_size: str,
    deck_commander_card_id: str,
    deck_package: str,
    deck_theme: str,
    deck_archetype: str,
    deck_owners: str,
    deck_colors: str,
    deck_related: str,
) -> dict:
    """Translate the upload form into a Deck(...) kwargs bag.

    All optional list/integer fields are coerced defensively so a stray
    comma or empty field does not blow up the create call.
    """

    def _csv(s: str) -> list[str]:
        return [p.strip() for p in (s or "").split(",") if p.strip()]

    def _csv_int(s: str) -> list[int]:
        out: list[int] = []
        for p in _csv(s):
            try:
                out.append(int(p))
            except ValueError:
                continue
        return out

    def _maybe_int(s: str) -> int | None:
        s = (s or "").strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return None

    return {
        "name": deck_name.strip(),
        "format": (deck_format or "1v1").strip() or "1v1",
        "size": _maybe_int(deck_size) or 60,
        "commander_card_id": _maybe_int(deck_commander_card_id),
        "package": (deck_package.strip() or None),
        "theme": (deck_theme.strip() or None),
        "archetype": (deck_archetype.strip() or None),
        "owners": _csv(deck_owners),
        "colors": _csv(deck_colors),
        "related_decks": _csv_int(deck_related),
    }


def _render_error(request, db, mode, error, *, status_code=400):
    cards = CardRepository(db).list() if mode == "deck" else []
    return templates.TemplateResponse(
        request,
        "upload.html",
        {"request": request, "mode": mode, "cards": cards, "error": error},
        status_code=status_code,
    )
