# Phase 1.6 — Prompt 2: leftovers wave

Six items implemented, two skipped per your "optional" / "defer" annotations.

## Decisions

* **Items 7 (IngestSession persistence) and 8 (multi-face cross-link FK)** — left untouched; the Phase 1 in-memory store stays, multi-face links remain name-based. Easy follow-ups if either becomes painful.
* **Item 5 (search)** — extended search to also match rule_text and flavor_text (previously name-only). Whitelist tags (`<i>`, `<b>`, `<em>` and their closing forms) are stripped via Postgres `regexp_replace` inside the WHERE clause so a query for `first-strike` matches text stored as `<i>first-strike</i>`. Same pass added to keyword search across name/reminder/rules.
* **Item 4 (stub dashboard)** — single page at `/keywords/stubs` listing `is_stub=True` rows. Companion view at `/related/missing` aggregates every `related_cards` entry that doesn't resolve to a Card or Token row.
* **Item 6 (HTMX log transitions)** — resolve/reopen forms now `hx-post` and `hx-swap="outerHTML"` against a `_row.html` partial. The route returns the partial for `HX-Request: true`, falls back to the original 303-redirect-with-anchor otherwise.
* **Item 3 (diff viewer)** — identity collisions now compute a per-field diff against the existing row. The diff is attached to the `identity_conflict` warning's payload; if the existing row is `printed=True` we additionally raise a `modifies_printed` warning. The review modal renders the diff as an old-vs-new table. `deepdiff` is in `requirements.txt` per the original stack list, but the visible diff is a flat per-field list — easier to read for the kind of edits the user does.
* **Item 2 (CRUD)** — manual edit & create forms for Cards, Tokens, Keywords, Decks. New routes module `web/routes/edit.py`. Detail pages get an Edit button; list pages get a New button. Deletes are POSTs with a JS confirm, no inline soft-delete state.
* **Item 1 (deck ingest)** — upload page now has a `Set | Deck` mode toggle. Deck mode collects deck metadata (name, format, size, commander, package, theme, archetype, owners, colors, related decks). The deck file is parsed exactly like a set file; quantities are the count of repeated `card:` blocks per name. Cards already in the Cards DB are skipped — only previously-unknown cards reach the review modal. Once the review queue drains, the Deck row + DeckCard links are created automatically; missing cards are logged.

## Files added

```
src/mse_viewer/ingest/deck.py                         (new)
src/mse_viewer/web/routes/edit.py                     (new)
src/mse_viewer/web/templates/cards/edit.html          (new)
src/mse_viewer/web/templates/tokens/edit.html         (new)
src/mse_viewer/web/templates/keywords/edit.html       (new)
src/mse_viewer/web/templates/keywords/stubs.html      (new)
src/mse_viewer/web/templates/decks/edit.html          (new)
src/mse_viewer/web/templates/log/_row.html            (new)
src/mse_viewer/web/templates/related_missing.html     (new)
```

## Files changed

```
requirements.txt                                       deepdiff added
src/mse_viewer/main.py                                edit router registered
src/mse_viewer/ingest/preview.py                       diff payload + modifies_printed warning
src/mse_viewer/repository/cards.py                     tag-stripped search across name/rule/flavor
src/mse_viewer/repository/keywords.py                  search() + list_stubs()
src/mse_viewer/services/ingest_session.py              deck_plan, _finalize_deck, _row_snapshot
src/mse_viewer/web/routes/browse.py                    keyword search bar, /keywords/stubs, /related/missing, card_facts plumbing
src/mse_viewer/web/routes/log.py                       HTMX-aware transitions
src/mse_viewer/web/routes/upload.py                    deck-mode submit path
src/mse_viewer/web/templates/base.html                 htmx script, Missing nav link
src/mse_viewer/web/templates/cards/list.html           New button + extended search placeholder
src/mse_viewer/web/templates/cards/detail.html         Edit button
src/mse_viewer/web/templates/tokens/list.html          New button + extended search placeholder
src/mse_viewer/web/templates/tokens/detail.html        Edit button
src/mse_viewer/web/templates/keywords/list.html        Search bar, New / Stubs buttons
src/mse_viewer/web/templates/keywords/detail.html      Edit button
src/mse_viewer/web/templates/decks/list.html           New / Import buttons
src/mse_viewer/web/templates/decks/detail.html         Edit button
src/mse_viewer/web/templates/log/list.html             row partial inclusion
src/mse_viewer/web/templates/review_modal.html         diff table section
src/mse_viewer/web/templates/review_done.html          deck-created link
src/mse_viewer/web/templates/upload.html               mode toggle, deck fields
```

## Notes / trade-offs

* **Diff renderer is flat, not nested.** Each row in the table is one field — easy to scan, trivial to extend. `deepdiff.DeepDiff` is invoked for parity with the original stack note but its structured output isn't surfaced; if you start hitting field-level edge cases (e.g. JSONB lists with set semantics) we can switch to its tree mode.
* **Diff fires for every identity collision, not only printed.** The `modifies_printed` warning is the dangerous case (raised on top of the collision warning); plain collisions still get the diff so the user can sanity-check before picking update / alternate / rename. The collision warning was previously surfacing without any diff context.
* **CRUD lists are CSV strings, deck cards are `qty card_id` lines.** No fancy autocomplete — the existing `<datalist>` infrastructure is only on the review modal. Easy to upgrade later without changing the routes.
* **Deck ingest skips cards already in the DB.** Re-importing a deck that mixes new and existing cards routes only the new ones through review; existing names are linked verbatim. If a deck file has updated rule text for a card already in the DB, that update is lost — this is the trade-off for not blowing the user's eye out with N modals on a 60-card deck. If you want updates to propagate, run the same file through Set mode first.
* **Keyword search hits reminder/rules text.** Not just match-string. Same tag-stripping rule as cards. The /keywords search bar is new — previously the page was list-only.
* **Stub dashboard is read-only with an Edit shortcut.** Fixing a stub goes through the existing keyword edit form. Once a real `keyword:` block (or a manual edit) flips `is_stub=False`, the absorption logic already handles repointing card refs.
* **Missing-related view aggregates per-target.** Each row is one missing identity with the list of cards/tokens that pointed at it. Click the source card to fix the typo, or just author the missing card.

## What to verify

* `pip install -r requirements.txt` to pick up deepdiff (a no-op if you don't run the code path that imports it).
* HTMX requires a network round-trip per click; if Pico's CSS rules cause a jitter on row replace, swap to `hx-swap="outerHTML transition:true"`.
* The edit forms accept lists as comma-separated strings — round-tripping through the form keeps the values, but if you have list members that contain commas, those will split. None of the actual columns we expose currently allow embedded commas.
* Deck-mode upload: import a deck of all-existing cards → review queue should be zero, deck row appears immediately on the review-done page.
