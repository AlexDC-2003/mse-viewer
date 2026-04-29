from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates


_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def get_templates() -> Jinja2Templates:
    return Jinja2Templates(directory=str(_TEMPLATES_DIR))


templates = get_templates()
