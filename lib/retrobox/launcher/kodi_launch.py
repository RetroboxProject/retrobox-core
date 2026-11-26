"""Start Kodi on its own: no game session, no overlay.

``bin/retrobox-kodi-launch`` is what EmulationStation runs for its Kodi entry.
Kodi is a frontend, not a game: it does not go through ``retrobox-launch``, so
it publishes no ``launch.json`` or ``session.json`` and opens no control
channel. It only says it runs in ``frontend.json`` (see ``launch_phase``), so
that the overlay stays closed over it: Kodi has menus of its own, and without a
session the overlay would offer its system menu. For ``retrobox-emukill``
there is no game while Kodi runs. What Kodi starts with ``retrobox-launch`` (a
web app, say) is a game session like any other: the overlay works over it and
``retrobox-emukill`` ends it without reaching Kodi.

What it does, in order:

1. Reads whether L1 and R1 (or Ctrl and Shift) are held, while the button that
   started Kodi is likely still down.
2. Offers to install Kodi when it is missing, or to install it again (to update
   it) when the chord is held: the overlay's task screen, a process of its own
   that needs no session (see ``emulator_setup``). Declining goes back to
   EmulationStation.
3. Writes Kodi's controller configuration and enables its Retrobox add-ons.
4. Runs ``bin/retrobox-kodi`` and waits for it, with ``frontend.json`` in place.

The power profile, the resolution, the idle inhibition, the controller monitor
and the user's game hooks belong to games and are left out.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from retrobox.configgen.Command import Command
from retrobox.configgen.controller import Controller
from retrobox.configgen.exceptions import BaseRetroboxException, RetroboxException
from retrobox.configgen.generators.kodi import kodi_addons, kodiConfig
from retrobox.configgen.utils.logger import setup_logging
from retrobox.launcher.cli import MAX_PLAYERS, build_argument_parser
from retrobox.launcher.emulator_setup import ensure_emulator
from retrobox.launcher.launch_phase import end_frontend, start_frontend
from retrobox.launcher.process import install_interrupt_handler, normalize_exit_code, run_command
from retrobox.paths import LOGS
from retrobox.utils.overlay_task import reinstall_requested

if TYPE_CHECKING:
    import argparse

__all__ = ["launch"]

_logger = logging.getLogger(__name__)

_EMULATOR = "kodi"


def run(args: argparse.Namespace) -> int:
    """Install or update Kodi if asked, configure it and run it.

    Args:
        args: The parsed command line (only the ``-p<N>...`` options matter).

    Returns:
        Kodi's exit code; 0 when the installation was declined.
    """
    # read right away: the chord that asks for an update is held while Kodi starts
    reinstall = reinstall_requested()
    controllers = Controller.load_for_players(MAX_PLAYERS, args)

    if not ensure_emulator(_EMULATOR, reinstall=reinstall):
        return 0

    # raises RetroboxException when no Kodi is installed, before anything is written
    userdata = kodiConfig.kodi_userdata()
    kodiConfig.write_kodi_config(controllers, userdata)
    kodi_addons.enable_addons(userdata)
    start_frontend()
    try:
        return run_command(Command([kodiConfig.KODI_LAUNCHER]))
    finally:
        end_frontend()


def launch() -> None:
    """Run Kodi and exit with the status EmulationStation reads."""
    with setup_logging(LOGS / "retrobox-kodi.log"):
        install_interrupt_handler()
        _logger.info("retrobox-kodi-launch started")
        args = build_argument_parser(MAX_PLAYERS, require_game=False).parse_args()

        exitcode = 0
        try:
            exitcode = run(args)
        except BaseRetroboxException as err:
            _logger.exception("kodi launch exception: ")
            exitcode = err.exit_code
            if isinstance(err, RetroboxException):
                Path("/tmp/launch_error.log").write_text(err.args[0], encoding="utf-8")
        except Exception:  # pylint: disable=broad-exception-caught
            # last-resort handler: log everything and exit cleanly for EmulationStation
            _logger.exception("kodi launch exception: ")

        # as retrobox-launch: the GPU's memory is given back before EmulationStation returns
        time.sleep(1)
        sys.exit(normalize_exit_code(exitcode))


if __name__ == "__main__":
    launch()
