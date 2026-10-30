"""Building blocks of the emulator launcher (entry point: ``main.py``).

Each module owns one concern of launching a game:

* ``cli``: command-line arguments.
* ``session``: the data shared by every step of one launch.
* ``runner``: the launch sequence itself, from ROM to exit code.
* ``process``: running the emulator command and mapping its exit status.
* ``power``: power profiles and ``nvidia-powerd``.
* ``hooks``: the ``retrohook`` script runner.
* ``emulator_setup``: offering to install a missing emulator (``retrobox.emusetup``).
* ``controller_monitor``: controller hot-plug watching.
* ``hud``: the MangoHud overlay (HUD text and environment).
* ``hud_bezel``: building the bezel image MangoHud draws as background.
"""
