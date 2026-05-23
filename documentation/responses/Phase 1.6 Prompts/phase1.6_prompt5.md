# Phase 1.6 — Prompt 5: deck-tokens + comma-split (for real this time)

Four bugs + the documentation pass. The comma-split fix landed, the deck schema gained tokens, and CLAUDE.md now points at the new unified todo list so future sessions don't re-derive the layout.

## What landed

### Bug 1 — Related-decks field missing in commander format

My prompt-4 implementation gated the Related-decks input on Package ∈ {Expansion, Supplement} — so picking "commander" but leaving Package empty hid the field entirely. The spec was "commander → all three fields visible; the *meaning* of Related-decks is package-dependent".

Fix in both [upload.html](src/mse_viewer/web/templates/upload.html) and [decks/edit.html](src/mse_viewer/web/templates/decks/edit.html): Related-decks always appears inside the commander/tester fieldset; the small caption mentions that it's only meaningful when the package is Expansion or Supplement. The JS only gates the whole fieldset on format, not the sub-field on package.

### Bug 2 — Default size 100 for commander

[upload.html](src/mse_viewer/web/templates/upload.html) — the format-change JS now sets the size input's default to 100 when commander/tester is selected, 60 otherwise. The auto-update only fires when the size still holds the *previous* default; if the user typed a custom number, that survives the format change.

### Bug/change 3 — Decks hold tokens too

Schema change. `DeckCard.card_id` becomes nullable; new `DeckCard.token_id` (FK to `tokens.id`); CHECK constraint `(card_id IS NOT NULL) <> (token_id IS NOT NULL)` plus two partial-unique indexes `(deck_id, card_id) WHERE card_id IS NOT NULL` and the symmetric one on `token_id`. Migration **`0006_deck_cards_tokens.py`**.

* [domain/deck_card.py](src/mse_viewer/domain/deck_card.py) — `card_id` / `token_id` nullable; both relationships; `member` / `member_kind` properties for the template.
* [repository/decks.py](src/mse_viewer/repository/decks.py) — new `add_token(deck, token_id, quantity)` mirroring `add_card`.
* [services/ingest_session.py](src/mse_viewer/services/ingest_session.py) `_finalize_deck` — Cards lookup first, Tokens fallback; only logs as missing when *neither* DB has the name.
* [decks/detail.html](src/mse_viewer/web/templates/decks/detail.html) — table iterates both kinds; links resolve to `/cards/{id}` or `/tokens/{id}` based on which FK is set; new "Kind" column; existing Total row preserved.
* [decks/edit.html](src/mse_viewer/web/templates/decks/edit.html) + [edit.py](src/mse_viewer/web/routes/edit.py) — deck members textarea accepts `<qty> <card_id>` for cards and `<qty> t<token_id>` for tokens. `_parse_deck_card_lines` returns `(qty, kind, target_id)` triples; `_replace_deck_cards` runs cards / tokens through separate dictionaries with the appropriate FK on insert.

### Bug 4 — Comma-keyword split (third time's the charm)

The actual root cause this time: the resolver only knows about keywords that the card already has in `keyword_ids`. If the card's rule_text is plain text (no `<kw-N>` wrappers in the source MSE), the parser never linked Haste / Vigilance / Reach. So my prompt-4 "register all keywords as known, return `""` for reminderless" only helped if the keyword was linked — which it wasn't.

New approach in [templating.py](src/mse_viewer/web/templating.py): classify each comma-segment as **strong** / **shaped** / **reject**.

* **Strong** — resolves against the keyword DB, OR carries an inline `(reminder)` body (tolerating trailing `).`, `).;` punctuation).
* **Shaped** — 1–3 alphabetic words, no English sentence-internal words (`this`, `when`, `you`, `may`, `gain`, …), first word matches `^[A-Za-z][A-Za-z'-]*$`, subsequent words can be alpha or a short parameter slot (`2`, `B`, `X`, `{cost}`).
* **Reject** — anything else.

