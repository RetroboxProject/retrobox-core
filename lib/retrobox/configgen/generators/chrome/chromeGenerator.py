from __future__ import annotations
import glob
import json
import os
import stat
import tempfile
import uuid
from typing import TYPE_CHECKING

from ...controller import generate_sdl_game_controller_config
from ... import Command
from ..Generator import Generator
from retrobox.paths import RUNTIME_DIR, SAVES

if TYPE_CHECKING:
    from ...typedefs import HotkeysContext

_DDG_SEARCH_DATA = {
    "short_name": "DuckDuckGo",
    "keyword": "duckduckgo.com",
    "url": "https://duckduckgo.com/?q={searchTerms}&t=chromium",
    "suggestions_url": "https://duckduckgo.com/ac/?q={searchTerms}&type=list",
    "favicon_url": "https://duckduckgo.com/favicon.ico",
    "safe_for_autoreplace": True,
    "input_encodings": ["UTF-8"],
    "id": "2",
    "prepopulate_id": 0,
    "is_active": 1,
}

def _seed_profile(user_data_dir: str) -> None:
    """Pre-siembra el perfil ANTES del primer lanzamiento. No pisa un perfil ya existente."""
    default_dir = os.path.join(user_data_dir, "Default")
    prefs_path = os.path.join(default_dir, "Preferences")
    if os.path.isfile(prefs_path):
        return  # perfil ya iniciado alguna vez, no tocar

    os.makedirs(default_dir, exist_ok=True)

    # marcador de "ya hicimos el first run" (además de --no-first-run, redundante a propósito)
    open(os.path.join(user_data_dir, "First Run"), "a").close()

    prefs = {
        "browser": {"check_default_browser": False},
        "signin": {"allowed": False, "allowed_on_next_startup": False},
        "sync_promo": {"show_on_first_run_allowed": False},
        "default_search_provider_data": {
            "template_url_data": _DDG_SEARCH_DATA,
            "synced_guid": str(uuid.uuid4()),
        },
    }
    with open(prefs_path, "w", encoding="utf-8") as fh:
        json.dump(prefs, fh)

def _find_chrome_binary() -> str:
    candidates = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "google-chrome",
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return "google-chrome"

def _make_wrapper(chrome_bin: str, url: str, user_data_dir: str, playersControllers, user_agent: str | None = None) -> str:
    uid = os.getuid()
    wayland = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    display = os.environ.get("DISPLAY", ":0")
    dbus = os.environ.get("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")
    home = os.environ.get("HOME", f"/home/{os.environ.get('USER', 'manuel')}")
    sdlconfig = generate_sdl_game_controller_config(playersControllers)
    sdl_export = f'export SDL_GAMECONTROLLERCONFIG="{sdlconfig}"' if playersControllers else ""
    ua_flag = f'    --user-agent="{user_agent}" \\' if user_agent else ""
    script = f"""#!/usr/bin/env bash
set -uo pipefail
trap 'rm -f "$0"' EXIT

{sdl_export}
export WAYLAND_DISPLAY="{wayland}"
export XDG_RUNTIME_DIR="{xdg_runtime}"
export DISPLAY="{display}"
export DBUS_SESSION_BUS_ADDRESS="{dbus}"
export HOME="{home}"
export GDK_SCALE="1.5"
export QT_SCALE_FACTOR="1.5"

"{chrome_bin}" \\
    --user-data-dir="{user_data_dir}" \\
    --kiosk \\
    --force-device-scale-factor=1.5 \\
    --no-sandbox \\
    --disable-dev-shm-usage \\
    --disable-gpu-shader-disk-cache \\
    --noerrdialogs \\
    --disable-infobars \\
    --disable-session-crashed-bubble \\
    --disable-features=TranslateUI \\
    --disable-sync \\
    --no-first-run \\
    --no-default-browser-check \\{ua_flag}
    "{url}" > /dev/null 2>&1
echo "[chrome-wrapper] Chrome cerrado."
exit 0
"""
    fd, path = tempfile.mkstemp(prefix="chrome_wrapper_", suffix=".sh", dir=RUNTIME_DIR)
    os.write(fd, script.encode())
    os.close(fd)
    os.chmod(path, stat.S_IRWXU)
    return path

class ChromeGenerator(Generator):
    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        for old in glob.glob(str(RUNTIME_DIR / "chrome_wrapper_*.sh")):
            try:
                os.remove(old)
            except OSError:
                pass

        chrome_bin = _find_chrome_binary()
        user_data_dir = os.path.join(system.config.get("saves_dir", str(SAVES)), "chrome")
        _seed_profile(user_data_dir)

        url = "about:blank"
        user_agent = ""
        if rom.name != "Chrome.chrome":
            with rom.open() as f:
                lines = f.read().splitlines()
            if lines:
                url = lines[0].strip()
                user_agent = lines[1].strip() if len(lines) >= 2 and lines[1].strip() else None
        wrapper_path = _make_wrapper(chrome_bin, url, user_data_dir, playersControllers, user_agent)
        return Command.Command(array=[wrapper_path], env={})

    def getMouseMode(self, config, rom):
        return False

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "chrome",
            "keys": {"exit": ["KEY_LEFTALT", "KEY_F4"]},
        }