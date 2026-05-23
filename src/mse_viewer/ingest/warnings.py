from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class WarningKind(StrEnum):
    identity_conflict = "identity_conflict"
    design_type_unrecognized = "design_type_unrecognized"
    rarity_special = "rarity_special"
    token_routing = "token_routing"
    modifies_printed = "modifies_printed"
    do_not_read = "do_not_read"
    parse_punt = "parse_punt"
    # The card's stylesheet says one frame family, the type line says another.
    # Phase 1.6: surfaces when m15-emblem-name-cut isn't an Emblem, or
    # m15-saga isn't a Saga, or future-planeswalker-horizontal isn't a Leyline.
    frame_type_mismatch = "frame_type_mismatch"
    # A Planeswalker with an alias but not in the Evolution branch — alias may
    # indicate a non-Normal design type so we want the user to confirm.
    planeswalker_alias = "planeswalker_alias"


@dataclass
class CardWarning:
    kind: WarningKind
    message: str
    payload: dict = field(default_factory=dict)


@dataclass
class WarningCollector:
    warnings: list[CardWarning] = field(default_factory=list)

    def add(self, kind: WarningKind, message: str, **payload: object) -> None:
        self.warnings.append(CardWarning(kind=kind, message=message, payload=dict(payload)))

    def of(self, kind: WarningKind) -> list[CardWarning]:
        return [w for w in self.warnings if w.kind == kind]

    def has(self, kind: WarningKind) -> bool:
        return any(w.kind == kind for w in self.warnings)

    def __bool__(self) -> bool:
        return bool(self.warnings)
