# Phase 2.0 prompt 3 — five more polish fixes

Follow-up to [phase2_prompt2](phase2_prompt2.md). All five are
self-contained CSS / templating tweaks. No migrations, no template
restructuring.

`?v=` cache-bust bumped to `phase2p3-20260524` so the previous stylesheet
doesn't mask these changes.

---

## 1. Special-rarity titles no longer get the gradient text

The pearl-purple gradient over the title looked noisy — the chip already
encodes the rarity, and the gradient text was hard to read against the
faint `row-mythic` / row-evo washes. `rarity_text_class` now returns
`""` for `special` rarity and for tokens:

```python
def rarity_text_class(rarity, *, is_token=False):
    slug = rarity_slug(rarity, is_token=is_token)
    if slug == "special":
        return ""
    return f"rarity-text-{slug}"
```

This is applied wherever the title and display-name picked up the class.
Effect: token titles render as default body color; rarity chips stay
pearl-purple. The same change covers any `special`-rarity card (the
non-token kind, rare in practice).

Common / uncommon / rare / mythic titles continue to take their
respective text colors as before.

## 2. Stronger Evolution row hue on the table view

Old: `tr.row-evolution > td { background: rgba(168, 132, 224, 0.10); }`
— at 10% alpha the purple barely read on a white table background.

New: introduced a dedicated `--mv-evo-row-bg` token at `rgba(151, 105,
220, 0.22)` — twice the alpha, slightly more saturated purple core. The
3px left-border on the first cell now uses the full `--mv-evo-chip-bg`
gradient so the row marker reads as the same purple as the chip in the
header.

Same treatment for `--mv-hero-row-bg` at `rgba(214, 162, 40, 0.22)` so
Hero rows visually balance.

Hover state on these rows now lifts to `0.30` alpha instead of using the
generic indigo hover tint, otherwise the indigo would have washed out
the purple/gold cue when the cursor was over a row.

The article-surface variants on detail pages (`--mv-evo-bg`,
`--mv-hero-bg`) stay at the lighter 0.10–0.13 alpha — those backgrounds
cover much more surface, so a darker tone there would be overwhelming.

## 3. Hero detected from `Heroic` supertype

`is_hero` accepted only `hero` as a type-line word. The corpus uses
`Heroic` ("Heroic Creature — Knight"), so cards weren't picking up the
chip / row hue.

```python
def is_hero(obj) -> bool:
    words = _supertype_words(getattr(obj, "card_type", None))
    return "hero" in words or "heroic" in words
```

Both spellings now trigger the chip + the row hue + the detail-page
wash. Verified end-to-end by creating "Heroic Creature — Knight" and
seeing `<article class="row-hero">` + `<span class="chip chip-hero">`
in the rendered detail page.

## 4. Mana glyphs raised so they sit on the text midline

Old `vertical-align: -0.22em` shifted the box **below** the baseline by
0.22em — visually the circles sat low under the surrounding letters.
Flipped sign and tightened the offset: `vertical-align: 0.15em` raises
the circle so its geometric centre lands roughly on the parent's
x-height middle. Now `Tap {T}: add {W} or {G}.` reads as a single
horizontal line with the glyphs nestled mid-line rather than dropping
under the descenders.

The same `.mana` class drives hybrid glyphs, so hybrids picked the
alignment up automatically.

## 5. Tap arrow flipped + rotated 90° clockwise

Applied the literal transform the user asked for to the inline SVG via
a `.mana-T .mana-icon` rule:

```css
.mana-T .mana-icon { transform: rotate(90deg) scaleY(-1); }
```

The SVG path itself is unchanged — only the rendered icon orientation
flips. Order is `scaleY(-1)` (flip vertically) then `rotate(90deg)`
(rotate 90° clockwise on screen), matching the prompt wording. If the
direction is wrong I can swap the transform order in one line.

---

## Files changed

- `src/mse_viewer/web/templating.py` — `rarity_text_class` returns `""`
  for special/token; `is_hero` accepts `Heroic` too.
- `src/mse_viewer/web/static/style.css` — `--mv-evo-row-bg` /
  `--mv-hero-row-bg` tokens, deeper hover tints for evo/hero rows,
  `.mana` vertical-align raised to `+0.15em`, `.mana-T .mana-icon`
  transform.
