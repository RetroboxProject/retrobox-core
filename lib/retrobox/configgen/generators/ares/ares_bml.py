"""Minimal reader and writer of the BML text that Ares uses for settings.bml.

Ares writes every setting as a node: one name per line, nested by two spaces,
with ``name: value`` when the node holds a value and a bare ``name`` when it
holds none (or an empty one). Reading the file into a tree lets the generator
change the settings it manages and leave every other one as the person
configured it in Ares.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_INDENT = "  "
_VALUE_SEPARATOR = ": "


@dataclass
class BmlNode:
    """A node of the tree: a name, an optional value and the nodes under it."""

    name: str = ""
    value: str | None = None
    children: list[BmlNode] = field(default_factory=list)

    def find(self, name: str) -> BmlNode | None:
        """Return the first child with this name, like Ares does for repeated names."""
        for child in self.children:
            if child.name == name:
                return child
        return None

    def set(self, path: str, value: object) -> None:
        """Set the value of the node at a ``/`` separated path, creating what is missing."""
        node = self
        for part in path.split("/"):
            child = node.find(part)
            if child is None:
                child = BmlNode(part)
                node.children.append(child)
            node = child
        node.value = _to_text(value)

    def get(self, path: str) -> str | None:
        """Return the value at a ``/`` separated path, or None when there is none."""
        node: BmlNode | None = self
        for part in path.split("/"):
            node = node.find(part) if node is not None else None
        return node.value if node is not None else None

    def remove_children(self, matches: Callable[[str], bool]) -> None:
        """Remove the children whose name satisfies ``matches``."""
        self.children = [child for child in self.children if not matches(child.name)]

    def replace_children(self, replacements: BmlNode) -> None:
        """Replace the children that share a name with those of ``replacements``."""
        names = {child.name for child in replacements.children}
        self.remove_children(names.__contains__)
        self.children.extend(replacements.children)


def _to_text(value: object) -> str | None:
    """Return a value as BML text; empty values are written as a bare name."""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    return text or None


def parse(text: str) -> BmlNode:
    """Read BML text into a tree whose root has no name."""
    root = BmlNode()
    stack = [root]
    for raw in text.splitlines():
        content = raw.lstrip(" ")
        if not content:
            continue
        depth = min((len(raw) - len(content)) // len(_INDENT), len(stack) - 1)
        name, separator, value = content.partition(_VALUE_SEPARATOR)
        node = BmlNode(name, value if separator else None)
        del stack[depth + 1 :]
        stack[depth].children.append(node)
        stack.append(node)
    return root


def render(root: BmlNode) -> str:
    """Write a tree as BML text."""
    lines: list[str] = []

    def walk(node: BmlNode, depth: int) -> None:
        line = f"{_INDENT * depth}{node.name}"
        if node.value is not None:
            line += f"{_VALUE_SEPARATOR}{node.value}"
        lines.append(line)
        for child in node.children:
            walk(child, depth + 1)

    for child in root.children:
        walk(child, 0)
    return "\n".join(lines) + "\n"
