"""Full-screen screen that offers to install a missing emulator.

The launcher runs it (``python3 -m retrobox.emusetup``) in its own process
when the emulator a game needs is not installed, so none of its memory
(SDL, Pillow, fonts, the background) stays behind while the game runs.

* ``app``: the window, its states and its event loop.
* ``terminal``: the scrollback of the installer output (wrapping, selection).
* ``process``: the installer child process and its output thread.
* ``pad``: player 1's gamepad, mapped as in EmulationStation.

Exit status: 0 installed (launch the game), 10 declined, 11 install failed,
12 no screen could be opened.
"""
