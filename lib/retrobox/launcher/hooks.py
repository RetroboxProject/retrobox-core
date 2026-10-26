"""Runner of the retrohook script system (on-start-game / on-close-game)."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from retrobox.paths import HOOKS

from .session import effective_core

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .session import GameSession

_logger = logging.getLogger(__name__)

_MAX_HOOK_NAME_LENGTH = 255  # filename limit on ext4/btrfs


def _sanitize_hook_name(name: str) -> str:
    """Sanitize a name for use as a path component under retrohook.d/.

    Only affects the hook directory lookup, not the args passed to the script.
    """
    name = name.replace("/", "_")  # the only truly illegal char on Linux
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)  # control chars
    return name[:_MAX_HOOK_NAME_LENGTH]


def call_retrohook(
    platform: str,
    game: str | Path,
    state: str,  # "on-start-game" | "on-close-game"
    extra_args: Iterable[str | Path] = (),
) -> None:
    """Invoke retrobox's hook system.

    Delegates all hierarchy and execution logic to the retrohook bash script.
    """
    if not HOOKS.is_file() or not os.access(HOOKS, os.X_OK):
        _logger.debug("retrohook not found or not executable: %s", HOOKS)
        return

    game_hook_name = _sanitize_hook_name(Path(game).stem)  # for the path

    cmd = [str(HOOKS), platform, game_hook_name, state, str(game), *map(str, extra_args)]

    _logger.info("[retrohook] %s %s %s", platform, game_hook_name, state)
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        _logger.warning("[retrohook] exited with code %s", result.returncode)


def call_game_hooks(session: GameSession, state: str) -> None:
    """Run the global, system and game hooks for a game state."""
    extra_args = [session.system.config.emulator, effective_core(session.system)]
    call_retrohook("_global", "_platform", state, extra_args)
    call_retrohook(session.args.system, "_platform", state, extra_args)
    call_retrohook(session.args.system, session.rom, state, extra_args)
