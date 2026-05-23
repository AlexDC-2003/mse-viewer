# Phase 1.6 — Prompt 4: bug-bash + nested-template wave

Everything not flagged "todo later" is implemented. Todo-later items at the bottom (the prompt-3 carry-overs you wanted moved into a separate list).

## What landed

### Item 1 — comma-separated keyword line still wasn't splitting

Root cause: my prompt-3 fix relied on a resolver populated from `keyword_rows`. The resolver only registered keywords that had a *non-empty reminder* — reminderless stub rows (Haste / Vigilance / Reach with `is_stub=True` and no captured reminder body) returned `None`, so my "all segments must look like keywords" test failed and the line stayed unsplit.

Fix two-part:

* [browse.py — `_build_keyword_reminder_resolver`](src/mse_viewer/web/routes/browse.py): registers **every** keyword on the card, not just reminderful ones. Returns `""` for "known but no reminder body" instead of `None`. The comma-splitter's `is not None` check now passes for stubs.
* [templating.py — `_process_keyword_lines`](src/mse_viewer/web/templating.py): only renders `<i>(reminder)</i>` when the reminder is non-empty. Empty-reminder keywords still get the line capitalized but no trailing italics.
* [templating.py — `_strip_trailing_parens` + `_split_keyword_comma_lines`](src/mse_viewer/web/templating.py): tolerates trailing sentence punctuation (`).`, `).,` etc.) so a keyword segment that ends a sentence with a period after the reminder still resolves.

Verified inline against the user's actual rule_text:

```
input:  Haste, vigilance, reach, resilient (Effects that say destroy don't destroy this creature.)
output: Haste, Vigilance, Reach, resilient (...)  → split into 4 separate lines
```

### Item 2 — drop `design_type` from Tokens

`design_type` moved off the mixin onto `Card` only ([_card_mixin.py](src/mse_viewer/domain/_card_mixin.py), [card.py](src/mse_viewer/domain/card.py)). Migration **`0005_drop_token_design_type.py`** drops the column. Pipeline / preview / token detail / token edit / review modal all updated to skip the field. `CardRepository.distinct_design_types` now no-ops on Token (used to short-circuit the review modal datalist).

### Item 3 — keyword reminders with `{if has_pt() …}` evaluate per-card

Two-part fix:

* New [`evaluate_inline_templates(text, card_facts)`](src/mse_viewer/parser/reminder_template.py) evaluates `{ if … then … else … }` blocks within a larger text body but does NOT touch `{paramN}` slots — `{B}` mana symbols and other braces survive.
* `card_facts is None` → leaves the source verbatim (keyword-detail view rendering). `card_facts is not None` → evaluates against the dict.
* [render_rule_text](src/mse_viewer/web/templating.py) now takes `card_facts` and runs inline-template eval before the keyword-reminder pass. Card / Token detail templates pass it through. `_card_facts` in [browse.py](src/mse_viewer/web/routes/browse.py) now also exposes `super_type` and `sub_type` so `is_artifact(card.super_type)` resolves.

### Item 4 — keyword updates propagate into card / token rule_text

New [`KeywordRepository.propagate_change(...)`](src/mse_viewer/repository/keywords.py) walks every Card / Token whose `keyword_ids` mentions the changed keyword and rewrites:

* `old_name` → `new_name` (case-insensitive, word-boundary regex; preserves the rest of the text).
* `(<old reminder>)` → `(<new reminder>)` (literal substring replace inside the parens).

Wired into [`_save_keyword`](src/mse_viewer/web/routes/edit.py) — old name + reminder are captured before the form-update writes, then propagation runs after the flush. No-op when neither name nor reminder changed.

Best-effort: simple substring / regex replacement, no parser. Edge cases (a keyword's name being a substring of another keyword, an old reminder body that's a prefix of a different reminder) we accept for now — the user can fix manually via the edit form.

### Item 5 — "Additional Information" toggle

Single global checkbox in the nav header ([base.html](src/mse_viewer/web/templates/base.html)). Persists in `localStorage` (`mseViewer.showAdditional`). Body class `show-additional` toggles visibility; CSS rule in [style.css](src/mse_viewer/web/static/style.css) hides `.additional-info` rows / columns when the class is absent.

Tagged elements:

