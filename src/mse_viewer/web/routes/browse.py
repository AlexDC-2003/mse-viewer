from __future__ import annotations

import re
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from mse_viewer.db.session import get_db
from mse_viewer.parser.reminder_template import evaluate_reminder_template
from mse_viewer.repository import (
    CardRepository,
    DeckRepository,
    KeywordRepository,
    TokenRepository,
)
from mse_viewer.web.templating import templates

router = APIRouter()


_RE_KW_ATOM_PARAM = re.compile(r"<atom-param>([^<]*)</atom-param>", re.IGNORECASE)


def _build_keyword_reminder_resolver(keyword_rows) -> Callable[[str], str | None]:
    """Build an in-memory resolver: given a card-side ref string (e.g.
    ``Trample`` / ``Splash 2`` / ``Evolve: Foo``), return the matching
    keyword's reminder body, evaluated against any captured invocation
    parameters.  Returns ``None`` when no keyword matches.

    Two passes:
      1. Exact (case-insensitive) match against ``keyword.name`` — no params
         to capture.
      2. Structural match: each ``<atom-param>X</atom-param>`` slot becomes
         ``(.+?)`` so parameterised keywords resolve from concrete
         invocations.  The captured groups are paired with the param names
         from the match string (``n``, ``cost``, ``name`` …) and fed into
         :func:`evaluate_reminder_template` so a card that reads
         ``Toxic 2`` gets ``2 poison counters.`` instead of leaking the
         raw ``{ if n.value=="1" then "counter." else "counters." }``.

    A tolerance retry strips a single ``:`` from the candidate before
    rematching — handles cases where MSE renders ``Evolve: <name>`` but the
    stored match string is ``Evolve <atom-param>name</atom-param>`` (no
    colon, MSE inserts it at display time).
    """
    exact: dict[str, str] = {}
    patterns: list[tuple[re.Pattern[str], str, list[str]]] = []
    for k in keyword_rows:
        if not k.reminder:
            continue
        param_names = _RE_KW_ATOM_PARAM.findall(k.name)
        if param_names:
            parts = _RE_KW_ATOM_PARAM.split(k.name)
            # ``re.split`` with a capturing group interleaves literal parts
            # and capture content; we only need the literal parts (every
            # second element).
            literals = parts[::2]
            pat_body = "(.+?)".join(re.escape(p) for p in literals)
            patterns.append(
                (re.compile(rf"^\s*{pat_body}\s*$", re.IGNORECASE | re.DOTALL),
                 k.reminder,
                 param_names)
            )
        else:
            exact[k.name.lower()] = k.reminder

    def _try(ref: str) -> str | None:
        if not ref:
            return None
        hit = exact.get(ref.lower())
        if hit is not None:
            return evaluate_reminder_template(hit)
        for pat, rem, names in patterns:
            m = pat.match(ref)
            if m:
                groups = m.groups()
                # Both named (``{name}``, ``{cost}``) and positional
                # (``{param1}``, ``{param2}``) references are common in MSE
                # reminder templates — populate both so either resolves.
                params = {nm: val for nm, val in zip(names, groups)}
                for i, val in enumerate(groups, start=1):
                    params.setdefault(f"param{i}", val)
                return evaluate_reminder_template(rem, params)
        return None

    def resolve(ref: str) -> str | None:
        ref_n = (ref or "").strip().rstrip(".,").strip()
        if not ref_n:
            return None
        hit = _try(ref_n)
        if hit is not None:
            return hit
        if ":" in ref_n:
            tolerant = ref_n.replace(":", "", 1).strip()
            return _try(tolerant)
        return None

    return resolve


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
    keyword_reminders = _build_keyword_reminder_resolver(keyword_rows)
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
    keyword_reminders = _build_keyword_reminder_resolver(keyword_rows)
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
