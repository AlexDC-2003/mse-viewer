# Phase-1 bugfix pass

Twelve issues from `phase1_prompt_3` are fixed in code; #14 is held pending the tag-stripping discussion.

## Fixes

| # | Issue | Where it landed |
| --- | --- | --- |
| 1 | Upload form: clicking near the file input opened the picker / cleared the file when cancelled | [upload.html](../../../src/mse_viewer/web/templates/upload.html): the `<label>`-wrapping is replaced with a `.field` wrapper so only the input itself opens the dialog |
| 2 | `card_subtype` not stripped of `<atom-sep>` / `<soft>` / `<word-list-*>` and trailing whitespace | [parser/tags.py](../../../src/mse_viewer/parser/tags.py) gains `strip_all_tags`; [parser/card_parser.py::_join_type_chain](../../../src/mse_viewer/parser/card_parser.py) uses it for super_type / sub_type |
| 2b | Missing `rarity:` line broke the UI | [card_parser.py](../../../src/mse_viewer/parser/card_parser.py) auto-fills `"common"` and sets `rarity_missing=True`; [review_modal.html](../../../src/mse_viewer/web/templates/review_modal.html) shows *"Missing (Presumed common)"* in that case |
| 3 | Multi-line `rule_text:` with sub-indented body wasn't accumulated; `keyword_refs` therefore came back empty | [parser/tree.py](../../../src/mse_viewer/parser/tree.py): always prep `pending_text` when pushing a node, regardless of whether the keyed line had an inline value |
| 4 / 6 | Cards that needed no decisions still triggered the review modal | [services/ingest_session.py](../../../src/mse_viewer/services/ingest_session.py): clean previews are now committed during session creation; the modal only opens for cards with real warnings. End-to-end test in this turn confirms Driad Dragon, Obliterate and your "Snow Promo" example all auto-pass with zero warnings. |
| 5 | `frames: fnm promo, snow` triggered a review on `m15-altered` | [ingest/derivations/design_type.py::_frames_without_snow](../../../src/mse_viewer/ingest/derivations/design_type.py): `snow` is filtered out of `frames` for *every* stylesheet before the rule table runs |
| 7 | (skipped — empty in source prompt) | — |
| 8 | Add planeswalker + emblem parsing TODOs to Phase 2 | [phase1_prompt_2.md](phase1_prompt_2.md) §2 carryovers gets two new bullets |
| 9 | Token cards showed `token_routing` "confirm" warnings even though there's no choice to confirm | [ingest/preview.py](../../../src/mse_viewer/ingest/preview.py): token routing is now silent (no warning); `rarity_special` only fires when super_type *didn't* already pin routing to Tokens |
| 10 | Empty PWL fields → 422 from FastAPI's int parsing | [routes/upload.py](../../../src/mse_viewer/web/routes/upload.py): PWL inputs accept strings, are parsed manually, and any blank value is dropped without erroring |
| 11 | rule_text not fully stripped: `<kw-a>`, standalone `<key>`, `<param-*>`, leftover `<i>` | [parser/tags.py](../../../src/mse_viewer/parser/tags.py): `_RE_KW_BLOCK` now matches `[a-zA-Z0-9]+` ids (DOTALL + IGNORECASE); a new `strip_wrapper_tags` covers `<key>` / `<atom-param>` / `<param-cost>` / `<param-number>` / `<nospellcheck>` / `<atom-sep>` / `<soft>` / `<atom-reminder*>` / `<b>`. Italics (`<i>` / `<i-auto>` / `<i-flavor>`) are normalized to a single `<i>` and *kept* in the DB. |
| 11b | Italic rendering in the UI | [web/templating.py::render_text](../../../src/mse_viewer/web/templating.py) Jinja filter HTML-escapes the value and then re-enables a tiny whitelist (`<i>`, `<em>`, `<b>`); newlines become `<br>`. Applied in [review_modal.html](../../../src/mse_viewer/web/templates/review_modal.html), [cards/detail.html](../../../src/mse_viewer/web/templates/cards/detail.html), [tokens/detail.html](../../../src/mse_viewer/web/templates/tokens/detail.html), [keywords/detail.html](../../../src/mse_viewer/web/templates/keywords/detail.html). |
| 12 | `<sym-auto>RW</sym-auto>` should become `{R}{W}` | [parser/tags.py::_tokenize_mana_string](../../../src/mse_viewer/parser/tags.py) splits each mana slot, preserving hybrid syntax: `RW → {R}{W}`, `2WU → {2}{W}{U}`, `2/W → {2/W}`, `2/W2/U → {2/W}{2/U}`. |
| 13 | "Reject & log" couldn't fire when a `required` field was empty | [review_modal.html](../../../src/mse_viewer/web/templates/review_modal.html): the reject button gets `formnovalidate` so HTML5 validation is bypassed for that path |

