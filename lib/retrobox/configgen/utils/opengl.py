"""What the OpenGL driver of this computer offers (one probe per process).

RetroArch's ``glcore`` video driver needs an OpenGL *core profile* context
(3.2 or later). The version that matters is therefore the one of the core
profile, not of the compatibility profile that ``glxinfo`` prints first
(``OpenGL version string``): on some drivers the latter is lower or higher
than the former.
"""

from __future__ import annotations

import functools
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Final

_logger: Final = logging.getLogger(__name__)

# probes, in order: glxinfo (X11 / XWayland), then eglinfo (wayland / gbm)
_PROBES: Final = (("glxinfo", "-B"), ("eglinfo", "-B"))
_TIMEOUT: Final = 15

_CORE_VERSION_RE: Final = re.compile(
    r"^OpenGL core profile version string:\s*(\d+)\.(\d+)", re.MULTILINE
)
_COMPAT_VERSION_RE: Final = re.compile(r"^OpenGL version string:\s*(\d+)\.(\d+)", re.MULTILINE)
_VENDOR_RE: Final = re.compile(r"^OpenGL vendor string:\s*(.+?)\s*$", re.MULTILINE)
_RENDERER_RE: Final = re.compile(r"^OpenGL renderer string:\s*(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class GLInfo:
    """The result of a successful probe."""

    vendor: str
    renderer: str
    core_version: tuple[int, int] | None  # None: the driver offers no core profile
    compat_version: tuple[int, int] | None


def parse(output: str) -> GLInfo | None:
    """Read the output of ``glxinfo -B`` / ``eglinfo -B``.

    Returns None when it holds no OpenGL information at all (no context could
    be created), which is not the same as a driver without a core profile.
    """
    vendor = _VENDOR_RE.search(output)
    core = _CORE_VERSION_RE.search(output)
    compat = _COMPAT_VERSION_RE.search(output)
    if vendor is None and core is None and compat is None:
        return None
    renderer = _RENDERER_RE.search(output)
    return GLInfo(
        vendor=vendor.group(1).casefold() if vendor else "unknown",
        renderer=renderer.group(1) if renderer else "unknown",
        core_version=(int(core.group(1)), int(core.group(2))) if core else None,
        compat_version=(int(compat.group(1)), int(compat.group(2))) if compat else None,
    )


@functools.lru_cache(maxsize=1)
def probe() -> GLInfo | None:
    """Ask the driver, once. None when nothing could tell (tool missing, no display...)."""
    for command in _PROBES:
        if shutil.which(command[0]) is None:
            continue
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=_TIMEOUT, check=False
            )
        except (OSError, subprocess.SubprocessError) as error:
            _logger.debug("%s failed: %s", command[0], error)
            continue
        info = parse(result.stdout)
        if info is not None:
            _logger.debug("OpenGL (%s): %s", command[0], info)
            return info
        _logger.debug("%s gave no OpenGL information (exit %s)", command[0], result.returncode)
    return None


def core_profile_status(minimum: tuple[int, int]) -> tuple[bool | None, str]:
    """Whether an OpenGL core profile of at least ``minimum`` is available.

    Returns ``(True | False, reason)``, or ``(None, reason)`` when it could not
    be found out: the caller decides what to assume then.
    """
    info = probe()
    if info is None:
        return None, "no glxinfo/eglinfo output to tell"
    if info.core_version is None:
        return False, f"{info.renderer} offers no OpenGL core profile"
    if info.core_version < minimum:
        return False, (
            f"OpenGL core profile {info.core_version[0]}.{info.core_version[1]} "
            f"< {minimum[0]}.{minimum[1]}"
        )
    return True, f"OpenGL core profile {info.core_version[0]}.{info.core_version[1]}"
