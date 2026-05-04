# Phase 1.5 — pre-Wave-3 fixes + Wave 3

## Pre-Wave-3 fixes

### Fix #5 — strip `(Evo-X)` suffix in alias-mined related cards

[card_parser.py](src/mse_viewer/parser/card_parser.py) gets `_RE_EVO_SUFFIX = re.compile(r"\s*\(Evo-[A-Za-z0-9]+\)\s*$", re.IGNORECASE)`. The alias prefix-mining loop now applies that strip before pushing each comma-segment into `related_from_notes`, so `Evo: Doom-Buster (Evo-I)` mines `Doom-Buster` instead of `Doom-Buster (Evo-I)`. The original alias field is still stored verbatim on the row (Wave 2) — only the related-card name is normalised.

### Fix #4 — `(missing)` annotation on unresolved related cards

`cards/detail.html` and `tokens/detail.html` now render unresolved related-card entries as `Leaf Blower <small>(missing)</small>` instead of plain text. Resolved entries still render as `<a href>`.

### Fix #2 — structural keyword match in reminder resolver

The Wave-2 dict was a flat `lower(name) → reminder` map, which only ever resolves keywords whose stored `name` has no `<atom-param>` slot. `Evolve: Inferno Dragon` against a stored `Evolve: <atom-param>name</atom-param>` (or even `Evolve <atom-param>name</atom-param>`) silently failed.

`_build_keyword_reminder_resolver` in [browse.py](src/mse_viewer/web/routes/browse.py) is now a closure with two passes:

1. Exact (case-insensitive) lookup against keywords with no `<atom-param>` slots.
2. Structural lookup: each `<atom-param>X</atom-param>` becomes `(.+?)`, the param names are recorded in order, and on a match the captured groups are paired with those names and forwarded to the template evaluator (see Wave 3 below).

A tolerance retry strips a single `:` from the candidate before re-matching, so `Evolve: Inferno Dragon` resolves whether MSE stores the match string with or without the colon.

The filter signature in [templating.py](src/mse_viewer/web/templating.py) now accepts a callable resolver (with a fallback for the legacy dict form) and the route passes the closure directly.

### Fix #1 — comma-separated keyword lists become one line per keyword

The user's example: `First strike, reach, splash 2 (When this deals damage, it deals damage equal to its power to up to two other creatures.)` should become three lines, with reminders for the bare keywords appended; the next line, `Damage dealt by Cantaloupe-Pult can't be prevented or reassigned.`, must stay intact (it's an ability sentence that happens to lack commas, but in general we have to coexist with comma-using prose).

`render_rule_text` runs a new `_split_keyword_comma_lines` pre-pass before the bare-keyword enrichment:

* `_tokenize_top_level_commas` splits on commas at parens-depth zero, so the comma inside `(... it deals damage, it deals ...)` doesn't break the line.
* `_strip_trailing_parens` peels off a balanced `(...)` reminder body before the keyword lookup, so `splash 2 (...)` is matched as `splash 2`.
* The line is split only when **every** segment resolves to a known keyword. A single non-keyword segment leaves the whole line untouched — that's how `When you do X, do Y.` and `First strike, but only at night.` survive.

Inline verification (real code, mock keyword rows):

| input | output |
|---|---|
| `First strike, reach, splash 2 (...)` | three lines, two get reminders, third keeps inline body |
| `Damage dealt … can't be prevented or reassigned.` | unchanged |
| `Evolve: Inferno Dragon` | gets reminder via structural match + colon tolerance |
| `Evocycling (...)` | unchanged (already has parens) |
| `When you do X, do Y.` | unchanged (Y not a keyword) |
| `First strike, but only at night.` | unchanged (mixed kw + prose) |

### Q#3 — where does Triple strike's reminder come from?

It's captured from the inline `<atom-reminder>` block in **another card's** rule_text, not from a `keyword:` block.

Walkthrough of how a stub gets a reminder body even when the user didn't define the keyword:

