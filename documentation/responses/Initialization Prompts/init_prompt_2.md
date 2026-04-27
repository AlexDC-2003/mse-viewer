# Consolidated Specification (v0.2)

## 1. Scope recap (reaffirmed)

- Input: plaintext `set` files copy-pasted/uploaded — **no unzipping**, no images.
- MSV is a **companion DB**, not an MSE replacement. No version history — only printed-card-modification notices.
- Two card DBs: **Cards** and **Tokens/Conjured**. Routing driven by `super_type` containing `Token`, or user override on a `rarity: special` warning.
- Keywords stored once, referenced by cards. Parse keywords *before* cards.
- Decks store references to cards + metadata; no card duplication.

## 2. Ingestion flow

```
[upload screen] → [pre-upload form] → [parser] → [per-card review modal] → [commit]
```

**Pre-upload form** (different for set vs deck — toggle at top):

*Set mode:*
- Set name (free text, required)
- PWL defaults per rarity (common/uncommon/rare/mythic → integer, optional)
- Confirm file header's `styling:` section parsed correctly (shown as preview; editable overrides)

*Deck mode:*
- Name, format (1v1 / tester / commander), code, owners, theme, colors, archetype
- If commander/tester: commander (dropdown from Cards DB), package (Core/Expansion/Supplement/empty), related decks (FK picker, only if Expansion/Supplement), size (default 100 commander / 60 otherwise, editable)

Parser then runs per-card and shows a **unified review modal** per card, with sections visible only when applicable. User can accept, reject, or mark-as-alternate-variant.

## 3. Card schema

| Attribute | Source | Derivation |
|---|---|---|
| `name` | `name:` | Literal. Stored identity = `name` unless super_type starts with `Basic` → stored as `"Basic <name>"`. Manual collisions → `"<name> 2"` etc. via review modal. |
| `card_type` | `super_type` | Strip `<word-list-*>` tags, concatenate `super_type`, `super_type_2`, `super_type_3`. If contains `Token` → route to Tokens DB. |
| `card_subtype` | `sub_type` | Strip tags, concatenate `_1/_2/_3`. |
| `rarity` | `rarity:` | Literal. If `special` → review modal asks which DB + Design Type. |
| `colors` | casting_cost / indicator / extra_data / card_color | See §3.1 below. Multi-valued. |
| `design_type` | stylesheet + styling_data | See §3.2 below. |
| `casting_cost` | `casting_cost:` | Literal (retain hybrid syntax like `2/W2/BG` for display). |
| `power` / `toughness` | `power:` / `toughness:` | Literal. |
| `flavor_text` | `flavor_text:` | Strip `<i-flavor>` etc. |
| `rule_text` | `rule_text:` | Full text, MSE tags canonicalized (see §3.3). |
| `keywords` | `rule_text` `<kw-N>` + `<key>` | FK list into Keyword DB, **stripped of parameters**. |
| `abilities` | `rule_text` | Full text incl. keywords *with* their parameters. |
| `related_cards` | `alias:` (Evo: X) OR `notes:` (`Related Cards: X`) for tokens | FK list. For tokens, default from notes; editable in modal. |
| `power_level` | `notes:` (`PWL: X`) or set-default-by-rarity | `PWL: X` in notes overrides; else set-form default for rarity. |
| `set` | pre-upload form | Append-only list (card can belong to multiple sets via alt-art). |
| `alt_arts` | review modal | Append-only list of labels like `"commander alternate"`, `"6x art"`. Populated by user when accepting as variant. |
| `printed` | notice workflow | Boolean. Flips `true` when a print-run notice for this card reaches `completed`. Drives whether future updates trigger a reprint notice. |

### 3.1 Color extraction (priority order, highest wins)

1. **casting_cost letters** (if any non-colorless letter present): `B=black, U=blue, R=red, G=green, W=white, O=orange, K=pink, P=purple, E=brown, L=yellow, N=teal`. Hybrid strings like `2/W2/BG` are just scanned char-by-char.
2. **indicator** field
3. **extra_data** subfields — prefer `extra_indicator` over `frame` on conflict
4. **card_color** field (ignore `multicolor`, `hybrid`, `horizontal` — those are layout hints, not colors)

If casting_cost yields only colorless, fall through to next tier.

### 3.2 Design Type rules

