# Unified todo list

Single source of truth for outstanding work across the entire app. Sourced from `documentation/report.md`, the staged prompts in `documentation/prompts/`, and the response files in `documentation/responses/`. Each entry notes the origin so it's easy to trace back.

When closing an item, leave it here with a strikethrough and a short note about the commit / migration that finished it; that keeps the audit trail visible without the file becoming an archive.

---

## A. Headline missing features (from the spec)

These are described in [`documentation/report.md`](../report.md) §1.2 use cases and §1.3 system context but the implementation hasn't started. They are the largest gaps to "feature-complete Phase 2".

### A1. Notice workflow — the headline Phase 2 feature

> Source: [report.md §1.2 use case 4](../report.md), [phase1_prompt_2.md §1](../responses/First%20Phase%20Prompts/phase1_prompt_2.md), `init_prompt_4.md` decision 7.

The schema is already there: `LogEntry.kind = notice`, states `unread → standby → issued → completed` — all defined on [`domain/notice.py`](../../src/mse_viewer/domain/notice.py). Today only `kind=action` rows are written.

- [ ] **Diff detection on ingest.** When `commit_face` finds an existing card with `printed=true` and the incoming face changes a meaningful field (rule_text, keywords, colors, casting_cost, P/T), enqueue a notice. Open decision: block the update until the notice clears, or update + write notice (default: update + write).
- [ ] **Affected-deck fan-out.** For a card-change notice, the affected set is every deck whose `deck_cards` references that card. For keyword changes (stretch), every card linking that keyword. Stored in the existing `LogEntry.affected_deck_ids` JSONB column.
- [ ] **Notice state-machine UI.** List view with kind/state filter pills (the GET handler already supports the filter; needs notice-specific transitions). Transitions: `unread → standby` (acknowledge), `standby → issued` (with required `storage_location` text), `issued → completed`.
- [ ] **Notice detail page.** Show: which card, which decks, the field-by-field diff that triggered it, free-text storage-location note when state is `issued`.
- [ ] **Bulk notice batching.** If one set ingest produces 12 reprint notices, surface them on the post-ingest summary page so the user can resolve/dismiss in one screen.
- [ ] **Notice fan-out for keyword updates.** When a keyword's name or reminder changes, every Card / Token whose `keyword_ids` mentions it gets a notice that says "rule text reflowed". Phase 1.6 prompt 4 item 4 implemented the find-and-replace; the notice side is still missing.

### A2. Card export — free-form text dump

> Source: [report.md §1.2 use case 3](../report.md): "Users can generate exports of selected card data as text files in a consistent, predefined format."

- [ ] **Export endpoint.** Pick a query → emit a `.txt` payload (deck-list shape, or "card-detail dump per card"). The current `/decks/{id}` page has no export action.
- [ ] **Format selection.** Plain text vs. Cockatrice vs. MTGA-style (stretch; phase 1 spec only mentions "consistent, predefined format" — pick one or surface a toggle).

### A3. Public Hooks ("player view")

> Source: [report.md §1.2 use case 6](../report.md), [phase1_prompt_2.md §6](../responses/First%20Phase%20Prompts/phase1_prompt_2.md).

The whole "Coming Soon" tier from the spec. Read-only over-the-web hooks. Auth needed.

- [ ] **Read-only JSON API.** Cards / Tokens / Keywords / Decks endpoints exposing query and detail. The existing FastAPI app already produces HTML — most repos already return rows, so a JSON serialization layer is the bulk of the work.
- [ ] **Permission boundary.** Creator vs. viewer roles. Viewer hits the public API; creator hits the HTML app.
- [ ] **Print-request submissions.** Viewers can request a print of a card; creator gets a notice. Power-allowance threshold gate.
- [ ] **Modification suggestions.** Viewer-side form to propose edits to a card / keyword / deck; lands in the action log for the creator to review.
- [ ] **Auth.** Today the app is single-user, no auth. The split needs at minimum API keys / OAuth.

### A4. Deckbuilder support ("Coming Soon")

> Source: [report.md §1.2 use case 7](../report.md), [report.md §1.3](../report.md).

- [ ] **Manual deckbuilder.** Browse-and-add UI under format constraints (Power allowance, color identity).
- [ ] **Automated deck generator.** Take a theme / archetype + Power threshold, produce a candidate deck balancing card synergies. Recommendation engine territory.

---

## B. Active design rework

These are large, touch the data model, and should land together rather than incrementally so the migration story stays clean.

