# Decisions locked

1. **Postgres in Docker** — locked.
2. **Strict keyword identity (B)** — locked. Match string is identity verbatim; param labels matter.
3. **Tokens** — separate ORM model, no rarity/PWL columns, everything else nullable. Discussed below.
4. **Color tiers** — first non-empty wins. Multi-face: face 2 derives independently from `_2` fields (own `casting_cost_2`, own `card_color_2` if present, etc.) — locked.
5. **Repo pattern** — explanation below.
6. **Vanilla `pip install -r requirements.txt`** — locked.
7. **Action log only for Phase 1**, notices deferred but schema-compatible — locked.

# Question 5 — Repo pattern vs direct ORM

The difference is *where* SQLAlchemy queries live in the codebase.

**Direct ORM from services:**
```python
# ingest/pipeline.py
def import_card(parsed: ParsedCard, db: Session):
    existing = db.query(Card).filter(Card.name == parsed.name).first()
    if existing:
        existing.sets = list(set(existing.sets) | {parsed.set_name})
    else:
        db.add(Card(name=parsed.name, ...))
    db.commit()
```

The query lives next to the business logic. Quick to write. Problem: when three different services all need "find by Basic-X-aware identity, then append to the set list", they each reinvent it slightly differently and drift.

**Repository pattern:**
```python
# repository/cards.py
class CardRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_identity(self, identity: str) -> Card | None: ...
    def upsert_from_parsed(self, parsed: ParsedCard) -> Card: ...
    def append_set(self, card: Card, set_name: str) -> None: ...
    def append_alt_art(self, card: Card, label: str) -> None: ...

# ingest/pipeline.py — no sqlalchemy import here
def import_card(parsed: ParsedCard, cards: CardRepository):
    card = cards.upsert_from_parsed(parsed)
    cards.append_set(card, parsed.set_name)
```

Quirks like "Basic X identity normalization", "append to a JSONB list without duplicates", "upsert with the right conflict semantics" live in *one* place. Services stay readable; tests can swap a fake repo when you want to test pipeline logic without a DB.

Trade-off: more boilerplate up front, and for trivial CRUD it feels like dead weight. For *your* model — lots of identity rules, append-only list fields, multi-table updates per ingest, future Phase 2 deck → notice fan-out — it pays for itself within the first month. **Going with repos.**

# Tokens schema — concrete plan

Three reasonable shapes, picking the simplest that fits:

- **Single Card table with `kind` discriminator** — would need rarity/PWL nullable and a check constraint that they're null when kind=token. Verbose, you don't want it.
- **Joined inheritance (Card base table + Token sub-table)** — over-engineered for two types, complicates queries.
- **Two independent tables with a shared SQLAlchemy mixin for common columns.** No surprises, no nullable-where-it-shouldn't-be, easy queries. Cross-references (Evo card → token, token → spell that creates it) handled by storing related_cards as a list of canonical-name strings rather than FKs.

```python
# domain/_card_mixin.py
class CardCoreMixin:
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)         # the stored identity
    display_name: Mapped[str]                              # original card name
    card_type: Mapped[str]
    card_subtype: Mapped[str | None]
    colors: Mapped[list[str]]                              # JSONB
    casting_cost: Mapped[str | None]
    power: Mapped[str | None]
    toughness: Mapped[str | None]
    flavor_text: Mapped[str | None]
    rule_text: Mapped[str | None]
    abilities: Mapped[str | None]
    keywords: Mapped[list[int]]                            # FK ids into keyword
    related_cards: Mapped[list[str]]                       # canonical names, resolved at query time
    sets: Mapped[list[str]]
    alt_arts: Mapped[list[str]]
    design_type: Mapped[str]
    notes: Mapped[str | None]
    printed: Mapped[bool] = mapped_column(default=False)

# domain/card.py
class Card(Base, CardCoreMixin):
    __tablename__ = "cards"
    rarity: Mapped[str]
    power_level: Mapped[int | None]

# domain/token.py
class Token(Base, CardCoreMixin):
    __tablename__ = "tokens"
    # no rarity, no power_level
```

Why `related_cards` as strings not FKs: your identity model already says "name is the unique key". Storing names lets a Card reference a Token (or vice versa) without a polymorphic FK column. The repository resolves names → records at read time. If this turns into a perf issue later (it won't, on your data scale), we add a denormalized index table.

# Phase 1 scope adjustment (per #7)

- **Notices**: still create the `notices` table and the `kind` discriminator (`action` | `notice`) so it's there. No code that *creates* a `notice`-kind row in Phase 1.
- **Action log**: fully implemented. Sources of action entries in Phase 1:
  - "Do Not Read" cards skipped during ingest
  - Cards rejected from review modal
  - Unparseable fields (parser punted)
  - Stub keywords created automatically
  - User-rejected design type warnings (i.e. modal closed without resolution)
- **State machine**: `open → resolved` for actions. Notices' `unread → standby → issued → completed` is in the schema enum but unused in Phase 1.
- **The `printed` flag is read from `Status: Printed` notes** and stored, but no diff-on-printed-card → notice trigger is wired. Phase 2 wires that.

# Anything else worth flagging before scaffolding

A few small things I want you to confirm or veto so I'm not guessing:

1. **Storage of `colors` and `keywords` lists** — I'm planning JSONB arrays in Postgres, indexed with GIN where useful. Means `WHERE 'red' = ANY(colors)` works. Alternative is a join table per list. JSONB is far simpler and fast enough at your data scale; recommending it. OK?
2. **The `name` column** as the stored identity needs a unique index. For Cards and Tokens *separately* (a card and a token can share a name — e.g. spell "Goblin" and a "Goblin" token). Confirming the namespaces are separate.
3. **`alt_arts` semantics** — when modal user marks "this is an alternate variant", we append the *label*. But we don't track which label corresponds to which physical print. That seems fine for Phase 1 since you said you'll manage prints manually; flagging in case I'm misunderstanding.
4. **Set name normalization** — `Set: New Capenna` and `Set: new capenna` should be treated as same? I'd say yes (case-insensitive compare, store as-typed-first-time). Confirm.
5. **Project name** — `mse-viewer` is the repo name, but is that also what you want as the Python package (`mse_viewer`) and Docker container name? Or do you have a friendlier name in mind? Easy to change later, just want to start with the right one.

Ready to scaffold once you confirm the five above (or just say "go with your defaults").