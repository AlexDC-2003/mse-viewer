from __future__ import annotations

from dataclasses import dataclass, field

from .lexer import Line


@dataclass
class MseNode:
    """A single key/value or block in the MSE tree.

    - ``key`` is the field name (e.g. ``card``, ``rule_text``, ``styling_data``).
    - ``value`` is the inline value when present.
    - ``children`` is a list of nested nodes (block bodies).
    - For multi-line text values the value lines are joined with newlines and stored
      in ``value``; ``children`` will be empty.
    """

    key: str
    value: str = ""
    children: list["MseNode"] = field(default_factory=list)

    # ---- helpers ----------------------------------------------------------

    def first(self, key: str) -> "MseNode | None":
        for c in self.children:
            if c.key == key:
                return c
        return None

    def all(self, key: str) -> list["MseNode"]:
        return [c for c in self.children if c.key == key]

    def get(self, key: str, default: str = "") -> str:
        node = self.first(key)
        return node.value if node is not None else default


def build_tree(lines: list[Line]) -> MseNode:
    """Build a nested tree from the line list produced by ``lex``.

    The root node has key ``"<root>"`` and its ``children`` are the top-level
    fields (set ``mse_version``, ``game``, ``stylesheet``, ``set_info``, blocks of
    ``card``, etc.).
    """
    root = MseNode(key="<root>")
    # Stack of (indent, node) — the node at the top is the current parent.
    stack: list[tuple[int, MseNode]] = [(-1, root)]

    pending_text: list[str] | None = None  # multi-line value collector
    pending_node: MseNode | None = None

    def flush_pending() -> None:
        nonlocal pending_text, pending_node
        if pending_node is not None and pending_text is not None:
            joined = "\n".join(pending_text).rstrip("\n")
            pending_node.value = (pending_node.value + "\n" + joined).strip("\n") if pending_node.value else joined
        pending_text = None
        pending_node = None

    for line in lines:
        # Blank line — if we're inside a multi-line value, keep it (preserves
        # paragraph breaks). Otherwise ignore.
        if line.indent == -1:
            if pending_text is not None:
                pending_text.append("")
            continue

        if line.key is None:
            # continuation of the previous value (deeper indented than its key)
            if pending_text is not None:
                pending_text.append(line.value)
            else:
                # Stray text — attach to nearest parent as a synthetic child.
                stack[-1][1].children.append(MseNode(key="_text", value=line.value))
            continue

        # New keyed line: pop the stack until we find a parent strictly less
        # indented than this line.
        flush_pending()
        while stack and stack[-1][0] >= line.indent:
            stack.pop()

        parent = stack[-1][1]
        node = MseNode(key=line.key, value=line.value)
        parent.children.append(node)

        # Always allow continuation accumulation: deeper-indented value-only
        # lines join the node's value, deeper-indented keyed lines become
        # children (and the empty pending_text flushes to a no-op).
        stack.append((line.indent, node))
        pending_text = []
        pending_node = node

    flush_pending()
    return root
