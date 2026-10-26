"""Retrobox emulator launcher: prepares the environment and runs an emulator for a ROM.

Run it with ``bin/retrobox-launch`` (or ``python3 -m retrobox.launcher``). This
module is only the entry point: the work is split into the modules of the
``retrobox.launcher`` package (see its docstring for the map).
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from retrobox.configgen import profiler
from retrobox.configgen.exceptions import BaseRetroboxException, RetroboxException
from retrobox.configgen.utils.logger import setup_logging
from retrobox.launcher.cli import MAX_PLAYERS, build_argument_parser
from retrobox.launcher.hooks import call_retrohook
from retrobox.launcher.process import install_interrupt_handler, normalize_exit_code
from retrobox.launcher.runner import run_rom

__all__ = ["call_retrohook", "launch"]

_logger = logging.getLogger(__name__)


def launch() -> None:
    """Handle program arguments and exception handling to EmulationStation and logs."""
    with setup_logging():
        install_interrupt_handler()

        _logger.info("%s Retrobox %s", "=" * 20, "=" * 20)
        _logger.info(
            "emulatorlauncher started at: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        args = build_argument_parser(MAX_PLAYERS).parse_args()
        _logger.debug(
            "args: %s", {k: v for k, v in vars(args).items() if v is not None and v is not False}
        )

        exitcode = 0
        try:
            exitcode = run_rom(args, MAX_PLAYERS)
        except BaseRetroboxException as err:
            _logger.exception("configgen exception: ")
            exitcode = err.exit_code

            if isinstance(err, RetroboxException):
                Path("/tmp/launch_error.log").write_text(err.args[0], encoding="utf-8")
        except Exception:  # pylint: disable=broad-exception-caught
            # last-resort handler: log everything and exit cleanly for EmulationStation
            _logger.exception("configgen exception: ")

        profiler.stop()

        # this seems to be required so that the gpu memory is restituated and available for es
        time.sleep(1)

        exitcode = normalize_exit_code(exitcode)

        _logger.debug("Exiting configgen with status %s", exitcode)

        sys.exit(exitcode)


if __name__ == "__main__":
    launch()
