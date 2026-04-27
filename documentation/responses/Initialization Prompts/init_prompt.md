## Database: Postgres vs Redis

**Don't use Redis as your primary store here.** Redis is a key-value / in-memory store optimized for caching, sessions, queues, pub/sub. Your data is highly relational — cards reference keywords, decks reference cards, notices reference decks+cards, and you'll want queries like "find every deck containing card X" or "find every card using keyword Y". That's exactly what a relational DB is built for. Redis *can* persist to disk (RDB snapshots / AOF), but you'd be hand-rolling indexes and join logic that Postgres gives you for free.

**Use Postgres**, and yes — running it in Docker exactly like you did with Redis is the standard approach. A one-liner `docker-compose.yml` with a named volume for `/var/lib/postgresql/data` gives you persistence across container restarts. You get:
- Proper foreign keys (card ↔ keyword ↔ deck ↔ notice)
- `JSONB` columns for the messy semi-structured bits like `rule_text` with its embedded `<kw-0>...` tags — you don't have to fully normalize MSE's markup
- Full-text search built in (useful for "find cards mentioning X")
- Transactions — important when a single card import touches cards, keywords, and potentially triggers notices

Alternative worth mentioning: **SQLite**. Single file, zero setup, no Docker needed, and honestly sufficient for a single-user localhost app with thousands of cards. The tradeoff is weaker concurrent writes and less rich JSON support than Postgres. If you want the "it just works" path, start with SQLite; if you want to practice the Postgres-in-Docker pattern, do that. Both are defensible.

## Backend stack (Python)

- **ORM**: [SQLAlchemy](https://www.sqlalchemy.org/) (2.0 style) with **Alembic** for migrations. Works with both SQLite and Postgres — swapping is a connection-string change.
- **Web framework**: **FastAPI** if you want a clean REST/JSON API you can hit from any frontend, with automatic OpenAPI docs. **Flask** if you want something simpler and more traditional. For this project FastAPI's type-driven validation (via Pydantic) pairs nicely with parsing MSE data into structured models.
- **MSE parsing**: `zipfile` (stdlib) to unpack `.mse-set`, then a custom parser for the `set` file. It's YAML-ish but **not valid YAML** (tabs as indent, unquoted values with colons inside, embedded XML-like tags). Don't try to `yaml.safe_load` it — write a small indent-aware line parser. Budget real time for this; it's the trickiest piece.
- **Diffing** (for the review workflow): `difflib` (stdlib) for text diffs, or `deepdiff` for structured object diffs — you'll want the latter for showing field-by-field changes in the review UI.

## UI options

Four realistic paths, from least to most effort:

1. **Streamlit / Gradio** — pure Python, no frontend code. You get file uploads, tables, forms, charts in ~50 lines. Ceiling is low though: custom interactions (diff viewers, drag-and-drop deck building, notice state machines) get awkward fast. Good for a prototype, probably not for the final thing given your feature list.

2. **FastAPI + Jinja2 templates + HTMX** — classic server-rendered HTML, HTMX sprinkles in partial-page updates without writing JS. Surprisingly capable for CRUD-heavy apps like this one. Low learning curve if you already know HTML/CSS.

3. **FastAPI backend + React/Vue frontend** — the "proper" SPA route. More power, more setup, two languages to juggle. Overkill for localhost single-user, but future-proof if you later want the "player view" you mentioned.

4. **Reflex** (formerly Pynecone) — write React-like components in pure Python, it compiles to a real React app. Middle ground between Streamlit and a full SPA.

**My recommendation**: start with **FastAPI + HTMX + Jinja** with a small CSS framework like Pico.css or Tailwind. It hits the sweet spot for your use cases: file upload, tabular query results, notice state toggles, diff views. If you later need the dual "creator vs player" interface split, the API is already there to bolt a React frontend onto.

## Other things worth thinking about now

- **The MSE parser is your biggest risk.** Before committing to any stack, write a throwaway script that parses one `.mse-set` and dumps the cards to JSON. If you can't cleanly round-trip the data, the rest of the architecture doesn't matter. Look at how the `<kw-0>`, `<atom-param>`, `<word-list-*>` tags nest — you'll need to decide whether to store them raw or parse them further.

- **Versioning / history.** Your notice workflow implies "this card changed — reprint affected decks." You'll want either a `card_versions` history table or an append-only log of changes. Decide early; retrofitting history is painful. Simplest approach: on every card update, snapshot the old row into a `card_history` table with a timestamp.

- **Keyword extraction from `rule_text`.** The `<kw-N>` tags in your example directly name the keywords used. That's your hook — you don't need NLP, just a parser. But consider: the same keyword can appear with different `<param-name>` values. Your storage model needs to separate the keyword definition (shared) from the per-card parameters (unique).

- **Images.** MSE stores `imageXX` files alongside card metadata. Decide: store blobs in Postgres (`bytea`), on disk with a path in the DB, or ignore art entirely for v1. Disk + path is standard; blobs in DB are convenient but bloat backups.

- **Identity / deduplication.** Your use case says "card with the same properties → warn." What defines "same"? Name alone? Name + cost + rules? You'll want an explicit rule, because your own prompt example shows two cards both named variants of "Baraggan" with different stylesheets — are those duplicates or intended variants? Nail this definition down before you start coding the ingestion path.

- **Don't model decks as JSON blobs.** Use a proper join table (`deck_cards` with `deck_id`, `card_id`, `quantity`). That's what makes "find decks containing card X" a trivial query and makes your update-workflow trigger cheap.

- **Package it.** Since you're using Docker for the DB anyway, write a `docker-compose.yml` with two services (app + db) from day one. Saves pain later and means you can blow it away and rebuild cleanly.