from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from mse_viewer.db.session import get_db
from mse_viewer.repository import (
    CardRepository,
    DeckRepository,
    KeywordRepository,
    TokenRepository,
)
from mse_viewer.web.templating import templates

router = APIRouter()


def _linkify_related(
    names: list[str] | None,
    *,
    current_kind: str,
    current_name: str | None,
    cards_repo: CardRepository,
    tokens_repo: TokenRepository,
) -> list[dict]:
    """Resolve a row's ``related_cards`` strings to ``{name, href}`` dicts.

    Lookup order for each name:

    * If the related name equals the current row's own name, the entry is an
      Evo-T-style cross-link → prefer the *opposite* kind so we link to the
      sibling, not back to ourselves.
    * Otherwise prefer the *same* kind first (covers the common DFC face1↔face2
      case where both faces are Cards), falling back to the opposite kind.
    """
    if not names:
        return []
    same_repo, same_path = (
        (cards_repo, "/cards/") if current_kind == "card" else (tokens_repo, "/tokens/")
    )
    other_repo, other_path = (
        (tokens_repo, "/tokens/") if current_kind == "card" else (cards_repo, "/cards/")
    )
    self_name = (current_name or "").strip().lower()
    out: list[dict] = []
    for name in names:
        if not name:
            continue
        if name.strip().lower() == self_name:
            order = [(other_repo, other_path), (same_repo, same_path)]
        else:
            order = [(same_repo, same_path), (other_repo, other_path)]
        href: str | None = None
        for repo, path in order:
            match = repo.find_by_identity(name)
            if match is None:
                ci = repo.find_by_name_ci(name)
                if ci:
                    match = ci[0]
            if match is not None:
                href = f"{path}{match.id}"
                break
        out.append({"name": name, "href": href})
    return out


# ---------- Cards ---------------------------------------------------------


@router.get("/cards")
def cards_list(request: Request, q: str | None = None, db: Session = Depends(get_db)):
    repo = CardRepository(db)
    cards = repo.search(q) if q else repo.list()
    return templates.TemplateResponse(
        request,
        "cards/list.html",
        {"request": request, "cards": cards, "q": q or ""},
    )


@router.get("/cards/{card_id}")
def cards_detail(request: Request, card_id: int, db: Session = Depends(get_db)):
    cards_repo = CardRepository(db)
    tokens_repo = TokenRepository(db)
    card = cards_repo.get(card_id)
    if card is None:
        raise HTTPException(404)
    keyword_repo = KeywordRepository(db)
    keyword_rows = [k for k in (keyword_repo.get(i) for i in (card.keyword_ids or [])) if k]
    keyword_reminders = {k.name.lower(): k.reminder for k in keyword_rows if k.reminder}
    related = _linkify_related(
        card.related_cards,
        current_kind="card",
        current_name=card.name,
        cards_repo=cards_repo,
        tokens_repo=tokens_repo,
    )
    return templates.TemplateResponse(
        request,
        "cards/detail.html",
        {
            "request": request,
            "card": card,
            "keywords": keyword_rows,
            "keyword_reminders": keyword_reminders,
            "related": related,
        },
    )


# ---------- Tokens --------------------------------------------------------


@router.get("/tokens")
def tokens_list(request: Request, q: str | None = None, db: Session = Depends(get_db)):
    repo = TokenRepository(db)
    rows = repo.search(q) if q else repo.list()
    return templates.TemplateResponse(
        request,
        "tokens/list.html",
        {"request": request, "tokens": rows, "q": q or ""},
    )


@router.get("/tokens/{token_id}")
def tokens_detail(request: Request, token_id: int, db: Session = Depends(get_db)):
    cards_repo = CardRepository(db)
    tokens_repo = TokenRepository(db)
    row = tokens_repo.get(token_id)
    if row is None:
        raise HTTPException(404)
    keyword_repo = KeywordRepository(db)
    keyword_rows = [k for k in (keyword_repo.get(i) for i in (row.keyword_ids or [])) if k]
    keyword_reminders = {k.name.lower(): k.reminder for k in keyword_rows if k.reminder}
    related = _linkify_related(
        row.related_cards,
        current_kind="token",
        current_name=row.name,
        cards_repo=cards_repo,
        tokens_repo=tokens_repo,
    )
    return templates.TemplateResponse(
        request,
        "tokens/detail.html",
        {
            "request": request,
            "token": row,
            "keywords": keyword_rows,
            "keyword_reminders": keyword_reminders,
            "related": related,
        },
    )


# ---------- Keywords ------------------------------------------------------


@router.get("/keywords")
def keywords_list(request: Request, db: Session = Depends(get_db)):
    rows = KeywordRepository(db).list()
    return templates.TemplateResponse(
        request,
        "keywords/list.html",
        {"request": request, "keywords": rows},
    )


@router.get("/keywords/{keyword_id}")
def keywords_detail(request: Request, keyword_id: int, db: Session = Depends(get_db)):
    row = KeywordRepository(db).get(keyword_id)
    if row is None:
        raise HTTPException(404)
    return templates.TemplateResponse(
        request,
        "keywords/detail.html",
        {"request": request, "keyword": row},
    )


# ---------- Decks ---------------------------------------------------------


@router.get("/decks")
def decks_list(request: Request, db: Session = Depends(get_db)):
    rows = DeckRepository(db).list()
    return templates.TemplateResponse(
        request,
        "decks/list.html",
        {"request": request, "decks": rows},
    )


@router.get("/decks/{deck_id}")
def decks_detail(request: Request, deck_id: int, db: Session = Depends(get_db)):
    deck = DeckRepository(db).get(deck_id)
    if deck is None:
        raise HTTPException(404)
    return templates.TemplateResponse(
        request,
        "decks/detail.html",
        {"request": request, "deck": deck},
    )
