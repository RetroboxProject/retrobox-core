from __future__ import annotations
import os
from pathlib import Path
from typing import TYPE_CHECKING

from ...controller import generate_sdl_game_controller_config
from ... import Command
from ..Generator import Generator

if TYPE_CHECKING:
    from ...typedefs import HotkeysContext

def _parse_rom_launcher(lines: list[str]) -> tuple[str, str | None]:
    """Soporta tanto el formato legacy (url en línea 1, user-agent opcional
    en línea 2) como el formato ludex ([ludex-element] con run=/user-agent=)."""
    if not lines:
        return "about:blank", None

    kv: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith(("[", "#", ";")):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            kv[key.strip().lower()] = value.strip()

    if "run" in kv:
        url = kv.get("run") or "about:blank"
        user_agent = kv.get("user-agent") or kv.get("user_agent") or None
        return url, user_agent

    url = lines[0].strip() if lines[0].strip() else "about:blank"
    user_agent = lines[1].strip() if len(lines) >= 2 and lines[1].strip() else None
    return url, user_agent

def _find_firefox_binary() -> str:
    candidates = [
        "/usr/bin/firefox",
        "/usr/bin/firefox-esr",
        "/usr/local/bin/firefox",
        "firefox",
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return "firefox"


class FirefoxGenerator(Generator):

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        firefox_bin = _find_firefox_binary()
        url = "about:blank"
        user_agent = None
        if rom.name != "Firefox.firefox":
            with rom.open() as f:
                lines = f.read().splitlines()
            url, user_agent = _parse_rom_launcher(lines)

        command_array = [
            firefox_bin,
            "--kiosk",
            "--no-remote",
            *(["--override-user-agent", user_agent] if user_agent else []),
            url,
        ]
        env = {
            "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(playersControllers),
            "GDK_SCALE": "1.5",
            "QT_SCALE_FACTOR": "1.5",
            "MOZ_ENABLE_WAYLAND": os.environ.get("MOZ_ENABLE_WAYLAND", "1"),
            "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY", "wayland-0"),
            "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
            "DISPLAY": os.environ.get("DISPLAY", ":0"),
            "DBUS_SESSION_BUS_ADDRESS": os.environ.get("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{os.getuid()}/bus"),
            "HOME": os.environ.get("HOME", str(Path.home())),
        }

        return Command.Command(array=command_array, env=env)

    def getMouseMode(self, config, rom):
        return False

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "firefox",
            "keys": {"exit": ["KEY_LEFTALT", "KEY_F4"]},
        }