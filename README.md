# mse-viewer

MSE companion DB / viewer. Phase 1 scaffold.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Then open http://localhost:8000

## Local (no Docker)

Requires Python 3.11+ and a running Postgres on `DATABASE_URL`.

```bash
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
pip install -e .
alembic upgrade head
uvicorn mse_viewer.main:app --reload
```