- [ ] **Redefine the Design Type taxonomy.** Phase 1.6 prompt 3 bug 9. The stylesheet → design_type table in [phase1.6_prompt3.md](../responses/Phase%201.6%20Prompts/phase1.6_prompt3.md) is the input. Today's code accumulates short-circuits in `derive_design_type` — redo the taxonomy in one pass.
- [ ] **Unify keyword stubs and missing-related-cards into one model.** Phase 1.6 prompt 3 change 8. Two surfaces today (`/keywords/stubs`, `/related/missing`); should be one "needs authoring" workflow.
- [ ] **Stub-merge keyed by match-string only.** Phase 1 carryover — `ensure_stub` / `upsert_from_parsed` still allow the old keyword-field heuristic to leak through. Strict identity B from `init_prompt_4 #2`: `Suspend(cost)` and `Suspend(number)` are different keyword rows.
- [ ] **Deck-ingest design completion.** Phase 1.6 prompt 4 item 7 (partial — empty `sets[]` propagation fixed). Phase 1.6 prompt 5 bug 3 added tokens as deck members. Outstanding: unified missing-refs model (folds into item above), and proper duplication-modal handling when a deck card already exists under a different kind.
- [ ] **Evolution / Hero auto-Normal cleanup.** Phase 1 carryover — `m15-altered-beyond` Evolution/Hero cards used to be flagged needs-user; the rule should be design_type=Normal for both. Most of this landed in Phase 1.6 prompt 1, but the rule-table cleanup is part of the wider Design Type redo above.

---

## C. Search

- [ ] **Advanced search page.** Phase 1.6 prompt 3 bug 7. Per-field inputs (name, type, subtype, P/T, cost, color, design_type, printed, rarity, etc.) on its own URL, alongside the existing basic bar.
- [ ] **Negation operator on the basic search bar.** Phase 1.6 prompt 3 bug 7. `Vigilance -Haste -"This enters tapped"` excludes results containing Haste or the quoted phrase.
- [ ] **Quoted-phrase tokenizer.** Phase 1.6 prompt 4 bottom note. Same parser as the negation operator.
- [ ] **Browse filters: by color, by keyword, by set, by rarity, by design_type.** Phase 1 carryover from `phase1_prompt_2.md §3`. GIN indexes already make these cheap.
- [ ] **Pagination + sort on `/cards`, `/tokens`, `/keywords`.** Currently unbounded. From `phase1_prompt_2.md §3`.

---

## D. Persistence / schema

- [ ] **IngestSession persistence.** Phase 1.6 prompt 2 item 7. In-process memory only; restarting uvicorn drops in-flight reviews. Easy fix: serialize to an `ingest_sessions` table.
- [ ] **Multi-face cross-link FK.** Phase 1.6 prompt 2 item 8. Face 1 ↔ face 2 link is a name string in `related_cards` today. A proper `card_face` row would let UI navigate without a name lookup. Defer unless a perf or correctness issue surfaces.
- [ ] **Set-level PWL defaults stored on the set record.** From `init_prompt_2.md` follow-up — Phase 1 only takes PWL defaults as transient form input. Re-importing the same set forces the user to re-enter them. Needs a `sets` table.

---

## E. Reminder-template / rule_text engine

- [ ] **Full recursive-descent parser for reminder templates.** Phase 1.6 prompt 4 item 8 landed brace-balanced + nested if/elseif/else + a few `is_*(...)` predicates. Outstanding: more function predicates as the corpus grows; richer arg paths (`card.colors`, `card.rarity`, etc.).
- [ ] **Keyword edit propagates rule_text canonically.** Phase 1.6 prompt 4 item 4 landed best-effort find-and-replace. Outstanding: edge cases where the old reminder body is a substring of another body, or the new name is a substring of unrelated rule_text. The real fix is to re-canonicalize from a stored "raw" rule_text we don't yet keep.

---

## F. UI polish

