"""Downloading files of the store."""

from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

USER_AGENT: Final = "retrobox-store"

_ALLOWED_SCHEMES: Final = ("https", "http", "file")
_CHUNK: Final = 256 * 1024
_TIMEOUT_SECONDS: Final = 30
# how often the progress is reported while downloading
_REPORT_INTERVAL: Final = 0.5


class DownloadError(Exception):
    """A file could not be downloaded or did not check out."""


def _stream_to_file(
    url: str,
    partial: Path,
    expected_size: int,
    progress: Callable[[int, int], None] | None,
) -> tuple[int, str]:
    """Copy a URL into a file; returns the bytes written and their SHA-256."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    digest = hashlib.sha256()
    done = 0
    last_report = 0.0
    with urllib.request.urlopen(  # noqa: S310
        request, timeout=_TIMEOUT_SECONDS
    ) as response, partial.open("wb") as output:
        total = int(response.headers.get("Content-Length") or expected_size or 0)
        while chunk := response.read(_CHUNK):
            output.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            now = time.monotonic()
            if progress is not None and now - last_report >= _REPORT_INTERVAL:
                last_report = now
                progress(done, total)
    return done, digest.hexdigest()


def download(
    url: str,
    destination: Path,
    *,
    expected_size: int = 0,
    expected_sha256: str = "",
    progress: Callable[[int, int], None] | None = None,
) -> None:
    """Download a file, keeping it only if it is complete and correct.

    The file is written next to ``destination`` and renamed when it is done,
    so ``destination`` never holds a partial download.

    Args:
        url: Where to download from (https, http or file).
        destination: The file to create.
        expected_size: The size it must have, if known.
        expected_sha256: The SHA-256 it must have, if known.
        progress: Called with the bytes downloaded and the total (0 if unknown).

    Raises:
        DownloadError: The download failed, or the size or checksum differ.
    """
    if urllib.parse.urlsplit(url).scheme not in _ALLOWED_SCHEMES:
        raise DownloadError(f"unsupported address: {url}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    try:
        done, digest = _stream_to_file(url, partial, expected_size, progress)
    except (urllib.error.URLError, OSError, ValueError) as error:
        partial.unlink(missing_ok=True)
        raise DownloadError(f"cannot download {url}: {error}") from error

    if expected_size and done != expected_size:
        partial.unlink(missing_ok=True)
        raise DownloadError(f"{url}: expected {expected_size} bytes, got {done}")
    if expected_sha256 and digest != expected_sha256.lower():
        partial.unlink(missing_ok=True)
        raise DownloadError(f"{url}: the checksum does not match")

    if progress is not None:
        progress(done, done)
    partial.replace(destination)
