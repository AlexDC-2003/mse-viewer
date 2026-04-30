from __future__ import annotations

from .models import ParsedCard, ParsedCardFace
from .notes_parser import parse_notes
from .tags import (
    canonicalize_flavor,
    canonicalize_text,
    iter_keyword_invocations,
    strip_all_tags,
)
from .tree import MseNode


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

    rule_text_raw = node.get(f"rule_text{suffix}") or ""
    rule_text_canon = canonicalize_text(rule_text_raw) or None
    abilities = rule_text_canon  # Phase 1: same content
    # Case-insensitive dedup of keyword refs: lower-case as the dedup key,
    # preserve the first-seen casing for display / lookup.
    keyword_refs: list[str] = []
    seen_refs: set[str] = set()
    for ref, _params in iter_keyword_invocations(rule_text_raw):
        key = ref.lower()
        if key in seen_refs:
            continue
        seen_refs.add(key)
        keyword_refs.append(ref)

    flavor_raw = node.get(f"flavor_text{suffix}") or ""
    flavor = canonicalize_flavor(flavor_raw) or None

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
        # Format examples seen: ``Evo: Foo``  ``Evolved: Foo, Bar``
        for prefix in ("Evo:", "Evolved:", "Related:"):
            if alias_field.startswith(prefix):
                rest = alias_field[len(prefix):]
                related_from_notes.extend(s.strip() for s in rest.split(",") if s.strip())
                break

    power = node.get(f"power{suffix}") or None
    toughness = node.get(f"toughness{suffix}") or None

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
        flavor_text=flavor,
        rule_text=rule_text_canon,
        abilities=abilities,
        keyword_refs=keyword_refs,
        notes=notes,
        raw_notes=raw_notes,
        alias=alias_field or None,
        related_from_notes=related_from_notes,
    )


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
