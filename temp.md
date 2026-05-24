## 🛠️ Phase 1.6 — Frame Expansion, CRUD & Workflow Polish

This PR introduces **Phase 1.6**, a multi-wave pass that expands the parser to four new MSE frame families, builds out manual CRUD + deck ingest + workflow surfaces, and lands a real reminder-template evaluator.

The goals of this phase are **feature expansion and correctness**:
- Recognise MSE's specialty frames (Planeswalker, Emblem, Saga, Leyline) end-to-end
- Close the manual-edit and deck-ingest loops that Phase 1 deferred
- Evaluate inline reminder templates (nested `if/elseif/else`, function predicates)
- Tighten the schema — drop columns that were redundant or never used
- Continue the Phase 1.5 trajectory: more correctness, more usability, no rewrites

---

## ✅ Summary of Changes

### 🃏 Wave 1 — Specialty frame parsers
_New frame families, plus the inline-template bug that exposed them._

#### 🧩 Frame parsers (all four)
- **Planeswalker** — detected by `super_type` (not stylesheet); `special_text` → `rule_text`; `<margin:130:0:0>` wrappers stripped; loyalty parsed as `starting_loyalty`; alias-without-Evolution triggers the review modal so non-Normal design types can be picked
- **Emblem** — detected by `Emblem` supertype; auto-routed to Tokens DB; `sub_type` (producing planeswalker) auto-added to `related_cards` with reverse cross-link; `rarity: special` no longer triggers a modal
- **Saga** — detected by `Saga` subtype + `Enchantment` supertype; `special_text` → `rule_text`; italic-only lines extracted as flavor with the first non-empty line protected (Read Ahead / "As this Saga enters" reminders never become flavor)
- **Leyline** — detected by `Leyline` subtype + `Enchantment` supertype; italic-only segments in `rule_text` extracted into `flavor_text`
- Frame-vs-stylesheet typing mismatch surfaces a new `frame_type_mismatch` warning

#### 🐞 Reminder template bug
- Optional `else` branch in `if/then` constructs
- New `has_pt()` function-call predicate threaded with per-card `card_facts`
- Keyword detail view leaves verbatim (no card context); card detail view evaluates

---

### 🗃️ Wave 2 — Workflow surfaces & feature buildout
_Closes the long-standing manual-edit and deck-ingest gaps._

#### 📥 Deck ingest flow
- Pre-upload form with mode toggle (`Set` / `Deck`)
- Repeated `card:` blocks per name collapse to `DeckCard.quantity`
- Cards already in the DB skip review; only previously-unknown cards reach the modal
- Deck row + DeckCard links created automatically at session-finish time
- Token references in deck files are now first-class deck members

#### ✏️ Manual CRUD
- Create / edit / delete forms for Cards, Tokens, Keywords, Decks
- Keyword field on card/token edit accepts names (e.g. `Haste, Ammo 2`) — resolved to ids server-side via the existing `find_for_card_ref` resolver
- Related-card casing auto-corrects against the canonical row name

#### 🔍 Diff viewer
- Identity-conflict warnings now compute a per-field diff
- `modifies_printed` warning raised when the existing row was `printed=true`
- Modal renders old-vs-new in a side-by-side table

#### 📊 Dashboards
- `/keywords/stubs` — keyword stubs needing definition
- `/related/missing` — every `related_cards` entry that doesn't resolve

#### 🔁 HTMX-inline log transitions
- Resolve / reopen swap the row in place via `hx-swap="outerHTML"` against a `log/_row.html` partial
- Falls back to the original 303-redirect-with-anchor when called without HTMX

#### 🔎 Search expansion
- Cards / Tokens search now matches name, rule_text, flavor_text, alias, card_type, card_subtype, and related_cards (JSONB cast)
- Whitelist tags (`<i>` / `<b>` / `<em>`) stripped via Postgres `regexp_replace` so a query for `first-strike` matches text stored as `<i>first-strike</i>`
- Keywords gain their own search bar across name / reminder / rules

---

### 🧬 Wave 3 — Schema tightening
_Four migrations. Drops two columns that were redundant, drops one that was wrong for the model, and reshapes deck membership._

#### 🗄️ Migrations
- `0003` — `cards.starting_loyalty` (Planeswalker support)
- `0004` — drops `cards.abilities`, `tokens.abilities`, `tokens.sets`
- `0005` — drops `tokens.design_type`
- `0006` — `deck_cards.token_id`, `card_id` nullable, XOR check + partial-unique indexes

#### 🧹 Column hygiene
- `abilities` was always identical to `rule_text` after canonicalization — dropped
- Tokens never need per-set provenance — `tokens.sets` dropped
- Tokens don't carry a design taxonomy — `tokens.design_type` dropped
- `design_type`, `sets`, `rarity`, `power_level`, `starting_loyalty` now Card-only (off the mixin)

