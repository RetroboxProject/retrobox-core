"""Text model of the terminal box: a bounded scrollback with wrapping and selection.

It knows nothing about SDL or fonts: it turns the raw output of a process into
lines (dropping colors and control codes, honouring carriage returns and
backspaces), wraps them to a column count and keeps the mouse selection. The
last line is the one being written, where the cursor is, and always exists
(empty or not). Memory is bounded by ``max_lines``; the oldest lines are
dropped first.
"""

from __future__ import annotations

import re
from collections import deque
from typing import NamedTuple

# CSI and two-byte escapes, OSC strings (terminated by BEL or ST), and lone ESC
_ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
# control characters other than backspace, \t, \n and \r (and a stray ESC)
_CTRL_RE = re.compile(r"[\x00-\x07\x0b\x0c\x0e-\x1f\x7f]")
_NEWLINE_RE = re.compile(r"(\r\n|\n|\r|\x08)")
# an escape sequence cut at the end of a chunk is kept until the next one
_MAX_PENDING_ESCAPE = 64


class Row(NamedTuple):
    """A visual row: a slice ``[start, end)`` of the absolute line ``line``."""

    line: int
    start: int
    end: int


class Position(NamedTuple):
    """A place in the text: absolute line number and character column."""

    line: int
    column: int


class TerminalBuffer:
    """Scrollback of the installer output."""

    def __init__(self, max_lines: int = 4000) -> None:
        self._lines: deque[str] = deque(maxlen=max_lines)
        self._partial = ""
        self._carriage_return = False
        self._escape_tail = ""
        self._dropped = 0
        self.anchor: Position | None = None
        self.cursor: Position | None = None

    # ------------------------------------------------------------------ input
    def feed(self, text: str) -> None:
        """Append raw process output."""
        text = self._escape_tail + text
        self._escape_tail = ""
        escape = text.rfind("\x1b")
        if escape != -1 and len(text) - escape < _MAX_PENDING_ESCAPE:
            if _ANSI_RE.match(text, escape) is None:
                self._escape_tail = text[escape:]
                text = text[:escape]
        text = _CTRL_RE.sub("", _ANSI_RE.sub("", text))

        for token in _NEWLINE_RE.split(text):
            if not token:
                continue
            if token in ("\n", "\r\n"):
                self._commit()
            elif token == "\r":
                self._carriage_return = True
            elif token == "\x08":
                self._partial = self._partial[:-1]
            else:
                if self._carriage_return:
                    # progress bars rewrite the whole line: overwrite, keep the tail
                    token = token.expandtabs()
                    self._partial = token + self._partial[len(token):]
                    self._carriage_return = False
                else:
                    self._partial = (self._partial + token).expandtabs()

    def _commit(self) -> None:
        if len(self._lines) == self._lines.maxlen:
            self._dropped += 1
        self._lines.append(self._partial)
        self._partial = ""
        self._carriage_return = False

    # ------------------------------------------------------------------ lines
    @property
    def first_line(self) -> int:
        """Absolute number of the oldest line still kept."""
        return self._dropped

    @property
    def cursor_line(self) -> int:
        """Absolute number of the line being written (where the cursor is)."""
        return self._dropped + len(self._lines)

    def _line_count(self) -> int:
        return len(self._lines) + 1

    def line(self, number: int) -> str:
        """Text of the absolute line ``number`` (empty if it is gone)."""
        index = number - self._dropped
        if 0 <= index < len(self._lines):
            return self._lines[index]
        if index == len(self._lines):
            return self._partial
        return ""

    def text(self) -> str:
        """The whole scrollback."""
        lines = list(self._lines)
        if self._partial:
            lines.append(self._partial)
        return "\n".join(lines)

    # --------------------------------------------------------------- wrapping
    @staticmethod
    def _rows_of(length: int, columns: int) -> int:
        return max(1, -(-length // columns))

    def row_count(self, columns: int) -> int:
        """Number of visual rows once wrapped to ``columns``."""
        total = sum(self._rows_of(len(line), columns) for line in self._lines)
        return total + self._rows_of(len(self._partial), columns)

    def rows(self, columns: int, first: int, count: int, total: int) -> list[Row]:
        """The visual rows ``[first, first + count)``, walking back from the end.

        ``total`` is :meth:`row_count`; walking backwards keeps the usual case
        (looking at the bottom of a long log) cheap.
        """
        wanted_end = min(first + count, total)
        result: list[Row] = []
        row = total
        number = self._dropped + self._line_count() - 1
        while number >= self._dropped and row > first:
            text = self.line(number)
            spans = self._rows_of(len(text), columns)
            row -= spans
            for span in range(spans - 1, -1, -1):
                visual = row + span
                if first <= visual < wanted_end:
                    start = span * columns
                    result.append(Row(number, start, min(start + columns, len(text))))
            number -= 1
        result.reverse()
        return result

    # -------------------------------------------------------------- selection
    def selection(self) -> tuple[Position, Position] | None:
        """Ordered selection bounds, or None when nothing is selected."""
        if self.anchor is None or self.cursor is None or self.anchor == self.cursor:
            return None
        if self.anchor < self.cursor:
            return self.anchor, self.cursor
        return self.cursor, self.anchor

    def select_all(self) -> None:
        """Select every line kept."""
        last = self.cursor_line
        self.anchor = Position(self._dropped, 0)
        self.cursor = Position(last, len(self.line(last)))

    def clear_selection(self) -> None:
        """Forget the selection."""
        self.anchor = self.cursor = None

    def selected_text(self) -> str:
        """The selected text, or the whole scrollback when nothing is selected."""
        bounds = self.selection()
        if bounds is None:
            return self.text()
        start, end = bounds
        first = max(start.line, self._dropped)
        parts = []
        for number in range(first, end.line + 1):
            text = self.line(number)
            begin = start.column if number == start.line else 0
            stop = end.column if number == end.line else len(text)
            parts.append(text[begin:stop])
        return "\n".join(parts)
