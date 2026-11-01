"""Full-screen screen that runs an installer and shows its output.

The launcher runs it (``python3 -m retrobox.emusetup``) in its own process
when the emulator a game needs is not installed (or, with ``--reinstall``,
when the hotkey was held to install it again), so none of its memory
(SDL, Pillow, fonts, the background) stays behind while the game runs. The
startup runs it too, with ``--download``, while it downloads the default
theme or bezels before EmulationStation starts.

* ``launch``: what the callers use to run it (arguments, exit statuses).

* ``app``: the window, its states and its event loop.
* ``terminal``: the scrollback of the installer output (wrapping, selection).
* ``process``: the installer child process and its output thread.
* ``pad``: player 1's gamepad, mapped as in EmulationStation.

Exit status: 0 installed (launch the game), 10 declined (or download
cancelled), 11 install failed, 12 no screen could be opened.
"""

EXIT_INSTALLED = 0
EXIT_DECLINED = 10
EXIT_FAILED = 11
EXIT_UNAVAILABLE = 12
