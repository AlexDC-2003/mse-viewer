# Phase 1.5 — Recurrent Zap regression fix + multi-word auto-promote

## The bug: Recurrent Zap stored as "Zap"

Self-introduced in this round's Fix #5 ((Evo-X) suffix strip). The original alias-mining code was a generator expression:

```python
related_from_notes.extend(s.strip() for s in rest.split(",") if s.strip())
```

A comprehension's loop variable doesn't bind in the enclosing function scope. When I rewrote it as a real `for` loop to add the `_RE_EVO_SUFFIX.sub(...)` call, I bound the loop variable to `name`:

```python
for raw in rest.split(","):
    name = _RE_EVO_SUFFIX.sub("", raw).strip()  # shadows the outer `name`
    if name:
        related_from_notes.append(name)
```

That `name` shadowed the function-scope `name = node.get(...).strip()` at line 59, the card's identity. After the alias loop ran, `name` held the **last alias segment** ("Zap") and the `ParsedCardFace(name=name, ...)` call at the bottom built the face with the wrong identity. The pipeline then created a Cards row with `name="Zap"` instead of `"Recurrent Zap"` — and on subsequent Recurrent Zap imports, identity lookup found the existing "Zap" row and kept overwriting it. Hence "evos basically ref themselves": the row in DB literally was the alias target.

Fix: rename the loop variable to `related_name` so the outer `name` survives. Verified by running `parse_set_text` against your Recurrent Zap block — the parsed face is now `('Recurrent Zap', related_from_notes=['Zap'])` as it should be.

The `(missing)` annotation on related cards (Fix #4 from the previous round) should also start showing correctly now that the related entry actually says "Zap" (with no Cards row by that name) instead of "Recurrent Zap" (which always exists, so the link looped back to itself).

**You will need to re-import affected cards** — anything where the alias started with `Evo:`/`Evolved:`/`Related:` and had at least one comma-segment was committed under the alias-target name. The Cards/Tokens rows that exist now under wrong identities won't fix themselves; clean import re-runs them through the corrected parser.

## Multi-word stubs now auto-promote too

Per your "OK seeing real reminders, just promote them" decision: `_is_self_defining` in [repository/keywords.py](src/mse_viewer/repository/keywords.py) is now `not has_atom_param(name)` — single- and multi-word forms both promote when a reminder is captured. Only names that already contain an `<atom-param>` slot (parameterised match strings, only ever produced by formal `keyword:` blocks) stay as stubs.

So after this change:

* `Haste`, `Triple strike`, `Strikethrough`, `Ward 3` → promote to `is_stub=False` as soon as a reminder is captured. The `(no definition yet)` annotation disappears for them.
* `Cleave <atom-param>cost</atom-param>`, `Ward <atom-param>cost</atom-param>` → still stays as stubs unless backed by a real `keyword:` block.

Trade-off (flagged for you): the existing absorption logic in `_absorb_matching_stubs` only merges `is_stub=True` rows. So if you import a parameterised `Ward <atom-param>cost</atom-param>` block *after* `Ward 3` has already been auto-promoted, the auto-promoted `Ward 3` row will not be absorbed — it'll sit alongside the parameterised definition as a separate keyword. Same for any other case where literal-value stubs predated the parameterised block. If that bites in practice, the fix is to broaden absorption to also pick up non-stub rows whose name structurally matches and whose `accepted_parameters` is empty (a heuristic for "previously auto-promoted") — say the word and I'll add it.

Verified inline (`9/9` cases): the predicate behaves correctly across single-word / multi-word / parameterised / empty inputs.

## Files touched this round

* [parser/card_parser.py](src/mse_viewer/parser/card_parser.py): rename shadowed `name` → `related_name` in the alias-mining loop.
* [repository/keywords.py](src/mse_viewer/repository/keywords.py): `_is_self_defining` now accepts multi-word names.

## What to verify on your end

* Re-import a set with Evolution / Evolved / Related-prefixed aliases — the Cards row should now keep its real `name:` value, and the related-card list should show the alias targets with `(missing)` annotations when those targets aren't (yet) in the DB.
* Triple strike, Strikethrough, Hexproof and other multi-word reminder-only stubs should lose their `(no definition yet)` annotation after re-import.
