# Phase 2.0 prompt 1 — UI uplift

The prompt asked for a holistic visual rework: cleaner spacing and type
scale, two-column detail layouts, modern-platform feel without over-design,
indicator chips next to the card title, Evolution / Hero row hues, mana
symbol glyph rendering, rarity-tinted display names, a tick instead of
"yes" in the printed column, dropped "Colors" column, PWL moved last on
the cards table, and consistent button sizes / search-bar layout across
every page.

Everything below is reversible by checking out the previous CSS / template
files — no migrations, no schema changes, no data model touches.

---

## What changed

### 1. Mana-symbol rendering ([F.Mana-symbol rendering](../../files/todolist.md#f-ui-polish))

`{W}` / `{2/U}` / `{X}` / `{T}` / `{G/U/R}` and friends inside any
`render_text` / `render_rule_text` / `render_reminder` / `render_cost`
output now produces a `<span class="mana mana-X">…</span>` glyph instead
of literal braces. The injection is a single regex pass that runs **after**
HTML escape (braces survive escape; the only HTML we inject is our own
controlled span markup), and the regex is narrow enough (`\{([0-9A-Za-z/]+)\}`)
that it can't escape into rule_text body content.

Glyph palette (CSS-only, no SVG sprite, no font dependency):

| Token | Glyph |
| ----- | ----- |
| `{W}` / `{U}` / `{B}` / `{R}` / `{G}` | white / blue / black / red / green circles with the letter inside |
| `{C}` | colorless gray circle |
| `{O}` `{L}` `{P}` `{K}` `{E}` `{N}` `{S}` | brewer / extended palette (orange / brown-land / phyrexian / pink / energy / teal / snow) |
| `{0}`–`{∞}` and `{X}` `{Y}` `{Z}` | colorless gray with the number / letter inside |
| `{T}` | gray pill with a curved-arrow tap glyph drawn from CSS pseudo-elements (no text) |
| `{G/U}` / `{R/W}` / `{2/W}` / `{W/P}` | hybrid pill — a wider oval split into two halves of the appropriate colors with the literal `G/U` text overlaid |
| `{G/U/R}` and other 3+-element hybrids | gradient oval covering all 5 colors as a fallback |

Storage is unchanged — the parser still writes Scryfall-style braces into
rule_text, and casting_cost still stores the raw MSE form. The template
layer calls a new public helper `parser.tags.casting_cost_to_braces` to
convert the raw cost into brace form before the same regex runs over it,
so the same glyphs render uniformly in both contexts.

Per the prompt, the **`colors` field is deliberately untouched** — it
goes through `render_colors`, not `render_text`, so the mana injector
never sees it.

### 2. Indicator chips in the card / token header

A new shared macro `_macros.html → ui.card_chips` emits the indicator row
in this order:

1. `Evolution` (light-purple gradient chip) if the card_type contains
   "Evolution".
2. `Hero` (gold gradient chip) if the card_type contains "Hero".
3. `Legendary` (cyan / green / white / purple aura gradient) if the
   card_type contains "Legendary".
4. `Snow` (snowy white-gray-blue gradient) if the card_type contains
   "Snow".
5. `Printed` (dark slate chip with a leading ✓) when `printed == true`.
6. The rarity chip with rarity-themed colors:
   - common → solid black
   - uncommon → silver gradient
   - rare → gold gradient
   - mythic rare → metallic orange gradient
   - special, or any token → metallic light-purple gradient

For tokens, the rarity chip label is `Token`. Tokens always read as
"special" for the rarity-class derivation (so the chip + display-name text
both use the metallic light-purple palette).

Chips sit in a flex `.chip-row` to the right of the title block, so the
column with the name and type line on the left is no longer paired with
empty whitespace on the right. The flex wraps onto a new line on narrow
viewports so chips never overflow.

### 3. Rarity-coloured display name + rarity text

`rarity_text_class(rarity)` returns the matching `.rarity-text-*` class.
The class is applied to the card's `<h2>` in the detail header, to the
"Display name" field value, to the "Rarity" field value, and to the
`<a>` linking each row in the cards / tokens list. Mythic and special
rarities use a `-webkit-background-clip: text` gradient so the text picks
up the same orange / purple gradient as the chip.

### 4. Two-column detail layout

The old plain `<dl>` was the source of the "everything is on the left,
right side empty" complaint. Detail pages now use a `.detail-grid` with
`grid-template-columns: repeat(2, minmax(0, 1fr))` and individual
`.field` cards stacked into the grid. Short-value fields (Display name,
Cost, Colors, Rarity, P/T, Power level, Design type, Sets, Alt arts,
Alias) sit two-per-row. Long-value fields (`related_cards`) carry a
`wide` class that spans both columns. On viewports under 720px the grid
collapses to a single column so nothing overflows.

