# Phase 1 scaffold — what shipped

Set up to match every locked decision in `init_prompt_4` and the answers in
`phase1_prompt_vauto`. Tests skipped per instruction.

## Project layout

```
mse-viewer/
├── docker-compose.yml          # postgres + app
├── Dockerfile                  # app container
├── requirements.txt            # vanilla pip
├── pyproject.toml              # editable install (`pip install -e .`)
├── alembic.ini
├── .env.example
├── alembic/
│   ├── env.py                  # reads DATABASE_URL, registers domain models
│   ├── script.py.mako
│   └── versions/0001_initial.py   # full Phase-1 schema in one migration
└── src/mse_viewer/
    ├── main.py                 # FastAPI app factory + router include
    ├── config.py               # pydantic-settings
    ├── db/
    │   ├── base.py             # DeclarativeBase
    │   └── session.py          # engine, SessionLocal, get_db dep
    ├── domain/
    │   ├── _card_mixin.py      # CardCoreMixin (shared cols + JSONB lists)
    │   ├── card.py             # Card (rarity, power_level)
    │   ├── token.py            # Token (no rarity / pwl)
    │   ├── keyword.py          # strict-identity keyword (init_prompt_4 B)
    │   ├── deck.py / deck_card.py
    │   ├── notice.py           # unified LogEntry (action+notice, schema-compatible)
    │   └── playbook.py         # remembered (stylesheet, styling_data) → design_type
    ├── parser/
    │   ├── lexer.py            # indent-aware MSE plaintext lexer
    │   ├── tree.py             # token stream → MseNode tree
    │   ├── tags.py             # mana → Scryfall, kw extraction, tag stripping
    │   ├── notes_parser.py     # PWL / Related / Status:Printed / Do Not Read
    │   ├── header.py           # set_info + styling-defaults map
    │   ├── card_parser.py      # card block → faces (DFC split via name_2)
    │   ├── keyword_parser.py
    │   ├── models.py           # Pydantic ParsedCard / ParsedKeyword / etc.
    │   └── driver.py           # parse_set_text(): full pipeline
    ├── ingest/
    │   ├── derivations/
    │   │   ├── colors.py       # 4-tier first-non-empty-wins (init_prompt_4 #4)
    │   │   ├── design_type.py  # rule table + playbook lookup hook
    │   │   ├── identity.py     # "Basic X" prefix + collision suffixes
    │   │   └── routing.py      # super_type contains "Token" → tokens DB
    │   ├── warnings.py         # WarningCollector + WarningKind enum
    │   ├── playbook.py         # PlaybookStore (auto-apply on re-imports)
    │   ├── preview.py          # FacePreview = parsed face + derivations + warnings
    │   └── pipeline.py         # commit_keywords, commit_face, IngestRepos bag
    ├── repository/             # repo pattern per init_prompt_4 #5
    │   ├── _helpers.py         # append_unique (JSONB-safe), normalize_set_name
    │   ├── cards.py            # CardRepository, TokenRepository (shared base)
    │   ├── keywords.py         # upsert + ensure_stub + stub→real merge
    │   ├── decks.py
    │   └── log.py              # LogRepository (action create / state transition)
    ├── services/
    │   └── ingest_session.py   # in-process ingest sessions + per-card commit handoff
    └── web/
        ├── templating.py
        ├── static/style.css
        ├── templates/          # base, home, upload, review_modal/done, cards/, tokens/,
        │                        # keywords/, decks/, log/
        └── routes/
            ├── home.py
            ├── upload.py       # GET form, POST → start IngestSession, redirect to review
            ├── review.py       # GET review modal, POST commit / discard
            ├── browse.py       # cards/tokens/keywords/decks list+detail
            └── log.py          # action-log list + state transitions
```

## Key decisions baked in (lockstep with init_prompt_4)

| Decision | Where it lives |
| --- | --- |
| Postgres in Docker | `docker-compose.yml`, `Dockerfile`, `alembic.ini` |
| Strict keyword identity (B) | `domain/keyword.py` unique on `name`; `parser/tags.py::normalize_keyword_match` only trims/collapses whitespace |
| Tokens = separate ORM model, no rarity/PWL | `domain/_card_mixin.py` (shared) + `domain/card.py` (adds rarity, pwl) + `domain/token.py` (mixin only) |
| Color tiers, first-non-empty-wins, multi-face independent | `ingest/derivations/colors.py` |
| Repo pattern | `repository/*` is the only place that imports SQLAlchemy session APIs |
| Vanilla pip | `requirements.txt` |
| Action log only in Phase 1, notice schema present | `domain/notice.py` (`LogKind`/`LogState` enums; only `action` rows are written) |
| Identity = `name` (with `Basic X` prefix), namespaces separate per Cards/Tokens | `ingest/derivations/identity.py`; unique indexes on each table |
| JSONB lists for colors / keyword_ids / sets / alt_arts | migration uses `JSONB` + GIN indexes |
| Set-name compare CI, store as-typed | `repository/_helpers.py::normalize_set_name` (trim only); compares are case-insensitive via `func.lower(...)` |
| Project name `mse_viewer` | package name + Docker container name + `pyproject.toml` |

## Ingest flow at runtime

1. `GET /upload` — pre-upload form (set name, optional PWL defaults, file or pasted text).
2. `POST /upload` — `parse_set_text` runs; an `IngestSession` is created in
   memory; **all keyword definitions are upserted immediately** so later card
   commits can FK them; redirect to `/review/{session_id}`.
3. `GET /review/{session_id}` — renders one card per page with the unified
   review modal: warnings list (identity conflict, design-type unknown, rarity:
   special, token routing, do-not-read), parsed values, override fields,
   accept/reject controls.
4. `POST /review/{session_id}/commit` — applies user overrides, runs
   `commit_face`: writes the row (or skips & logs an action), advances cursor.
   Each commit is its own DB transaction.
5. When `cursor == total`, `review_done.html` summarizes counts and links.

## Parser smoke-tested against synthetic inputs

- Header `set_info: title: ...` → `header.set_name`.
- Styling defaults from `magic-m15-altered:` → `styling_defaults["m15-altered"]`.
- Mana symbols `<sym-auto>3</sym-auto>` → `{3}`; `<sym>1</sym>` → `{1}`.
- `<kw-N><key>Haste</key>...</kw-N>` → keyword_refs=["Haste"], inline text kept.
- `notes: PWL: 2` → `notes.pwl == 2`.
- DFC split via `name_2` — face 1 reads only `super_type`, face 2 reads only
  `super_type_2`; non-DFC cards still chain `_2`/`_3` for multi-word
  supertypes.
- Cross-link: face 1 ↔ face 2 added to `related_from_notes`.

## How to run

```bash
cp .env.example .env
docker compose up --build
# open http://localhost:8000
```

Local-no-Docker path is in the README. Migration is run on container start
(`alembic upgrade head`).

## Known limits / Phase-2 hooks

- Notice rows aren't generated yet — printed-card-diff trigger is intentionally
  not wired; the schema and `LogKind.notice` / `LogState.unread→completed`
  values are reserved.
- Deck *ingest* is out of Phase 1 (browse views render, but there's no
  upload-deck flow); the `Deck` / `DeckCard` schema is in place so adding it
  later is additive.
- Action log resolution is `open ↔ resolved` only. Notice transitions are
  defined in the enum but unused.
- `IngestSession` is process-local memory; restarting the server discards any
  in-progress import. Fine for localhost single-user.
