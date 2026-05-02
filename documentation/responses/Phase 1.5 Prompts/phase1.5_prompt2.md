# Phase 1.5 — pre-Wave-2 fixes + Wave 2

## Pre-Wave-2 fixes (from prompt)

### Detail-page rule_text: append captured reminders for bare-keyword lines

Implemented as a new optional argument on `render_rule_text(value, keyword_reminders=None)`.

- Routes (`browse.py: cards_detail` / `tokens_detail`) build a `lower(name) → reminder` dict from the keyword rows referenced by the card.
- Filter splits on `;` / `\n` (existing behaviour), then for each line whose entire body matches a keyword name (trimmed, stripped of `.` / `,`, lower-cased) AND has no `(` already, appends ` <i>(reminder)</i>`.
- Pre-existing `<i>` tags inside the stored reminder are stripped before re-wrapping so we don't end up with nested italics rendering as upright.

Verified inline:

| input line | result |
|---|---|
| `Haste\nTrample\nWhen CARDNAME attacks…` | each keyword annotated, prose untouched |
| `Haste; Trample; When CARDNAME…` | same after `;`-split |
| `Haste <i>(Already there)</i>\nTrample` | left alone for Haste, annotated for Trample |
| `Triple strike\nWhen…` | multi-word keyword annotated (works because lookup keys off the stored name, not the auto-promote rule) |
| `Trample creatures of your color.` | left alone (sentence, not a bare line) |
| `keyword_reminders=None` | back to plain `;`-split rendering |

### Triple strike — why "(no definition yet)" sticks

Behaving as designed. Wave 1 only auto-promotes **single-word** stubs (no whitespace, no `<atom-param>`) when a reminder is captured — that rule was deliberately scoped to keywords whose reminder text *is* the full definition. "Triple strike" has whitespace, so `_is_self_defining("Triple strike")` is `False` and the row stays `is_stub=True`. The `(no definition yet)` annotation is the correct label for "stub with reminder body, but no formal `keyword:` block": the user knows about it, just hasn't filled in `accepted_parameters` / `rules` / pseudo-flag yet. With the rule_text reminder-line enrichment above, the keyword still reads correctly inline; the annotation is just the "you may want to define this in a `keyword:` block someday" prompt.

If you want the annotation gone for multi-word reminder-only stubs too, that's a one-line broadening of `_is_self_defining` (or a separate flag) — say the word and I'll do it. I left the original spec intact for now.

### Rarity:special radio order

`review_modal.html` — Tokens DB radio is now first and `checked`, Cards DB is second.

## Wave 2

### Alias column on Cards / Tokens

- `_card_mixin.CardCoreMixin.alias` (`Mapped[str | None]`, `Text`).
- New Alembic revision `0002_card_token_alias.py` adds the column to both tables, nullable, no default.
- `pipeline.commit_face` includes `alias=face.alias` in `common_kwargs` — captured verbatim, the existing `Evo:` / `Evolved:` / `Related:` prefix mining still runs into `related_cards` so we don't lose that signal either.
- Detail templates show an `Alias` row in the `<dl>`; **list views deliberately do not show alias** per your clarification.
- The update-in-place guard in `commit_face` already skips empty values, so re-importing a card with `alias:` blank doesn't clobber an existing alias.

### Evo-T auto-route + cross-reference

- `is_token_route` now matches `evo-t` substring as well as `token`. New `is_evo_t(face)` predicate in `routing.py`.
- `commit_face` calls a new `_apply_evo_t_cross_link` helper after both the update and create branches:
  - **Token side**: if the face is Evo-T, look up Cards with the same display name (case-insensitive) and append each into the Token's `related_cards`; reciprocally append the Token's name into the Card's `related_cards`.
  - **Card side**: if the face is a Card, look up Tokens with the same display name whose stored `card_type` contains `evo-t`, and cross-link both ways. Catches the order-dependent case where the Evo-T was imported first.
- `append_related` is de-duplicating, so re-imports never accumulate extra entries.

### Linked Related Cards

- New `_linkify_related` helper in `web/routes/browse.py`. For each related-cards entry it returns `{name, href}`:
  - If the entry equals the current row's own name → prefer the *opposite* kind (handles the Evo-T cross-link case where Card "Doom-Bringer" has "Doom-Bringer" in `related_cards` and should link to the Token, not back to itself).
  - Otherwise prefer the *same* kind first (covers DFC face1↔face2 in Cards), falling back to the opposite kind.
  - Lookup is exact-match on `name`, then case-insensitive fallback. If neither hits, render plain text.
- Detail templates render each related entry as `<a href>` when a match exists, plain text otherwise.
- **No DB column-type change needed**: `related_cards` stays `JSONB` list of strings — the resolution happens at render time, which means renames on the target row are picked up automatically.

### Override datalists in review modal

- Three new repo methods: `_BaseCardRepo.distinct_design_types()`, `_BaseCardRepo.distinct_colors()`, `CardRepository.distinct_rarities()`. JSONB colors are flattened in Python; the row counts are small enough to skip a set-returning Postgres function.
- `review_current` route now takes `db: Session` and feeds `distinct_design_types` (Cards ∪ Tokens), `distinct_rarities` (Cards only), `distinct_colors` (Cards ∪ Tokens) into the template.
- `review_modal.html` adds `<datalist>` blocks for each and wires `list="dl_..."` onto the three override inputs.
- **Caveat**: the colors input is comma-separated, and `<datalist>` only suggests against the *whole* input. Typing a comma + space then expecting per-token autocomplete won't work natively. For now you can pick one value at a time; a chip-based multi-select would be a separate UI widget and felt out of scope here.

## Verification

- `python -m py_compile` clean across all modified files.
- Pure-path checks against the actual code: bare-keyword reminder enrichment cases above; `is_token_route` / `is_evo_t` table for `Token Creature`, `Evo-T Creature`, plain `Creature`, etc.
- DB-touching paths (alias column read/write, Evo-T cross-link both directions, datalist values, the migration) need a running Postgres — please run `alembic upgrade head` and re-import a set with an Evo-T card to confirm.

## What's left

- **Wave 3** (your call when): conditional reminder pretty-printer (the `{ if param.value=="1" then "X" else "Y" }` mini-language).
- **Deferred**: Evolution / Hero row hue + tag chip — held until the full UI redesign.
