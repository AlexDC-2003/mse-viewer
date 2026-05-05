"""Pretty-printer for MSE reminder templates.

MSE reminders embed inline expressions in ``{...}`` braces, e.g. ::

    {param1} poison { if param1.value=="1" then "counter." else "counters." }
    Permanents ... that are dealt damage by this { if has_pt() then "creature" } are exiled.

For display we want the rendered form, not the raw template. With concrete
parameter values supplied, the predicate is evaluated; without values we pick
the ``else`` branch (the plural form is the safer default for English) and
render ``{paramN}`` as ``<paramN>`` (literal angle brackets) so a reader can
still see the slot.

Phase 1.6 supports two predicate forms:
  * ``foo.value == "X"`` / ``!=`` — string equality, evaluated against ``params``.
  * ``has_pt()`` and other ``name()`` function calls — evaluated against
    ``card_facts`` (truthy when the named fact is present and non-empty).

Both ``then`` and ``else`` are now optional; an unmatched branch renders empty.
"""
from __future__ import annotations

import re
from typing import Callable, Mapping

# {paramN} substitution slot — a single identifier inside braces, no spaces.
_RE_PARAM_SUB = re.compile(r"\{(\w+)\}")

# { if EXPR then "STRING" [ else "STRING" ] }  — else is optional.
_RE_IF_THEN_ELSE = re.compile(
    r'\{\s*if\s+(?P<predicate>.+?)\s+then\s+"(?P<then>(?:[^"\\]|\\.)*)"'
    r'(?:\s+else\s+"(?P<else_branch>(?:[^"\\]|\\.)*)")?\s*\}',
    re.DOTALL,
)

# Simple equality predicate: ``foo.value == "X"`` or ``foo.value=='X'``.
_RE_EQ_PREDICATE = re.compile(
    r'^\s*(\w+)\.value\s*(==|!=)\s*["\'](.*?)["\']\s*$',
    re.DOTALL,
)

# Bare function-call predicate: ``name()`` / ``has_pt()``.
_RE_FUNC_PREDICATE = re.compile(r"^\s*(\w+)\s*\(\s*\)\s*$")


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
    predicates like ``has_pt()`` are evaluated. Without enough information to
    decide, the ``else`` branch is chosen — the plural form for the canonical
    ``if param.value=="1" then "X" else "Y"`` shape.

    ``{paramN}`` slots become ``<paramN>`` (literal angle brackets) when no
    params are supplied, or are substituted directly when they are.
    """
    if not text:
        return text or ""

    # Iterate to a fixed point so a substituted ``{paramN}`` inside an
    # already-picked branch can itself be processed if needed. Cap the loop
    # so a malformed template cannot run away.
    for _ in range(8):
        new = _RE_IF_THEN_ELSE.sub(
            lambda m: _maybe_replace_if(
                m.group(0),
                m.group("predicate"),
                m.group("then"),
                m.group("else_branch"),
                params,
                card_facts,
            ),
            text,
        )
        if new == text:
            break
        text = new

    text = _RE_PARAM_SUB.sub(lambda m: _sub_param(m.group(1), params), text)
    return text


def _maybe_replace_if(
    original: str,
    predicate: str,
    then_branch: str,
    else_branch: str | None,
    params: Mapping[str, str] | None,
    card_facts: Mapping[str, object] | None,
) -> str:
    """Decide whether a captured ``{ if … then … }`` template should be
    replaced. The regex is intentionally loose to handle nested forms like
    ``else if X then "Y" else "Z"``; it can over-match on those — when it
    does, the predicate group ends up containing a stray ``then`` / ``else``
    fragment from the inner expression. We detect that and bail out instead
    of producing nonsense replacements (Phase 1.6 prompt 3 bug 12).
    """
    if any(token in predicate for token in (" then ", " else ", "{", "}")):
        return original
    decided = _eval_predicate(predicate, params, card_facts)
    fallback = else_branch if else_branch is not None else ""
    if decided is None:
        return fallback
    return then_branch if decided else fallback


def _eval_predicate(
    predicate: str,
    params: Mapping[str, str] | None,
    card_facts: Mapping[str, object] | None,
) -> bool | None:
    """Return ``True`` / ``False`` if the predicate resolves, ``None`` if not.

    Supported forms:
      * ``param.value == "X"``  — string equality (needs ``params``).
      * ``param.value != "X"``  — string inequality (needs ``params``).
      * ``name()``              — function call, dispatched via ``_FUNCS``
                                    against ``card_facts``.
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
        return fn(card_facts)

    return None


def _has_pt(facts: Mapping[str, object]) -> bool:
    """``has_pt()`` is true when the invoking card has both power and
    toughness recorded as non-empty values."""
    p = facts.get("power")
    t = facts.get("toughness")
    return bool(p) and bool(t) and str(p).strip() != "" and str(t).strip() != ""


_FUNCS: dict[str, Callable[[Mapping[str, object]], bool]] = {
    "has_pt": _has_pt,
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