| stylesheet | styling_data | super_type | design_type |
|---|---|---|---|
| (absent) | — | — | `Normal` |
| `m15-altered` | `frames: fnm promo` | — | `Colorpushed` |
| `m15-altered` | `frames: snow` or empty | — | `Normal` |
| `m15-altered` | other | — | **warn + custom input** |
| `m15-mainframe-planeswalker` | — | — | `Normal` |
| `m15-mainframe-tokens` | — | — | `Normal` |
| `m15-altered-beyond` | — | contains `Evolution` or `Hero` | (handled by those — flagged, see §9) |
| `m15-altered-beyond` | — | otherwise | `Unique` |
| `m15-extra-udelude` | — | — | `Additional Color` |
| `m15-extra-udelude-beyond` | — | — | `Additional Color - Unique` |
| anything else | — | — | **warn + custom input** |

Apply set-header styling overrides first: if set header's `styling:` defines defaults for a stylesheet (e.g. `magic-m15-altered:` → `frames: fnm promo`), a card with empty `styling_data.frames` inherits them. Similarly the `m15-extra-udelude` → `Additional Color - Unique` rule you described for missing-stylesheet cards in that set.

### 3.3 Rule text canonicalization

Not "strip all tags" — some carry semantics. Specifically:
- `<sym-auto>W</sym-auto>` → `{W}` (mana symbol) — **preserve**
- `<i-flavor>...</i-flavor>`, `<i-auto>...</i-auto>` → italicize marker or stripped (your call)
- `<kw-N>...<key>NAME</key>...<param-name>X</param-name>...</kw-N>` → parse into keyword link + params; keep text form for `abilities`, extract link for `keywords`
- `<nospellcheck>`, `<atom-reminder-custom>`, `<soft>`, `<atom-sep>` → strip, keep inner text

## 4. Keyword schema

| Attribute | Source | Notes |
|---|---|---|
| `name` | `match:` | **Identity = the full match string.** Different param signatures = different keywords. |
| `accepted_parameters` | `<atom-param>X</atom-param>` in match | Ordered list of param type labels (e.g. `["number", "cost"]`). |
| `reminder` | `reminder:` | Preserve logic functions like `{english_number_a(param1)}`. |
| `rules` | `rules:` | Literal. |
| `pseudo_keyword` | `mode:` | `true` iff `mode: pseudo`. |
| `source_keyword_field` | `keyword:` | Stored for display; not identity. |

**Stub keywords**: when a card references a `<key>` not defined in the keyword section (vanilla MTG keywords like Trample), create a stub with `name = <key text>`, everything else empty, and emit a notice "Define keyword X" to the action log.

## 5. Deck schema

| Attribute | Source | Notes |
|---|---|---|
| `name`, `code`, `theme`, `archetype` | pre-upload form | Literal. |
| `format` | pre-upload form | Enum: `1v1 / tester / commander`. |
| `owners` | pre-upload form | Append-only list of strings. |
| `colors` | pre-upload form | Manual for now (automatable later from member cards). |
| `size` | pre-upload form | Default 100 if commander, else 60. |
| `commander` | pre-upload form | FK to Cards. Required if format ∈ {commander, tester}. |
| `package` | pre-upload form | Enum: `Core / Expansion / Supplement / (empty)`. Only if commander/tester. |
| `related_decks` | pre-upload form | FK list to other decks. Only if package ∈ {Expansion, Supplement}. |
| `cards` | parser of deck file | List of FK to Cards. **Quantity per card?** ← flagged in §9. |

## 6. Review modal design (unified, sections hide when N/A)

One modal per card, with collapsible sections — always same layout so muscle memory builds:

