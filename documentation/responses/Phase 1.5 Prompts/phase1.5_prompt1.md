# Phase 1.5 — proposed batching

Items group naturally by what they touch. I'd run them in three waves with one explicit defer.

## Wave 1 — bugs + zero-schema polish

Cohesive: parser, ingest pipeline, templates only. No migration, fast feedback.

- **Doom-Bringer 500 (Tokens DB save).** Traced: at `pipeline.py:217` the fresh-create branch keys off `preview.route`, but the repo + identity pool above keyed off `effective_route` (which folds in `route_override`). When a Card-by-default routes to Tokens via the rarity:special modal, the code still calls `repos.cards.create(...)`. With "Doom-Bringer" already in the Cards DB, the `cards.name` unique constraint blows up → 500. Fix: use `effective_route` for the create branch too, and only set `rarity` / `power_level` on the kwargs when creating a Card.
- **"evolve" mid-sentence false-keyword.** Example: `When you <kw-0>...<key>evolve</key>...</kw-0> Banana Launcher into ...`. The `<kw-N>` wrapper is genuinely there in the file, so `iter_keyword_invocations` treats it as an invocation. Cleanest fix without going NLP-fuzzy: drop bare-`<key>` invocations whose body matches a small blocklist of verb forms (`evolve`, `evolves`, `evolved`) **AND** carry no `<atom-param>` and no `<atom-reminder…>` neighbour. The structural keyword block (`Evolve <atom-param>name</atom-param>`) is unaffected. I'd land it as a list constant in `tags.py` so adding more forms later is one edit.
- **Stub auto-definition (the four sub-items).**
  1. Investigate why ordinary cards leave Haste / Strikethrough / etc. as bare stubs. My hypothesis after reading `keywords.py:188-216`: `ensure_stub` does call `find_for_card_ref` first, which scans *all* keywords. If the very first card with `<key>Haste</key>` had no captured reminder (because `iter_keyword_invocations` failed to find one for that specific layout), a reminder-less stub is born. Subsequent cards with `<atom-reminder-core>` *do* now carry a reminder, but `ensure_stub`'s update predicate only fills the existing stub when `existing.is_stub and reminder and not existing.reminder` — that part is right, so the failure is upstream: the *first* card's `<atom-reminder>` was never captured. Likely cause is a single-card-per-line layout the regex didn't expect. I'll add a one-line debug log per ref and a unit-style trace, then patch whichever capture variant is missing.
  2. Strip outer `(` / `)` from the captured body in `_clean_reminder` (`tags.py:241`).
  3. Auto-promote single-word, no-param keywords: when a stub is being created and we have a reminder, set `is_stub=False` if the canonical name has no whitespace and no `<atom-param>`. New rows go in pre-promoted; existing reminder-less stubs that later get filled by a follow-up card also flip.
  4. UI label change is a free consequence — `(stub)` only renders for `is_stub=True` rows; auto-promoted rows already lose it.
- **Semicolon as line separator in rendered rule_text.** Storage unchanged. Add splitting in `render_text` / `render_text_snippet` (`templating.py:21-54`): split on `;` after escape, drop the separator, join with `<br>`.
- **Hide reminder text in rule-text snippets in table views.** I'd do this purely at snippet-render time — strip a trailing parenthesized clause `(...)` from each segment before truncation. Keeps storage canonical.
- **Reduce columns in cards / tokens browse tables.** Drop "Alt arts" and "Design" from `cards/list.html` and the matching tokens template. Both stay on the detail page. Open question: **do you also want to drop "PWL" and "Sets" from the overview, or keep them?** Currently leaning *keep*, but say the word.

**Skip / no-op in Wave 1:**
- **Triple+ hybrid mana display.** Reviewed `tags.py:335-346` — `render_casting_cost` already wraps any token containing `/` in parens, regardless of arity. The original item said "verify in production data and add a test case." With no test suite this collapses to a manual eyeball check; I'd note it as verified and move on rather than invent infrastructure for a single line.

## Wave 2 — schema-touching

Each one needs its own Alembic migration or migration-adjacent thinking. Done together so we batch the migration churn.

- **Alias column on Cards / Tokens.** Add `alias: Mapped[str | None]` to `CardCoreMixin`; one autogen migration covers both tables. Persist `face.alias` verbatim in `commit_face` (the existing `Evo:` / `Evolved:` / `Related:` mining still runs — it only writes to `related_cards`). Add a row in each detail-page `<dl>`.
- **Evo-T auto-route to Tokens DB + cross-reference the namesake card.** Broaden `is_token_route` to also match `evo-t` / `evo-t creature` / etc. — I'd add an explicit `evo-t` substring test rather than try to extend "token" matching. For the cross-reference, `commit_face` would, when routing to Tokens and a Card with the same `display_name` exists, append the card's name to the Token's `related_cards` (and vice-versa on the Card if it's already in DB).
- **Linked Related Cards in UI.** Reviewed the column: it's `JSONB` list of strings (`_card_mixin.py:35-36`). **No DB type change is needed** — name strings are fine because Cards / Tokens already have unique `name` lookups. The change is template-only: in detail pages, render each entry as `<a href>` if a Card or Token exists with that identity, else as plain text. I'd add a tiny `resolve_related` template helper that takes a list and returns `(name, href|None)` pairs.
- **Override-field datalists in the review modal.** Pull existing distinct values for `design_type`, `rarity`, `colors` from the repos and render `<datalist>` in `review_modal.html`. No schema work; mentioning here because it's small enough to ride along.

