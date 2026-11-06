"""Reading the tar archives of the store: sync databases and packages.

Both are tar files, compressed with gzip, xz or (the packages, mostly) zstd.
They are read as a stream, so a package is never held in memory or unpacked to
a temporary file.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import tarfile
from contextlib import contextmanager
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
# 2 GiB: the packages may be compressed with a long-distance window (zstd --long)
_WINDOW_LOG_MAX = 31


class ZstdUnavailableError(OSError):
    """There is no way to decompress zstd on this machine."""


def _python_zstd(raw: IO[bytes]) -> IO[bytes] | None:
    """A zstd reader from Python itself (3.14) or from the ``zstandard`` module.

    Both accept the biggest compression window, as the packages may use ``--long``.
    """
    try:
        module = importlib.import_module("compression.zstd")
        options = {module.DecompressionParameter.window_log_max: _WINDOW_LOG_MAX}
        return module.ZstdFile(raw, options=options)
    except ImportError:
        pass
    try:
        module = importlib.import_module("zstandard")
        return module.ZstdDecompressor(max_window_size=1 << _WINDOW_LOG_MAX).stream_reader(
            raw, read_across_frames=True
        )
    except ImportError:
        return None


@contextmanager
def _zstd_reader(raw: IO[bytes]) -> Iterator[IO[bytes]]:
    """The decompressed content of a zstd file.

    Raises:
        ZstdUnavailableError: Neither Python nor the ``zstd`` tool can do it.
        OSError: The ``zstd`` tool failed; the message is its own.
    """
    if (reader := _python_zstd(raw)) is not None:
        with reader:
            yield reader
        return

    if shutil.which("zstd") is None:
        raise ZstdUnavailableError(
            "cannot decompress zstd: install the 'zstd' package (or the zstandard Python module)"
        )
    # the tool reads the file from its start: this one is not read by anyone else
    command = ["zstd", "-dc", f"--long={_WINDOW_LOG_MAX}", "-q"]
    with subprocess.Popen(  # noqa: S603
        command, stdin=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ) as process:
        stdout = process.stdout
        if stdout is None or process.stderr is None:
            raise ZstdUnavailableError("cannot read the output of zstd")
        try:
            yield stdout
        except (tarfile.TarError, EOFError) as error:
            # the tool failed before giving any tar: say why
            process.kill()
            reason = process.stderr.read().decode("utf-8", errors="replace").strip()
            raise OSError(f"zstd failed: {reason or error}") from error
        finally:
            stdout.close()
            process.kill()
            process.wait()


@contextmanager
def open_tar_stream(path: Path) -> Iterator[tarfile.TarFile]:
    """Open a (compressed) tar file to be read once, member by member.

    Args:
        path: The archive.

    Yields:
        The archive, in stream mode: its members can be read only in order,
        and each one only while it is the current one.
    """
    # unbuffered: the zstd tool shares this file's offset, so seek() must reach the OS
    with path.open("rb", buffering=0) as raw:
        is_zstd = raw.read(len(_ZSTD_MAGIC)) == _ZSTD_MAGIC
        raw.seek(0)
        if is_zstd:
            with _zstd_reader(raw) as stream, tarfile.open(fileobj=stream, mode="r|") as archive:
                yield archive
        else:
            with tarfile.open(fileobj=raw, mode="r|*") as archive:
                yield archive
