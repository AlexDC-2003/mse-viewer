from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from mse_viewer.db.session import get_db
from mse_viewer.domain.notice import LogKind, LogState
from mse_viewer.repository import LogRepository
from mse_viewer.web.templating import templates

router = APIRouter(prefix="/log", tags=["log"])


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


@router.get("")
def log_list(
    request: Request,
    kind: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    kind_e = LogKind(kind) if kind else None
    state_e = LogState(state) if state else None
    rows = LogRepository(db).list(kind=kind_e, state=state_e)
    return templates.TemplateResponse(
        request,
        "log/list.html",
        {
            "request": request,
            "entries": rows,
            "filter_kind": kind or "",
            "filter_state": state or "",
        },
    )


@router.post("/{entry_id}/resolve")
def resolve(request: Request, entry_id: int, db: Session = Depends(get_db)):
    return _transition(request, entry_id, LogState.resolved, db)


@router.post("/{entry_id}/reopen")
def reopen(request: Request, entry_id: int, db: Session = Depends(get_db)):
    return _transition(request, entry_id, LogState.open, db)


def _transition(request: Request, entry_id: int, new_state: LogState, db: Session):
    repo = LogRepository(db)
    entry = repo.get(entry_id)
    if entry is None:
        raise HTTPException(404)
    repo.transition(entry, new_state)
    db.commit()
    if _is_htmx(request):
        # Swap just the row in place — no redirect, no scroll reflow.
        return templates.TemplateResponse(
            request, "log/_row.html", {"request": request, "e": entry}
        )
    # Anchor on the row so the browser scrolls back to where the user was.
    return RedirectResponse(url=f"/log#entry-{entry_id}", status_code=303)


@router.post("")
def log_create_manual(
    title: str = Form(...),
    body: str = Form(""),
    db: Session = Depends(get_db),
):
    LogRepository(db).create_action(title=title, body=body or None)
    db.commit()
    return RedirectResponse(url="/log", status_code=303)