- ~~**Evolution / Hero row hue + tag chip.**~~ Landed in Phase 2.0 prompt 1 — `is_evolution` / `is_hero` template globals + `.row-evolution` / `.row-hero` row hue classes + `.chip-evolution` / `.chip-hero` chips in detail & list views.
- ~~**Mana-symbol rendering.**~~ Landed in Phase 2.0 prompt 1 — `_inject_mana_symbols` post-processes any `{X}` token through `render_text` / `render_cost`; CSS glyphs cover W U B R G C O L P K E N S T X Y Z, two-color hybrids, numeric hybrids (2/W…), phyrexian hybrids, and three-color hybrids.
- [ ] **Color chips in card lists.** From `phase1_prompt_2.md §3`.
- [ ] **Inline rule_text keyword links.** When `<kw-N>` referred to a known keyword, link to `/keywords/{id}` from the card detail page. From `phase1_prompt_2.md §3`.
- [ ] **HTMX on the review modal.** Each accept/reject is a full page navigation today. HTMX would let us lift "next/previous" to keys. From `phase1_prompt_2.md §3`.
- [ ] **Triple+ hybrid mana display verification.** `G/U/R` should render `(G/U/R)`. Tokenizer already handles it — needs a test against real production data.
- [ ] **Datalist multi-select for the colors field.** From `phase1.5_prompt2.md` — current `<datalist>` only suggests against the whole input. A chip-based multi-select would replace the comma-separated string.
- [ ] **Additional-info toggle resting state.** Phase 1.6 prompt 4 item 5 landed (off by default). Revisit: is there a column the user always wants on?
- [ ] **Pretty diff viewer with deepdiff's structured (tree) mode.** Phase 1.6 prompt 2 item 3 landed a flat per-field table. Tree mode would handle JSONB list-set semantics better.
- ~~**Mark printed cards visually.**~~ Landed in Phase 2.0 prompt 1 — `.chip-printed` on the detail page header, `.printed-tick` icon in the cards list "Printed" column.

---

## G. Operational / quality

- [ ] **Tests.** From `phase1_prompt_2.md §5`. Parser fixtures from real `.mse-set` payloads, exhaustive tables for `derive_colors` / `derive_design_type`, an end-to-end ingest test against a fixture file. There's no `tests/` directory yet.
- [ ] **DB export / import.** `pg_dump` scripts in the compose project, plus a "fresh re-ingest" path for when the schema changes.
- [ ] **Structured logging.** Today errors print to stderr; a request-scoped log that surfaces in the action log when ingest blows up would be more useful.
- [ ] **Action-log retention / rollup.** No retention policy today — the log grows unbounded. Eventually need a "older than N days, auto-archive resolved entries" mechanism.

---

## H. Stretch / Phase 3 territory

> Source: [phase1_prompt_2.md §6](../responses/First%20Phase%20Prompts/phase1_prompt_2.md).

- [ ] **Auth + multi-user.** Init_prompt mentioned creator vs. player split — picks up the Public Hooks (A3) work too.
- [ ] **Cockatrice / plain-text deck export.** Common community deck formats. Folds into A2.
- [ ] **Image storage.** Currently ignored (the `image:` MSE field). Either disk-path or `bytea` blob — discussed in init_prompt_2 follow-ups.
- [ ] **Read-only frontend SPA.** A React/Vue consumer of the JSON API once it exists.

---

## Completed (kept for audit)

- ~~Phase 2.0 prompt 1 — UI uplift, mana glyphs, Hero / Evolution / rarity chips, printed indicator.~~ Landed in [prompt1 response](../responses/Phase%202.0%20Prompts/phase2_prompt1.md). No migration.
- ~~Phase 1.6 prompt 1 — Planeswalker / Emblem / Saga / Leyline frame parsing.~~ Landed in [prompt1 response](../responses/Phase%201.6%20Prompts/phase1.6_prompt1.md). Migration `0003` (cards.starting_loyalty).
- ~~Phase 1.6 prompt 2 — bug-bash + deck ingest + diff viewer + HTMX log + CRUD + stub dashboard.~~ Landed in [prompt2 response](../responses/Phase%201.6%20Prompts/phase1.6_prompt2.md).
- ~~Phase 1.6 prompt 3 — Bugs 1–13 except deferred; `abilities` + `tokens.sets` dropped; keyword reject list.~~ Landed in [prompt3 response](../responses/Phase%201.6%20Prompts/phase1.6_prompt3.md). Migration `0004`.
- ~~Phase 1.6 prompt 4 — items 1–8 + 3 bug/changes; nested if/elseif evaluator; `tokens.design_type` dropped.~~ Landed in [prompt4 response](../responses/Phase%201.6%20Prompts/phase1.6_prompt4.md). Migration `0005`.
- ~~Phase 1.6 prompt 5 — Bugs 1–4; decks-hold-tokens schema; default size 100 for commander; comma-split classifier.~~ Landed in [prompt5 response](../responses/Phase%201.6%20Prompts/phase1.6_prompt5.md). Migration `0006`.
- ~~Phase 1.5 — all three waves (parser bug-fixes, alias column, related-card links, reminder pretty-printer).~~ See [Phase 1.5 responses](../responses/Phase%201.5%20Prompts/).
- ~~First Phase — Cards/Tokens/Keywords/Decks schema, ingest pipeline, review modal, action log, base UI.~~ See [First Phase responses](../responses/First%20Phase%20Prompts/).
- ~~Initialization — stack pick, repo layout, identity rules, design taxonomy v1, playbook table.~~ See [Initialization responses](../responses/Initialization%20Prompts/).