### 5. Row hue for Evolution / Hero

`row_hue_class(obj)` returns one of `"row-evolution"`, `"row-hero"`, or
`""`. Templates apply it to the wrapping `<article class="…">` on the
detail page and to each matching `<tr class="…">` on the list views.
CSS paints a light-purple gradient on Evolution rows and a light-gold
gradient on Hero rows, plus a 3px coloured left border on the row's first
table cell so the cue reads quickly when scrolling a long list.

The prompt explicitly asked for the hue to cover the **entire detail
page** for Evolution / Hero cards — the `.row-evolution` / `.row-hero`
classes on the outer `<article>` paint both the body and the header bar,
matching that requirement.

### 6. Cards list cleanup

- Dropped the `Colors` column.
- Moved `PWL` to the rightmost position.
- The `Printed` column now shows a green ✓ tick if the card is printed
  and nothing otherwise — no more literal "yes" string.
- Each row is `<tr class="{{ row_hue_class(c) }}">` so Evolution / Hero
  rows pick up the hue.
- Each row's name link picks up the rarity color class, and the row
  carries small `Evo` / `Hero` / `Leg` chips inline with the link so the
  scan-by-eye reads quickly even when the row hue is subtle.
- Search bar / button / Advanced-search / New-card are now in a single
  `.toolbar` flex row where the search bar grows and the secondary
  buttons sit on the right separated by a `toolbar-spacer`. No more
  "Search button stretches the whole row, New deck button is small on
  the next row" layout.

The `/cards/advanced` link goes to a placeholder page (`Coming soon`) —
the actual per-field advanced search is a separate todo (§C).

### 7. Cards / tokens / keywords / decks / log / upload / review

Every list / detail / edit page picked up the same primitives:

- `.toolbar` for "search bar + buttons" layouts.
- `.action-row` for "buttons only" layouts (cancel / save / delete).
- `.detail-grid` for two-column field layouts on detail pages.
- `.chip` + `.chip-rarity-*` / `.chip-printed` / `.chip-hero` /
  `.chip-evolution` / `.chip-legendary` / `.chip-snow` for indicator
  chips.

The `.toolbar` keeps every button at the same 2.5rem height and stops
buttons from stretching to fill the row, addressing the "the Missing
button is smaller than the others" / "Search stretches across the row"
complaints.

The log table now renders state and kind through colored chips instead
of plain text — picks up the same rarity palette so "open" rows visually
match "rare" weight, "completed" rows visually match "uncommon" weight,
etc.

### 8. Modern-platform feel without over-design

- Soft radial gradient on the body background tints the top of every
  page with a barely-there indigo wash.
- Article surfaces get a 1px border + a layered soft shadow + a 0.6rem
  radius; the header band of the article has a faint indigo wash to
  separate it from the body.
- Calmer type scale — `h1 1.7rem`, `h2 1.35rem`, `h4 1.0rem`, body
  0.95rem. Field labels are `0.75rem` uppercase with a 0.06em
  letter-spacing so they read as labels, not body text.
- Table header rows use the same uppercase-tiny label treatment.
- Hover state on table rows uses the indigo tint as a backdrop.
- Pico's default styles are still loaded, so the form elements still
  carry the same focus / disabled affordances.

---

## Trade-offs / deviations

