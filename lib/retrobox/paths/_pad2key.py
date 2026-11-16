"""retrobox.paths constants for the pad profiles (pad -> keyboard mappings).

The launcher composes the game's profile from these
(retrobox.launcher.pad_profile) and the overlay's input daemon
(``retrobox-inputd``) maps the controllers with it.
"""

from __future__ import annotations

from typing import Final

from ._base import CONFIG_DIR, RUNTIME_DIR, SHARE_DIR

PAD_PROFILES: Final = SHARE_DIR / "pad2key" / "profiles"
# User profiles are configuration (they override the shipped ones), so they
# live in the config dir, mirroring share/pad2key/profiles.
USER_PAD_PROFILES: Final = CONFIG_DIR / "pad2key" / "profiles"

# The standard hotkeys (controller combination -> action), and the user's
# own table, which replaces it when present.
HOTKEYS_TABLE: Final = SHARE_DIR / "pad2key" / "hotkeys.yaml"
USER_HOTKEYS_TABLE: Final = CONFIG_DIR / "pad2key" / "hotkeys.yaml"
# The profile composed for the game being played (mappings + hotkeys).
SESSION_PAD_PROFILE: Final = RUNTIME_DIR / "pad2key" / "session.keys"
