from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ParsedNotes(BaseModel):
    pwl: int | None = None
    related: list[str] = Field(default_factory=list)
    status_printed: bool = False
    do_not_read: bool = False
    remainder: str = ""


class ParsedKeyword(BaseModel):
    """A keyword block straight out of the file — *not yet* a Keyword row."""
    name: str                         # the literal match string (identity)
    source_keyword_field: str | None = None   # raw `keyword:` field
    accepted_parameters: list[str] = Field(default_factory=list)
    reminder: str | None = None
    rules: str | None = None
    pseudo_keyword: bool = False


class ParsedCardFace(BaseModel):
    """One face of a card, as parsed (no derivations applied yet)."""

    name: str
    super_type: str = ""              # joined type chain, with tags stripped
    sub_type: str | None = None
    rarity: str | None = None
    casting_cost: str | None = None
    indicator: str | None = None
    extra_data: dict[str, str] = Field(default_factory=dict)
    card_color: str | None = None
    stylesheet: str | None = None
    styling_data: dict[str, str] = Field(default_factory=dict)
    power: str | None = None
    toughness: str | None = None
    flavor_text: str | None = None
    rule_text: str | None = None      # canonicalized text
    abilities: str | None = None      # canonicalized text including kw bodies
    keyword_refs: list[str] = Field(default_factory=list)  # `<key>` text references
    notes: ParsedNotes = Field(default_factory=ParsedNotes)
    raw_notes: str = ""
    alias: str | None = None          # for related-card discovery (Evo: X)
    related_from_notes: list[str] = Field(default_factory=list)


class ParsedCard(BaseModel):
    """One physical card block — may have one or two faces (DFC)."""
    faces: list[ParsedCardFace]
    raw_block: str = ""               # for action-log diagnostics


class ParsedSetHeader(BaseModel):
    set_name: str | None = None
    mse_version: str | None = None
    game: str | None = None
    # styling defaults: stylesheet name (without ``magic-`` prefix) → defaults dict
    styling_defaults: dict[str, dict[str, str]] = Field(default_factory=dict)


class ParsedSet(BaseModel):
    header: ParsedSetHeader
    keywords: list[ParsedKeyword] = Field(default_factory=list)
    cards: list[ParsedCard] = Field(default_factory=list)


# ------ ingestion-time enrichment models ----------------------------------

DesignType = Literal[
    "Normal",
    "Colorpushed",
    "Unique",
    "Additional Color",
    "Additional Color - Unique",
    "Custom",
]
