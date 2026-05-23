# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`mse-viewer` is a FastAPI + Postgres companion app for **Magic Set Editor** (MSE). It ingests MSE plaintext set files, parses them into normalized cards / tokens / keywords / decks, and lets the user browse, search, and curate the resulting database via server-rendered Jinja templates. It is a single-user localhost app (no auth, no multi-tenancy). See `documentation/report.md` for the full problem statement and `documentation/prompts/` for the staged design prompts that drove the implementation — they are the authoritative spec.

## Commands

Docker (preferred during development — auto-applies migrations on boot, mounts `src/` and `alembic/` for live-reload):

```bash
cp .env.example .env
docker compose up --build
# app at http://localhost:8000, postgres at localhost:5432 (mse/mse/mse_viewer)
```

Local without Docker (needs Python 3.11+ and a Postgres reachable at `DATABASE_URL`):

```bash
python -m venv .venv && source .venv/bin/activate    # .venv\Scripts\activate on Windows
pip install -r requirements.txt
pip install -e .                                     # installs the `mse_viewer` package
alembic upgrade head
uvicorn mse_viewer.main:app --reload
```

Migrations:

```bash
alembic revision --autogenerate -m "<message>"      # autogen against models in src/mse_viewer/domain
alembic upgrade head
alembic downgrade -1
```

Lint: `ruff` is configured (line-length 100, target py311) but no test suite exists yet — there is no `pytest` config and no `tests/` directory. Don't claim tests pass; run the app and exercise the upload → review → browse flow instead.

## Architecture

The ingest path is the heart of the app. It is intentionally split into **pure** stages and **DB-touching** stages so each stage can be reasoned about independently.

```
raw .mse-set text
   │
   ▼  parser/             (pure, no DB)
ParsedSet { header, keywords[], cards[ faces[] ] }
   │
   ▼  ingest/derivations/ (pure, no DB — colors, identity, design_type, routing)
   ▼  ingest/preview.py   (FacePreview + WarningCollector)
   │
   ├── no warnings ──► ingest/pipeline.commit_face  (auto-committed in order)
   │
   └── warnings    ──► services/ingest_session     (queued for review modal)
                          │
                          ▼  POST /review/{id}/commit applies modal answers,
                             then commit_face writes Cards/Tokens/Keywords/LogEntry rows.
```

Key architectural rules to preserve when editing:

- **`parser/` and `ingest/derivations/` must stay pure.** They take parsed structures and return parsed structures; no Session, no I/O. The order of operations in `parser/driver.parse_set_text` is fixed: lex → tree → header → **keywords (before cards)** → cards. Keywords are parsed first so card refs can be cross-checked.
- **`ingest/preview.build_preview` is the only place that decides "needs review."** A `FacePreview` with any `WarningCollector` warnings is queued to the modal; one without warnings is auto-committed. `notes.do_not_read` is auto-skipped (logged, not shown). See `services/ingest_session._needs_review`.
- **`ingest/pipeline.commit_face` is the only path that writes Card/Token rows.** Both auto-commit and post-modal commit go through it. It applies `preview.overrides` (from the modal), resolves identity collisions (`update` / `alternate` / `rename` / `fresh`), resolves keyword refs (auto-creating stub keyword rows + log entries), and merges `sets`/`alt_arts`/`related_cards` rather than overwriting.
- **Cards and Tokens share a column set via `domain/_card_mixin.CardCoreMixin`** but live in separate tables with separate identity namespaces (`existing_card_identities` vs `existing_token_identities`). Routing between them is decided in `ingest/derivations/routing.py` (super_type contains "Token" or "Emblem", plus the Evo-T marker) and may be overridden by the user when `rarity == "special"`. Card-only columns (live on `Card`, not on the mixin): `rarity`, `power_level`, `starting_loyalty`, `sets`, `design_type`. Tokens never carry these.
- **`name` is the stored identity, `display_name` is what the card shows.** Basic lands collapse to `"Basic <display_name>"` (one row holds all alt-art labels). Collisions get suffixed via `next_collision_suffix` only when the user picks `rename` in the modal.
- **`PlaybookStore` (table `playbook_entries`) remembers user decisions** so the same unrecognized stylesheet/styling combo isn't re-asked. Currently used for `design_type`; key built by `ingest/derivations/design_type.playbook_key`.
- **Ingest sessions live in process memory** (`services/ingest_session._store`, a module-level singleton). Restarting uvicorn drops in-flight reviews — fine for Phase 1, but don't add features that depend on session durability without changing this.
- **`LogEntry` is a unified action/notice table** (`domain/notice.py`). Phase 1 only writes `kind=action` rows; the `notice` kind and the `unread/standby/issued/completed` states are reserved for Phase 2 — the schema is shared so Phase 2 won't need a migration.
- **Update-in-place semantics:** when committing onto an existing identity (`update`/`alternate` resolution), empty values from the import do **not** clobber existing fields — see the `if value not in (None, "", []):` guard in `commit_face`. New imports also append to `sets`/`alt_arts`/`related_cards` rather than replacing them.

