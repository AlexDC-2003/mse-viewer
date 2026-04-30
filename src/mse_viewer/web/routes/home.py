from __future__ import annotations

from fastapi import APIRouter, Request

from mse_viewer.web.templating import templates

router = APIRouter()


@router.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", {"request": request})