* [cards/detail.html](src/mse_viewer/web/templates/cards/detail.html) — Design type, Sets, Alt arts, Alias rows.
* [cards/list.html](src/mse_viewer/web/templates/cards/list.html) — Sets column.
* [tokens/detail.html](src/mse_viewer/web/templates/tokens/detail.html) — Alt arts, Alias rows.

Empty-row hiding:

* P/T row hides when both Power and Toughness are empty (parity with how Starting Loyalty already worked).
* Alias row hides when Alias is empty.

### Item 6 — diff snapshot uses real incoming values

Reordered [build_preview](src/mse_viewer/ingest/preview.py): `derive_colors` and `derive_design_type` now run **before** the identity-collision check. The `_face_snapshot` for the diff payload uses the actual derived `colors` and `dt.value` (or `(pending)` only when `dt.needs_user` is true and we genuinely don't know yet). No more `[]` and `(pending)` placeholders in the side-by-side table.

### Item 7 — deck ingest fixes

* `collapse_deck` accepts `existing_token_names` and skips deck cards whose name already exists in either the Cards or Tokens DB ([deck.py](src/mse_viewer/ingest/deck.py), [upload.py](src/mse_viewer/web/routes/upload.py)). No more duplication-modal storm when the deck references a token-only entry.
* Deck-mode submit passes `set_name=""` so the deck name does NOT bleed into the per-card `sets[]` provenance list. `append_unique` already drops empty strings, so `commit_face`'s `repo.append_set(...)` becomes a no-op for deck ingest.

The wider deck-ingest redesign — matching tokens through `DeckCard` (which currently only FK's to Cards), and the unified missing-refs model — stays todo-later (you flagged it that way and the schema change is non-trivial). With the two fixes above the existing flow should at least stop blowing up on token-only references.

### Item 8 — nested if/elseif/else evaluator

Replaced the over-match-guarded regex sub with a real brace-balanced parser ([reminder_template.py](src/mse_viewer/parser/reminder_template.py)):

* `_replace_blocks(text, …)` walks the text, finds top-level `{...}` blocks via brace counting (no regex over-match possible), and only treats blocks whose body starts with `if` as templates.
* `_eval_if_chain(body, …)` parses `if PRED then "X" [else if PRED then "Y"]* [else "Z"]` and walks the chain, returning the first branch whose predicate evaluates to True, the fallback, or `None` (leave verbatim) when nothing was decidable.
* New function predicates: `is_artifact(arg)`, `is_creature(arg)`, `is_enchantment(arg)`, `is_land(arg)` — all walk the resolved arg (or `card_facts['super_type']`) and check for the family substring. Same dispatch table as `has_pt()`.
* Function predicates accept a single dotted-path argument (`is_artifact(card.super_type)`); the leading `card.` is stripped before lookup against `card_facts`.

Verified:

```
{if has_pt() then "creature" else if is_artifact(card.super_type) then "artifact" else "permanent"}
  card_facts={'power':'2','toughness':'3'}    → "creature"
  card_facts={'super_type':'Artifact'}        → "artifact"
  card_facts={'super_type':'Enchantment'}     → "permanent"
  card_facts=None                             → verbatim (keyword detail page)
```

`Toxic 1` / `Toxic 2` plurality forms still resolve. `{B}` / other braces survive untouched.

### Bug/change 5 — Total row in deck detail

[decks/detail.html](src/mse_viewer/web/templates/decks/detail.html) — table footer with a sum of `quantity` across `deck.cards`. Renders only when there are any cards.

### Bug/change 6 — `<B>` in stored text was being promoted to a real bold tag

The `_ALLOWED_TAG` regex re-enabled `<i>`, `<em>`, **and `<b>`** after HTML-escaping, so a stray `<B>` substring (e.g. `<1B>` from malformed mana markup in a captured stub reminder) became an actual `<b>` open-tag and bolded everything until the next `</b>` — which never appears, so the rest of the page bolded.

Fix: drop `<b>` from the whitelist ([templating.py](src/mse_viewer/web/templating.py)). Canonicalized rule text never emits `<b>`, so removing it from the re-enable list has no UI cost. Italics (`<i>`/`<em>`) still survive. The `render_text_snippet` tag-balancing loop also only tracks `i` now.

### Bug/change 7 — commander/tester fields hide unless format calls for them

Both the deck upload form ([upload.html](src/mse_viewer/web/templates/upload.html)) and the deck edit form ([decks/edit.html](src/mse_viewer/web/templates/decks/edit.html)) now:

* Hide the Commander / Package / Related-decks fieldset entirely unless the selected format is `commander` or `tester`.
* Within that fieldset, hide Related-deck-IDs unless Package is `Expansion` or `Supplement`.
* Package became a `<select>` with the three valid choices (Core / Expansion / Supplement) plus a "none" sentinel.
* Format `<select>` includes `tester` alongside `commander`.

Toggling is pure JS reading `value` on change and `style.display` on the fieldset / label. No round-trip required.

---

## Files changed / added

```
alembic/versions/0005_drop_token_design_type.py         (new)
src/mse_viewer/domain/_card_mixin.py                    drop design_type from mixin
src/mse_viewer/domain/card.py                           design_type now Card-only
src/mse_viewer/parser/reminder_template.py              brace-balanced parser; new function predicates
src/mse_viewer/repository/cards.py                      distinct_design_types guards on missing column
src/mse_viewer/repository/keywords.py                   propagate_change()
src/mse_viewer/ingest/deck.py                           collapse_deck accepts existing_token_names
src/mse_viewer/ingest/pipeline.py                       design_type Card-only; common_kwargs trimmed
src/mse_viewer/ingest/preview.py                        diff snapshot uses real derived values
src/mse_viewer/web/routes/browse.py                     resolver registers all keywords; card_facts adds super_type / sub_type
src/mse_viewer/web/routes/edit.py                       keyword save propagates; token form drops design_type
src/mse_viewer/web/routes/review.py                     distinct_design_types from cards only
src/mse_viewer/web/routes/upload.py                     deck-mode set_name=""; tokens lookup
src/mse_viewer/web/static/style.css                     .additional-info hide rule
src/mse_viewer/web/templating.py                        evaluate_inline_templates; tolerate trailing punct; drop <b> whitelist; render_rule_text takes card_facts
src/mse_viewer/web/templates/base.html                  Additional-info toggle + JS persistence
src/mse_viewer/web/templates/cards/detail.html          additional-info tags; hide empty P/T + Alias; pass card_facts
src/mse_viewer/web/templates/cards/list.html            Sets column tagged additional-info
src/mse_viewer/web/templates/tokens/detail.html         additional-info tags; hide empty P/T + Alias; design_type removed; pass card_facts
src/mse_viewer/web/templates/tokens/edit.html           design_type field removed
src/mse_viewer/web/templates/decks/detail.html          Total row in cards table
src/mse_viewer/web/templates/decks/edit.html            commander/tester gated fields + tester format option
src/mse_viewer/web/templates/upload.html                same gated-field treatment for deck-mode upload
```

---

## Todo-later list (carried forward + new)

These were either explicitly marked "todo later" in this prompt, or carried over from prompts 2 / 3.

1. **Advanced search page** (Bug 7 prompt 3). Per-field inputs (name, type, subtype, P/T, cost, color, design_type, printed, etc.) plus a `-term` negation operator on the basic search bar. Live alongside the current bar.
2. **Unify keyword stubs and missing-related-cards** (Change 8 prompt 3). Two surfaces today, one model.
3. **Redefine the entire Design Type field** (Bug 9 prompt 3). The stylesheet table from prompt 3 is the input; redo the taxonomy in one pass instead of accumulating short-circuits.
4. **IngestSession persistence** (carried from prompt 2). In-process memory only.
5. **Multi-face cross-link FK** (carried from prompt 2). Name-based for now.
6. **Deck ingest design completion** (Item 7 partial). Beyond the two fixes that landed this prompt: tokens-as-deck-cards (DeckCard FKs Cards only today), unified missing-refs model — both should land alongside item 2 above. The duplication-modal storm should be gone now thanks to the token lookup, but the ingest flow can still be simplified once tokens are first-class deck members.
7. **Search separator logic for the basic bar**. The bottom-of-prompt-4 bug — even the simple bar's tokenization should respect quoted phrases / negation eventually. Folded into item 1.

---

## To pick up the changes

```
alembic upgrade head     # applies 0005 — drops tokens.design_type
```

No re-import needed. Existing rule_text already in the database renders correctly under all the templating changes. A keyword update saved via the edit form now propagates into rule_text immediately.
