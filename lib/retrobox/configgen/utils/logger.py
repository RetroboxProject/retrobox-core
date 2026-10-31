"""
Logging setup shared by every Retrobox Python entry point.

Lines look like the ones of the bash helpers (tools/lib/log.sh) used by the
emulator installers:

    [INFO] 2026-10-31_12:00:00 Generated es_systems.cfg
    [ OK ] 2026-10-31_12:00:01 Default theme installed
    [WARN] 2026-10-31_12:00:01 ...
    [ERR ] 2026-10-31_12:00:02 ...

On a terminal the tag is colored per level and the line is bold, exactly
like log.sh; colors are dropped when the stream isn't a terminal or when
NO_COLOR is set (see no-color.org). The terminal shows INFO and above
(DEBUG too with RETROBOX_DEBUG=1); the log file always gets everything,
plus the source location of each line.

Besides the standard levels there is OK (between INFO and WARNING) for
"this step finished fine": `_logger.log(OK, "...")`.
"""

from __future__ import annotations

import errno
import io
import logging
import logging.handlers
import os
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, Final, TextIO

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

OK: Final = 25
logging.addLevelName(OK, "OK")

_LOG_MAX_BYTES: Final = 1_000_000
_LOG_BACKUPS: Final = 5
_DATE_FORMAT: Final = "%Y-%m-%d_%H:%M:%S"

_BOLD: Final = "\033[1m"
_RESET: Final = "\033[0m"
_WHITE: Final = "\033[97m"

# level -> (4-char tag, ANSI color of the tag); same scheme as log.sh.
_TAGS: Final[dict[int, tuple[str, str]]] = {
    logging.DEBUG: ("DBG ", "\033[90m"),
    logging.INFO: ("INFO", "\033[36m"),
    OK: (" OK ", "\033[32m"),
    logging.WARNING: ("WARN", "\033[33m"),
    logging.ERROR: ("ERR ", "\033[31m"),
    logging.CRITICAL: ("CRIT", "\033[31m"),
}


def _tag_for(levelno: int) -> tuple[str, str]:
    """The tag of the highest known level not above `levelno`."""
    known = [level for level in _TAGS if level <= levelno]
    return _TAGS[max(known)] if known else _TAGS[logging.DEBUG]


def _wants_color(stream: TextIO) -> bool:
    """Whether to color the output written to `stream`."""
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return stream.isatty()
    except (AttributeError, ValueError, OSError):
        return False


class TaggedFormatter(logging.Formatter):
    """Format records as "[TAG] yyyy-mm-dd_hh:mm:ss message"."""

    def __init__(self, color: bool = False, with_source: bool = False) -> None:
        """
        Args:
            color: Color the tag and make the line bold (terminals only).
            with_source: Append " (file.py:line)" to every line.
        """
        super().__init__(datefmt=_DATE_FORMAT)
        self._color = color
        self._with_source = with_source

    def format(self, record: logging.LogRecord) -> str:
        """Render one record (exception tracebacks go on the next lines)."""
        tag, tag_color = _tag_for(record.levelno)
        message = record.getMessage()
        if self._with_source:
            message = f"{message} ({record.filename}:{record.lineno})"
        timestamp = self.formatTime(record, self.datefmt)

        if self._color:
            line = f"{_BOLD}{tag_color}[{tag}]{_WHITE} {timestamp} {message}{_RESET}"
        else:
            line = f"[{tag}] {timestamp} {message}"

        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        if record.stack_info:
            line = f"{line}\n{self.formatStack(record.stack_info)}"
        return line


def _is_epipe(exc: OSError) -> bool:
    """Whether `exc` means the reader of the stream went away."""
    return isinstance(exc, BrokenPipeError) or exc.errno == errno.EPIPE


class EpipeTolerantStreamHandler(logging.StreamHandler):
    """A StreamHandler that silently drops output once its reader is gone."""

    def emit(self, record: logging.LogRecord) -> None:
        """Write `record`, ignoring a broken pipe."""
        try:
            super().emit(record)
        except OSError as exc:
            if not _is_epipe(exc):
                raise

    def flush(self) -> None:
        """Flush the stream, ignoring a broken pipe."""
        try:
            super().flush()
        except OSError as exc:
            if not _is_epipe(exc):
                raise


