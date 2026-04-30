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
    card = CardRepository(db).get(card_id)
    if card is None:
        raise HTTPException(404)
    keyword_repo = KeywordRepository(db)
    keyword_rows = [keyword_repo.get(i) for i in (card.keyword_ids or [])]
    return templates.TemplateResponse(
        request,
        "cards/detail.html",
        {"request": request, "card": card, "keywords": [k for k in keyword_rows if k]},
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
    row = TokenRepository(db).get(token_id)
    if row is None:
        raise HTTPException(404)
    keyword_repo = KeywordRepository(db)
    keyword_rows = [keyword_repo.get(i) for i in (row.keyword_ids or [])]
    return templates.TemplateResponse(
        request,
        "tokens/detail.html",
        {"request": request, "token": row, "keywords": [k for k in keyword_rows if k]},
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
