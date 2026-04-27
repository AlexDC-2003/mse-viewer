# Replies to your replies

**1, 3, 6, 9, 11, 12, 13** — agreed, locked in.

**2 (dry-run)** — fair enough, dropped. We stay with per-card modal flow.

**4 — keyword identity, clarified with an example.** You and I agree on the principle: **Suspend(number) ≠ Suspend(number, cost)** — different param *count* and different param *types* mean different keywords. The thing I was raising is more subtle. Imagine you defined two keywords:

```
keyword: Suspend       match: Suspend <atom-param>number</atom-param>
keyword: Suspend       match: Suspend <atom-param>count</atom-param>
```

Same name, same param count, same semantic param type (a number). The only difference is the *label* inside `<atom-param>` (`number` vs `count`). My suggestion was: those should be treated as **the same keyword**, because the label is just a human hint for what the param means — not a type. The `accepted_parameters` attribute would store `["number"]` (or `["count"]` — whichever was defined first) for display, but identity would be based on a normalized form like `Suspend <atom-param>_</atom-param>`.

If you'd rather the label *also* count toward identity (so `number` and `count` create two keyword rows), that's fine too — it's just stricter. **Pick one:**
- (A) **Loose identity** (my suggestion): name + param count. Labels are display-only. Cleaner, less risk of accidental duplicates.
- (B) **Strict identity** (literal match string): two keywords with different labels are different rows. Safer if you ever have two keywords that *look* identical structurally but mean different things.

I'd default to (A). Your call.

**5 — set record retracted.** You're right, there's no set record in your model — sets are just strings on cards. Drop my suggestion; you re-enter PWL defaults in the upload form each import, that's fine.

**7, 8, 10, 14** — locked in.

**15 (notes grammar)** — got it. Parser does:
- Scan each line of `notes:` looking for prefixes: `PWL:`, `Related:`, `Status: Printed`, `Do Not Read`.
- Strip those lines from the raw text.
- Whatever's left is stored as the card's free-text `notes` attribute.
- `Related:` is comma-separated; we split on `,` and trim each entry.
- `Do Not Read` short-circuits: skip card, log to action list with full raw card data.

**16 (multi-face)** — got it. Each face becomes its own record, cross-linked via `related_cards`. The parser splits a `name_2`-bearing card block into two synthesized card blocks before passing to the per-card pipeline. The shared fields (stylesheet, styling_data, notes) are duplicated to both faces. `image_2` belongs to face 2.

**17 (printed flag)** — got it, simpler than my version: read `Status: Printed` from notes at ingest, store as boolean, never auto-flip.

# Spec deltas (delta on top of v0.2)

- **Keyword identity** = match-string normalized per (A) above unless you say otherwise. Param-name labels stored in `accepted_parameters` for display, not identity.
- **PWL defaults**: pre-upload form only, no persistence.
- **Action log = Notice log** (single table, two filters):
  - `kind = notice` (reprint required) | `kind = action` (parser punted, missing keyword, "Do Not Read" card, etc.)
  - States `unread → standby → issued → completed` apply to notices; actions probably just have `open → resolved`. Same UI, filter pills.
- **Notes parser**: extract `PWL:`, `Related:`, `Status: Printed`, `Do Not Read` markers, store remainder as `notes` text.
- **Multi-face cards**: parser splits into N face records; cross-links via `related_cards`.
- **Manual edits are authoritative**: no confirmation prompt for hand-input keywords/cards. Only set-file ingest can trigger conflict warnings.
- **Stub keywords**: when later defined, merge silently into the stub (matched by `keyword:` field, since the stub only has the key text from `<key>`).
- **Rejected cards**: skip, dump full card block + reason into action log entry user can review later.
- **Basic lands**: one record per `Basic X`, alt-art labels appended for duplicate entries.

## Open ambiguities I still see

