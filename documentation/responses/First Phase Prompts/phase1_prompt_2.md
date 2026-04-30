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
- **Planeswalker parsing** (added 2026-04-30). The Planeswalker frame uses a different shape: loyalty cost lines (`+1:`, `-X:`, `0:`), starting loyalty, ability tiers — none of which the Phase 1 parser recognises. Need a planeswalker-specific face extractor + a place to store the loyalty bands.
- **Emblem parsing** (added 2026-04-30). Emblems are a thinner Planeswalker output (just rule_text, no cost / P/T / loyalty); they may be modelled as Tokens with a special design_type or a separate `emblems` table. Decide before writing the parser.
- **Saga parsing** (added 2026-04-30). Sagas have ordered chapters (`I`, `II`, `III`, …) with their own rule_text bodies and an "after the last chapter, sacrifice" rule. Needs a chapter list on the card record.
- **Leyline parsing** (added 2026-04-30). Leylines aren't structurally novel but they trip the design-type rules: most are on `m15-altered-beyond` with a self-replacing-from-hand ability that may want a tagged Design Type or a special note for the player view.
- **Stub tracking dashboard** (added 2026-04-30). Every `is_stub=True` keyword is a TODO — once a real definition exists the absorption logic runs automatically (verified 2026-04-30), but a "Stubs needing definition" page would let you eyeball the queue without hand-querying. Same idea for missing Related Cards: they're currently just strings on `related_cards` with no row to point at — Phase 2 should add a real "missing referenced cards" view.
- **Stub auto-definition from card-text reminders** (added 2026-04-30, corrected). Real MSE files wrap reminders the same way for tokens and ordinary cards (`<atom-reminder-core>`, `<atom-reminder-custom>`, `<atom-reminder-expert>` — the user confirmed both Angry Apple and 3o Apple use the wrapper). The current behaviour leaves Haste / Strikethrough / etc. as bare stubs on ordinary cards even though their rule_text carries reminder bodies — likely a codepath bug rather than a parser limitation. Phase 2 fix:
  1. **Investigate why ordinary cards don't end up with the captured reminder** even though the format matches the token case. Likely candidates: (a) `ensure_stub` hits an existing reminder-less stub from an earlier card and the update predicate fails for the wrong reason, (b) the rule_text raw value reaching the parser has been rewritten by an earlier transform, (c) the import order means the keyword row was created during the *first* card's pass with no reminder and never refilled. Add a small diagnostic that logs the captured reminder per ref during ingest.
  2. **Strip the outer `(` and `)`** from the captured body before storing — the parens belong to the rendering layer, not the field. So `(This creature deals first-strike, …)` becomes `This creature deals first-strike, …`.
  3. **Auto-promote `is_stub=False` for single-word keywords** (no spaces, no `<atom-param>` slots) once a reminder is captured — applies to both Cards and Tokens equally. The reminder text *is* the definition for those: `name = bare key text`, `source_keyword_field = same`, `accepted_parameters = []`, `reminder = captured body`, `is_stub = False`. Multi-word / parameterized keywords still need an explicit `keyword:` block; leave them as stubs and let the existing structural-match absorption merge them when the real definition lands.
  4. **UI labels follow from the data**: with auto-promotion in place, the "(no definition yet)" annotation disappears for the auto-promoted rows because they're no longer `is_stub`. Keep "(stub)" only for the rows that genuinely have neither a definition nor a captured reminder.
- **Alias field on Cards / Tokens** (added 2026-04-30). MSE's `alias:` field carries free-text relationship info (`alias: Created by 3o Apple`, `alias: Evo: …`). Phase 1 only mines it for structured prefixes (`Evo:`, `Evolved:`, `Related:`) which extract into `related_cards`; *anything else* is dropped at commit time. There is **no `alias` column on either the `cards` or `tokens` table** today (verified 2026-04-30). Phase 2:
  1. Add `alias: str | None` to `CardCoreMixin` so both Card and Token gain the column. New Alembic migration.
  2. Persist `face.alias` verbatim during commit (after the prefix mining still runs to populate `related_cards`).
  3. Surface the alias in the UI: a row in the detail page's `<dl>`.
