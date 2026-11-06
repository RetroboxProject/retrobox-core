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


class ZstdUnavailableError(OSError):
    """There is no way to decompress zstd on this machine."""


def _python_zstd(raw: IO[bytes]) -> IO[bytes] | None:
    """A zstd reader from Python itself (3.14) or from the ``zstandard`` module."""
    try:
        return importlib.import_module("compression.zstd").ZstdFile(raw)
    except ImportError:
        pass
    try:
        return importlib.import_module("zstandard").ZstdDecompressor().stream_reader(raw)
    except ImportError:
        return None


@contextmanager
def _zstd_reader(raw: IO[bytes]) -> Iterator[IO[bytes]]:
    """The decompressed content of a zstd file.

    Raises:
        ZstdUnavailableError: Neither Python nor the ``zstd`` tool can do it.
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
    with subprocess.Popen(  # noqa: S603
        ["zstd", "-dc"], stdin=raw, stdout=subprocess.PIPE
    ) as process:
        stdout = process.stdout
        if stdout is None:
            raise ZstdUnavailableError("cannot read the output of zstd")
        try:
            yield stdout
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
    with path.open("rb") as raw:
        is_zstd = raw.read(len(_ZSTD_MAGIC)) == _ZSTD_MAGIC
        raw.seek(0)
        if is_zstd:
            with _zstd_reader(raw) as stream, tarfile.open(fileobj=stream, mode="r|") as archive:
                yield archive
        else:
            with tarfile.open(fileobj=raw, mode="r|*") as archive:
                yield archive