class EpipeTolerantTextIO(io.TextIOBase):
    """Wrap a text stream to swallow BrokenPipeError/EPIPE on write/flush/close."""

    _raw: TextIO

    def __init__(self, raw: TextIO) -> None:
        super().__init__()
        self._raw = raw

    def write(self, s: str) -> int:
        """Write `s`; returns 0 once the reader is gone."""
        try:
            return self._raw.write(s)
        except OSError as exc:
            if _is_epipe(exc):
                return 0
            raise

    def flush(self) -> None:
        """Flush the wrapped stream, ignoring a broken pipe."""
        try:
            self._raw.flush()
        except OSError as exc:
            if not _is_epipe(exc):
                raise

    @property
    def encoding(self) -> str:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Encoding of the wrapped stream."""
        return self._raw.encoding

    def fileno(self) -> int:
        """File descriptor of the wrapped stream."""
        return self._raw.fileno()

    def isatty(self) -> bool:
        """Whether the wrapped stream is a terminal."""
        return self._raw.isatty()

    def close(self) -> None:
        """Close the wrapped stream, ignoring a broken pipe."""
        try:
            self._raw.close()
        except OSError as exc:
            if not _is_epipe(exc):
                raise

    @property
    def closed(self) -> bool:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Whether the wrapped stream is closed."""
        return self._raw.closed


def _stream_handler(stream: TextIO, level: int) -> logging.Handler:
    """A console handler for `stream`, colored when it is a terminal."""
    handler = EpipeTolerantStreamHandler(stream=stream)
    handler.setLevel(level)
    handler.setFormatter(TaggedFormatter(color=_wants_color(stream)))
    return handler


@contextmanager
def setup_logging(logfile: Path | None = None) -> Iterator[None]:
    """
    Configure logging for the duration of the `with` block.

    - INFO and OK to stdout (DEBUG too with RETROBOX_DEBUG=1)
    - WARNING..CRITICAL to stderr
    - everything (DEBUG..CRITICAL) to `logfile`, rotated, when given

    sys.stdout/sys.stderr are replaced by EPIPE-tolerant wrappers so that
    print() or library writes don't crash once the reader is gone.

    The file is the complete record: EmulationStation captures our stdout
    through `head -300`, so anything past 300 lines would otherwise be lost.
    A file that cannot be opened is skipped; logging never breaks a launch.
    """
    logger = logging.getLogger()
    original_handlers = list(logger.handlers)
    original_stdout, original_stderr = sys.stdout, sys.stderr
    sys.stdout = EpipeTolerantTextIO(sys.stdout)
    sys.stderr = EpipeTolerantTextIO(sys.stderr)

    for handler in original_handlers:
        logger.removeHandler(handler)

    console_level = logging.DEBUG if os.environ.get("RETROBOX_DEBUG") else logging.INFO
    stdout_handler = _stream_handler(sys.stdout, console_level)
    stdout_handler.addFilter(lambda record: record.levelno < logging.WARNING)
    logger.addHandler(stdout_handler)
    logger.addHandler(_stream_handler(sys.stderr, logging.WARNING))
    logger.setLevel(logging.DEBUG)

    if logfile is not None:
        try:
            logfile.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                logfile, maxBytes=_LOG_MAX_BYTES, backupCount=_LOG_BACKUPS, encoding="utf-8"
            )
        except OSError as err:
            logger.warning("Cannot write log file %s: %s", logfile, err)
        else:
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(TaggedFormatter(with_source=True))
            logger.addHandler(file_handler)

    try:
        yield
    finally:
        for handler in logger.handlers[:]:
            try:
                handler.flush()
            except (OSError, ValueError):
                pass
            handler.close()
            logger.removeHandler(handler)

        for handler in original_handlers:
            logger.addHandler(handler)

        sys.stdout, sys.stderr = original_stdout, original_stderr
