# Phase 1.6 — Prompt 3: bug-bash wave

Items implemented (everything not flagged "todo later"). Todo-later list at the bottom.

## What landed

### Bug 1 — search now includes `alias`

Yes, included. Same tag-stripped LIKE pass as the other fields. You're right that `Evo:` itself is a low-value query, but searching for the literal name attached to an alias (e.g. `Heroic Sparky`) is useful, so the column is in.

### Bug 2 — `/cards/new` 422 from `int_parsing`

Root cause: `edit.router` was registered after `browse.router`, so FastAPI tried `/cards/{card_id}` first and rejected `"new"` as a non-int. Fix: register `edit.router` before `browse.router` in [main.py](src/mse_viewer/main.py). The static path now wins. Verified `/cards/new` and `/cards/{card_id}` resolve in the right order:

```
GET    /cards/new
POST   /cards/new
GET    /cards/{card_id}/edit
POST   /cards/{card_id}/edit
POST   /cards/{card_id}/delete
GET    /cards/{card_id}
```

### Bug 3 — `abilities` column dropped

You're right — the parser was setting `abilities = rule_text_canon` verbatim. The two columns held identical content. `abilities` is removed from:

* [`CardCoreMixin`](src/mse_viewer/domain/_card_mixin.py)
* [`ParsedCardFace`](src/mse_viewer/parser/models.py)
* The parser ([card_parser.py](src/mse_viewer/parser/card_parser.py)), pipeline ([pipeline.py](src/mse_viewer/ingest/pipeline.py)), preview snapshot ([preview.py](src/mse_viewer/ingest/preview.py)), session snapshot ([ingest_session.py](src/mse_viewer/services/ingest_session.py)), and edit forms.
* Migration **`0004_drop_abilities_token_sets.py`** drops `cards.abilities` and `tokens.abilities`.

Keyword refs are still extracted (the `keyword_refs` field on the parsed face) and the rule_text body still contains the keyword names + reminders inline — exactly the shape your prompt described.

### Bug 4 — keyword field accepts names, not IDs

The card / token edit form now has a single **Keywords** input that takes comma-separated names like `Haste, Ammo 2`. On save, the route calls `_resolve_keyword_names_to_ids(...)` ([edit.py](src/mse_viewer/web/routes/edit.py)) which uses `KeywordRepository.find_for_card_ref` — same resolver the ingest pipeline uses — so `Ammo 2` correctly resolves to the parameterised `Ammo <atom-param>n</atom-param>` row. Names that don't resolve are *not* auto-created as stubs (manual edits should be authoritative); they're written to the action log so you can fix them. The form pre-fills with the row's current keyword names (resolved from stored ids).

### Bug 5 — auto-correct casing on related_cards

Two places do this now:

* **Pipeline** — `_canonicalize_related(names, repos)` in [pipeline.py](src/mse_viewer/ingest/pipeline.py) is called whenever `commit_face` writes related_cards. It looks each entry up against Cards then Tokens (CI fallback), and replaces the casing with the matched row's stored name.
* **Manual edit** — `_canonicalize_related_names(raw, db)` in [edit.py](src/mse_viewer/web/routes/edit.py) does the same on the card / token edit POST.

Misspells and other differences are *not* corrected — only casing where a CI hit exists. Names that don't resolve survive verbatim (the missing-related view still flags them).

### Bug 6 — `tokens.sets` dropped

`sets` was moved off `CardCoreMixin` and onto `Card` only. Migration 0004 drops `tokens.sets`. Token detail and list templates lose their Sets column / row. The pipeline guards `repo.append_set` with `if effective_route == "card"` to avoid writing to a column that no longer exists. `CardRepository.append_set` also has a defensive `hasattr` no-op so any straggler call is safe.

### Bug 7 — search expansion (partial)

For now, the cards / tokens search additionally matches `card_type`, `card_subtype`, `alias`, and `related_cards` (JSONB cast to text). The full advanced-search page with per-field inputs and `-term` negation is **todo later**.

### Bug 9 — `m15-mainframe-dfc` allowlisted

