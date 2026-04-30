# Phase 1 — final bugfix pass

## Fixes

### Modal / Review

| # | Issue | Fix |
| --- | --- | --- |
| 1 | "Choose Cards or Tokens DB" picker invisible despite the warning | **Root cause**: Jinja2 `{% set %}` inside a `{% for %}` loop is scoped to the loop body, so my flag stayed `false` after the loop ended.  Switched to a `namespace` object (`ns.has_rarity_special` / `ns.has_conflict`) — same pattern fixes the identity-conflict picker that was hiding the same way. |
| 2 | Stub keywords showed lowercase in `keywords (refs)` | The "refs" row in [review_modal.html](../../../src/mse_viewer/web/templates/review_modal.html) now applies `\|capitalize` to each ref so `flying`/`reach` display as `Flying`/`Reach`.  (The stored stub names were already canonicalized; this fix is just the modal display.) |

### Parser / Tag stripping

| # | Issue | Fix |
| --- | --- | --- |
| 8 | `M<kw-1>ulti-strike 3 (...)` left ``<kw-1>`` in the rendered text because the closer was missing | new `_RE_STRAY_KW` regex runs at the end of `canonicalize_text` and removes any unpaired `<kw-…>` / `</kw-…>`. |
| 9 | `<soft-line>` (and friends) survived in keyword `notes`/`reminder` | [parser/keyword_parser.py](../../../src/mse_viewer/parser/keyword_parser.py) now runs `canonicalize_text` over both fields before storing, so the keyword detail page no longer leaks markup. |
| 5 | When a card had `Triple strike (...)` followed by parenthetical reminder text, the resulting stub had no body — useless in the Keywords list | **Two-stage fix.** The first attempt only recognised `<atom-reminder…>` blocks that *followed* the `<kw-N>` close, but real MSE wraps the reminder *inside* the kw block (e.g. `<kw-A>...<atom-reminder-custom>(...)</atom-reminder-custom></kw-A>`).  `iter_keyword_invocations` now searches inside the body first and falls back to scanning after the close — both positions captured.  `card_parser.py` keeps a lower-case-ref → reminder map; the ingest pipeline forwards into `KeywordRepository.ensure_stub(ref, reminder=…)`.  Plus `KeywordRepository.upsert_from_parsed` no longer clobbers a card-captured reminder when a later `keyword:` definition without its own reminder lands. |
| 5b | "If a stub is populated by a reminder text, it kinda stops being a stub" | Kept `is_stub=True` on the row (absorption still needs to walk it when a fuller `Cleave <atom-param>cost</atom-param>` definition lands later), but the UI label now distinguishes: card / token detail show **(no definition yet)** when the reminder is set vs **(stub)** when fully empty. |

### Keyword UI

| # | Issue | Fix |
| --- | --- | --- |
| 6 | Tokens detail page didn't show `(stub)` next to stub keywords | [tokens/detail.html](../../../src/mse_viewer/web/templates/tokens/detail.html) now mirrors the cards page (renders `\| render_match` and appends `(stub)` for `is_stub` rows). |
| 7 | Keyword names with `<atom-param>` wrappers showed as `Rearm <atom-param>cost</atom-param>` on card / token detail | both detail templates now apply the `render_match` filter, so the same row shows as `Rearm <cost>`.  Match was already applied on the keyword list and detail pages — this extends it to the per-card / per-token "Keywords" sections. |

### Misc UI

| # | Issue | Fix |
| --- | --- | --- |
| 10 | Power-level fields hidden behind a `<details>` collapsible | [upload.html](../../../src/mse_viewer/web/templates/upload.html): wrapped in a plain `<fieldset>` instead, fields visible by default. |
| 11 | Resolving / reopening a log entry redirected to `/log` and scrolled the page back to the top | [routes/log.py](../../../src/mse_viewer/web/routes/log.py) redirects to `/log#entry-{id}` and the row gets `id="entry-{id}"`.  Plus a CSS `tr:target { background: … }` highlight in [style.css](../../../src/mse_viewer/web/static/style.css) and `html { scroll-behavior: smooth }` so the jump is visible-but-soft.  *Note*: a true zero-jump fix needs HTMX inline updates — that's the planned Phase 2 polish. |
| 12 | Cards / tokens browse table showed raw `<i>...</i>` markers in the rule_text snippet | new `render_text_snippet` filter in [web/templating.py](../../../src/mse_viewer/web/templating.py): same as `render_text` (italic preserved, everything else escaped), but truncates to 120 characters and **balances any `<i>` / `<b>` whose closing tag fell outside the truncation window**.  Without that balance, a snippet ending mid-italic would italicize the rest of the page. |

## Verification done in this turn

- Reminder capture: `<kw-0>...<key>Triple strike</key></kw-0><atom-reminder-core>(reminder)</atom-reminder-core>` extracts the parenthetical and pins it to the stub.  Same for `<atom-reminder-expert>` and bare `<atom-reminder>`.
- Stray `<kw-1>` in `M<kw-1>ulti-strike 3 (text)</kw-1>` and the malformed `M<kw-1>ulti-strike 3 (no closer)` both produce `Multi-strike 3 (...)` cleanly.
- Snippet balancing: input ending `<i>(This creature deals fi…` correctly auto-closes with `</i>`.
- App boots; 23 routes register.

## Phase 2 plan additions

Folded into [phase1_prompt_2.md](phase1_prompt_2.md) §2:

- **Override-field dropdowns** — `<datalist>` of existing values for Design Type / Rarity / Colors during review (init_prompt_5 #3).
- **Conditional reminder pretty-printer** — evaluate MSE template logic (`{ if param1.value == "1" then ... else ... }`) inline at display time (init_prompt_5 #4).
- **Tag-insensitive queries** — search / filter operators must compare against tag-stripped text so the preserved `<i>` markers don't break "match this phrase" lookups (init_prompt_5 #12).
- **HTMX-inline log transitions** — eliminate the redirect entirely so the page never reflows (init_prompt_5 #11 — scroll anchor is the Phase 1 mitigation).
- Triple hybrid mana (G/U/R) and higher order hybrid mana should appear with brackets "( )"
- Keywords & abilities separated by ";" in the rules text should appear as on a new line (; should act as a line separator in the UI views. The line separation means you don't display the ";" character)
## Held / not yet implemented

- A standalone "Stubs queue" page (already in Phase 2 plan from earlier).
- Saga / Leyline / Planeswalker / Emblem face parsers (Phase 2).
