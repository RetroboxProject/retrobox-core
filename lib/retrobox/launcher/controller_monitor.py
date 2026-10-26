"""Background monitoring of controller hot-plug events while a game runs."""

from __future__ import annotations

import ctypes
import logging
import threading
from copy import deepcopy
from typing import TYPE_CHECKING

import pyudev
import sdl2

if TYPE_CHECKING:
    from collections.abc import Iterable

    from retrobox.configgen.controller import Controller

_logger = logging.getLogger(__name__)

_GUID_BUFFER_SIZE = 33


def _init_sdl_joystick() -> bool:
    """Initialize the SDL2 joystick subsystem if needed.

    Returns:
        True if this call initialized it, False if the host had already done it.
    """
    if sdl2.SDL_WasInit(sdl2.SDL_INIT_JOYSTICK) != 0:
        _logger.info(
            ">>> SDL2 joystick subsystem already initialized by host (emulator). "
            "Will not re-initialize."
        )
        return False

    _logger.info(">>> SDL2 joystick subsystem not initialized. Initializing it now.")
    sdl2.SDL_Init(sdl2.SDL_INIT_JOYSTICK)
    return True


def _scan_online_controllers() -> dict[str, str]:
    """Return a GUID -> device path map of the joysticks currently seen by SDL2."""
    sdl2.SDL_JoystickUpdate()
    online_controllers: dict[str, str] = {}
    for index in range(sdl2.SDL_NumJoysticks()):
        try:
            guid_struct = sdl2.SDL_JoystickGetDeviceGUID(index)
            guid_buffer = (ctypes.c_char * _GUID_BUFFER_SIZE)()
            sdl2.SDL_JoystickGetGUIDString(guid_struct, guid_buffer, _GUID_BUFFER_SIZE)
            guid = guid_buffer.value.decode("utf-8")

            path_bytes = sdl2.SDL_JoystickPathForIndex(index)
            path = path_bytes.decode("utf-8") if path_bytes else None

            if guid and path:
                online_controllers[guid] = path
        except Exception as err:  # pylint: disable=broad-exception-caught
            # one misbehaving device must not stop the monitoring of the others
            _logger.warning("Error while querying joystick index %s with pysdl2: %s", index, err)
    return online_controllers


# a worker object: start() is its whole public interface
# pylint: disable-next=too-few-public-methods
class ControllerMonitor:
    """Watches controller add/remove events in a background thread.

    Uses pysdl2 to reliably get controller GUIDs and paths, then "revives" the
    original controller object to preserve the player order without disrupting
    the emulator.
    """

    def __init__(self, controllers: Iterable[Controller | None]) -> None:
        # a lock to safely modify the active controller list from the thread
        self._lock = threading.Lock()
        self._controllers: list[Controller | None] = list(controllers)
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        """Start watching for controller events."""
        self._thread.start()

    def _sync_active_controllers(
        self, snapshot: list[Controller | None], online_controllers: dict[str, str]
    ) -> None:
        """Revive the original controller objects and update the active list.

        Reusing the original objects preserves the player order without
        disrupting the emulator.
        """
        with self._lock:
            new_active: list[Controller | None] = [None] * len(snapshot)

            for index, controller in enumerate(snapshot):
                if controller and controller.guid in online_controllers:
                    new_path = online_controllers[controller.guid]
                    if controller.device_path != new_path:
                        _logger.info(
                            ">>> [Revival] Player %s (GUID: %s) path has changed.",
                            controller.player_number,
                            controller.guid,
                        )
                        controller.device_path = new_path
                    new_active[index] = controller

            current_paths = [c.device_path if c else None for c in self._controllers]
            new_paths = [c.device_path if c else None for c in new_active]

            if current_paths != new_paths:
                _logger.info(
                    ">>> [Check 2] Controller state changed. Old Paths: %s. New Paths: %s",
                    current_paths,
                    new_paths,
                )
                self._controllers = new_active
            else:
                _logger.info(">>> [Check 2] No change in assigned controller paths detected.")

    def _run(self) -> None:
        """Body of the monitor thread."""
        with self._lock:
            snapshot = deepcopy(self._controllers)
            for index, controller in enumerate(snapshot):
                if controller and controller.guid:
                    _logger.info(
                        ">>>   [P%s] Stored GUID: %s, Initial Path: %s",
                        index + 1,
                        controller.guid,
                        controller.device_path,
                    )

        try:
            we_initialized_sdl = _init_sdl_joystick()
        except Exception as err:  # pylint: disable=broad-exception-caught
            # a background thread must log and stop instead of dying with a traceback
            _logger.error("FATAL: Could not initialize pysdl2 for controller monitoring: %s", err)
            return

        monitor = pyudev.Monitor.from_netlink(pyudev.Context())
        monitor.filter_by(subsystem="input")

        _logger.info(">>> Starting background controller monitor.")
        for device in iter(monitor.poll, None):
            if device.properties.get("ID_INPUT_JOYSTICK") != "1":
                continue

            _logger.info(
                "--- Joystick Event Detected: %s on %s ---", device.action, device.sys_path
            )

            online_controllers = _scan_online_controllers()
            _logger.info(
                ">>> [Check 1] Pysdl2 scan found online controllers: %s", online_controllers
            )
            self._sync_active_controllers(snapshot, online_controllers)

        if we_initialized_sdl:
            sdl2.SDL_QuitSubSystem(sdl2.SDL_INIT_JOYSTICK)