- `src/mse_viewer/web/templates/base.html` — CSS cache-bust to
  `phase2p3-20260524`.
- `documentation/responses/Phase 2.0 Prompts/phase2_prompt3.md` — this
  file.

---

## Follow-up batch (same prompt, second pass)

Three more table-view tweaks the user asked for after the initial pass:

### F1. Indicator chips moved into the Rarity cell, with full "Legendary"

Old layout (in the Name cell):
```
<td>
  <a>Card Name</a> <chip Evo> <chip Hero> <chip Leg>
</td>
…
<td><chip Mythic Rare></td>
```

New layout (in the Rarity cell):
```
<td>Card Name</td>
…
<td class="rarity-cell">
  <chip Evolution> <chip Hero> <chip Legendary> <chip Mythic Rare>
</td>
```

The supertype chips render BEFORE the rarity chip so the visual scan
reads "what kind, then how rare". The legendary chip now uses the full
word `Legendary` instead of the abbreviated `Leg` — same for evolution
(`Evolution`, not `Evo`). The `Hero` chip stays `Hero` because that's
already the canonical one-word label.

A new `.rarity-cell` selector (`display: flex; flex-wrap: wrap; gap:
.25rem`) lets the chips stack neatly when the cell is narrow without
overflowing into adjacent columns.

Applied to both `cards/list.html` and `tokens/list.html`.

### F2. Hero hue slightly brighter

Old hero palette:
```
--mv-hero-bg:      rgba(231, 191,  80, 0.13);
--mv-hero-row-bg:  rgba(214, 162,  40, 0.22);
--mv-hero-border:  rgba(231, 191,  80, 0.45);
--mv-hero-chip-bg: linear-gradient(135deg, #f6c651 0%, #c89316 100%);
```

New hero palette — small bump in saturation and luminance:
```
--mv-hero-bg:      rgba(248, 211,  86, 0.18);
--mv-hero-row-bg:  rgba(241, 191,  38, 0.28);
--mv-hero-border:  rgba(241, 191,  38, 0.50);
--mv-hero-chip-bg: linear-gradient(135deg, #ffd95a 0%, #d49a14 100%);
```

Hover tint on hero rows also lifted from `0.30` → `0.36` alpha so the
hover state still reads against the slightly brighter base.

### F3. Column reorder — Sets after Rule text, PWL behind the toggle

Old card-list column order:
`Name · Type · Cost · P/T · Rarity · Sets[adt] · Printed · Rule text · PWL`

New order:
`Name · Type · Cost · P/T · Rarity · Printed · Rule text · Sets[adt] · PWL[adt]`

Sets sits immediately after Rule text (still gated by the
"Additional info" toggle, since long set lists are noisy on a busy
table), and the PWL column is now ALSO gated by the toggle — by default
the table ends at "Sets" being hidden, "Rule text" being the rightmost
visible column. With the "Additional info" checkbox on in the nav, the
two extra columns appear together on the right.

Tokens don't carry PWL or Sets so their table is unchanged by this
fix.

### Files changed (follow-up)

- `src/mse_viewer/web/templates/cards/list.html` — chip migration into
  rarity cell, full-word chips, column reorder, PWL gated by
  `additional-info`.
- `src/mse_viewer/web/templates/tokens/list.html` — chip migration into
  rarity cell with full-word chips.
- `src/mse_viewer/web/static/style.css` — brighter Hero palette,
  `td.rarity-cell` flex/wrap rule.
- `src/mse_viewer/web/templates/base.html` — CSS cache-bust bumped to
  `phase2p3b-20260524`.

### Regression fix: rarity cell row-hue gap

First follow-up pass put `display: flex` on the `<td>` itself. Side
effect: replacing `display: table-cell` with `display: flex` removes
the cell from the table's column-grid layout, so the row's
background color (the Evolution / Hero / Mythic hue) stopped painting
that cell — the page background punched through behind the chips.

Fix: keep the `<td>` as a normal table cell and put a
`<div class="rarity-cell-inner">` inside it for the chip layout. The
flexbox lives on the inner div, the table-layout / row-background
stays on the `<td>`. CSS class renamed from `td.rarity-cell` to
`.rarity-cell-inner` to reflect that.

CSS cache-bust bumped to `phase2p3c-20260524`.