1. The card the user imports has rule_text like `<kw-1><key>Triple strike</key></kw-1><atom-reminder>(Whenever this creature attacks, it deals damage three times.)</atom-reminder>`.
2. [parser/tags.py:iter_keyword_invocations](src/mse_viewer/parser/tags.py) extracts every keyword reference from rule_text *and* picks up the inline reminder body next to each one. Wave 1 added `_clean_reminder` so the outer parens get peeled.
3. The face's `keyword_reminders` dict (ref → body) carries that captured text into the ingest pipeline.
4. [pipeline.resolve_keyword_refs_for_face](src/mse_viewer/ingest/pipeline.py) calls `KeywordRepository.ensure_stub(ref, reminder=…)` (or `maybe_backfill_reminder` if the row already exists). With no `keyword:` block, the row is created as `is_stub=True` and `reminder=<captured body>`.

So the reminder body in the DB came from the rule_text of whatever card mentioned the keyword first; the user never explicitly defined it. This is intentional — without it the Keywords list would be a wall of empty rows for every nonce keyword the user invents.

For single-word names, Wave 1 also auto-promoted the row to `is_stub=False` because the reminder body alone is enough to call it a definition. Multi-word names like `Triple strike` deliberately stay as stubs because we don't know whether they take parameters, and the formal `keyword:` block is the source of truth for that. The `(no definition yet)` annotation is a nudge to fill that block in someday.

If you'd rather have multi-word stubs *also* auto-promote when a reminder is captured (so Triple strike loses the annotation), it's a one-line broadening of `_is_self_defining` in [repository/keywords.py](src/mse_viewer/repository/keywords.py). Say the word and I'll do it.

## Wave 3 — conditional reminder pretty-printer

New module: [parser/reminder_template.py](src/mse_viewer/parser/reminder_template.py). It exports `evaluate_reminder_template(text, params=None)`.

Grammar handled in this round:

* `{paramN}` slot — substituted with the concrete value when `params` is passed; otherwise rendered as `<paramN>` (literal angle brackets, so the slot stays visible in the keyword detail view).
* `{ if EXPR then "X" else "Y" }` — if `params` resolves the predicate, return the chosen branch; otherwise default to the `else` branch (the plural form, which is the safer default for English).
* Predicate forms: `param.value == "X"` and `param.value != "X"`. Anything else is treated as undecidable and falls through to `else`. Adding more grammar later is a `_eval_predicate` extension.

Two integration points in [templating.py](src/mse_viewer/web/templating.py):

* New `render_reminder` filter, used by [keywords/detail.html](src/mse_viewer/web/templates/keywords/detail.html) for the standalone keyword view (no params, plural fallback, slots show as `<paramN>`).
* The keyword resolver in [browse.py](src/mse_viewer/web/routes/browse.py) evaluates the reminder *with the captured invocation params* before returning. That's how `Toxic 2` becomes `2 poison counters.` and `Toxic 1` becomes `1 poison counter.` — the structural regex captures `n=2` / `n=1`, hands them to the evaluator, and the right plural form drops out.

Verification (live against the actual code):

* Direct evaluator: 8/8 cases pass — plural default, then-branch with `==`, else-branch with `==`, `!=` predicate, undecidable predicate falls to else, plain text untouched, `{paramN}` → `<paramN>`, multiple `if/then/else` in one template.
* Integration through `render_rule_text`: `Toxic 2` → `2 poison counters.`, `Toxic 1` → `1 poison counter.`, `Reach` → plain reminder, `Evolve: Inferno Dragon` → resolves via structural match + colon tolerance, comma-split keeps the `(...)` reminder on the third segment.
* Integration through `render_reminder`: a templated reminder with no params shows `<param1> poison counters.`; a plain reminder is untouched.

## Verification summary

* `python -m py_compile` clean across all modified files.
* All pure-path checks above run against the actual code, no mocking past the keyword rows themselves.
* Untested here (needs a running Postgres + a real `.mse-set` fixture): the alias `(Evo-X)` strip end-to-end, the `(missing)` annotation when the related card actually doesn't exist in DB, and the resolver against keyword rows whose `name` came from MSE rather than my mocks. Please re-import and click around to confirm.

## What's left from the original plan

* **Deferred** (your call): Evolution / Hero row hue + tag chip — held until the full UI redesign.
* **Open question** (Q#3 follow-up): want multi-word stubs with captured reminders to auto-promote too? One-line change if yes.