#### 🎯 Routing
- `Emblem` supertype added to `is_token_route`
- Frame-family short-circuits in `derive_design_type` (Planeswalker / Emblem / Saga / Leyline → Normal regardless of stylesheet)
- DFC / saga / leyline / emblem stylesheets allowlisted to Normal (no more "stylesheet not in rule table" modals)

#### 🃏 Decks hold tokens
- `DeckCard` can reference either a Card or a Token (CHECK constraint enforces exactly one)
- Deck detail / edit / finalize all updated; edit form accepts `<qty> t<id>` syntax for token rows

---

### 🧠 Wave 4 — Reminder template evaluator + UI polish
_Real recursive parser. Final round of UX gates._

#### ✨ Nested if/elseif/else evaluator
- Replaced the over-match-guarded regex with a brace-balanced parser
- Chains like `{ if has_pt() then "creature" else if is_artifact(card.super_type) then "artifact" else "permanent" }` evaluate correctly per-card
- Function predicates: `has_pt()`, `is_artifact(arg)`, `is_creature(arg)`, `is_enchantment(arg)`, `is_land(arg)` — `card.path` arg resolution
- Keyword detail page leaves templates verbatim (no card context)
- `{B}` mana symbols and other braces survive untouched

#### 🔁 Keyword updates propagate
- Renaming a keyword or editing its reminder rewrites `rule_text` on every linked Card / Token
- Word-boundary regex for the rename; literal substring replace inside parens for the reminder body

#### 🚫 Keyword reject list
- Explicit reject patterns (`Evolve <atom-param>n</atom-param>`, `Evolve <digits>`) — dropped at parse time and at card-ref resolve time
- Both source paths log to the action log so the user can audit

#### 🎨 UI gates
- Global "Additional info" toggle in the nav header (localStorage-persisted)
- Sets / Alt arts / Design type / Alias columns and rows hidden by default
- Empty P/T and Alias rows hide automatically on the detail view (parity with how `starting_loyalty` already worked)
- Commander / tester format reveals Commander, Package, Related-decks fields
- Default deck size auto-bumps from 60 → 100 when commander/tester is selected
- Deck detail gets a Total row summing `quantity` across cards & tokens

#### 🧩 Rendering improvements
- Comma-split rule for keyword lines: strong (resolves OR has inline reminder) / shaped (1–3 alpha words, no sentence-internal words) / reject classifier — splits `Haste, vigilance, reach, resilient (...)` cleanly while leaving sentences intact
- `<B>` substrings (e.g. from malformed mana markup) no longer get promoted to bold tags — `<b>` removed from the re-enabled tag whitelist
- HTMX script bundled in `base.html`

---

### 📚 Documentation pass

- Unified `documentation/files/todolist.md` covering every outstanding item across the whole app — not just Phase 1.6 carry-overs. Sourced from `report.md`, every prompt directory, and every response file.
- `CLAUDE.md` gains a documentation-navigation guide + canonical migration schedule so future sessions skip re-reading prompt history.
- Per-prompt response files saved under `documentation/responses/Phase 1.6 Prompts/` — five files, one per prompt, with "Files changed" sections that double as the changelog.

---

## 📌 Issues Closed

This PR closes:

<!-- TODO: fill in the closed issue numbers -->

---

## 🧪 Notes for Reviewers

- Wave 1 introduces **four new frame parsers** plus one **schema column** (`cards.starting_loyalty`)
- Wave 2 ships **new routes**, **new templates**, and **no schema changes** of its own
- Wave 3 ships **three schema-tightening migrations** in sequence (`0004`, `0005`, `0006`)
- Wave 4 ships a **real recursive parser** for reminder templates plus a **content-rewrite propagation** path on keyword edits
- Parser changes follow the same purity rule as Phase 1 — `parser/` and `ingest/derivations/` stay DB-free
- Schema changes are non-destructive in spirit: dropped columns either held duplicate data (`abilities`) or were never populated meaningfully for the target model (`tokens.sets`, `tokens.design_type`)
- `deepdiff` is now a hard dependency (used by the diff viewer)

## 🚀 Impact

- Adds full ingest support for the four most-requested specialty frames
- Closes the manual-edit loop — every entity can be created / edited / deleted via UI
- Closes the deck-ingest loop — files in, deck rows out, tokens included
- Eliminates raw `{ if … then … else … }` syntax on rendered card pages
- Renames / reminder-edits on keywords now self-heal across the card corpus
- UI is significantly less noisy by default thanks to the additional-info toggle
- Search reaches the fields that actually matter (rule text, flavor, related cards, types)
- Workflow surfaces (stub dashboard, missing-related view, HTMX log) prepare the ground for the Phase 2 notice fan-out
