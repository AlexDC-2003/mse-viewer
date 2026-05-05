from __future__ import annotations

import re

from .models import ParsedCard, ParsedCardFace
from .notes_parser import parse_notes
from .special_text import extract_italic_flavor, parse_starting_loyalty
from .tags import (
    canonicalize_flavor,
    canonicalize_text,
    iter_keyword_invocations,
    strip_all_tags,
)
from .tree import MseNode


# Trailing ``(Evo-I)`` / ``(Evo-T)`` / ``(Evo-II)`` etc. — annotation suffix
# the alias author writes to disambiguate variants. The annotation belongs in
# the alias display but not in the related-card name we link against.
_RE_EVO_SUFFIX = re.compile(r"\s*\(Evo-[A-Za-z0-9]+\)\s*$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Top-level entrypoint
# ---------------------------------------------------------------------------


def parse_cards(root: MseNode) -> list[ParsedCard]:
    """Collect every top-level ``card:`` block, splitting DFCs into two faces."""
    out: list[ParsedCard] = []
    for node in root.all("card"):
        faces = _faces_from_card_node(node)
        if not faces:
            continue
        out.append(ParsedCard(faces=faces, raw_block=_raw_block(node)))
    return out


def _faces_from_card_node(node: MseNode) -> list[ParsedCardFace]:
    """Return one or two faces; faces are detected via ``name_2`` presence."""
    is_dfc = node.first("name_2") is not None
    primary = _face_from_node(node, suffix="", is_dfc=is_dfc)
    if primary is None:
        return []
    if is_dfc:
        secondary = _face_from_node(node, suffix="_2", is_dfc=True)
        if secondary is not None:
            primary.related_from_notes = list(dict.fromkeys(primary.related_from_notes + [secondary.name]))
            secondary.related_from_notes = list(dict.fromkeys(secondary.related_from_notes + [primary.name]))
            return [primary, secondary]
    return [primary]


# ---------------------------------------------------------------------------
# Face extraction
# ---------------------------------------------------------------------------


def _face_from_node(node: MseNode, *, suffix: str, is_dfc: bool = False) -> ParsedCardFace | None:
    name = node.get(f"name{suffix}").strip()
    if not name:
        return None

    super_type = _join_type_chain(node, "super_type", suffix, is_dfc=is_dfc)
    sub_type = _join_type_chain(node, "sub_type", suffix, is_dfc=is_dfc) or None

    frame = detect_frame(super_type, sub_type)

    # Choose where rule text comes from based on frame:
    #   * Planeswalker / Saga prefer ``special_text`` (which assembles the
    #     loyalty/level chapters into a single readable block) and fall back
    #     to ``rule_text`` if it's empty.
    #   * Everything else (Normal, Emblem, Leyline) reads ``rule_text``.
    if frame in ("planeswalker", "saga"):
        primary = node.get(f"special_text{suffix}") or ""
        rule_text_raw = primary if primary.strip() else (node.get(f"rule_text{suffix}") or "")
    else:
        rule_text_raw = node.get(f"rule_text{suffix}") or ""

    extra_flavor_raw = ""
    # Italic-flavor extraction for Leyline / Saga: pull `<i>...</i>` spans
    # out of rule text into flavor before canonicalization. Saga's first
    # non-empty line is protected (Read-ahead reminder, etc.).
    if frame == "leyline":
        rule_text_raw, extra_flavor_raw = extract_italic_flavor(rule_text_raw)
    elif frame == "saga":
        rule_text_raw, extra_flavor_raw = extract_italic_flavor(
            rule_text_raw, protect_first_line=True
        )

    rule_text_canon = canonicalize_text(rule_text_raw) or None
    abilities = rule_text_canon  # Phase 1: same content
    # Case-insensitive dedup of keyword refs: lower-case as the dedup key,
    # preserve the first-seen casing for display / lookup.  Reminder text from
    # the trailing ``<atom-reminder>`` block (if any) is kept alongside so the
    # ingest pipeline can attach it to freshly-created stubs.
    keyword_refs: list[str] = []
    keyword_reminders: dict[str, str] = {}
    seen_refs: set[str] = set()
    for ref, _params, reminder in iter_keyword_invocations(rule_text_raw):
        key = ref.lower()
        if key not in seen_refs:
            seen_refs.add(key)
            keyword_refs.append(ref)
        if reminder and key not in keyword_reminders:
            keyword_reminders[key] = reminder

    flavor_raw = node.get(f"flavor_text{suffix}") or ""
    flavor = canonicalize_flavor(flavor_raw) or None
    if extra_flavor_raw:
        extracted = canonicalize_flavor(extra_flavor_raw)
        if extracted:
            flavor = f"{flavor}\n{extracted}" if flavor else extracted

    casting_cost = node.get(f"casting_cost{suffix}") or None
    indicator = node.get(f"indicator{suffix}") or None
    card_color = node.get(f"card_color{suffix}") or None
    # Rarity is not face-scoped in MSE.  Missing → autofill 'common' (init_prompt_3 #2);
    # the original-missing flag is on ``rarity_missing``.
    raw_rarity = (node.get("rarity") or "").strip()
    rarity = raw_rarity or "common"
    rarity_missing = not raw_rarity

    extra_data = _flatten_extra_data(node, suffix)
    stylesheet = node.get("stylesheet") or None
    styling_data = _flatten_styling_data(node)

    raw_notes = node.get("notes") or ""
    notes = parse_notes(raw_notes)
    alias_field = node.get("alias")
    related_from_notes: list[str] = list(notes.related)
    if alias_field:
        # Format examples seen: ``Evo: Foo``  ``Evolved: Foo, Bar``  ``Evo: Foo (Evo-I)``
        for prefix in ("Evo:", "Evolved:", "Related:"):
            if alias_field.startswith(prefix):
                rest = alias_field[len(prefix):]
                for raw in rest.split(","):
                    related_name = _RE_EVO_SUFFIX.sub("", raw).strip()
                    if related_name:
                        related_from_notes.append(related_name)
                break

    # Emblems carry the producing planeswalker's name in ``sub_type`` — auto-add
    # it as a related card so the cross-link surfaces in the UI without requiring
    # a Related: entry in notes.
    if frame == "emblem" and sub_type:
        related_from_notes.append(sub_type.strip())

    # Dedup while preserving first-seen order.
    related_from_notes = list(dict.fromkeys(n for n in related_from_notes if n))

    power = node.get(f"power{suffix}") or None
    toughness = node.get(f"toughness{suffix}") or None
    starting_loyalty = (
        parse_starting_loyalty(node.get(f"loyalty{suffix}") or node.get("loyalty"))
        if frame == "planeswalker"
        else None
    )

    return ParsedCardFace(
        name=name,
        super_type=super_type,
        sub_type=sub_type,
        rarity=rarity,
        rarity_missing=rarity_missing,
        casting_cost=casting_cost,
        indicator=indicator,
        extra_data=extra_data,
        card_color=card_color,
        stylesheet=stylesheet,
        styling_data=styling_data,
        power=power,
        toughness=toughness,
        starting_loyalty=starting_loyalty,
        flavor_text=flavor,
        rule_text=rule_text_canon,
        abilities=abilities,
        keyword_refs=keyword_refs,
        keyword_reminders=keyword_reminders,
        notes=notes,
        raw_notes=raw_notes,
        alias=alias_field or None,
        related_from_notes=related_from_notes,
    )


# ---------------------------------------------------------------------------
# Frame detection
# ---------------------------------------------------------------------------


def detect_frame(super_type: str, sub_type: str | None) -> str:
    """Identify a face's frame family from its type line.

    Returns one of ``"planeswalker"``, ``"emblem"``, ``"saga"``, ``"leyline"``,
    ``"normal"``. Stylesheet is intentionally ignored — users reuse stylesheets
    for unrelated frames, so the type line is the only reliable signal.

    Order matters: ``Emblem`` is checked before ``Planeswalker`` because some
    emblems carry ``Planeswalker`` in their subtype chain. Saga and Leyline
    only fire on Enchantment frames.
    """
    s = (super_type or "").lower()
    sub = (sub_type or "").lower()
    if "emblem" in s:
        return "emblem"
    if "planeswalker" in s:
        return "planeswalker"
    if "enchantment" in s:
        if "saga" in sub:
            return "saga"
        if "leyline" in sub:
            return "leyline"
    return "normal"


def is_evolution_planeswalker(super_type: str) -> bool:
    """A Planeswalker whose type line also mentions Evolution. Such cards
    always carry an alias, so the alias signal that normally indicates a
    non-Normal design type does not apply."""
    s = (super_type or "").lower()
    return "planeswalker" in s and "evolution" in s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _join_type_chain(node: MseNode, base_key: str, suffix: str, *, is_dfc: bool) -> str:
    """Concatenate the super-type / sub-type chain, with word-list tags stripped.

    On a single-face card MSE may use ``super_type``, ``super_type_2``,
    ``super_type_3`` to express multi-word supertypes (e.g. *Legendary Snow
    Creature*).  On a DFC the ``_2`` slot is reserved for the *second face*, so
    we must NOT chain across faces — face 1 reads only ``super_type`` and face
    2 reads only ``super_type_2``.
    """
    parts: list[str] = []
    if is_dfc:
        key = f"{base_key}{suffix}"
        val = node.get(key)
        if val:
            parts.append(strip_all_tags(val))
    else:
        for extra in ("", "_2", "_3"):
            key = f"{base_key}{extra}"
            val = node.get(key)
            if val:
                parts.append(strip_all_tags(val))
    joined = " ".join(p for p in parts if p)
    # collapse runs of internal whitespace that the per-part tag stripping
    # may have left behind.
    return " ".join(joined.split())


def _flatten_extra_data(node: MseNode, suffix: str) -> dict[str, str]:
    """Pick up ``extra_data`` (and ``extra_data_2`` for face 2)."""
    block = node.first(f"extra_data{suffix}") or node.first("extra_data")
    if block is None:
        return {}
    return {child.key: child.value for child in block.children}


def _flatten_styling_data(node: MseNode) -> dict[str, str]:
    block = node.first("styling_data")
    if block is None:
        return {}
    return {child.key: child.value for child in block.children}


def _raw_block(node: MseNode) -> str:
    """Produce a best-effort raw dump of the card block for action-log entries."""
    lines: list[str] = []
    _dump(node, indent=0, out=lines)
    return "\n".join(lines)


def _dump(node: MseNode, *, indent: int, out: list[str]) -> None:
    pad = "\t" * indent
    head = f"{pad}{node.key}:"
    if node.value:
        first, _, rest = node.value.partition("\n")
        out.append(f"{head} {first}")
        if rest:
            for line in rest.splitlines():
                out.append("\t" * (indent + 1) + line)
    else:
        out.append(head)
    for child in node.children:
        _dump(child, indent=indent + 1, out=out)
