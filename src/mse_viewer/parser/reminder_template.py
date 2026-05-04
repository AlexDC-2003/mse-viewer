"""Pretty-printer for MSE reminder templates.

MSE reminders embed inline expressions in ``{...}`` braces, e.g. ::

    {param1} poison { if param1.value=="1" then "counter." else "counters." }

For display we want the rendered form, not the raw template. With concrete
parameter values supplied, the predicate is evaluated; without values we pick
the ``else`` branch (the plural form is the safer default for English) and
render ``{paramN}`` as ``<paramN>`` (literal angle brackets) so a reader can
still see the slot.

Phase 1.5 scope is the ``if/then/else`` plurality form plus simple
``foo.value=="X"`` predicates and bare ``{paramN}`` substitution. Anything
else is left in place — adding more grammar later is a matter of extending
:func:`_eval_predicate`.
"""
from __future__ import annotations

import re

# {paramN} substitution slot — a single identifier inside braces, no spaces.
_RE_PARAM_SUB = re.compile(r"\{(\w+)\}")

# { if EXPR then "STRING" else "STRING" }
_RE_IF_THEN_ELSE = re.compile(
    r'\{\s*if\s+(?P<predicate>.+?)\s+then\s+"(?P<then>(?:[^"\\]|\\.)*)"'
    r'\s+else\s+"(?P<else_branch>(?:[^"\\]|\\.)*)"\s*\}',
    re.DOTALL,
)

# Simple equality predicate: ``foo.value == "X"`` or ``foo.value=='X'``.
_RE_EQ_PREDICATE = re.compile(
    r'^\s*(\w+)\.value\s*(==|!=)\s*["\'](.*?)["\']\s*$',
    re.DOTALL,
)


def evaluate_reminder_template(
    text: str | None,
    params: dict[str, str] | None = None,
) -> str:
    """Render an MSE reminder template for display.

    With ``params`` (a ``param_name → value`` map taken from a card-side
    invocation), ``if/then/else`` predicates are evaluated. Without it the
    ``else`` branch is chosen — that is the plural form for the
    canonical ``if param.value=="1" then "X" else "Y"`` shape.

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
            lambda m: _eval_if(
                m.group("predicate"), m.group("then"), m.group("else_branch"), params
            ),
            text,
        )
        if new == text:
            break
        text = new

    text = _RE_PARAM_SUB.sub(lambda m: _sub_param(m.group(1), params), text)
    return text


def _eval_if(
    predicate: str,
    then_branch: str,
    else_branch: str,
    params: dict[str, str] | None,
) -> str:
    """Evaluate a single ``if/then/else``. Default to ``else`` when the
    predicate cannot be decided (no params, unsupported grammar, etc.)."""
    decided = _eval_predicate(predicate, params)
    if decided is None:
        return else_branch
    return then_branch if decided else else_branch


def _eval_predicate(predicate: str, params: dict[str, str] | None) -> bool | None:
    """Return ``True`` / ``False`` if the predicate resolves, ``None`` if not.

    Supported forms (Phase 1.5):
      * ``param.value == "X"``  — string equality
      * ``param.value != "X"``  — string inequality
    """
    if params is None:
        return None
    m = _RE_EQ_PREDICATE.match(predicate)
    if not m:
        return None
    name, op, expected = m.group(1), m.group(2), m.group(3)
    actual = _lookup_param(name, params)
    if actual is None:
        return None
    if op == "==":
        return str(actual).strip() == expected
    return str(actual).strip() != expected


def _lookup_param(name: str, params: dict[str, str]) -> str | None:
    """Resolve ``name`` against the param dict, tolerating both ``"foo"`` and
    ``"foo.value"`` keys so callers don't have to think about which form
    they passed in."""
    if name in params:
        return params[name]
    return params.get(f"{name}.value")


def _sub_param(name: str, params: dict[str, str] | None) -> str:
    """Substitute ``{paramN}``: with concrete params, return the value;
    without, render as ``<paramN>`` so the slot is visible."""
    if params is not None:
        v = _lookup_param(name, params)
        if v is not None:
            return str(v)
    return f"<{name}>"