1. **Keyword identity finalization** — I need your A/B answer on #4 above before I can write the schema.
2. **Color extraction priority** — re-reading my own §3.1: I wrote "casting_cost > indicator > extra_data > card_color, fall through if casting_cost is colorless-only". Your answer to #12 confirmed casting cost wins. But your prompt 2 said *"if discrepancy, extra_indicator > frame"* applies *within* `extra_data`, and *"colors extracted from casting costs (unless only colorless is extracted) > indicator > extra_data > card_color"*. Confirming: the four tiers are tried in order, and we **return the first non-empty tier's result** — we don't merge across tiers. Right? Or should card_color contribute extra colors that casting_cost missed?
3. **Multi-face `card_color`**. The DFC example has `card_color: blue, land`. Both faces share this string but they're really different colors (Vast Lagoon = blue, Drop in the Water = blue too, but in general the back face could be a different color). For multi-face cards, do we apply the same color rules per face using face-2's `casting_cost_2` etc., and ignore the shared `card_color` for face 2? I'd default to: yes, each face derives independently, shared `card_color` only seeds face 1.
4. **Tokens DB schema**: same shape as Cards DB? Or stripped down (tokens have no rarity, no PWL, no flavor)? I'd default to "same schema, fields nullable" for simplicity.
5. **`<sym>1</sym>` vs `<sym-auto>1</sym-auto>`**. Your DFC example uses both forms. Confirming both convert to `{1}` Scryfall-style.

---

# Phase 1 — code & structure plan

## Stack pinned

- **Python 3.11+**
- **FastAPI** + **Jinja2 templates** + **HTMX** for the UI
- **SQLAlchemy 2.0** ORM + **Alembic** migrations
- **Pydantic v2** for parser output models / API validation
- **PostgreSQL 16** in Docker (with `docker-compose.yml`)
- **pytest** for tests
- **uv** or **pip-tools** for dep management (your preference; uv is faster)

If you'd rather start without Docker: swap Postgres for SQLite by changing one connection string. Same code. I'd recommend Postgres from day one for the JSONB and full-text search reasons we discussed, but it's a one-line switch.

## Phase 1 scope (what's in / what's out)

**In:**
- DB schema for: Cards, Tokens, Keywords, Decks, DeckCards (join), Notices, PlaybookEntries
- Set-file parser: lexer → tree → typed parser output (Pydantic models)
- Ingest pipeline: parser output → derivations → upsert into DB, with the unified review modal
- Pre-upload form (set/deck mode toggle, set name, PWL defaults, deck metadata)
- Browse views: card list, card detail, keyword list, keyword detail, deck list, deck detail
- Action/notice log with state transitions and filtering
- Warning playbook auto-apply on second-and-subsequent imports

**Out (Phase 2+):**
- Reprint workflow triggers (the `printed` flag is read but no notices are generated yet — defer the diff-on-printed-card → notice path)
- Deck export to Cockatrice/text format
- Pretty diff viewer for review modal (Phase 1 just shows old/new field-by-field)
- Authentication, multi-user
- Backups / export / import of DB

## Project layout

```
mse-viewer/
├── docker-compose.yml          # postgres service + app service
├── Dockerfile                  # app container
├── pyproject.toml              # deps + tooling config
├── alembic.ini
├── .env.example
├── alembic/
│   ├── env.py
│   └── versions/               # generated migrations
├── src/mse_viewer/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app factory + routing wireup
│   ├── config.py               # pydantic-settings, reads .env
│   ├── db/
│   │   ├── session.py          # engine, SessionLocal, get_db dep
│   │   └── base.py             # DeclarativeBase
│   ├── domain/                 # ORM models — one per file
│   │   ├── card.py
│   │   ├── token.py            # may share table or share base mixin
│   │   ├── keyword.py
│   │   ├── deck.py
│   │   ├── deck_card.py        # association table with quantity
│   │   ├── notice.py
│   │   └── playbook.py
│   ├── parser/                 # MSE plaintext → typed objects
│   │   ├── lexer.py            # indent-aware tokenizer
│   │   ├── tree.py             # token stream → nested dict
│   │   ├── tags.py             # MSE inline tag normalization (mana → Scryfall, etc.)
│   │   ├── header.py           # set header (styling: defaults, etc.)
│   │   ├── card_parser.py      # card block → ParsedCard, splits multi-face
│   │   ├── keyword_parser.py   # keyword block → ParsedKeyword
│   │   ├── notes_parser.py     # PWL/Related/Status/DoNotRead extraction
│   │   └── models.py           # Pydantic ParsedCard, ParsedKeyword, ParsedSet
│   ├── ingest/                 # parser output → DB
│   │   ├── pipeline.py         # orchestrator: per-card loop, modal handoff
│   │   ├── derivations/
│   │   │   ├── design_type.py  # stylesheet+styling_data → design_type
│   │   │   ├── colors.py       # 4-tier color resolution
│   │   │   ├── identity.py     # name → stored identity ("Basic X", collision suffixing)
│   │   │   └── routing.py      # Cards vs Tokens routing
│   │   ├── warnings.py         # Warning class + collector
│   │   └── playbook.py         # auto-apply remembered overrides
│   ├── repository/             # DB access — one per aggregate
│   │   ├── cards.py
│   │   ├── keywords.py
│   │   ├── decks.py
│   │   ├── notices.py
│   │   └── playbook.py
│   ├── web/
│   │   ├── routes/
│   │   │   ├── upload.py       # GET form, POST file → start ingest session
│   │   │   ├── review.py       # per-card modal endpoints (HTMX)
│   │   │   ├── browse.py       # cards/keywords/decks list+detail
│   │   │   └── log.py          # action/notice log
│   │   ├── templates/
│   │   │   ├── base.html
│   │   │   ├── upload.html
│   │   │   ├── review_modal.html
│   │   │   ├── cards/
│   │   │   ├── keywords/
│   │   │   ├── decks/
│   │   │   └── log/
│   │   └── static/
│   │       └── style.css       # one Pico-css or Tailwind import + tweaks
│   └── services/               # cross-domain orchestration if needed
│       └── ingest_session.py   # holds in-progress import state across modals
└── tests/
    ├── unit/
    │   ├── parser/             # heavy coverage — parser is highest risk
    │   ├── ingest/             # derivation rule tables tested exhaustively
    │   └── repository/
    ├── integration/
    │   └── test_ingest_e2e.py  # whole pipeline against a fixture set file
    └── fixtures/
        ├── sample_set.mse-set-text
        ├── sample_dfc.mse-set-text
        ├── sample_basic_lands.mse-set-text
        ├── sample_keywords.mse-set-text
        └── sample_deck.mse-set-text
```