Added to the Normal short-circuit list in [design_type.py](src/mse_viewer/ingest/derivations/design_type.py). DFC cards no longer trigger the "stylesheet not in rule table" review.

The full design_type / stylesheet table is at the bottom of this file.

### Bug 11 — keyword-comma split now accepts inline-reminder segments

Root cause: `_split_keyword_comma_lines` required *every* segment to resolve to a known keyword, so a line like `Haste, vigilance, reach, resilient (...)` failed because `Resilient` wasn't catalogued yet.

Fix: in [templating.py](src/mse_viewer/web/templating.py), a segment now passes the gate if **either** it resolves OR it ends in `(reminder)` and the head is ≤ 4 words. The trailing parens are a strong signal of a self-defining inline keyword. Verified inline:

```
input:  Haste, vigilance, reach, resilient (Effects that say "destroy" don't destroy this creature.)
output: Haste
        vigilance
        reach
        resilient (Effects that say "destroy" don't destroy this creature.)
```

### Bug 12 — function-predicate over-match in nested if/else

The user's example: `{ if has_pt() then "creature" else if is_artifact(card.super_type) then "artifact" else "permanent" }`. The regex was loose enough to over-match across the inner `else if` and produce `"permanent"` even with no `card_facts`.

Fix: `_maybe_replace_if` in [reminder_template.py](src/mse_viewer/parser/reminder_template.py) inspects the captured `predicate` group; if it contains stray `then` / `else` / `{` / `}` tokens (a sign we straddled a nested template), it returns the original text verbatim instead of substituting. Verified:

```
no facts:    {if has_pt() then "creature" else if is_artifact(...) then "artifact" else "permanent"}
with PT:     {if has_pt() then "creature" else if is_artifact(...) then "artifact" else "permanent"}
without PT:  {if has_pt() then "creature" else if is_artifact(...) then "artifact" else "permanent"}
simple true: creature
simple false: ''
toxic 1:     '1 poison counter'
toxic 2:     '2 poison counters'
```

The keyword detail page no longer renders a misleading evaluation. Proper nested-if support is **todo later** — see Bug 10's neighbour entry.

### Change 13 — keyword reject-list

New module [parser/keyword_rejects.py](src/mse_viewer/parser/keyword_rejects.py). Two filter sets:

* `is_rejected_match(match_string)` — applied at file-parse time. Drops `keyword:` blocks whose match identity matches `Evolve <atom-param>n|number|cost|count</atom-param>` or `Evolve <digits>`.
* `is_rejected_ref(ref_text)` — applied at card-side resolve time. Drops bare references like `Evolve 4` so they don't create a stub.

Both sources log:

* File-side: `parse_keywords()` returns `(accepted, rejected_match_strings)`; the session creator calls `log_rejected_keywords` once before commit so each rejection appears in the action log.
* Card-side: `resolve_keyword_refs_for_face` returns rejected refs as a third tuple element; `commit_face` writes one log entry per ref tagged with the source card name.

Verified inline against an MSE snippet with both shapes — the bad keyword definition is dropped, the legitimate `Evolve <atom-param>name</atom-param>` is kept, and the bad ref doesn't create a stub.

### Bug 15a — `IngestRepos` AttributeError on deck commit

Trivial regression I introduced in prompt 2. `_finalize_deck` calls `repos.decks.find_by_name(...)` but `IngestRepos.__init__` never instantiated `self.decks`. Added [`DeckRepository(db)`](src/mse_viewer/ingest/pipeline.py). The "rejecting everything throws an internal server error" was the same root cause — the reject path runs `_finalize_deck` after marking the session finished, and the AttributeError fired there too. The wider deck-ingest flaws (sets-include-deck-name, treating Tokens vs Cards correctly, modal duplications) are **todo later** per your instruction.

---

## Stylesheet → design_type → meaning table

Per Bug 9, here's the complete derivation. Each row is one decision the code can make. "Frame-family short-circuits" run first and override stylesheet rules, since you reuse stylesheets across frames. After that, stylesheet rules apply.

