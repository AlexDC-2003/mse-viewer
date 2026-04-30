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
