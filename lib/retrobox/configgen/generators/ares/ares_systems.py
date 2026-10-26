"""Names that Ares gives to the systems of Retrobox.

Ares picks the system of a game from the extension of its file, and several
systems share one (.bin, .cue, .sg...). Passing ``--system`` removes the guess.
The systems that were already run by Ares before this table are left out, so
they start as they always did.
"""

from __future__ import annotations

# system of Retrobox -> name of the system in Ares (as ``ares --help`` lists them)
ARES_SYSTEM_NAMES: dict[str, str] = {
    "atari2600": "Atari 2600",
    "atari5200": "Atari 5200",
    "colecovision": "ColecoVision",
    "fds": "Famicom Disk System",
    "gb": "Game Boy",
    "gbc": "Game Boy Color",
    "gba": "Game Boy Advance",
    "n64dd": "Nintendo 64DD",
    "megacd": "Mega CD",
    "saturn": "Saturn",
    "mastersystem": "Master System",
    "gamegear": "Game Gear",
    "sg1000": "SG-1000",
    "sc3000": "SC-3000",
    "pcengine": "PC Engine",
    "pcenginecd": "PC Engine CD",
    "supergrafx": "SuperGrafx",
    "psx": "PlayStation",
    "ngp": "Neo Geo Pocket",
    "ngpc": "Neo Geo Pocket Color",
    "wswan": "WonderSwan",
    "wswanc": "WonderSwan Color",
    "msx1": "MSX",
    "msx2": "MSX2",
    "zxspectrum": "ZX Spectrum",
}


def ares_system_name(system_name: str) -> str | None:
    """Return the name Ares gives to a system, or None when it must pick it itself."""
    return ARES_SYSTEM_NAMES.get(system_name)