1. **Identity conflict** — only if name already exists
   - Radio: `Update existing` / `Add as alternate variant` / `Save as "<name> 2"` / `Cancel`
   - If alternate variant → text field for label (e.g. "commander alternate"), prefilled with smart default (e.g. "commander alternate" if incoming set's pre-upload form marked it commander)
2. **Design Type unrecognized** — only if stylesheet/styling_data combo not in the rule table
   - Shows: card name, stylesheet, styling_data verbatim
   - Text input for custom Design Type
3. **Rarity: special** — only if `rarity: special`
   - Radio: Cards DB / Tokens DB
   - Text input for Design Type
4. **Token/Conjured routing confirmation** — if `super_type` contained "Token"
   - Shows parsed `Related Cards:` default from notes, editable
5. **Modifies a printed card** — if existing card is marked `printed: true` AND `rule_text`/`keywords`/colors/cost/pt changed
   - Informational: "This will enqueue a reprint notice."
6. **Override fields** — catch-all, every auto-derived value shown in an editable field so you can correct on the fly
   - Pre-filled with current derivation; editing just overrides for this import

Every editable field that affects append-only attributes (set, alt_arts, owners) displays current stored value so you can append manually.

## 7. Notice / workflow adjustment

Simpler than v0.1: no history table. Flow:
- Card ingested → matches existing by name → compared field-by-field
- If existing has `printed: true` AND any meaningful field changed → write notice in `unread` state referencing (card_id, affected_deck_ids)
- "Affected decks" = every deck whose card list contains this card
- State machine: `unread → standby → issued → completed`. On `completed`, card's `printed: true` stays true (obvious but worth stating). Issued-state notices carry a free-text storage-location note.

For keyword changes: same flow, but affected set = every card linking the keyword.

## 8. Suggested improvements (non-breaking)

- **Persist a "warning playbook" table**. Each time you answer "unknown Design Type = Colorpushed-experimental" in a modal, store the mapping. Next import with the same (stylesheet, styling_data) combo auto-applies it. Saves clicks across imports.
- **Dry-run mode for ingestion.** Parse the whole file, show all warnings at once in a summary table, let you review & batch-resolve before anything commits. You already want per-card warnings — a "summary view" option on top is cheap and stops you losing 40 minutes to modals.
- **Canonical mana symbol format.** Pick `{W}` / `{2/W}` / `{X}` (Scryfall's convention) for rule_text storage. Future you will thank current you when rendering or diffing.
- **Keyword identity hashing.** Normalize the `match` string (trim whitespace, normalize `<atom-param>name</atom-param>` → `<atom-param>_</atom-param>` for identity; keep raw version for display). Two keywords with the same structure but different param labels (`number` vs `count`) should be the same keyword; param labels go into `accepted_parameters` for reference, not identity.
- **Store set-level PWL defaults on the set record**, not just as transient form input. If you re-import the same set later you don't want to re-enter them.
- **Action log ≠ notice log.** You already noticed this drift — I'd formalize two streams: *notices* (reprint-required, user-actionable workflow), and *action log* (missing keyword defs, unparseable fields, anything the parser punted on). Same UI, two filters.

## 9. Open questions / things I spotted in your snippets that aren't spec'd

1. **Multi-face cards** — `name_2`, `rule_text_2`, `super_type_2`, `power_2`, etc. exist in MSE for split/modal/transform cards. Your spec treats `_2/_3` as non-existent. Are these cards out of scope, or do you want a second face stored? (A simple option: concatenate into `rule_text` separated by `---`; harder-but-correct: store faces as child records.)
2. **"Evolution or Hero" exception for `m15-altered-beyond`** — what *is* the exception's output? You said "this should not be the case", but didn't say what design_type it *should* be. My guess: `Unique - Evolution` / `Unique - Hero`? Or fall through to another rule entirely?
3. **Deck card quantities** — decks are card references, but constructed decks need 4-ofs, lands need counts. How are quantities encoded in your deck files? Same `name:` repeated N times, or a count field? I can't see a deck file snippet.
4. **`card_color: hybrid, horizontal, multicolor`** — confirming these are *layout hints* we should ignore, not color values. (My inference.)
5. **Identity for stub keywords**. If "Trample" appears before any keyword-input file defines it, we create a stub. Later you upload a file defining Trample. Should the parser merge into the stub (matched by `keyword:` or by `match:`?), or prompt for confirmation via a notice?
6. **Basic Lands in a set** — you said multiple entries with same name are expected (6× art Plains). Should these all fold into one record with `alt_arts = ["6x art"]`, or six records with disambiguated names? Your rule "Basic X" suggests one record.
7. **Cards with colorless cost but colored rule text activations** (e.g. cost = `3`, but ability adds `{W}`). Per your spec these are `colorless`. Confirming.
8. **Set header parsing** — the header's `styling:` uses keys like `magic-m15-altered` while cards use `stylesheet: m15-altered` (missing `magic-` prefix). Parser needs to reconcile. Confirming: strip `magic-` prefix when matching. Note your example also has a bug where `casting_cost_mana_symbols` appears twice under `magic-m15-altered` — expect duplicates in the wild.
9. **Rejecting in review modal** — does "reject this card" skip just this card, or abort the whole import? Default: skip-and-continue, log to action log.
10. **Notes field grammar** — is it one key-value per line (`PWL: 3\nRelated Cards: Zap Token`)? Comma-separated? I'll assume one-per-line unless told otherwise.

---

Biggest risks for implementation order, in my opinion: **(a) the rule_text parser** (nested tags + keyword pattern matching + parameter binding) and **(b) the review modal state machine** (which warnings compose, and how overrides flow back into the import). Everything else is straightforward CRUD once those two are solid.

Want me to take a crack at a concrete SQLAlchemy schema + a minimal Pydantic model for the parser output next, so you can sanity-check the shape before we wire any UI? That'd be the smallest next increment.