## #14 — keyword `match:` tags: inventory + recommendation

Per your instruction, **no tag-stripping code has been changed in this pass**. What follows is the inventory + a recommendation, awaiting your sign-off.

### Tag inventory

#### In keyword `match:` strings (the place that surfaced #14)

| Tag | DB | Display | Why |
| --- | --- | --- | --- |
| `<atom-param>label</atom-param>` | keep verbatim | render as styled chip `[label]` | The literal match string is the identity (strict B from init_prompt_4 #2). Stripping it loses param-slot positioning. |

#### In card `rule_text` / `flavor_text` / keyword `reminder` / keyword `rules`

| Tag | DB policy | Notes |
| --- | --- | --- |
| `<sym>X</sym>`, `<sym-auto>X</sym-auto>` | transform → `{X}` (Scryfall) | each atomic slot becomes its own `{...}`; hybrid `2/W` → `{2/W}` |
| `<kw-N>...</kw-N>` (digit OR letter id) | strip wrapper, keep body | reference also extracted into `keyword_refs` |
| `<key>NAME</key>` (inside or outside a `<kw-N>` block) | strip wrapper, keep body | `NAME` is captured as a keyword ref |
| `<param-name>X</param-name>`, `<param-cost>X</param-cost>`, `<param-number>X</param-number>`, `<param-text>X</param-text>` | strip wrapper, keep body | per-card concrete values; Phase 2 could store these as "param bindings on this card → keyword" if useful |
| `<i>...</i>`, `<i-auto>...</i-auto>`, `<i-flavor>...</i-flavor>` | keep, normalized to `<i>` | UI renders italic |
| `<b>...</b>` | keep | UI renders bold |
| `<word-list-*>...</word-list-*>` | strip everywhere | typeahead artifacts, no semantic value |
| `<nospellcheck>`, `<soft>`, `<atom-sep>` | strip wrapper, keep body | MSE editor noise |
| `<atom-reminder>`, `<atom-reminder-custom>` | strip wrapper, keep body | the body is usually italic; that survives |

#### In `super_type` / `sub_type`

Pure plaintext — strip every `<...>` wrapper, collapse whitespace. (`strip_all_tags`, used by `_join_type_chain` since the bugfix.)

#### Tags not yet seen but might appear

`<o-flavor>`, `<o-auto>`, `<icon>`, `<frame>`, `<color-*>` — none have shown up. If one does, the parser leaves it in place and we log a parse-punt action, then revisit policy.

### Recommendation: keep wrappers in DB, beautify in UI

Concretely:

- New Jinja filter `render_match` in [web/templating.py](../../../src/mse_viewer/web/templating.py): HTML-escape then re-enable `<atom-param>X</atom-param>` as `<span class="param">X</span>`. Same shape as `render_text` for italics.
- CSS for `.param`: monospace, light background, rounded corners; tinted variant when `accepted_parameters` includes a `cost`-shaped label so mana-cost slots stand out.
- Keyword detail page: show the rendered match large, plus the raw match string in a `<code>` block beneath.

Why not strip in the DB: two keywords with the same name but different param *signatures* (`Suspend <atom-param>number</atom-param>` vs `Suspend <atom-param>cost</atom-param>`) are different keywords by strict B. Stripping the wrapper collapses them to `Suspend number` / `Suspend cost` — distinct strings here, but the first time someone defines a keyword with a literal word that happens to match a param label we'd silently merge them. Keeping the wrapper is cheap insurance. `accepted_parameters` already exposes the bare label list (`["number"]`) for anywhere that needs it without parsing the match string.

If approved the change is purely additive (filter + template + CSS) — no parser changes, no migration.

## Verification done in this turn

- Lexer/tree: multi-line `rule_text:` produces a joined string and `keyword_refs` populates correctly (incl. `<key>...<param-cost>...</param-cost></key>` style refs like *ward 2*).
- design_type: Driad Dragon → `Unique`, Obliterate → `Colorpushed`, Snow-promo with `fnm promo, snow` → `Colorpushed`. None of them generate warnings.
- Mana splitting: `RW`, `2WU`, `2/W`, `2/W2/U`, `R/W` all tokenize correctly.
- Italic filter: `<i>...</i>` and `<b>...</b>` survive, `<script>` stays escaped, newlines become `<br>`.
- FastAPI app boots; 23 routes register.
