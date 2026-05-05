# Phase 1.6 — proposed plan for prompt 1

Five items in this prompt: one reminder-template bug, plus four new frame families (Planeswalker, Emblem, Saga, Leyline). The frame work is genuinely sensitive — each one bypasses the existing "stylesheet not in rule table → ask the user" path and adds its own type-checked detection — so I want to get scope and a few schema decisions confirmed before I touch code. Implementation grouped into three waves below.

---

## 0. The bug — `{if has_pt() then "creature"}` doesn't render

Two compounding gaps in [parser/reminder_template.py](src/mse_viewer/parser/reminder_template.py):

1. **The regex requires `else "..."`.** The user's example has only `then "creature"` — no else branch. `_RE_IF_THEN_ELSE` won't match it at all, so the template leaks through verbatim.
2. **The predicate is a function call (`has_pt()`), not equality.** `_eval_predicate` only knows `name.value == "X"` / `!=`. `has_pt()` returns `None` (unknown) and we'd default to the else branch even if the regex matched — but for a card that *does* have P/T, the right answer is the then branch.

There's also a third issue I'd like to nail down before coding: **`has_pt()` needs the card's facts**, not just keyword params. The current API is `evaluate_reminder_template(text, params=None)` and the caller in [browse.py:73](src/mse_viewer/web/routes/browse.py#L73) doesn't pass anything except the parameter values mined from the keyword reference. I want to extend the API to:

```python
evaluate_reminder_template(text, params=None, *, card_facts=None)
# card_facts: { "has_pt": bool, "power": str|None, "toughness": str|None, ... }
```