- **Advanced search button is wired but the endpoint returns a "Coming
  soon" stub.** The prompt asked for the layout `[search bar] [Search]
  … [Advanced Search] [New Deck]`, so the button is present; the actual
  per-field advanced search remains under todo §C.
- **Hero / Evolution detection is currently a substring match on
  `card_type`.** If the design taxonomy ever gets refactored into a
  dedicated column, only `templating.py` needs to update — the chip /
  hue classes are derived from one global so the templates are stable.
- **Hybrid mana glyphs use linear-gradient halves + an overlaid text
  label** rather than the Mana font / dedicated SVG file. Pure CSS works
  offline (no font CDN), but the visual is slightly less polished than
  the Mana font's hand-drawn glyphs. If the user prefers the Mana font
  look later, only `style.css` and `_mana_span_for_token` change — the
  rest of the rendering chain stays put.
- **Tap glyph is drawn from CSS pseudo-elements** rather than a real
  arrow SVG, which keeps the same "no asset files" property. The shape
  is a curved arc + chevron sized off the host font; it scales with the
  surrounding text.

---

## Files changed / added

### Added

- `src/mse_viewer/web/templates/_macros.html` — shared `ui.card_chips`
  macro consumed by every detail / list view.
- `src/mse_viewer/web/templates/cards/advanced.html` — placeholder
  "Coming soon" page for the Advanced search button.
- `documentation/responses/Phase 2.0 Prompts/phase2_prompt1.md` — this
  file.

### Modified

- `src/mse_viewer/web/static/style.css` — full rewrite. Spacing tokens,
  body wash, article surface, two-column `.detail-grid`, chip palette,
  rarity-text gradient classes, row-hue classes, `.toolbar` /
  `.action-row`, mana-glyph CSS (single + hybrid + tap + phyrexian),
  table polish, `.printed-tick`.
- `src/mse_viewer/web/templating.py` — added `_inject_mana_symbols`,
  `_mana_span_for_token`, `_hybrid_classes`; switched `render_text` to
  inject mana glyphs after the italic / line-break passes; rewrote
  `render_cost` to brace-then-inject; added `is_hero` / `is_evolution`
  / `is_legendary` / `is_snow` / `row_hue_class` / `rarity_slug` /
  `rarity_chip_class` / `rarity_text_class` / `rarity_chip_label`
  globals on the Jinja env.
- `src/mse_viewer/parser/tags.py` — exposed `casting_cost_to_braces`
  helper so the templating layer doesn't have to reach into
  `_tokenize_mana_string`.
- `src/mse_viewer/web/routes/browse.py` — added the `/cards/advanced`
  placeholder route (ordered before `/cards/{card_id}` so FastAPI
  doesn't try to interpret "advanced" as an int).
- `src/mse_viewer/web/templates/base.html` — light nav cleanup; removed
  the stray `<small>` around the "Missing" link.
- `src/mse_viewer/web/templates/home.html` — article surface +
  `.action-row` of secondary buttons.
- `src/mse_viewer/web/templates/upload.html` — fieldsets grouped,
  `.action-row` for the submit button, error banner replaced with
  `.warn-tile`.
- `src/mse_viewer/web/templates/cards/list.html` — new toolbar, dropped
  Colors column, PWL moved last, ✓ printed tick, row hue + inline
  chips, rarity-coloured name link.
- `src/mse_viewer/web/templates/cards/detail.html` — `.detail-header`
  with chip row, `.detail-grid`, row-hue article class, rarity-tinted
  title.
- `src/mse_viewer/web/templates/cards/edit.html` — grouped fields,
  `.action-row` for Save / Cancel / Delete buttons.
- `src/mse_viewer/web/templates/tokens/list.html` — same uplift as
  cards/list (no PWL / printed columns since tokens don't carry them).
- `src/mse_viewer/web/templates/tokens/detail.html` — same uplift as
  cards/detail; rarity chip is locked to `Token` (metallic
  light-purple).
- `src/mse_viewer/web/templates/tokens/edit.html` — grouped fields +
  `.action-row`.
- `src/mse_viewer/web/templates/keywords/list.html` — toolbar layout,
  pseudo / stub columns use ✓ / chip instead of "yes" / "yes".
- `src/mse_viewer/web/templates/keywords/detail.html` — header chip row,
  two-column field grid.
- `src/mse_viewer/web/templates/keywords/edit.html` — grouped fields +
  `.action-row`.
- `src/mse_viewer/web/templates/keywords/stubs.html` — toolbar styling.
- `src/mse_viewer/web/templates/decks/list.html` — `.action-row` for
  "Import deck file" + "New deck" buttons, format chip, centered Size.
- `src/mse_viewer/web/templates/decks/detail.html` — `.detail-header`
  with chips, `.detail-grid` for the eight short fields, prettied
  members table with bold Qty.
- `src/mse_viewer/web/templates/decks/edit.html` — grouped fields +
  `.action-row`.
- `src/mse_viewer/web/templates/log/list.html` — `.toolbar` for the
  filter form.
- `src/mse_viewer/web/templates/log/_row.html` — chip for kind / state
  columns; state chips colored by lifecycle stage.
- `src/mse_viewer/web/templates/related_missing.html` — muted-class
  cleanup, body row tightening.
- `src/mse_viewer/web/templates/review_modal.html` — `.detail-header`,
  `.detail-grid` over the parsed-values panel, `.warn-tile` callout,
  `.action-row` for the accept / reject / discard buttons.
- `src/mse_viewer/web/templates/review_done.html` — article surface +
  `.action-row` of follow-up links.

### Todo list

- `documentation/files/todolist.md` — struck through F.Evolution-Hero,
  F.Mana-symbol, and F.Mark-printed-cards-visually; added a one-line
  entry for "Phase 2.0 prompt 1" in the Completed section.
