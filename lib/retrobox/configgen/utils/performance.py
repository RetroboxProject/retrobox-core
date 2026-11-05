"""The "performance" power profile as a bundle of performance settings.

Choosing ``power_profile = performance`` makes the launcher switch
power-profiles-daemon (and nvidia-powerd) to performance, and makes the
emulators that support Feral's GameMode turn it on. Any other profile leaves
GameMode off: it would otherwise hold power-profiles-daemon's performance
profile for the whole game and override the profile the user chose.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from retrobox.configgen.config import SystemConfig

PERFORMANCE_PROFILE = "performance"


def performance_mode(config: SystemConfig) -> bool:
    """Whether the game runs with the performance power profile."""
    profile = str(config.get("power_profile", "balanced") or "balanced")
    return profile.strip().lower() == PERFORMANCE_PROFILE


def gamemode_value(config: SystemConfig) -> str:
    """GameMode's switch for the emulators' settings: "true" or "false"."""
    return "true" if performance_mode(config) else "false"
