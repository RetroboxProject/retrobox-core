"""What the libretro buildbot offers: its addresses, its list of cores and their .info files.

The buildbot (``https://buildbot.libretro.com``) builds every core each night,
for each architecture, into ``nightly/linux/<arch>/latest/``: one
``<core>_libretro.so.zip`` per core, and a ``.index-extended`` that lists them
one per line, as ``<date> <crc32> <core>_libretro.so.zip``. The ``.info`` file
of every core (its name, the system it emulates, its license...) is in
``assets/frontend/info.zip``.
"""

from __future__ import annotations

import os
import platform
import re
from dataclasses import dataclass
from typing import Final

DEFAULT_BUILDBOT: Final = "https://buildbot.libretro.com/"
BUILDBOT_ENV: Final = "RETROBOX_BUILDBOT"
"""Another buildbot (a mirror, or a ``file://`` folder laid out the same way)."""

ARCH_ENV: Final = "RETROBOX_CORES_ARCH"
"""The machine to download the cores for, instead of this one's (``uname -m``)."""

BASE_CORES: Final = (
    "mame2003_plus", "fbneo", "fceumm", "snes9x", "mupen64plus_next", "gambatte", "mgba",
    "genesis_plus_gx", "picodrive", "flycast",
    "mednafen_pce", "mednafen_pce_fast", "mednafen_supergrafx",
    "mednafen_ngp", "mednafen_wswan", "pokemini", "gw",
    "stella", "a5200", "atari800", "prosystem",
    "handy", "holani", "mednafen_lynx",
    "pcsx_rearmed",
)
"""The cores RetroArch's installer downloads the first time (the rest are on demand)."""

BUILT_ON_ARM: Final = ("flycast",)
"""Cores RetroArch's installer builds from source on ARM, against desktop
OpenGL as RetroArch is there: whether the buildbot's aarch64 flycast runs on it
is still to be checked (its mupen64plus_next links libGL, so that one is
downloaded). They are not offered for download on ARM, so a download never
replaces them."""

_ARCHES: Final = {
    "x86_64": "x86_64", "amd64": "x86_64",
    "aarch64": "aarch64", "arm64": "aarch64",
    "armv7l": "armhf", "armhf": "armhf",
    "i686": "x86", "i386": "x86",
}
_INDEX_LINE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<crc>[0-9A-Fa-f]{1,8})\s+"
    r"(?P<core>[\w.+-]+)_libretro\.so\.zip$"
)
_INFO_LINE = re.compile(r'^\s*(?P<key>[\w.]+)\s*=\s*"?(?P<value>.*?)"?\s*$')
CORE_NAME: Final = re.compile(r"^[a-z0-9][a-z0-9_+.-]*$")
"""What a core name may be: it becomes a file name."""


@dataclass(frozen=True, slots=True)
class Build:
    """One core of the buildbot: its name and the build it has now."""

    core: str
    date: str
    crc: str

    @property
    def version(self) -> str:
        """The build as one string, as it is shown and remembered (``date crc``)."""
        return f"{self.date} {self.crc}"


def buildbot() -> str:
    """The buildbot's address, ending in ``/``."""
    base = os.environ.get(BUILDBOT_ENV) or DEFAULT_BUILDBOT
    return base if base.endswith("/") else base + "/"


def machine() -> str:
    """The machine the cores are for."""
    return os.environ.get(ARCH_ENV) or platform.machine()


def buildbot_arch(name: str) -> str | None:
    """The buildbot's folder for a machine (``uname -m``), or None if it builds no cores for it."""
    return _ARCHES.get(name.lower())


def offered(core: str, arch: str) -> bool:
    """Whether a core is offered for download on ``arch`` (see BUILT_ON_ARM)."""
    return arch == "x86_64" or core not in BUILT_ON_ARM


def cores_url(arch: str) -> str:
    """The folder of the latest builds of ``arch``."""
    return f"{buildbot()}nightly/linux/{arch}/latest/"


def index_url(arch: str) -> str:
    """The list of the cores of ``arch``."""
    return cores_url(arch) + ".index-extended"


def core_url(arch: str, core: str) -> str:
    """The archive of a core."""
    return f"{cores_url(arch)}{core}_libretro.so.zip"


def info_url() -> str:
    """The archive with the .info file of every core."""
    return buildbot() + "assets/frontend/info.zip"


def parse_index(text: str) -> dict[str, Build]:
    """The cores of a ``.index-extended``, by name; lines that don't fit are skipped."""
    builds = {}
    for line in text.splitlines():
        match = _INDEX_LINE.match(line.strip())
        if match and CORE_NAME.match(match["core"]):
            builds[match["core"]] = Build(match["core"], match["date"], match["crc"].lower())
    return builds


def parse_info(text: str) -> dict[str, str]:
    """The ``key = "value"`` lines of a .info file."""
    values = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = _INFO_LINE.match(line)
        if match:
            values[match["key"]] = match["value"]
    return values