## Wave 3 — its own pull

- **Conditional reminder pretty-printer.** This is a real mini-language: `{ if param.value=="1" then "X" else "Y" }`, possibly with `and` / `or` / `==` / numeric compares. Worth a separate pass with a small parser (likely a hand-written Pratt or even just a recursive-descent for the `if` form). I'd start with the `if/then/else` plurality form only, then expand once we have a corpus of real reminders to test against.

## Defer

- **Evolution / Hero row hue + tag chip.** You yourself flagged this as something that may belong in the full UI redesign. Holding it.

---

**My ask:** confirm Wave 1 as-is (or redirect — e.g. "drop the snippet reminder-stripper, push to Wave 2"), and answer the Wave-1 column-pruning question (drop PWL/Sets too, or keep them?). Once you say go, I'll start with the Doom-Bringer trace + fix since it's the most impactful, then the stub-reminder cluster.

---

## Wave 1 — implemented

User confirmed: keep PWL and Sets on the overview tables; drop only Alt arts and Design.

Changes landed:

- **`pipeline.py`** — fresh-create branch and update-branch result both key off `effective_route` instead of `preview.route`. Doom-Bringer-style "card by default but routed to tokens via rarity:special" no longer hits the `cards.name` UNIQUE.
- **`tags.py`** — `_VERB_FORM_BLOCKLIST` (`evolve` / `evolves` / `evolved` / `evolving`); `iter_keyword_invocations` drops bare `<key>X</key>` references whose key is in the blocklist *and* has no `<atom-param>` and no neighbouring `<atom-reminder…>`. `_clean_reminder` now strips the outer `( … )` wrapper from captured reminders.
- **`repository/keywords.py`** — added `_is_self_defining` helper; `ensure_stub` now auto-promotes single-word keywords (no whitespace, no atom-params) to `is_stub=False` when a reminder is captured. Extracted the backfill logic into a public `maybe_backfill_reminder` so the ingest path can call it on existing rows too.
- **`pipeline.resolve_keyword_refs_for_face`** — now also calls `maybe_backfill_reminder` on the *existing-keyword* path. This is the actual fix for the user's "ordinary cards never get reminders" symptom: previously `ensure_stub` was the only place that backfilled, but `find_for_card_ref` short-circuited the call when a row already existed. Per-ref `logger.info` line emitted for diagnostics.
- **`main.py`** — `logging.getLogger("mse_viewer").setLevel(logging.INFO)` so the diagnostic logs surface under uvicorn.
- **`templating.py`** — added `render_rule_text` (splits `;` into line breaks) and `render_rule_text_snippet` (strips `<i>(...)</i>` and bare `(...)` reminder clauses + `;`-split + truncation). `render_text` / `render_text_snippet` unchanged so flavor and keyword reminders aren't affected.
- **Templates** — `cards/list.html` and `tokens/list.html` drop Alt arts and Design columns (Card list also keeps PWL, Rarity, Printed; Token list keeps PWL is N/A); both lists switch the rule-text cell to `render_rule_text_snippet`. `cards/detail.html` and `tokens/detail.html` switch the rule-text body to `render_rule_text`.

Verification (pure paths, ran against the actual code):

- Doom-Bringer rule_text → all three reminders captured, outer parens stripped.
- `When you <kw-0><key>evolve</key></kw-0> Banana Launcher into …` → no invocation emitted.
- `<kw-0><key>Evolve</key><atom-param>Foo</atom-param></kw-0>` → still emitted as `('Evolve', ['Foo'], None)`.
- `render_rule_text` splits `;` → `<br>`; `render_text` (flavor) keeps `;`.
- `render_rule_text_snippet` strips `<i>(...)</i>` clauses before truncating.
- `_is_self_defining`: `Haste`, `Omni-strike`, `Strikethrough` → True; `First strike`, parameterised forms, empty → False.

End-to-end DB paths (the 500 fix, the auto-promotion on the actual `Keyword` table, the backfill log lines under uvicorn) are not verified here because Docker isn't running in this environment — please retry the Doom-Bringer upload and re-import a set with `<key>Haste</key>` cards to confirm.
