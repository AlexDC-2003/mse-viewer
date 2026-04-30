# Phase 1 — second bugfix pass

## Fixes

### Tag stripping

| # | Issue | Fix |
| --- | --- | --- |
| 6 | `<atom-reminder-core>` / `<atom-reminder-expert>` / `<atom-reminder-custom>` survived in rule_text | [parser/tags.py](../../../src/mse_viewer/parser/tags.py): generic `_RE_ATOM_REMINDER_FAMILY` regex covers `<atom-reminder>` and any `<atom-reminder-…>` variant. Same treatment for `<atom-sep…>`. **Not** kept for UI — they were just bugs. |
| 11 | Flavor text kept tags (`<soft-line>`, `<i-flavor>`) | [parser/tags.py::canonicalize_flavor](../../../src/mse_viewer/parser/tags.py): aggressive strip-all for flavor — italic and everything else gone. The italic-preservation policy for rule_text stays. |
| 11 | `<param-*s>` plurality marker survived in rule_text | new `_RE_PARAM_FAMILY` covers `<param-*s>`, `<param-*es>`, `<param-name>`, `<param-cost>`, etc. — wrapper stripped, inner text preserved (`Gold toke<param-*s>n</param-*s>` → `Gold token`). |
| 11 | `</sym>1<sym>` swapped/stray symbol pair survived | `_RE_STRAY_SYM` final pass after mana normalization removes any `<sym…>` / `</sym…>` that didn't pair up. |

### Display

| # | Issue | Fix |
| --- | --- | --- |
| 5 | Hybrid casting costs unreadable (`G/UG/U`) | new `render_casting_cost` filter and `tags.py::render_casting_cost`: tokenizes the cost; hybrid slots wrap in parens — `G/UG/U → (G/U)(G/U)`, `2WU → 2WU` (unchanged), `2/W2/U → (2/W)(2/U)`. Applied in cards/tokens list + detail + review modal. |
| 4 | Cards browse table didn't show enough fields | [templates/cards/list.html](../../../src/mse_viewer/web/templates/cards/list.html) (and [tokens/list.html](../../../src/mse_viewer/web/templates/tokens/list.html)): now shows Name, Type, Cost, Colors, P/T, Rarity, PWL, Design, Sets, Alt arts, Printed, Rule-text excerpt. |
| 12 | Empty colors rendered as `—` | new `render_colors` filter — empty list → `colorless`. Applied wherever colors render. |

### Review modal & ingest

| # | Issue | Fix |
| --- | --- | --- |
| 2 | `rarity_special` warning had no UI control | review modal now renders a Cards-DB / Tokens-DB radio fieldset whenever the warning is present. The form field `route_override` flows from the modal through `commit_face`, where it overrides the auto-derived route. |

### Keyword identity & stub absorption — the headline change

| # | Issue | Fix |
| --- | --- | --- |
| 1 | Duplicate keyword refs (`First strike` and `first strike` both stored on the card) | [parser/card_parser.py](../../../src/mse_viewer/parser/card_parser.py): `keyword_refs` dedup is now case-insensitive (lower-case dedup key, first-seen casing preserved). |
| 7 | Case-sensitive matching meant `strikethrough` couldn't link to `Strikethrough` | [repository/keywords.py::find_for_card_ref](../../../src/mse_viewer/repository/keywords.py) does case-insensitive exact-name match before structural fallback. |
| 9, 10 | `Cleave 1RR`, `Cleave 4BB`, `Barrage 3` etc. became their own stubs instead of linking to the `<atom-param>`-shaped real keyword | **Full rewrite of `KeywordRepository`.** Card-side references now resolve via `find_for_card_ref(ref_text)`, which: (a) tries case-insensitive exact match on the literal name, then (b) compiles each parameterized definition's match string into a regex (`<atom-param>X</atom-param>` → `(.+?)`) and tests the reference against it, real definitions before stubs, then (c) singular-form retry. |
| (95) | "Food tokens" and "Food token" should fold to one stub; capitalization should normalize | `_stub_canonical` strips inline tags, drops trailing 's' (heuristic), and capitalizes the first letter — `food tokens` and `Food Tokens` both become the canonical `Food token`. Subsequent `food tokens` references reuse that same stub. |
| (54, 91-93) | "How would you know to update cards with stubs once a real definition lands?" | `KeywordRepository._absorb_matching_stubs` runs every time a real keyword is upserted: builds the regex, walks every `is_stub=True` row, and for each stub the regex matches it (a) re-points `Card.keyword_ids` and `Token.keyword_ids` from the stub id to the real id, then (b) deletes the stub. End-to-end test in this turn: two case-different stubs (`Cleave 1RR`, `cleave 4BB`) on two cards both got absorbed into the real `Cleave <atom-param>cost</atom-param>` automatically when its definition was upserted — both cards' `keyword_ids` updated. |

### Keyword UI

| # | Issue | Fix |
| --- | --- | --- |
| 8 | "Rules" field name on keyword detail | renamed to "Notes". |
| 14 (carryover from prompt 3) + 94 | Atom-param wrappers ugly in display | new `render_match` filter: `Barrage <atom-param>number</atom-param>` displays as `Barrage <number>` (literal angle brackets). Applied in keyword list and detail. The keyword detail page also shows the **Raw match** (literal stored string) in a `<code>` block — this is the strict-B identity the matcher uses. |

## Held / not yet done

- The user's question about `<atom-reminder-…>` "is it kept for UI?" — **no, that was a bug; it's stripped now.** Same for the `</sym>1<sym>` and `<param-*s>` survivors.
- A standalone "Stubs queue" page is in the Phase 2 plan; absorption is automatic but a dashboard would help confirm coverage at a glance.
- Stub tracking for **Related Cards**: today they're stored as plain strings on `card.related_cards` with no row to point at. A "missing referenced cards" view, plus optional auto-link when a card with that name is later added, is in the Phase 2 plan.

## Phase 2 plan additions

Added to [phase1_prompt_2.md](phase1_prompt_2.md) §2 carryovers:

- Saga parsing (chapters)
- Leyline parsing (mostly a Design Type tag question)
- Stub tracking dashboard (auto-absorption is wired; a UI to surface the queue is the missing bit)

## Verification done in this turn

- Tag stripping: `<atom-reminder-core>`, `<atom-reminder-expert>`, `<param-*s>`, `</sym>1<sym>`, `<soft-line>` — all confirmed gone.
- Mana split + casting-cost display: `2WU → 2WU`, `G/UG/U → (G/U)(G/U)`, `2/W2/U → (2/W)(2/U)`.
- Match display: `Barrage <atom-param>number</atom-param>` → `Barrage <number>`; `Suspend <atom-param>number</atom-param> - <atom-param>cost</atom-param>` → `Suspend <number> - <cost>`.
- Keyword absorption end-to-end: two stubs on two cards correctly merged into a single real keyword on upsert.
- Structural lookup: `Cleave 5G` and `cleave x` resolve to `Cleave <atom-param>cost</atom-param>` without creating new stubs.
- Singular-form stub canonicalization: `Food tokens` and `food token` fold to the same `Food token` stub.