The line splits **iff every segment is non-reject AND at least one segment is strong**. The "at least one strong" gate is what keeps free-text sentences (`Apples, oranges, pears, and bananas.`) from being over-split — none of those segments is strong, so the line stays unified. The user's actual case (`Haste, vigilance, reach, resilient (...)`) splits because the last segment has trailing parens → strong, and the other three are 1-word alpha → shaped, with no sentence words.

Verified inline:

```
Haste, vigilance, reach, resilient (Effects that say "destroy" don't destroy this creature.)
→ Haste / Vigilance / Reach / resilient (...)  on 4 separate lines

When this enters, you gain 1 life, draw a card.
→ stays on one line (sentence words trigger reject)

Foo, bar, baz
→ stays on one line (no strong segment)

Banding, first strike, haste, splash 2
→ splits (resolver hits any one of these → strong; rest are shaped)
```

---

## Documentation pass

### `documentation/files/todolist.md` — new

Single unified todo list for the whole app, across all phases. Sectioned into:

* **High-priority design rework** — Design Type taxonomy redo, keyword-stubs / missing-related unification, deck-ingest design completion.
* **Search** — advanced search page, negation operator, quoted-phrase tokenization.
* **Persistence / schema** — IngestSession persistence, multi-face cross-link FK.
* **Reminder-template / rule_text engine** — full parser, keyword-edit rule_text propagation edge cases.
* **UI polish** — additional-info toggle resting-state, deepdiff structured rendering.
* **Completed (for audit)** — Phase 1.6 prompts 1–5 with response-file links and the migration numbers they touched.

When a future prompt finishes an item, move it from its section to the "Completed" tail with a short note linking the response file. That keeps the audit trail in one place instead of scattered across prompt response files.

### `CLAUDE.md` — updated

* **Card-only column list** added to the routing rule so a future read of CLAUDE.md doesn't have to grep `domain/card.py` to know which fields aren't on the mixin.
* **Documentation workflow** section rewritten with:
  * A table of where each doc lives (`report.md`, `prompts/`, `responses/`, the new `files/todolist.md`).
  * A "How to navigate documentation efficiently" subsection that says: start at todolist, grep responses for decisions, read migrations for schema evolution. This lets future sessions skip the full prompt history.
  * A canonical **migration schedule table** mapping revision → what changed → which prompt originated it. `0001` initial, `0002` alias, `0003` starting_loyalty, `0004` drop abilities + tokens.sets, `0005` drop tokens.design_type, `0006` deck_cards tokens.

---

## Files added

```
alembic/versions/0006_deck_cards_tokens.py
documentation/files/todolist.md
```

## Files changed

```
CLAUDE.md                                              card-only columns; docs navigation guide
src/mse_viewer/domain/deck_card.py                     token_id + XOR check + member/member_kind
src/mse_viewer/repository/decks.py                     add_token()
src/mse_viewer/services/ingest_session.py              _finalize_deck checks Tokens fallback
src/mse_viewer/web/templating.py                       new strong/shaped/reject classification
src/mse_viewer/web/routes/edit.py                      deck-form parsing handles ``t<id>`` token rows
src/mse_viewer/web/templates/upload.html               commander auto-size 100; Related-decks always visible
src/mse_viewer/web/templates/decks/detail.html         Member + Kind columns; total preserved
src/mse_viewer/web/templates/decks/edit.html           Token IDs section; tokens passed in via context
```

## To pick up the changes

```
alembic upgrade head     # applies 0006 — deck_cards.token_id + partial-unique indexes
```

Existing decks are unaffected; new decks can pick up token rows immediately. Upload a deck file that contains a token-only entry and finalize_deck will now resolve it via the Tokens DB instead of logging "card not found".

## Verified inline

```
Bug 4 — all four classification cases (strong + shaped + sentence + bare-list) behave correctly.
Bug 3 — DeckCard model accepts either FK; _parse_deck_card_lines round-trips "4 5" and "2 t7" correctly.
App boots cleanly with 45 routes.
```
