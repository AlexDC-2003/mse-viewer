from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Line:
    """A single logical line of an MSE plaintext file."""
    indent: int            # number of leading tab/space-pairs (treated equivalent)
    key: str | None        # text before ':' (None for value-only continuation lines)
    value: str             # text after ':' (or whole line for continuations)
    raw: str               # original line


def _measure_indent(raw_line: str) -> int:
    """MSE indent unit is 1 tab. We also accept 1 tab == 1 indent level.

    Lines that lead with spaces are tolerated by treating any amount of leading
    whitespace as the same indent unit; the structure parser only cares about the
    relative depth.
    """
    indent = 0
    for ch in raw_line:
        if ch == "\t":
            indent += 1
        elif ch == " ":
            # Skip spaces, but they don't count as a fresh indent step on their own.
            continue
        else:
            break
    return indent


def lex(text: str) -> list[Line]:
    """Convert raw MSE text into a list of structured lines.

    The MSE format is YAML-ish but uses tabs for indentation, allows colons inside
    unquoted values, and supports multi-line string values via deeper-indented
    continuation lines.  We do *not* try to be YAML compatible — this is a simple
    indent-aware splitter.
    """
    out: list[Line] = []
    for raw in text.splitlines():
        if not raw.strip():
            # blank lines are sometimes meaningful inside multi-line values; we keep
            # them as raw continuations at indent=-1 so they survive value joining.
            out.append(Line(indent=-1, key=None, value="", raw=raw))
            continue
        if raw.lstrip().startswith("#"):
            # MSE files don't really use comments but tolerate them defensively.
            continue
        indent = _measure_indent(raw)
        body = raw[indent:] if indent and raw[:indent] == "\t" * indent else raw.lstrip("\t")
        body = body.rstrip("\r")
        # Split on the first colon followed by whitespace OR end-of-line.
        idx = _find_key_colon(body)
        if idx is None:
            out.append(Line(indent=indent, key=None, value=body, raw=raw))
        else:
            key = body[:idx].strip()
            value = body[idx + 1 :]
            if value.startswith(" "):
                value = value[1:]
            out.append(Line(indent=indent, key=key, value=value.rstrip(), raw=raw))
    return out


def _find_key_colon(body: str) -> int | None:
    """Find the colon that separates the key from its value.

    We require the key to be made of identifier-ish characters (letters, digits,
    underscore, hyphen, space) so that ``rule_text: foo: bar`` keys on the *first*
    colon and values can contain further colons unquoted.
    """
    for i, ch in enumerate(body):
        if ch == ":":
            head = body[:i]
            if head and all(c.isalnum() or c in "_- " for c in head):
                return i
            return None
        if not (ch.isalnum() or ch in "_- "):
            return None
    return None