| Design Type                  | Trigger (priority order)                                                                  | Stylesheet typically seen                  | Meaning                                                                                |
|-----------------------------|-------------------------------------------------------------------------------------------|--------------------------------------------|----------------------------------------------------------------------------------------|
| Normal                       | `super_type` contains "Emblem"                                                            | `m15-emblem-name-cut`                      | Emblem (always Normal regardless of stylesheet)                                        |
| Normal                       | `super_type` contains "Planeswalker"                                                      | `m15-mainframe-planeswalker`, others       | Planeswalker (alias-driven review handled in preview, not here)                        |
| Normal                       | `super_type` contains "Enchantment" AND `sub_type` contains "Saga"                        | `m15-saga`                                 | Saga                                                                                   |
| Normal                       | `super_type` contains "Enchantment" AND `sub_type` contains "Leyline"                     | `future-planeswalker-horizontal`           | Leyline                                                                                |
| Normal                       | `stylesheet == "m15-altered"` AND `frames == ""` (snow filtered out)                      | `m15-altered`                              | Plain m15 frame (the default frame for "normal" cards)                                 |
| Colorpushed                  | `stylesheet == "m15-altered"` AND `frames == "fnm promo"`                                 | `m15-altered`                              | FNM-promo styled cards                                                                 |
| (ask user / playbook)        | `stylesheet == "m15-altered"` AND `frames` is anything else                               | `m15-altered`                              | Unrecognised frame combination — modal asks unless playbook remembers                  |
| Normal                       | `stylesheet == "m15-mainframe-planeswalker"`                                              | `m15-mainframe-planeswalker`               | Mainframe planeswalker frame                                                           |
| Normal                       | `stylesheet == "m15-mainframe-tokens"`                                                    | `m15-mainframe-tokens`                     | Mainframe token frame                                                                  |
| Normal                       | `stylesheet == "m15-mainframe-dfc"`                                                       | `m15-mainframe-dfc`                        | DFC frame (Phase 1.6 prompt 3 bug 9)                                                   |
| Normal                       | `stylesheet == "m15-emblem-name-cut"`                                                     | `m15-emblem-name-cut`                      | Emblem stylesheet (fallback for emblems without a typed supertype)                     |
| Normal                       | `stylesheet == "future-planeswalker-horizontal"`                                          | `future-planeswalker-horizontal`           | Leyline stylesheet (fallback for leylines without a typed subtype)                     |
| Normal                       | `stylesheet == "m15-saga"`                                                                | `m15-saga`                                 | Saga stylesheet (fallback for sagas without a typed subtype)                           |
| Normal                       | `stylesheet == "m15-altered-beyond"` AND `super_type` contains "evolution" or "hero"      | `m15-altered-beyond`                       | Evolutions / Hero cards on the Beyond frame                                            |
| Unique                       | `stylesheet == "m15-altered-beyond"` (everything else)                                    | `m15-altered-beyond`                       | Standard "Unique" tier card on the Beyond frame                                        |
| Additional Color             | `stylesheet == "m15-extra-udelude"`                                                       | `m15-extra-udelude`                        | Card whose colour identity adds an extra colour                                        |
| Additional Color - Unique    | `stylesheet == "m15-extra-udelude-beyond"`                                                | `m15-extra-udelude-beyond`                 | Beyond-tier extra-colour card                                                          |
| Normal                       | `stylesheet` is empty                                                                     | (no stylesheet field set)                  | Default                                                                                |
| (ask user / playbook)        | `stylesheet` is anything not listed above                                                 | unknown stylesheet                         | Modal asks; playbook remembers the answer for the (stylesheet, styling_data) pair      |

The "ask user / playbook" rows are where the modal currently fires for unrecognised stylesheets. Whenever you redefine the design-type field (your todo-later note in Bug 9), this table is the input — the existing "Custom" / "Colorpushed-experimental" / etc. entries you've added through the playbook live in the `playbook_entries` table and aren't shown above.

---

## Todo-later list

These were either explicitly marked "todo later" by you, or marked here because they need wider design.

