from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from mse_viewer.db.session import get_db
from mse_viewer.ingest.pipeline import IngestRepos
from mse_viewer.services.ingest_session import IngestSessionStore, get_session_store
from mse_viewer.web.templating import templates

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/{session_id}")
def review_current(
    request: Request,
    session_id: str,
    store: IngestSessionStore = Depends(get_session_store),
):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Ingest session not found or already finished.")
    if session.finished:
        return templates.TemplateResponse(
            request,
            "review_done.html",
            {"request": request, "session": session},
        )
    preview = session.current()
    return templates.TemplateResponse(
        request,
        "review_modal.html",
        {
            "request": request,
            "session": session,
            "preview": preview,
            "warnings": preview.warnings.warnings if preview else [],
            "index": session.cursor + 1,
            "total": session.review_total,
        },
    )


@router.post("/{session_id}/commit")
def review_commit(
    session_id: str,
    action: str = Form("accept"),
    design_type: str | None = Form(None),
    rarity: str | None = Form(None),
    colors: str | None = Form(None),
    alt_art_label: str | None = Form(None),
    collision_resolution: str | None = Form(None),
    route_override: str | None = Form(None),
    db: Session = Depends(get_db),
    store: IngestSessionStore = Depends(get_session_store),
):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Ingest session not found.")
    if session.finished:
        return RedirectResponse(url=f"/review/{session_id}", status_code=303)
    repos = IngestRepos(db)
    store.commit_current(
        session,
        repos,
        action=action,
        modal_data={
            "design_type": design_type,
            "rarity": rarity,
            "colors": colors,
            "alt_art_label": alt_art_label,
            "collision_resolution": collision_resolution,
            "route_override": route_override,
        },
    )
    return RedirectResponse(url=f"/review/{session_id}", status_code=303)


@router.post("/{session_id}/discard")
def discard_session(
    session_id: str,
    store: IngestSessionStore = Depends(get_session_store),
):
    store.discard(session_id)
    return RedirectResponse(url="/upload", status_code=303)
