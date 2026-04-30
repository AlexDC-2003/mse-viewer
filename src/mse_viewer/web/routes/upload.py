from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from mse_viewer.db.session import get_db
from mse_viewer.ingest.pipeline import IngestRepos
from mse_viewer.parser import parse_set_text
from mse_viewer.services.ingest_session import IngestSessionStore, get_session_store
from mse_viewer.web.templating import templates

router = APIRouter(prefix="/upload", tags=["upload"])


@router.get("")
def upload_form(request: Request):
    return templates.TemplateResponse(request, "upload.html", {"request": request})


@router.post("")
async def upload_submit(
    request: Request,
    file: UploadFile | None = None,
    pasted_text: str = Form(""),
    set_name: str = Form(...),
    pwl_common: str = Form(""),
    pwl_uncommon: str = Form(""),
    pwl_rare: str = Form(""),
    pwl_mythic: str = Form(""),
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
        return templates.TemplateResponse(
            request,
            "upload.html",
            {
                "request": request,
                "error": "No file uploaded and no text pasted.",
            },
            status_code=400,
        )

    parsed = parse_set_text(raw)
    if parsed.header.set_name and not set_name.strip():
        set_name = parsed.header.set_name

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
        return templates.TemplateResponse(
            request,
            "upload.html",
            {
                "request": request,
                "error": f"Power-level field(s) must be integers (or left blank): {', '.join(bad)}.",
            },
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