1. **Advanced search page** (Bug 7). Per-field inputs (name, type, subtype, P/T, cost, color, design_type, printed, etc.) plus a `-term` negation operator on the basic search bar. To live alongside the current bar, not replace it.
2. **Unify keyword stubs and missing-related-cards into one model** (Change 8). Two surfaces today, should be one workflow.
3. **Redefine the entire Design Type field** (Bug 9). The stylesheet table above is the input; Phase 2 should re-do the taxonomy in one pass instead of accumulating short-circuits.
4. **Updating a keyword propagates to card rule-text** (Bug 10). Right now the Keyword Refs panel updates but the inline rule-text body keeps the old name + reminder. Needs a re-canonicalize pass over every Card / Token whose `keyword_ids` mentions the changed keyword.
5. **Hide / move metadata UI columns** (Change 14). Sets, alt arts, design type, alias should hide behind a global "Additional Information" toggle that persists across pages. Empty P/T and Alias rows on the detail page should also hide automatically (parity with how Starting Loyalty hides today).
6. **Diff view incoming side incomplete** (Change 15). Today the diff shows `(pending)` for design_type and `[]` for colors because `_face_snapshot` is built before those derive from the modal. Needs the snapshot rebuilt after overrides apply.
7. **Deck ingest design issues** (Change 15). Beyond the AttributeError: deck cards inherit the "deck name" as a `sets[]` entry on the card row (they shouldn't — a deck is a list of refs, not a provenance tag). The duplication-modal storm is also from treating deck-file cards as full-fat ingest entries; tokens look-up is missing. Whole flow should be reconsidered alongside the unified missing-refs model from item 2.
8. **Nested-if / function-predicate parser for reminder templates**. The Bug 12 fix is a guard, not an evaluator — a real recursive-descent for `if/then/elseif/else` plus more function predicates (`is_artifact(card.super_type)`, etc.) is the proper move once we have a corpus to test against.
9. **IngestSession persistence** (carried over from prompt 2). In-process memory only.
10. **Multi-face cross-link FK** (carried over from prompt 2). Name-based for now.

---

## Files added

```
alembic/versions/0004_drop_abilities_token_sets.py    (new)
src/mse_viewer/parser/keyword_rejects.py              (new)
```

## Files changed

```
src/mse_viewer/main.py                                 route order: edit before browse
src/mse_viewer/domain/_card_mixin.py                   drop abilities; sets moved off mixin
src/mse_viewer/domain/card.py                          sets column on Card only
src/mse_viewer/parser/driver.py                        propagate rejected_keywords
src/mse_viewer/parser/card_parser.py                   drop abilities field on face
src/mse_viewer/parser/keyword_parser.py                reject-list integration; new return type
src/mse_viewer/parser/models.py                        rejected_keywords on ParsedSet; abilities removed
src/mse_viewer/parser/reminder_template.py             over-match guard for nested if/else
src/mse_viewer/repository/cards.py                     search expansion + append_set hasattr guard
src/mse_viewer/ingest/derivations/design_type.py       m15-mainframe-dfc allowlist
src/mse_viewer/ingest/pipeline.py                      decks repo, abilities removal, related canonicalization, reject logging, sets-only-for-card
src/mse_viewer/ingest/preview.py                       drop abilities from snapshot
src/mse_viewer/services/ingest_session.py              drop abilities from snapshot, log rejected keywords
src/mse_viewer/web/routes/edit.py                      keyword name resolution, related casing fix, abilities/sets dropped
src/mse_viewer/web/templating.py                       relaxed comma-split rule
src/mse_viewer/web/templates/cards/edit.html           Keywords field; abilities removed
src/mse_viewer/web/templates/tokens/edit.html          Keywords field; abilities + sets removed
src/mse_viewer/web/templates/tokens/list.html          Sets column removed
src/mse_viewer/web/templates/tokens/detail.html        Sets row removed
```

## To pick up the changes

```
alembic upgrade head     # applies 0004 — drops cards.abilities, tokens.abilities, tokens.sets
```

No re-import is required for ingest behaviour, but a re-import will:

* Pick up the keyword-reject log entries for any file containing `Evolve <atom-param>n</atom-param>` or `Evolve <digits>` references.
* Rewrite related_cards casing to match canonical Card / Token names.