- **Override-field dropdowns** (added 2026-04-30). When the modal asks for a Design Type / Rarity / Color override, prefill a `<datalist>` with values already in the DB so the user can pick from past entries instead of retyping (init_prompt_5 #3).
- **Conditional reminder pretty-printer** (added 2026-04-30). MSE reminders embed templating logic such as ``{param1} poison { if param1.value=="1" then "counter." else "counters." }``.  Phase 2 should evaluate these inline expressions for display (init_prompt_5 #4) — at minimum the `if/then/else` plurality form, ideally the full mini-expression grammar.
- **Tag-insensitive search/queries** (added 2026-04-30). Free-text search across `rule_text` / `flavor_text` should ignore the preserved ``<i>...</i>`` (and any future whitelisted) tags so a query for *"This creature deals first-strike"* matches a row stored with the italic markup. Implement by stripping the whitelist tags in a normalized search column or via a Postgres `regexp_replace` inside the WHERE clause (init_prompt_5 #12).
- **Triple+ hybrid mana display** (added 2026-04-30 by user). `G/U/R` and any higher-order hybrid slot should render in parens `(G/U/R)` like the two-color hybrids do. The tokenizer already emits the slot intact; only `render_casting_cost` needs the `"/" in t` test broadened — already does that today, so this item is mostly *verify in production data and add a test case*.
- **Semicolon as line separator in rendered rule text** (added 2026-04-30 by user). When rule_text contains `Keyword1; Keyword2; Ability …`, render each segment on its own line (the `;` itself hidden — pure separator). Storage stays as-is so the round-trip back to MSE format isn't lossy; only the `render_text` / `render_text_snippet` filters split on `;` for display.
- **HTMX-inline log transitions** (added 2026-04-30). Eliminate the redirect entirely so the page never reflows (init_prompt_5 #11 — scroll anchor is the Phase 1 mitigation).
- **IngestSession persistence (optional)**. Sessions are in-process memory; a server restart loses them. If you ingest a 200-card set and walk away mid-review, this matters. Easy fix: serialize to an `ingest_sessions` table.
- **Multi-face cross-link FK strengthening**. Face 1 ↔ face 2 link is currently a name string in `related_cards`. Works, but a `card_face` row would let UI navigate without a name lookup. Defer unless a perf or correctness issue surfaces.

- User addition to this plan: **Reduce columns in the cards / tokens browse tables** - right now, the tables for cards and tokens show some columns that shouldn't be shown in the overview, such as the "Alt arts", the "Design". We should decide exactly which columns to keep in this showcase and which columns should only appear as rows in the detail page. For now until the UI beautification, don't show these columns.
- User addition to this plan: Also if possible, don't show keyword reminder text in the small rules text snippets in the table views, only the keywords and other abilities
- Saving in Tokens DB for certain cards triggers an internal server error. Here is a card that does so:
card:
	stylesheet: m15-altered-beyond
	stylesheet_version: 2020-09-04
	has_styling: true
	styling_data:
		frames: 
		legend_crown: standard
		other_options: 
		text_box_mana_symbols: magic-mana-small.mse-symbol-font
		level_mana_symbols: magic-mana-large.mse-symbol-font
		overlay: 
	notes: 
	time_created: 2023-12-30 18:53:34
	time_modified: 2025-05-16 03:58:26
	card_color: white, black, red, hybrid, horizontal
	name: Doom-Bringer
	alias: 
	casting_cost: 6RWB
	image: image80
	image_2: 
	mainframe_image: 
	mainframe_image_2: 
	super_type: <word-list-type-en>Evo-T Creature</word-list-type-en>
	sub_type: <word-list-race-en>Mushroom</word-list-race-en><atom-sep> </atom-sep><word-list-class-en>God</word-list-class-en><soft><atom-sep> </atom-sep></soft><word-list-class-en></word-list-class-en>
	rarity: special
	rule_text:
		<kw-1><nospellcheck><key>Haste</key></nospellcheck><atom-reminder-core> <i-auto>(This creature can attack and <sym>T</sym> as soon as it comes under your control.)</i-auto></atom-reminder-core></kw-1>
		<kw-1><nospellcheck><key>Omni-strike</key></nospellcheck><atom-reminder-custom> <i-auto>(Whenever this creature attacks and deals combat damage, it deals that much damage to each creature the defending player controls.)</i-auto></atom-reminder-custom></kw-1>
		<kw-1><nospellcheck><key>Voidsnare</key></nospellcheck><atom-reminder-action> <i-auto>(Permanents you don’t control that are dealt damage by this creature are exiled.)</i-auto></atom-reminder-action></kw-1>
	flavor_text: <i-flavor>Destruction and chaos, personified.</i-flavor>
	power: 4
	toughness: 6
	card_code_text: 
	card_code_text_2: 
	card_code_text_3: 
	copyright: 
	copyright_2: 
	copyright_3: 

- Creatures with Evo-T in their supertype should also be auto-routed to the Tokens DB just like tokens (since to me, Evo-T are basically tokens). However, Evo-Ts have the exact same name as another card that should be sent to the regular card db. Thus, the Evo-T should also reference that card from the card db.
- In the UI, Related cards are only a list of texts, and aren';'t linked to the cards with those names. They should (this may also require a DB modification to that column's value type, please check)
- In the table view, Evolution cards should probably have a light-purple hue background for that row, and Heroes a light-gold hue background for that row. In the detail view, the respective hues should be on the entire page. Additionally, in the header that specifies the name & type of the card, for Evolution and Hero cards, a respective text box should appear as a sort of tag to the right side of that area. The object should be a rectangle colored in stronger/darker hues of the respective color, with white text on top that says "Evolution"/"Hero". Though all of this may also be catalogued as an advanced UI feature that should be dealt with when tackling the final full UI design, so not necessarily phase 2.
- "When you <kw-0><nospellcheck><key>evolve</key></nospellcheck></kw-0> Banana Launcher into Banana Blaster, conjure two Banana Bomb tokens.". Currently, the "evolve" word is treated as a key. However, it shouldn't. This is a bug/discrepancy I have with MSE. For me "evolve" without it being the Evolve: <name> or its many variations is not a keyword. Thus, it should be ignored.

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
