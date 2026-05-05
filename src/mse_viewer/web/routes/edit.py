"""Manual CRUD routes for Cards / Tokens / Keywords / Decks.

init_prompt_3 decision: manual edits are authoritative — the user can fix
anything ingest got wrong without re-running the pipeline. These routes pair
the existing browse views with simple HTML forms; lists are stored as
comma-separated values in textareas, integers go through coercion, and
identity / FK fields are validated at the route level.
"""
from __future__ import annotations

from typing import Iterable

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from mse_viewer.db.session import get_db
from mse_viewer.domain.card import Card
from mse_viewer.domain.deck import Deck
from mse_viewer.domain.deck_card import DeckCard
from mse_viewer.domain.keyword import Keyword
from mse_viewer.domain.token import Token
from mse_viewer.repository import (
    CardRepository,
    DeckRepository,
    KeywordRepository,
    TokenRepository,
)
from mse_viewer.web.templating import templates

router = APIRouter(tags=["edit"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _split_csv_int(raw: str | None) -> list[int]:
    out: list[int] = []
    for p in _split_csv(raw):
        try:
            out.append(int(p))
        except ValueError:
            continue
    return out


def _resolve_keyword_names_to_ids(
    raw: str | None, repo: KeywordRepository
) -> tuple[list[int], list[str]]:
    """Take a free-text keyword field and return (ids, unresolved_names).

    Names go through :meth:`KeywordRepository.find_for_card_ref` which already
    handles parameterised matches (``Ammo 2`` → ``Ammo <atom-param>n</atom-param>``).
    Unresolved names are returned so the route can surface them to the user;
    we deliberately do NOT auto-create stubs here — manual edits are
    authoritative, and a typo shouldn't pollute the keyword DB.
    """
    ids: list[int] = []
    seen: set[int] = set()
    unresolved: list[str] = []
    for name in _split_csv(raw):
        kw = repo.find_for_card_ref(name)
        if kw is None:
            unresolved.append(name)
            continue
        if kw.id not in seen:
            ids.append(kw.id)
            seen.add(kw.id)
    return ids, unresolved


def _keyword_names_for_display(ids: list[int] | None, repo: KeywordRepository) -> str:
    """Render a row's stored keyword id list as a human-readable comma-list
    so the edit form can round-trip them as names."""
    if not ids:
        return ""
    parts: list[str] = []
    for kid in ids:
        kw = repo.get(kid)
        if kw is not None:
            parts.append(kw.name)
    return ", ".join(parts)


def _canonicalize_related_names(raw: str | None, db: Session) -> list[str]:
    """Auto-correct casing on a CSV related-cards list against existing
    Card / Token rows. Phase 1.6 prompt 3 bug 5 (manual-edit side)."""
    cards = CardRepository(db)
    tokens = TokenRepository(db)
    out: list[str] = []
    seen: set[str] = set()
    for raw_name in _split_csv(raw):
        canonical = raw_name
        for repo in (cards, tokens):
            hit = repo.find_by_identity(raw_name)
            if hit is not None:
                canonical = hit.name
                break
            ci = repo.find_by_name_ci(raw_name)
            if ci:
                canonical = ci[0].name
                break
        key = canonical.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(canonical)
    return out


def _maybe_int(raw: str | None) -> int | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _maybe_text(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip()
    return s or None


def _bool(raw: str | None) -> bool:
    return str(raw or "").lower() in ("on", "true", "1", "yes")


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------


@router.get("/cards/new")
def cards_new(request: Request):
    return templates.TemplateResponse(
        request,
        "cards/edit.html",
        {
            "request": request,
            "card": None,
            "action": "/cards/new",
            "is_new": True,
            "keyword_names_value": "",
        },
    )


@router.post("/cards/new")
async def cards_create(request: Request, db: Session = Depends(get_db)):
    return await _save_card(request, db, existing=None)


@router.get("/cards/{card_id}/edit")
def cards_edit(request: Request, card_id: int, db: Session = Depends(get_db)):
    card = CardRepository(db).get(card_id)
    if card is None:
        raise HTTPException(404)
    return templates.TemplateResponse(
        request,
        "cards/edit.html",
        {
            "request": request,
            "card": card,
            "action": f"/cards/{card_id}/edit",
            "is_new": False,
            "keyword_names_value": _keyword_names_for_display(
                card.keyword_ids, KeywordRepository(db)
            ),
        },
    )


@router.post("/cards/{card_id}/edit")
async def cards_update(request: Request, card_id: int, db: Session = Depends(get_db)):
    card = CardRepository(db).get(card_id)
    if card is None:
        raise HTTPException(404)
    return await _save_card(request, db, existing=card)


@router.post("/cards/{card_id}/delete")
def cards_delete(card_id: int, db: Session = Depends(get_db)):
    card = CardRepository(db).get(card_id)
    if card is None:
        raise HTTPException(404)
    db.delete(card)
    db.commit()
    return RedirectResponse("/cards", status_code=303)


async def _save_card(request: Request, db: Session, *, existing: Card | None):
    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    repo = CardRepository(db)
    if existing is None:
        existing = repo.find_by_identity(name)
        if existing is not None:
            raise HTTPException(409, f"Card {name!r} already exists.")
        existing = Card(name=name)
        db.add(existing)
    else:
        existing.name = name

    existing.display_name = (form.get("display_name") or name).strip()
    existing.card_type = (form.get("card_type") or "").strip()
    existing.card_subtype = _maybe_text(form.get("card_subtype"))
    existing.colors = _split_csv(form.get("colors"))
    existing.casting_cost = _maybe_text(form.get("casting_cost"))
    existing.power = _maybe_text(form.get("power"))
    existing.toughness = _maybe_text(form.get("toughness"))
    existing.flavor_text = _maybe_text(form.get("flavor_text"))
    existing.rule_text = _maybe_text(form.get("rule_text"))
    existing.design_type = (form.get("design_type") or "Normal").strip() or "Normal"
    existing.notes = _maybe_text(form.get("notes"))
    existing.alias = _maybe_text(form.get("alias"))
    existing.printed = _bool(form.get("printed"))
    existing.rarity = (form.get("rarity") or "common").strip() or "common"
    existing.power_level = _maybe_int(form.get("power_level"))
    existing.starting_loyalty = _maybe_int(form.get("starting_loyalty"))
    existing.related_cards = _canonicalize_related_names(form.get("related_cards"), db)
    existing.sets = _split_csv(form.get("sets"))
    existing.alt_arts = _split_csv(form.get("alt_arts"))
    kw_ids, unresolved = _resolve_keyword_names_to_ids(
        form.get("keyword_names"), KeywordRepository(db)
    )
    existing.keyword_ids = kw_ids
    if unresolved:
        # Surface unresolved names in the action log so the user can fix
        # them after the redirect.
        from mse_viewer.repository import LogRepository

        LogRepository(db).create_action(
            title=f"Unresolved keyword(s) on {existing.name!r}",
            body="\n".join(f"  - {n}" for n in unresolved),
            payload={"card_id": existing.id, "unresolved": unresolved},
            card_id=existing.id,
        )
    db.commit()
    return RedirectResponse(f"/cards/{existing.id}", status_code=303)


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


@router.get("/tokens/new")
def tokens_new(request: Request):
    return templates.TemplateResponse(
        request,
        "tokens/edit.html",
        {
            "request": request,
            "token": None,
            "action": "/tokens/new",
            "is_new": True,
            "keyword_names_value": "",
        },
    )


@router.post("/tokens/new")
async def tokens_create(request: Request, db: Session = Depends(get_db)):
    return await _save_token(request, db, existing=None)


@router.get("/tokens/{token_id}/edit")
def tokens_edit(request: Request, token_id: int, db: Session = Depends(get_db)):
    token = TokenRepository(db).get(token_id)
    if token is None:
        raise HTTPException(404)
    return templates.TemplateResponse(
        request,
        "tokens/edit.html",
        {
            "request": request,
            "token": token,
            "action": f"/tokens/{token_id}/edit",
            "is_new": False,
            "keyword_names_value": _keyword_names_for_display(
                token.keyword_ids, KeywordRepository(db)
            ),
        },
    )


@router.post("/tokens/{token_id}/edit")
async def tokens_update(request: Request, token_id: int, db: Session = Depends(get_db)):
    token = TokenRepository(db).get(token_id)
    if token is None:
        raise HTTPException(404)
    return await _save_token(request, db, existing=token)


@router.post("/tokens/{token_id}/delete")
def tokens_delete(token_id: int, db: Session = Depends(get_db)):
    token = TokenRepository(db).get(token_id)
    if token is None:
        raise HTTPException(404)
    db.delete(token)
    db.commit()
    return RedirectResponse("/tokens", status_code=303)


async def _save_token(request: Request, db: Session, *, existing: Token | None):
    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    repo = TokenRepository(db)
    if existing is None:
        if repo.find_by_identity(name) is not None:
            raise HTTPException(409, f"Token {name!r} already exists.")
        existing = Token(name=name)
        db.add(existing)
    else:
        existing.name = name
    existing.display_name = (form.get("display_name") or name).strip()
    existing.card_type = (form.get("card_type") or "").strip()
    existing.card_subtype = _maybe_text(form.get("card_subtype"))
    existing.colors = _split_csv(form.get("colors"))
    existing.casting_cost = _maybe_text(form.get("casting_cost"))
    existing.power = _maybe_text(form.get("power"))
    existing.toughness = _maybe_text(form.get("toughness"))
    existing.flavor_text = _maybe_text(form.get("flavor_text"))
    existing.rule_text = _maybe_text(form.get("rule_text"))
    existing.design_type = (form.get("design_type") or "Normal").strip() or "Normal"
    existing.notes = _maybe_text(form.get("notes"))
    existing.alias = _maybe_text(form.get("alias"))
    existing.printed = _bool(form.get("printed"))
    existing.related_cards = _canonicalize_related_names(form.get("related_cards"), db)
    existing.alt_arts = _split_csv(form.get("alt_arts"))
    kw_ids, unresolved = _resolve_keyword_names_to_ids(
        form.get("keyword_names"), KeywordRepository(db)
    )
    existing.keyword_ids = kw_ids
    if unresolved:
        from mse_viewer.repository import LogRepository

        LogRepository(db).create_action(
            title=f"Unresolved keyword(s) on token {existing.name!r}",
            body="\n".join(f"  - {n}" for n in unresolved),
            payload={"token_id": existing.id, "unresolved": unresolved},
            token_id=existing.id,
        )
    db.commit()
    return RedirectResponse(f"/tokens/{existing.id}", status_code=303)


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------


@router.get("/keywords/new")
def keywords_new(request: Request):
    return templates.TemplateResponse(
        request,
        "keywords/edit.html",
        {"request": request, "keyword": None, "action": "/keywords/new", "is_new": True},
    )


@router.post("/keywords/new")
async def keywords_create(request: Request, db: Session = Depends(get_db)):
    return await _save_keyword(request, db, existing=None)


@router.get("/keywords/{keyword_id}/edit")
def keywords_edit(request: Request, keyword_id: int, db: Session = Depends(get_db)):
    kw = KeywordRepository(db).get(keyword_id)
    if kw is None:
        raise HTTPException(404)
    return templates.TemplateResponse(
        request,
        "keywords/edit.html",
        {
            "request": request,
            "keyword": kw,
            "action": f"/keywords/{keyword_id}/edit",
            "is_new": False,
        },
    )


@router.post("/keywords/{keyword_id}/edit")
async def keywords_update(request: Request, keyword_id: int, db: Session = Depends(get_db)):
    kw = KeywordRepository(db).get(keyword_id)
    if kw is None:
        raise HTTPException(404)
    return await _save_keyword(request, db, existing=kw)


@router.post("/keywords/{keyword_id}/delete")
def keywords_delete(keyword_id: int, db: Session = Depends(get_db)):
    kw = KeywordRepository(db).get(keyword_id)
    if kw is None:
        raise HTTPException(404)
    db.delete(kw)
    db.commit()
    return RedirectResponse("/keywords", status_code=303)


async def _save_keyword(request: Request, db: Session, *, existing: Keyword | None):
    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    repo = KeywordRepository(db)
    if existing is None:
        if repo.find_by_match(name) is not None:
            raise HTTPException(409, f"Keyword {name!r} already exists.")
        existing = Keyword(name=name)
        db.add(existing)
    else:
        existing.name = name
    existing.source_keyword_field = _maybe_text(form.get("source_keyword_field"))
    existing.accepted_parameters = _split_csv(form.get("accepted_parameters"))
    existing.reminder = _maybe_text(form.get("reminder"))
    existing.rules = _maybe_text(form.get("rules"))
    existing.pseudo_keyword = _bool(form.get("pseudo_keyword"))
    existing.is_stub = _bool(form.get("is_stub"))
    db.commit()
    return RedirectResponse(f"/keywords/{existing.id}", status_code=303)


# ---------------------------------------------------------------------------
# Decks
# ---------------------------------------------------------------------------


@router.get("/decks/new")
def decks_new(request: Request, db: Session = Depends(get_db)):
    return _render_deck_form(request, db, deck=None, action="/decks/new", is_new=True)


@router.post("/decks/new")
async def decks_create(request: Request, db: Session = Depends(get_db)):
    return await _save_deck(request, db, existing=None)


@router.get("/decks/{deck_id}/edit")
def decks_edit(request: Request, deck_id: int, db: Session = Depends(get_db)):
    deck = DeckRepository(db).get(deck_id)
    if deck is None:
        raise HTTPException(404)
    return _render_deck_form(
        request, db, deck=deck, action=f"/decks/{deck_id}/edit", is_new=False
    )


@router.post("/decks/{deck_id}/edit")
async def decks_update(request: Request, deck_id: int, db: Session = Depends(get_db)):
    deck = DeckRepository(db).get(deck_id)
    if deck is None:
        raise HTTPException(404)
    return await _save_deck(request, db, existing=deck)


@router.post("/decks/{deck_id}/delete")
def decks_delete(deck_id: int, db: Session = Depends(get_db)):
    deck = DeckRepository(db).get(deck_id)
    if deck is None:
        raise HTTPException(404)
    db.delete(deck)
    db.commit()
    return RedirectResponse("/decks", status_code=303)


def _render_deck_form(
    request: Request,
    db: Session,
    *,
    deck: Deck | None,
    action: str,
    is_new: bool,
):
    cards = CardRepository(db).list()
    decks = DeckRepository(db).list()
    return templates.TemplateResponse(
        request,
        "decks/edit.html",
        {
            "request": request,
            "deck": deck,
            "cards": cards,
            "all_decks": decks,
            "action": action,
            "is_new": is_new,
        },
    )


async def _save_deck(request: Request, db: Session, *, existing: Deck | None):
    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    repo = DeckRepository(db)
    if existing is None:
        if repo.find_by_name(name) is not None:
            raise HTTPException(409, f"Deck {name!r} already exists.")
        existing = Deck(name=name, format=(form.get("format") or "1v1").strip())
        db.add(existing)
        db.flush()
    else:
        existing.name = name
    existing.code = _maybe_text(form.get("code"))
    existing.format = (form.get("format") or "1v1").strip() or "1v1"
    existing.theme = _maybe_text(form.get("theme"))
    existing.archetype = _maybe_text(form.get("archetype"))
    existing.owners = _split_csv(form.get("owners"))
    existing.colors = _split_csv(form.get("colors"))
    existing.size = _maybe_int(form.get("size")) or 60
    existing.commander_card_id = _maybe_int(form.get("commander_card_id"))
    existing.package = _maybe_text(form.get("package"))
    existing.related_decks = _split_csv_int(form.get("related_decks"))

    # Cards: ``deck_cards`` raw textarea — each line is ``<qty> <card_id>``.
    raw_cards = form.get("deck_cards") or ""
    _replace_deck_cards(db, existing, _parse_deck_card_lines(raw_cards))
    db.commit()
    return RedirectResponse(f"/decks/{existing.id}", status_code=303)


def _parse_deck_card_lines(raw: str) -> list[tuple[int, int]]:
    """Each non-empty line is ``<qty> <card_id>``. Bad lines are skipped."""
    out: list[tuple[int, int]] = []
    for line in raw.splitlines():
        parts = line.strip().split()
        if len(parts) != 2:
            continue
        try:
            qty = int(parts[0])
            cid = int(parts[1])
        except ValueError:
            continue
        if qty > 0 and cid > 0:
            out.append((qty, cid))
    return out


def _replace_deck_cards(db: Session, deck: Deck, pairs: Iterable[tuple[int, int]]) -> None:
    """Reset ``deck.cards`` to exactly ``pairs``. Existing rows not in the new
    set are deleted; existing rows that survive get their quantity updated;
    rows not in the DB are inserted. The unique ``(deck_id, card_id)`` keeps
    duplicate lines benign."""
    pairs_dict: dict[int, int] = {}
    for qty, cid in pairs:
        pairs_dict[cid] = pairs_dict.get(cid, 0) + qty
    seen_card_ids: set[int] = set()
    for dc in list(deck.cards):
        if dc.card_id not in pairs_dict:
            db.delete(dc)
            continue
        dc.quantity = pairs_dict[dc.card_id]
        seen_card_ids.add(dc.card_id)
    for cid, qty in pairs_dict.items():
        if cid in seen_card_ids:
            continue
        db.add(DeckCard(deck_id=deck.id, card_id=cid, quantity=qty))