…and have both call sites ([browse.py](src/mse_viewer/web/routes/browse.py) and [templating.py:render_reminder](src/mse_viewer/web/templating.py#L280)) build a `card_facts` dict from the surrounding card row when they have one. `render_reminder` is called with no card context (it's the keyword detail page), so for that call site `has_pt()` resolves to `None` and we fall through to the else branch (or empty string if there's no else) — same defensive default as today.

Plan for the fix:

- Make `else "..."` optional in `_RE_IF_THEN_ELSE`. When it's missing and the predicate is true, emit the then branch; when false or unknown, emit empty string.
- Add a function-call predicate matcher (`^\s*(\w+)\s*\(\s*\)\s*$`) and a small `_FUNCS` dispatch keyed on the function name. Seed it with `has_pt` (true iff `card_facts.get("power")` or `card_facts.get("toughness")` is non-empty — both, ideally; one of them being non-empty is the same set as both for legal MTG cards). Adding `has_cost`, `is_creature`, etc. later is one entry.
- Thread `card_facts` through both browse.py callers from the resolving Card / Token row.

**Question for you:** for `has_pt()`, do you want the truth condition to be "both P and T present" or "either"? I'll default to **both non-empty** unless you say otherwise — that's the case where "creature" actually makes sense in the surrounding sentence.

---

## 1. Planeswalker parsing

**Detection.** Primary signal: `super_type` contains `Planeswalker` (case-insensitive). Stylesheet is *not* trusted — you said you reuse `*planeswalker*` stylesheets for other things. So:

- If supertype has `Planeswalker` → planeswalker frame, regardless of stylesheet.
- If stylesheet is `m15-mainframe-planeswalker` but supertype lacks `Planeswalker` → typing mismatch, trigger review.
- If supertype has `Planeswalker` but stylesheet differs → still planeswalker; no warning (you said you reuse stylesheets).

**Source of rule_text.** Per your direction, take `special_text:` verbatim and run it through `canonicalize_text` after first stripping `<margin:...:...:...>...</margin:...>` wrappers (kept as plain text). I'll add a `<margin>` family stripper to [tags.py](src/mse_viewer/parser/tags.py); the regex pattern is `</?margin(?::[^>]*)?>` similar to the existing `_RE_ATOM_REMINDER_FAMILY`. I'll *not* try to assemble rule_text from `loyalty_cost_N` + `level_N_text` for now — flagged as the pivot path you mentioned if `special_text` turns out to be unreliable.

**Starting loyalty.** New nullable column on `Card`: `starting_loyalty: Mapped[int | None]`. **I'd put it on `Card` only, not on `CardCoreMixin`**, because:

- Tokens never have starting loyalty (Emblems aren't planeswalkers themselves; they're created *by* planeswalkers).
- The mixin already has `power_level` only on Card via subclass — there's precedent for Card-only attributes.

This needs an Alembic migration: `0003_card_starting_loyalty.py`. UI: a row in [cards/detail.html](src/mse_viewer/web/templates/cards/detail.html) for "Starting Loyalty"; nothing on the browse list.

**Design type / review.**

- No alias and not Evolution Planeswalker → auto-commit as `Normal`. No modal.
- Has an alias and not Evolution Planeswalker → trigger modal so you can pick a non-Normal design type.
- Evolution Planeswalker (supertype contains both `Evolution` and `Planeswalker`) → ignore the alias as a review trigger; auto-commit as `Normal` *unless* something else legitimately warns (rarity-special, identity collision, etc.).

I'll plumb this by short-circuiting the `derive_design_type` call for planeswalker-supertype faces: `m15-mainframe-planeswalker` already returns `Normal` from the rule table, but the new path covers the case where you've used a different stylesheet for a planeswalker.

**Cards vs Tokens routing.** Planeswalkers route to Cards. The rarity ladder is normal — `mythic` / `rare` / `uncommon` / `common`. Nothing special.

---

## 2. Emblem parsing

**Detection.** Primary signal: supertype contains `Emblem`. Stylesheet `m15-emblem-name-cut` is the typical match.

- Supertype `Emblem` → token route. **Override `is_token_route` for this case** (or, cleaner, add `"emblem" in s` to the existing token-supertype substring check in [routing.py:19](src/mse_viewer/ingest/derivations/routing.py#L19)). Either way, no rarity-special prompt is triggered (your example has `rarity: special`; the existing logic already suppresses the rarity-special warning when token routing is auto-decided — see [preview.py:60](src/mse_viewer/ingest/preview.py#L60) — so this falls out for free).
- Stylesheet `m15-emblem-name-cut` should not trigger the "stylesheet not in rule table" warning. I'll add it to [design_type.py](src/mse_viewer/ingest/derivations/design_type.py) returning `Normal`.
- **Typing mismatch check.** If stylesheet is `m15-emblem-name-cut` but supertype lacks `Emblem`, OR supertype is `Emblem` but stylesheet isn't an emblem stylesheet → trigger review. New `WarningKind.frame_type_mismatch` (or reuse `parse_punt`).

**Subtype → related_cards.** The `sub_type` field on an emblem holds the producing planeswalker's name (in your example, `Solar Flare`). I'll have the planeswalker face extractor write that into `related_from_notes` when supertype contains `Emblem` and subtype is non-empty. The reverse direction (the planeswalker's related_cards picking up the emblem) won't auto-populate from the planeswalker's own data — but the `_apply_evo_t_cross_link` style of post-commit linking can do it: on Emblem commit, look up any Card with the same display name as the emblem's subtype and append the cross-reference both ways. I'll add an `_apply_emblem_cross_link` modeled on the Evo-T one.

**Casting cost.** Already nullable. No change.

**Design type.** Always `Normal` for Emblems — short-circuit in `derive_design_type` based on supertype.

---

## 3. Leyline parsing

**Detection.** Subtype (an `<word-list-enchantment>` chain) contains `Leyline`. Supertype `Enchantment` is required — typing mismatch otherwise.

- Stylesheet `future-planeswalker-horizontal` shouldn't trigger the "stylesheet not in rule table" warning. Add it to [design_type.py](src/mse_viewer/ingest/derivations/design_type.py) returning `Normal`.
- If stylesheet is `future-planeswalker-horizontal` but the subtype isn't `Leyline` (and/or supertype isn't `Enchantment`) → trigger review.

**Flavor extraction from rule_text.** Your example:

```
If Leyline of Equilibrium is in your opening hand, you may begin the game with it on the battlefield.
<i>Years of power scaling have broken down the core concepts of this everchanging reality.</i>
When Leyline of Equilibrium enters, each player gains 10 life. ...
```

The `<i>...</i>` line in the middle is flavor. I'll add a helper in [card_parser.py](src/mse_viewer/parser/card_parser.py) (or a new `parser/special_text.py` module) that splits the canonicalized rule_text into segments by line, and for each segment that **starts with `<i>` and ends with `</i>` and contains no other tags** (no `<kw-N>`, no keyword refs, no atom-reminder, no mana symbols), moves it to the flavor field. Multiple flavor segments concatenate with newlines preserving order. The remaining ability-text segments rejoin with newlines.

This helper is shared with Saga (see below) — same exact logic ("italic-only line, no other markup → flavor"), with one exception that's saga-specific.

**Design type.** Always `Normal`.

---

## 4. Saga parsing

**Detection.** Subtype contains `Saga`. Supertype must be `Enchantment`.

- Stylesheet `m15-saga` shouldn't trigger the "stylesheet not in rule table" warning. Add to [design_type.py](src/mse_viewer/ingest/derivations/design_type.py) → `Normal`.
- If stylesheet is `m15-saga` but typing doesn't match → review.

**Source of rule_text.** Take `special_text:` verbatim, canonicalize. Same `<margin>` strip is needed if it shows up; in your saga example it doesn't, but better to handle it once.

**Flavor extraction with the saga exception.** Use the same italic-only-line splitter as Leyline, but with:

- **The first non-empty segment is never flavor.** This is the rule you stated; it covers both `Read ahead` (which has `<kw-A>` tags so the helper wouldn't have stripped it anyway) and the always-italic `(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)` line that has no other markup.
- After segment 1, the same italic-only rule applies. So `I — Search your library...`, `II — ...` stay as ability text; an italic-only line trailing them goes to flavor.

**Design type.** Always `Normal`.

I'm explicitly *not* adding a `chapters` table or column — your direction is "use special_text", and chapter ordering is preserved in the rendered text. If you later want structured chapters, that's a clean follow-up.

---

## Schema summary

One migration this whole prompt:

- `0003_card_starting_loyalty.py` — `cards.starting_loyalty INT NULL`. No tokens column; emblems are tokens and don't need loyalty.

Everything else is parser / ingest / display only.

---

## Wave plan

Three waves, each landable on its own. The bug fix is its own first wave so you get value before the frame work and so I'm not bundling unrelated changes.

### Wave 1 — reminder-template bug

Just §0 above. Optional `else`, `has_pt()` predicate, `card_facts` plumbed through the two callers.

Files: [parser/reminder_template.py](src/mse_viewer/parser/reminder_template.py), [web/routes/browse.py](src/mse_viewer/web/routes/browse.py), [web/templating.py](src/mse_viewer/web/templating.py).

### Wave 2 — Planeswalker

Schema migration + parser + ingest. Largest of the four because of the column add and the design_type / alias logic.

Files: new migration, [domain/card.py](src/mse_viewer/domain/card.py), [parser/card_parser.py](src/mse_viewer/parser/card_parser.py) (planeswalker face path: special_text → rule_text, loyalty extraction), [parser/tags.py](src/mse_viewer/parser/tags.py) (`<margin>` stripper), [ingest/preview.py](src/mse_viewer/ingest/preview.py) (alias-without-Evolution → modal), [ingest/derivations/design_type.py](src/mse_viewer/ingest/derivations/design_type.py) (Planeswalker auto-Normal), [ingest/pipeline.py](src/mse_viewer/ingest/pipeline.py) (write `starting_loyalty` to Card), [web/templates/cards/detail.html](src/mse_viewer/web/templates/cards/detail.html) (display row).

### Wave 3 — Emblem + Leyline + Saga

Three frames, one shared piece (italic-only flavor splitter) plus three small detection rules.

Files: new `parser/special_text.py` (or a section in `card_parser.py`) for the italic-only splitter; updates to [parser/card_parser.py](src/mse_viewer/parser/card_parser.py) for emblem subtype → related, leyline / saga special_text + flavor split; [ingest/derivations/routing.py](src/mse_viewer/ingest/derivations/routing.py) (emblem → token route); [ingest/derivations/design_type.py](src/mse_viewer/ingest/derivations/design_type.py) (three new stylesheet → Normal entries); [ingest/preview.py](src/mse_viewer/ingest/preview.py) (typing-mismatch warning kind); [ingest/pipeline.py](src/mse_viewer/ingest/pipeline.py) (`_apply_emblem_cross_link`).

I'd land waves in that order. Wave 1 lands as a self-contained fix; Wave 2 ships the schema change once, on its own, so the migration history stays clean; Wave 3 then layers the no-schema frame work on top.

---

## Open questions before I start

1. **`has_pt()` truth condition** — both P and T non-empty (my default), or either? See §0.
2. **Starting loyalty placement** — `Card` only (my default), or in `CardCoreMixin` for symmetry?
3. **Loyalty parsing** — the `loyalty:` field is sometimes integer, sometimes a letter (X), sometimes empty. I'll store it as `int | None`, accepting integer parses only and silently dropping non-integer values (e.g. an empty `loyalty:` is None; `loyalty: X` is None; `loyalty: 4` is 4). OK, or do you want a string column instead?
4. **Margin tag handling** — strip wrapper, keep inner text (my default). Or do you want margin spans surfaced anywhere else (CSS, layout)?
5. **Emblem subtype → related_cards** — auto-add the subtype as a related card, no modal, even when the named planeswalker doesn't yet exist in the DB (my default). The existing `(missing)` annotation will surface for it until you import the planeswalker.
6. **Saga "first segment is never flavor" rule** — strict positional rule (my default), or do you want me to also detect the specific `(As this Saga enters... Sacrifice after X.)` template explicitly?
7. **Wave-1 ship-on-its-own** — happy with that, or do you want everything bundled into one PR for this phase?

Confirm the answers (or just "defaults are fine") and I'll start Wave 1.

---

## Decisions (user reply)

1. `has_pt()` — both P and T must be non-empty. (Note: every card with toughness has power, so this is equivalent to either, but the code requires both.)
2. `starting_loyalty` lives on `Card` only — only planeswalkers care.
3. Loyalty stored as `int | None`; non-integer values silently coerce to `None`.
4. `<margin:130:0:0>...</margin:130:0:0>` wrapper stripped entirely, body kept as plain text. No formatting preserved.
5. Emblem subtype auto-added to `related_cards` even when the named planeswalker isn't in the DB; the existing `(missing)` annotation surfaces until it is.
6. Saga "first non-empty line is never flavor" is a strict positional rule — the `(As this Saga enters... Sacrifice after X.)` template will always be that first line.
7. All three waves landed in this run.

---

## Wave 1 — implemented

- [parser/reminder_template.py](src/mse_viewer/parser/reminder_template.py) — `_RE_IF_THEN_ELSE` makes the `else "..."` branch optional; an unmatched branch renders empty. Added `_RE_FUNC_PREDICATE` and a `_FUNCS` dispatch table seeded with `has_pt` (true iff both `power` and `toughness` are non-empty). `evaluate_reminder_template` now takes a keyword-only `card_facts` parameter; `_eval_predicate` accepts both `params` (for `name.value=="X"`) and `card_facts` (for function calls).
- [web/routes/browse.py](src/mse_viewer/web/routes/browse.py) — added `_card_facts(row)` helper. `_build_keyword_reminder_resolver` accepts a `card_facts` kwarg and forwards it to `evaluate_reminder_template`. Both `cards_detail` and `tokens_detail` build a `card_facts` dict from the resolved row and pass it through.
- [web/templating.py](src/mse_viewer/web/templating.py) — `render_reminder` is unchanged (no card context on keyword detail pages); `has_pt()` resolves to "unknown" → empty fallback as designed.

Verified inline: `{if has_pt() then "creature"}` → `creature` with PT, `` (empty) without. Existing `Toxic 1` / `Toxic 2` plurality templates still resolve correctly.

## Wave 2 — implemented

- [parser/tags.py](src/mse_viewer/parser/tags.py) — added `_RE_MARGIN_FAMILY` (`</?margin(?::[^>\s]*)?(?:\s[^>]*)?>`) to `strip_wrapper_tags`. Margin spans now disappear at canonicalization time on every text field.
- [parser/special_text.py](src/mse_viewer/parser/special_text.py) — new module. `extract_italic_flavor(raw, *, protect_first_line)` masks atom-reminder spans, pulls out non-keyword `<i>...</i>` italic spans into a flavor return string, and re-stitches the rule_text minus those spans. `parse_starting_loyalty(raw)` is the integer coercion helper.
- [parser/models.py](src/mse_viewer/parser/models.py) — `ParsedCardFace.starting_loyalty: int | None`.
- [parser/card_parser.py](src/mse_viewer/parser/card_parser.py) — added `detect_frame(super_type, sub_type) -> "planeswalker"|"emblem"|"saga"|"leyline"|"normal"` and `is_evolution_planeswalker(super_type)`. `_face_from_node` now branches on frame: planeswalker / saga read `special_text` (falling back to `rule_text` if empty); leyline / saga apply the italic-flavor splitter; emblem appends its `sub_type` to `related_from_notes`; planeswalker reads `loyalty` (suffix-aware) into `starting_loyalty`. Related-from-notes is deduped at the end so emblem subtype + Evo-alias mining don't double-list.
- [domain/card.py](src/mse_viewer/domain/card.py) — `starting_loyalty: Mapped[int | None]` column on `Card` only (Tokens never have it; emblems are tokens).
- [alembic/versions/0003_card_starting_loyalty.py](alembic/versions/0003_card_starting_loyalty.py) — migration adds `cards.starting_loyalty INTEGER NULL`.
- [ingest/derivations/design_type.py](src/mse_viewer/ingest/derivations/design_type.py) — frame short-circuits at the top: Emblem / Planeswalker / Saga / Leyline always return `Normal`. The `m15-emblem-name-cut` / `future-planeswalker-horizontal` / `m15-saga` stylesheets are also allowlisted to `Normal` so a bare-stylesheet match doesn't punt to the playbook prompt.
- [ingest/preview.py](src/mse_viewer/ingest/preview.py) — `_check_frame_type_mismatch` raises the new `frame_type_mismatch` warning when the stylesheet expects a frame the type line doesn't deliver. Planeswalker-with-alias (and not Evolution) raises the new `planeswalker_alias` warning so the modal asks the user about design type. Emblem rarity-special is silenced by virtue of `is_token_route` already short-circuiting.
- [ingest/warnings.py](src/mse_viewer/ingest/warnings.py) — new `WarningKind.frame_type_mismatch` and `WarningKind.planeswalker_alias`.
- [ingest/pipeline.py](src/mse_viewer/ingest/pipeline.py) — fresh-create for `effective_route == "card"` writes `starting_loyalty=face.starting_loyalty` onto the new Card. Update path writes the field only when `face.starting_loyalty is not None`, matching the empty-import guard pattern used for other fields.
- [web/templates/cards/detail.html](src/mse_viewer/web/templates/cards/detail.html) — new `Starting loyalty` row; only renders when the card has one.

Verified inline against synthetic Kathleen-style Planeswalker, Three-Visits-style Saga, Leyline-of-Equilibrium-style Leyline, Scorched-Earth-Emblem-style Emblem, and a deliberately mistyped `m15-saga` Creature: each produces the expected `frame`, `route`, `design_type`, `starting_loyalty`, `rule_text` / `flavor_text` split, and `warnings` set.

## Wave 3 — implemented (folded in with Wave 2)

- [ingest/derivations/routing.py](src/mse_viewer/ingest/derivations/routing.py) — `is_token_route` now matches `"emblem"` in supertype as well as `"token"` and `evo-t`.
- [ingest/pipeline.py](src/mse_viewer/ingest/pipeline.py) — new `_apply_emblem_cross_link(face, route, row, repos)` mirrors `_apply_evo_t_cross_link`: when an Emblem commits to Tokens, look up any Card whose name matches the Emblem's `sub_type` and append both directions of the cross-reference. Re-runnable; the related lists are de-duped by `append_related`.
- The Saga / Leyline italic-flavor splitter and `<margin>` strip live in the parser changes already covered in Wave 2.

## Files touched

```
alembic/versions/0003_card_starting_loyalty.py     (new)
src/mse_viewer/domain/card.py
src/mse_viewer/ingest/derivations/design_type.py
src/mse_viewer/ingest/derivations/routing.py
src/mse_viewer/ingest/pipeline.py
src/mse_viewer/ingest/preview.py
src/mse_viewer/ingest/warnings.py
src/mse_viewer/parser/card_parser.py
src/mse_viewer/parser/models.py
src/mse_viewer/parser/reminder_template.py
src/mse_viewer/parser/special_text.py              (new)
src/mse_viewer/parser/tags.py
src/mse_viewer/web/routes/browse.py
src/mse_viewer/web/templates/cards/detail.html
src/mse_viewer/web/templating.py                   (no change required after final pass)
```

## What to verify on your end

- `alembic upgrade head` to apply `0003`.
- Re-import Kathleen / a Planeswalker with no alias → auto-commits as Normal, no modal; detail page shows Starting loyalty: 4.
- Import a Planeswalker with a non-Evolution alias → modal appears with the `planeswalker_alias` warning, design_type field pre-filled `Normal` and editable.
- Import an Evolution Planeswalker (alias mandatory) → no modal.
- Import an Emblem → routes to Tokens silently, sub_type shows under Related cards on the Emblem and on the planeswalker (if the planeswalker is in the DB; otherwise `(missing)`).
- Import the example Leyline → `<i>...</i>` mid-text moves to flavor.
- Import a Saga → first reminder line stays as ability text; chapter-trailing italics move to flavor.
- Re-render any card whose reminder text uses `{if has_pt() then "creature"}` — the word "creature" should now appear when the card has P/T, and disappear cleanly when it doesn't.