Web layer is thin: routes in `web/routes/` (home, upload, review, browse, log) call repositories from `repository/` and render Jinja templates from `web/templates/`. There is no JSON API yet — every endpoint returns HTML or a 303 redirect.

Models are registered with SQLAlchemy metadata via the `from mse_viewer.domain import …` import in `alembic/env.py`; **adding a new model requires adding it to that import list** or autogenerate will miss it.

## Conventions

- `from __future__ import annotations` at the top of every module — relied on for postponed evaluation of typing references in mixins (`Mapped[list[str]]`).
- Pydantic v2 (`BaseModel`, `Field(default_factory=...)`, `model_dump(mode="json")`).
- SQLAlchemy 2.x typed-mapping style (`Mapped[...]`, `mapped_column(...)`, `DeclarativeBase`).
- Postgres-specific: list/dict columns use `JSONB` (see `_card_mixin`); don't switch to generic `JSON` without checking query sites.
- Don't introduce a global `db.commit()` outside the session-store / route boundary — `commit_face` flushes; the orchestrator commits.

## Documentation workflow

`documentation/` layout:

| Path | Contents | When to read |
| ---- | -------- | ------------ |
| `documentation/report.md` | Full problem statement (the canonical spec). | At the start of any task whose scope touches multiple subsystems. |
| `documentation/prompts/<batch>/<name>` | Staged design prompts — the authoritative spec, prompt-by-prompt. | When the user references a prompt by path. |
| `documentation/responses/<batch>/<name>.md` | My answers to each prompt, mirrored from the in-conversation reply. | When checking *what's been decided*, *what's been implemented*, and *what trade-offs are recorded*. The bottom "Files changed / added" sections are the authoritative changelog. |
| `documentation/files/todolist.md` | Unified todo list across all phases / prompts. | Always — this is the live "what's left" list. Keep it in sync when finishing a prompt: move the item to the "Completed" section. |

When the user shares a prompt by file path and asks for an answer, mirror the full reply into `documentation/responses/<same-name>.md` (same basename, `.md` extension) — do not abbreviate the saved copy.

### How to navigate documentation efficiently

You don't need to re-read every prompt/response on every task. Instead:

1. Start with `documentation/files/todolist.md` for the open-work picture.
2. If you need history on a specific decision (e.g. "why is `design_type` Card-only?"), grep the `responses/` directory for the keyword — the responses section their changes by bug/item number that maps to the original prompt.
3. The bottom of every response file has a **"Files changed / added"** list; that's faster than diffing the repo.
4. The **migrations** in `alembic/versions/` are numbered chronologically with one-line descriptions in their docstrings — read them to understand the schema evolution without scrolling prompt history.
5. The CLAUDE.md "Architecture" section above describes invariants that the responses uphold; don't break them silently. If you do need to, note it in the next response file under a "Trade-offs / deviations" section.

### Migration schedule (canonical)

| Revision | Adds / drops | Origin |
| -------- | ------------ | ------ |
| `0001` | Initial schema. | Phase 1. |
| `0002` | `cards.alias`, `tokens.alias`. | Phase 1.5. |
| `0003` | `cards.starting_loyalty`. | Phase 1.6 prompt 1 (Planeswalker support). |
| `0004` | Drops `cards.abilities`, `tokens.abilities`, `tokens.sets`. | Phase 1.6 prompt 3 (`abilities` was redundant with `rule_text`; tokens don't need set provenance). |
| `0005` | Drops `tokens.design_type`. | Phase 1.6 prompt 4 (design taxonomy is Card-only). |
| `0006` | `deck_cards.token_id`, `deck_cards.card_id` nullable, XOR check + partial-unique indexes. | Phase 1.6 prompt 5 (decks hold tokens too). |