## Build order (smallest steppable increments)

The big risk is the parser. Build bottom-up so you can prove correctness at each layer before stacking the next.

1. **Skeleton + Docker** — `docker-compose up` brings up Postgres + app. FastAPI shows "hello". Alembic initialized.
2. **DB schema migration** — All ORM models, one Alembic migration, can `pytest` against it.
3. **Lexer + tree** — given a sample set file string, produce nested dicts. Just structure, no semantics. ~200 LOC + thorough tests.
4. **Tag normalization** — `<sym-auto>W</sym-auto>` → `{W}`, `<word-list-*>` strip, `<kw-N>` extraction, etc. Pure functions, hammer with tests.
5. **Notes parser** — small, well-defined: pull out `PWL:`, `Related:`, `Status: Printed`, `Do Not Read`, return cleaned `notes` string + extracted fields.
6. **Card parser + multi-face split** — assembles ParsedCard from the tree. Multi-face block emits N ParsedCard objects.
7. **Keyword parser** — produces ParsedKeyword.
8. **Header parser** — produces ParsedSetHeader (stylesheet defaults).
9. **Derivations** — colors / design_type / identity / routing — each is a pure function over ParsedCard + ParsedSetHeader. Test exhaustively against your rule tables.
10. **Repository layer** — upsert / find-by-name / append-list helpers.
11. **Ingest pipeline (CLI first, no UI)** — parse a file, run derivations, write to DB, dump warnings to stdout. Now you can prove end-to-end with a real file before any HTML.
12. **Browse UI** — Jinja templates for cards/keywords/decks/log lists + detail. Mostly read-only. This is your "verify input is correct" view.
13. **Upload + review modal UI** — wire the ingest pipeline to a web flow with HTMX-driven per-card modals. Modal state lives server-side keyed by an `ingest_session_id`.
14. **Playbook table** — when an unrecognized design_type is resolved in the modal, store the (stylesheet, styling_data) → design_type mapping and auto-apply on future imports.
15. **Tests pass, demo to yourself with one or two real `.mse-set` files.**

Steps 1–11 are pure backend; you can develop them entirely without touching HTML. That's the right way to de-risk.

## Decisions to lock before I write any code

- **Postgres (Docker) or SQLite (no Docker)** for Phase 1?
- **Keyword identity**: loose (A) or strict (B)?
- **Tokens DB**: same schema with nullable fields, or distinct ORM model?
- **Color tiers**: first-non-empty-wins (no merge), confirmed?
- **Repository pattern** vs talking to ORM directly from services. I lean toward thin repositories (just to centralize the upsert / append-list / identity-lookup quirks). Confirm or veto.
- **uv vs pip-tools** vs vanilla `pip install -r requirements.txt`. Doesn't change anything structural; pick what you'll actually run.

Once those five are answered I can scaffold the project (no logic yet, just the directory tree + empty modules + working `docker-compose up` + first Alembic migration) — that'd be a good first PR before any parser code.