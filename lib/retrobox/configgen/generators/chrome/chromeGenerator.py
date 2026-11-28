from __future__ import annotations
import configparser
import glob
import json
import os
import stat
import tempfile
import uuid

from ...controller import generate_sdl_game_controller_config
from ... import Command
from ..Generator import Generator
from retrobox.paths import EMULATORS_CONFIG, LOGS, RUNTIME_DIR, SAVES


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

def parse_webapp(text: str) -> tuple[str, str | None]:
    """Return ``(url, user_agent)`` from the text of a ``.webapp`` file.

    The format is an INI file::

        [kodi_webapp]
        name=YouTube Music
        url=https://music.youtube.com
        user_agent=Mozilla/5.0 ...

    ``user_agent`` is optional. The older format (URL on the first line,
    optional user agent on the second) is still understood.
    """
    parser = configparser.RawConfigParser(interpolation=None)
    try:
        parser.read_string(text)
    except configparser.Error:
        parser = None
    if parser is not None and parser.has_section("kodi_webapp"):
        section = parser["kodi_webapp"]
        url = section.get("url", "").strip()
        user_agent = section.get("user_agent", "").strip()
        return url or "about:blank", user_agent or None
    lines = text.splitlines()
    if not lines or not lines[0].strip():
        return "about:blank", None
    user_agent = lines[1].strip() if len(lines) >= 2 else ""
    return lines[0].strip(), user_agent or None


def _seed_profile(user_data_dir: str) -> None:
    """Seed the profile BEFORE its first launch. An existing profile is left alone."""
    default_dir = os.path.join(user_data_dir, "Default")
    prefs_path = os.path.join(default_dir, "Preferences")
    if os.path.isfile(prefs_path):
        return  # the profile has run before: leave it

    os.makedirs(default_dir, exist_ok=True)

    # the "first run done" marker (on top of --no-first-run, redundant on purpose)
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

def _record_profile(user_data_dir: str) -> None:
    """Tell ``retrobox-webapp-back`` where the profile is (Chrome's DevTools port is in it)."""
    try:
        (RUNTIME_DIR / "webapp-profile").write_text(user_data_dir, encoding="utf-8")
    except OSError:
        pass  # without it the back button falls back to Alt+Left


def _supports_symlinks(folder: str) -> bool:
    """Tell whether ``folder`` can hold symbolic links (Chrome locks its profile with one)."""
    try:
        os.makedirs(folder, exist_ok=True)
        link = os.path.join(folder, f".symlink-test-{os.getpid()}")
        os.symlink("test", link)
        os.remove(link)
        return True
    except OSError:
        return False


def _profile_dir(saves_dir: str) -> str:
    """Return the Chrome profile folder: in the saves, or in the config if they hold no symlinks.

    The saves can be on a FAT or exFAT card, where Chrome cannot create its
    SingletonLock and stops at once.
    """
    in_saves = os.path.join(saves_dir, "chrome")
    if _supports_symlinks(in_saves):
        return in_saves
    return str(EMULATORS_CONFIG / "chrome")


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
    chrome_log = LOGS / "chrome.log"
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
    --remote-debugging-port=0 \\
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
    "{url}" > "{chrome_log}" 2>&1
status=$?
echo "[chrome-wrapper] Chrome closed with status $status (output: {chrome_log})"
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
        user_data_dir = _profile_dir(system.config.get("saves_dir", str(SAVES)))
        _seed_profile(user_data_dir)
        _record_profile(user_data_dir)

        url, user_agent = "about:blank", None
        if rom.name != "Chrome.chrome":
            url, user_agent = parse_webapp(rom.read_text(encoding="utf-8", errors="replace"))
        wrapper_path = _make_wrapper(chrome_bin, url, user_data_dir, playersControllers, user_agent)
        return Command.Command(array=[wrapper_path], env={})
