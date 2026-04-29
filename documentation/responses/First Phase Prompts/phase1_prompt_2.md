# Phase 2 — what comes next

The big theme of Phase 2 is **closing the workflow loop**: Phase 1 gets data *in*, Phase 2 makes the data *act* (notices, reprint triggers, deck management). Grouped by what changes vs. what gets added.

## 1. Notice workflow (the headline feature)

Deliberately omitted from Phase 1. Schema is already there (`LogEntry.kind = notice`, states `unread → standby → issued → completed`), so it's all new code, no migration.

- **Diff detection on ingest**. When `commit_face` finds an existing card with `printed: true` and the incoming face changes any *meaningful* field (rule_text, keywords, colors, casting_cost, P/T), enqueue a notice instead of silently updating.
  - Decision needed: do we *block* the update until the notice is processed, or update + write the notice and trust the user to follow up? Default proposal: "update + write notice" — closer to spec.
- **Affected-deck fan-out**. For a card-change notice, the affected set = every deck whose `deck_cards` references that card. For keyword changes (stretch), affected = every card linking the keyword. Stored in the existing `affected_deck_ids` JSONB column.
- **Notice state machine UI**. List view with kind/state filter pills (we have the GET handler; needs notice-specific transitions). Transitions: `unread → standby` (acknowledge), `standby → issued` (with required `storage_location` text), `issued → completed`.
- **Notice detail page**. Show: which card, which decks, the field-by-field diff that triggered it, free-text storage-location note when `issued`.
- **Bulk notice batching**. If one set ingest produces 12 reprint notices, surface them on the post-ingest summary page so the user can resolve/dismiss in one screen.

## 2. Phase-1 carryovers to finish

- **Deck ingest flow**. Schema is in; we need: pre-upload form for deck mode (format, commander dropdown, package, related-decks), a parser for deck files, per-card review modal reused, deck commit step. Quantities are encoded as **repeated `card:` entries with the same name** (a 4-of Zap = four `card:` blocks named Zap) — the deck parser collapses repeats into `DeckCard.quantity`.
- **Manual CRUD for cards / keywords / decks**. init_prompt_3 says "manual edits are authoritative". Currently you can only add things via set-file ingest. Add edit/create forms for each (the repos already have the upsert methods).
- **Pretty diff viewer in the review modal**. Currently the "modifies printed card" warning is just text. Phase 2 should render side-by-side old/new for each changed field. `deepdiff` is in init_prompt's stack list for this reason.
- **IngestSession persistence (optional)**. Sessions are in-process memory; a server restart loses them. If you ingest a 200-card set and walk away mid-review, this matters. Easy fix: serialize to an `ingest_sessions` table.
- **Multi-face cross-link FK strengthening**. Face 1 ↔ face 2 link is currently a name string in `related_cards`. Works, but a `card_face` row would let UI navigate without a name lookup. Defer unless a perf or correctness issue surfaces.

## 3. UI polish

- **Browse filters**: by color, by keyword, by set, by rarity, by design_type. GIN indexes already make these cheap.
- **Pagination + sort** on `/cards`, `/tokens`, `/keywords`. Currently unbounded.
- **Mana-symbol rendering**. We store Scryfall-style `{W}{2/U}{X}`; Phase 2 can render glyphs instead of literal braces. Pure CSS / SVG sprites.
- **Color chips** in card lists.
- **Inline rule_text rendering** with keyword links — when `<kw-N>` referred to a known keyword, link to `/keywords/{id}` from the card detail page.
- **HTMX on the review modal**. Each accept/reject is a full page navigation today. HTMX swaps feel snappier and let us lift "next/previous" to keys.

## 4. Decisions confirmed (2026-04-28)

The three open ambiguities are resolved:

- **Deck quantities** — repeated `card:` blocks with the same name in the deck file. The deck parser will collapse repeats into `DeckCard.quantity` rather than expecting a count field.
- **Stub merge** — by `match:` string, **not** by `keyword:` field. Strict identity B from init_prompt_4 is the only rule that matters: `Suspend(cost)` and `Suspend(number)` are different keyword rows, full stop. Phase 1 currently merges stubs by `keyword:`-field, which contradicts this — **Phase 2 must rework `KeywordRepository.ensure_stub` / `upsert_from_parsed` to key everything off the match string**. Cards that reference a keyword via `<kw-N>...<key>X</key><atom-param>...</atom-param></kw-N>` will resolve to a definition whose match-string structure matches the per-invocation param signature; cards that have only `<key>X</key>` (no atom-params) link to a stub keyed by that bare key text.
- **Evolution / Hero** — not an exception. Cards on `m15-altered-beyond` whose `super_type` contains *Evolution* or *Hero* get **`design_type = Normal`** (or, if you'd rather distinguish them in browse views, a single shared `Evolution` design_type that covers both). Phase 1 currently flags these as needs-user — that's a bug to fix in Phase 2 alongside the rule-table cleanup.

## 5. Operational / quality

- **Tests** — parser fixtures from real `.mse-set` payloads, exhaustive tables for `derive_colors` / `derive_design_type`, an end-to-end ingest test against a fixture file.
- **DB export/import**. `pg_dump` scripts in the compose project, plus a "fresh re-ingest" path for when the schema changes.
- **Structured logging**. Today errors print to stderr; a request-scoped log that surfaces in the action log when ingest blows up would be more useful.

## 6. Stretch / Phase 3 territory

- Auth + multi-user (init_prompt mentioned the "creator vs player" split).
- Cockatrice / plain-text deck export.
- Image storage (currently ignored — disk path + `bytea` were the two options).
- The "player view" — read-only frontend consuming the existing FastAPI as a JSON API.

## Suggested order

1. Open-questions sweep (so the work is unblocked).
2. Notice workflow (diff + fan-out + state machine + UI).
3. Deck ingest flow.
4. Manual CRUD.
5. Browse filters / pagination / mana glyphs.
6. Tests.
7. Polish round on whatever surfaces from manual testing.
