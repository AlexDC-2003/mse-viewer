# Phase 2.0 prompt 2 — eight UI polish fixes

Follow-up to [phase2_prompt1](phase2_prompt1.md). Eight discrete fixes;
all CSS / template / templating-helper changes — no migrations.

The `?v=` cache-bust query on `<link href="/static/style.css">` was bumped
to `phase2p2-20260524` so browsers don't keep the old stylesheet pinned.

---

## 1. Tap glyph — cleaner icon, also catches literal `<T>`

The old `mana-T` used CSS pseudo-elements (a curved border + a tiny
triangle) to draw the arrow. It read poorly at small sizes — the arc and
arrowhead never quite met.

Replaced it with an **inline SVG** emitted by `_TAP_SVG` in
[templating.py](../../../src/mse_viewer/web/templating.py): a 270° clockwise
arc + a triangle arrowhead at the top, drawn in `currentColor` so the chip
text-color palette controls the arrow ink. The SVG is sized at `width: 78%;
height: 78%` of the chip so the strokes don't touch the rim. The chip's
own `<span class="mana mana-T">` still supplies the gray background.

`render_text` also now catches the **legacy literal `<T>`** form that
older reminder text carries. The reminder strings in storage sometimes
have `<T>` (no `<sym>` wrapper) — post-escape they become `&lt;T&gt;`,
which the brace tokenizer never sees. A second pass `_ANGLE_TAP_RE`
finds that exact escaped pattern and replaces it with the same tap glyph
markup. Confirmed against the user's example: `"Haste (This creature can
attack and <T> as soon as it comes under your control.)"` now renders
the tap glyph in place of the literal angle-bracket form.

The pattern is intentionally narrow (only `&lt;T&gt;`, not
`&lt;[any letter]&gt;`) so it doesn't accidentally convert keyword
parameter labels like `<X>` into mana glyphs.

## 2. Special rarity — whiter purple

Old special: `linear-gradient(135deg, #c8a8e9 0%, #b18cd9 50%, #8a6fc9 100%)` —
a saturated purple identical in tone to the Evolution chip.

New special: `linear-gradient(135deg, #fbf5ff 0%, #e9d5fa 45%, #c4a6e6 100%)` —
near-white at the start, soft lavender mid, pale purple at the end. Plus
the special chip's text color is now `#6f4ba0` (dark purple ink on the
pearl background) rather than white-on-purple — much higher contrast and
visually distinct from the bold Evolution palette.

The same `--mv-rarity-special` gradient also drives the `.rarity-text-special`
gradient-text used on token display names, so token titles now read as
soft pearl-purple instead of saturated purple.

## 3. Mythic-rare detail-page wash

Added a `row-mythic` row-hue class that paints a faint metallic-orange
wash on the article background — same shape as `row-evolution` /
`row-hero` but tied to the mythic color. A new
`detail_hue_class(obj)` global picks the right class for the detail
page only:

```
Evolution? → row-evolution      (priority 1)
Hero?      → row-hero           (priority 2)
Mythic?    → row-mythic         (only if neither above)
else       → ""
```

List views still call the old `row_hue_class` (no rarity hue) so the
table doesn't fill with orange rows. Tokens use `detail_hue_class` too
but their stored rarity isn't "mythic", so the mythic case never fires
for them.

Per the prompt's "rarities take priority for the text" clause: the row
hue (background) is set by evo/hero first, mythic second. The text-color
classes (`rarity-text-*`) are still applied independently to the title
and display-name, so a Hero card with mythic rarity still has a
mythic-gradient title even though the background is the Hero gold wash.

## 4. Detail rarity field text — only mythic colors it

Old behaviour applied `rarity_text_class(card.rarity)` unconditionally to
the rarity field, so common cards got an obvious-but-noisy black, uncommon
got gray, rare got gold, etc.

New behaviour: the rarity field only carries `rarity-text-mythic` when the
card actually is mythic-rare:

```html
<p class="field-value{% if rarity_slug(card.rarity) == 'mythic' %} rarity-text-mythic{% endif %}">
    {{ card.rarity }}
</p>
```

Common / uncommon / rare cards now show their rarity as default body
text — the rarity chip in the header still encodes the color (the gold
chip for rares, etc.), so no information is lost.

The display-name field still picks up rarity color across the board
(common = solid black, uncommon = silver-gray, rare = gold, mythic =
metallic-orange gradient, special / token = pearl-purple gradient).

## 5. Mana glyphs in line with text

Switched from `width/height: 1.05em; font-size: 0.78em; vertical-align: -0.12em`
to `width/height: 1.15em; font-size: 0.85em; vertical-align: -0.22em`. The
larger box means the circle's geometric centre lands on the text's
visual midline rather than on the baseline. Side-effect: the letters
inside (W / U / B / R / G) get a hair more font weight to read.

## 6. Hybrid glyph height matches regular

The hybrid was getting a much smaller box because it set `font-size: 0.62em`
without re-asserting height — the inherited `height: 1.05em` shrank
proportionally. Two changes:

- Hybrid font-size now matches the regular `.mana` font-size (no
  override).
- Hybrid `height: 1.15em` (same as regular).
- The inner `<span class="mana-hybrid-text">` carries the smaller text
  size (`font-size: 0.78em` of the chip) so the `G/U` label still fits
  inside the oval.

Now a row of `{W}{2/U}{X}` reads as three same-height glyphs.

## 7. Default chip background darker

Old: `background: var(--pico-card-sectioning-background-color, #f1f3f5)` —
nearly the same color as the page background, the deck format chips
disappeared.

New: `background: linear-gradient(135deg, #e3e7ee 0%, #c7cdd6 100%)` —
a subtle gray-blue gradient with a `1px rgba(0,0,0,.08)` border so the
chip's edge reads against the page surface. Applies to deck format
chips (`1v1`, `commander`, etc.), token chips on detail pages, and
generic state / kind chips on the log table.

## 8. White glyph — off-yellow cream

Changed `#f9faf2` (effectively pure white) to `#fff8d6` (warm cream)
across every place the white mana color appears — the standalone
`.mana-W`, the WU / WB / WR / WG hybrid halves, the WP phyrexian hybrid,
the num-W (`2/W`) half, and the multi-color fallback gradient. The W
glyph now reads as "the white mana ball" instead of "an empty circle on
a white page".

---

## Files changed

- `src/mse_viewer/web/static/style.css` — special palette, mythic
  detail wash, default chip background, white-glyph cream, mana sizing
  (regular + hybrid), tap chip simplified (SVG lives in markup now).
- `src/mse_viewer/web/templating.py` — added `_TAP_SVG`, new
  `_ANGLE_TAP_RE` second pass, `detail_hue_class()` helper, registered
  on the Jinja env.
- `src/mse_viewer/web/templates/cards/detail.html` — `detail_hue_class`
  on the article, conditional rarity-text class on the Rarity field.
- `src/mse_viewer/web/templates/tokens/detail.html` — `detail_hue_class`
  on the article.
- `src/mse_viewer/web/templates/base.html` — bumped CSS cache-bust to
  `phase2p2-20260524` so the new stylesheet doesn't get masked by a
  cached older copy.
- `documentation/responses/Phase 2.0 Prompts/phase2_prompt2.md` — this
  file.
