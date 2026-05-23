"""Pretty-printer for MSE reminder templates.

MSE reminders embed inline expressions in ``{...}`` braces:

    {param1} poison { if param1.value=="1" then "counter." else "counters." }
    Permanents ... that are dealt damage by this { if has_pt() then "creature" } are exiled.
    Effects that say "destroy" don't destroy this {
        if has_pt() then "creature"
        else if is_artifact(card.super_type) then "artifact"
        else "permanent"
    }.

The renderer evaluates ``if/then/else`` chains against:

  * ``params`` — captured invocation parameters, used for the
    ``foo.value == "X"`` family of equality predicates.
  * ``card_facts`` — the invoking card's row snapshot (power, toughness,
    super_type, …), used for function-call predicates like ``has_pt()`` and
    ``is_artifact(card.super_type)``.

When ``card_facts`` is ``None`` the inline-template path leaves the source
verbatim — that's the keyword-detail-page rendering, which should show the
unevaluated template (Phase 1.6 prompt 4 item 3 / bug 12). Per-card detail
pages pass a real card_facts dict and get a fully evaluated result.
"""
from __future__ import annotations

import re
from typing import Callable, Mapping

# {paramN} substitution slot — a single identifier inside braces, no spaces.
_RE_PARAM_SUB = re.compile(r"\{(\w+)\}")

# Simple equality predicate: ``foo.value == "X"`` or ``foo.value=='X'``.
_RE_EQ_PREDICATE = re.compile(
    r'^\s*(\w+)\.value\s*(==|!=)\s*["\'](.*?)["\']\s*$',
    re.DOTALL,
)

# Function-call predicate: ``name()`` or ``name(arg.path)``.
_RE_FUNC_PREDICATE = re.compile(
    r"^\s*(\w+)\s*\(\s*([\w.]*)\s*\)\s*$"
)


def evaluate_inline_templates(
    text: str | None,
    *,
    card_facts: Mapping[str, object] | None = None,
) -> str:
    """Evaluate ``{ if … then … else … }`` blocks within a larger text body
    WITHOUT touching ``{paramN}`` slots.

    Used at render time on canonicalized rule_text so inline templates
    resolve to their evaluated form, while plain ``{B}`` mana symbols and
    other braces survive untouched (Phase 1.6 prompt 4 item 3).

    Returns the original text when ``card_facts`` is ``None`` so keyword
    detail pages — which have no card context — render the template body
    verbatim instead of a misleading evaluation.
    """
    if not text:
        return text or ""
    if card_facts is None:
        return text
    return _replace_blocks(text, params=None, card_facts=card_facts)


def evaluate_reminder_template(
    text: str | None,
    params: Mapping[str, str] | None = None,
    *,
    card_facts: Mapping[str, object] | None = None,
) -> str:
    """Render an MSE reminder template for display.

    With ``params`` (a ``param_name → value`` map taken from a card-side
    invocation), ``foo.value=="X"`` predicates are evaluated. With
    ``card_facts`` (a fact map sourced from the invoking card row), function
    predicates like ``has_pt()`` and ``is_artifact(card.super_type)`` are
    evaluated. Without enough information to decide either branch, the
    template is left verbatim — that's the safe default for the keyword
    detail page where neither params nor card_facts apply.

    ``{paramN}`` slots become ``<paramN>`` (literal angle brackets) when no
    params are supplied, or are substituted directly when they are.
    """
    if not text:
        return text or ""

    text = _replace_blocks(text, params=params, card_facts=card_facts)
    text = _RE_PARAM_SUB.sub(lambda m: _sub_param(m.group(1), params), text)
    return text


# ---------------------------------------------------------------------------
# Brace-balanced block finder + chain parser
# ---------------------------------------------------------------------------


def _replace_blocks(
    text: str,
    *,
    params: Mapping[str, str] | None,
    card_facts: Mapping[str, object] | None,
) -> str:
    """Find every top-level ``{...}`` block whose body starts with ``if`` and
    replace it with the evaluated branch. Brace-balanced — no regex over-match.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch != "{":
            out.append(ch)
            i += 1
            continue
        # Find matching '}'
        depth = 1
        j = i + 1
        while j < n and depth > 0:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if depth != 0:
            # No matching brace — emit the rest verbatim and stop.
            out.append(text[i:])
            return "".join(out)
        body = text[i + 1 : j]
        if re.match(r"^\s*if\s", body, re.DOTALL):
            replacement = _eval_if_chain(body, params, card_facts)
            if replacement is None:
                # Leave the original ``{...}`` so keyword-detail-style views
                # still show the source template.
                out.append(text[i : j + 1])
            else:
                out.append(replacement)
        else:
            # Not an if-template (likely ``{B}`` mana / ``{paramN}``) — leave alone.
            out.append(text[i : j + 1])
        i = j + 1
    return "".join(out)


_RE_IF_HEAD = re.compile(
    r'^\s*if\s+(?P<pred>.+?)\s+then\s+"(?P<branch>(?:[^"\\]|\\.)*)"\s*',
    re.DOTALL,
)
_RE_ELSE_IF_HEAD = re.compile(r"^\s*else\s+if\s", re.DOTALL)
_RE_ELSE_TAIL = re.compile(
    r'^\s*else\s+"(?P<branch>(?:[^"\\]|\\.)*)"\s*$',
    re.DOTALL,
)


def _eval_if_chain(
    body: str,
    params: Mapping[str, str] | None,
    card_facts: Mapping[str, object] | None,
) -> str | None:
    """Parse a body of the form

        if PRED then "X" [ else if PRED then "Y" ]* [ else "Z" ]

    and return the chosen branch, or ``None`` when the chain is unparseable
    or no predicate could be evaluated (so the caller leaves the source
    verbatim).
    """
    branches: list[tuple[str, str]] = []
    fallback: str | None = None
    s = body
    while True:
        m = _RE_IF_HEAD.match(s)
        if not m:
            return None  # malformed
        branches.append((m.group("pred").strip(), m.group("branch")))
        s = s[m.end():]
        if s.strip() == "":
            break
        m_elseif = _RE_ELSE_IF_HEAD.match(s)
        if m_elseif:
            # Re-anchor to the inner ``if`` so _RE_IF_HEAD can re-match.
            s = s[m_elseif.end() - 3 :]  # back up to the ``if``
            continue
        m_else = _RE_ELSE_TAIL.match(s)
        if m_else:
            fallback = m_else.group("branch")
            break
        return None

    any_evaluable = False
    for pred, branch in branches:
        decided = _eval_predicate(pred, params, card_facts)
        if decided is None:
            continue
        any_evaluable = True
        if decided:
            return branch
    if fallback is None:
        # No fallback — empty string when something evaluated to False, or
        # leave verbatim when nothing was decidable.
        return "" if any_evaluable else None
    if not any_evaluable and not branches:
        return fallback  # only an else clause — render it
    return fallback if any_evaluable else None


# ---------------------------------------------------------------------------
# Predicate evaluation
# ---------------------------------------------------------------------------


def _eval_predicate(
    predicate: str,
    params: Mapping[str, str] | None,
    card_facts: Mapping[str, object] | None,
) -> bool | None:
    """Return ``True`` / ``False`` if the predicate resolves, ``None`` if not.

    Supported forms:
      * ``param.value == "X"``  — string equality (needs ``params``).
      * ``param.value != "X"``  — string inequality (needs ``params``).
      * ``name()``              — zero-arg function call against ``card_facts``.
      * ``name(arg.path)``      — single-arg function (the path is resolved
                                   against ``card_facts``; a leading ``card.``
                                   is stripped).
    """
    m = _RE_EQ_PREDICATE.match(predicate)
    if m:
        if params is None:
            return None
        name, op, expected = m.group(1), m.group(2), m.group(3)
        actual = _lookup_param(name, params)
        if actual is None:
            return None
        if op == "==":
            return str(actual).strip() == expected
        return str(actual).strip() != expected

    m = _RE_FUNC_PREDICATE.match(predicate)
    if m:
        fn = _FUNCS.get(m.group(1).lower())
        if fn is None or card_facts is None:
            return None
        arg_path = m.group(2).strip()
        arg_value = _resolve_arg_path(arg_path, card_facts) if arg_path else None
        return fn(arg_value, card_facts)

    return None


def _resolve_arg_path(path: str, facts: Mapping[str, object]) -> object:
    """Resolve a dotted path against ``card_facts``.

    A leading ``card.`` is stripped (the user writes ``is_artifact(card.super_type)``
    but we store the field as ``super_type``).
    """
    key = path
    if key.startswith("card."):
        key = key[5:]
    return facts.get(key)


# ---------------------------------------------------------------------------
# Function-predicate registry
# ---------------------------------------------------------------------------


def _has_pt(_arg: object, facts: Mapping[str, object]) -> bool:
    """``has_pt()`` is true when the invoking card has both power and
    toughness recorded as non-empty values."""
    p = facts.get("power")
    t = facts.get("toughness")
    return bool(p) and bool(t) and str(p).strip() != "" and str(t).strip() != ""


def _is_artifact(arg: object, facts: Mapping[str, object]) -> bool:
    """``is_artifact(card.super_type)`` is true when the resolved super-type
    string contains the word ``artifact`` (case-insensitive)."""
    s = arg if arg is not None else facts.get("super_type")
    return "artifact" in str(s or "").lower()


def _is_creature(arg: object, facts: Mapping[str, object]) -> bool:
    """Useful synonym in case the user writes ``is_creature(card.super_type)``."""
    s = arg if arg is not None else facts.get("super_type")
    return "creature" in str(s or "").lower()


def _is_enchantment(arg: object, facts: Mapping[str, object]) -> bool:
    s = arg if arg is not None else facts.get("super_type")
    return "enchantment" in str(s or "").lower()


def _is_land(arg: object, facts: Mapping[str, object]) -> bool:
    s = arg if arg is not None else facts.get("super_type")
    return "land" in str(s or "").lower()


_FUNCS: dict[str, Callable[[object, Mapping[str, object]], bool]] = {
    "has_pt": _has_pt,
    "is_artifact": _is_artifact,
    "is_creature": _is_creature,
    "is_enchantment": _is_enchantment,
    "is_land": _is_land,
}


def _lookup_param(name: str, params: Mapping[str, str]) -> str | None:
    """Resolve ``name`` against the param dict, tolerating both ``"foo"`` and
    ``"foo.value"`` keys so callers don't have to think about which form
    they passed in."""
    if name in params:
        return params[name]
    return params.get(f"{name}.value")


def _sub_param(name: str, params: Mapping[str, str] | None) -> str:
    """Substitute ``{paramN}``: with concrete params, return the value;
    without, render as ``<paramN>`` so the slot is visible."""
    if params is not None:
        v = _lookup_param(name, params)
        if v is not None:
            return str(v)
    return f"<{name}>"
