from __future__ import annotations
import glob
import os
import sys
import subprocess
import time
import tempfile
import stat
from pathlib import Path
from typing import TYPE_CHECKING
from ... import Command
from ..Generator import Generator
from runtime.paths import RUNTIME_DIR

if TYPE_CHECKING:
    from ...batoceraTypes import HotkeysContext

POLL_INTERVAL = 4
LAUNCH_TIMEOUT = 300  # segundos esperando a que aparezca el reaper / Steam

BIGPICTURE_ROM_NAME = "steam.steam"
BIGPICTURE_ROM_CONTENT = "steam"


def _find_steam_binary() -> str:
    candidates = [
        "/usr/bin/steam",
        "/usr/local/bin/steam",
        str(Path.home() / ".local/bin/steam"),
        "steam",
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return "steam"


def _is_bigpicture_rom(rom) -> bool:
    """
    rom "steam.webapp" cuyo único contenido (tras strip) es la palabra "steam"
    -> lanzar Steam en modo Big Picture en vez de un applaunch de un juego concreto.
    """
    if rom.name.lower() != BIGPICTURE_ROM_NAME:
        return False
    try:
        with rom.open() as f:
            content = f.read().strip()
    except OSError:
        return False
    return content == BIGPICTURE_ROM_CONTENT

def _make_wrapper(steam_bin: str, app_id: str | None, big_picture: bool = False, close_launcher: bool = True) -> str:
    MAX_TOTAL = 7200  # 2h timeout global de seguridad
    close_launcher_str = "true" if close_launcher else "false"

    # Plazos del detector de shaders
    FIRST_DETECT_TIMEOUT = 180   # 3 min: primera espera a que aparezca el juego
    REDETECT_TIMEOUT = 60        # 1 min: reintento tras un cierre sospechoso
    SHADER_GRACE = 45            # <45s de "vida" tras detectar => probablemente shaders
    MAX_DETECT_ATTEMPTS = 2      # 1 detección inicial + 1 reintento

    if big_picture:
        # Big Picture: no hay AppId que vigilar, ni tiene sentido pollear
        # RunningAppID/procesos de juego concretos. Solo esperamos a que
        # Steam arranque y luego a que el propio Steam se cierre.
        launch_cmd = f'"{steam_bin}" -bigpicture -gamepadui > /dev/null 2>&1 &'
        monitor = f"""\
POLL={POLL_INTERVAL}
MAX_TOTAL={MAX_TOTAL}
LAUNCH_TIMEOUT={LAUNCH_TIMEOUT}

echo "[steam-wrapper] Esperando arranque de Steam (Big Picture)..."
START=$(date +%s)
_elapsed() {{ echo $(( $(date +%s) - START )); }}

DEADLINE=$(( START + LAUNCH_TIMEOUT ))
APPEARED=0
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    if pgrep -x steam > /dev/null 2>&1; then
        APPEARED=1
        break
    fi
    sleep "$POLL"
done

if [ "$APPEARED" -eq 0 ]; then
    echo "[steam-wrapper] Steam no arrancó tras ${{LAUNCH_TIMEOUT}}s, saliendo."
    exit 0
fi

echo "[steam-wrapper] Steam detectado, esperando a que se cierre (sin vigilar juegos)..."

while true; do
    if [ "$(_elapsed)" -ge "$MAX_TOTAL" ]; then
        echo "[steam-wrapper] Timeout global, saliendo."
        exit 0
    fi
    if ! pgrep -x steam > /dev/null 2>&1; then
        echo "[steam-wrapper] Steam se ha cerrado."
        exit 0
    fi
    sleep "$POLL"
done
"""
    else:
        launch_cmd = ""
        monitor = ""
        if app_id:
            launch_cmd = f'"{steam_bin}" -silent -applaunch {app_id} > /dev/null 2>&1 &'
            monitor = f"""\
APPID="{app_id}"
POLL={POLL_INTERVAL}
MAX_TOTAL={MAX_TOTAL}
FIRST_DETECT_TIMEOUT={FIRST_DETECT_TIMEOUT}
REDETECT_TIMEOUT={REDETECT_TIMEOUT}
SHADER_GRACE={SHADER_GRACE}
MAX_DETECT_ATTEMPTS={MAX_DETECT_ATTEMPTS}
STEAM_BIN="{steam_bin}"
CLOSE_LAUNCHER="{close_launcher_str}"

REG="$HOME/.steam/registry.vdf"
[ -f "$REG" ] || REG="$HOME/.local/share/Steam/registry.vdf"

_running_appid() {{
    [ -f "$REG" ] || return 1
    awk -F'"' '/"RunningAppID"/ {{ print $4; exit }}' "$REG"
}}

_appid_is_running() {{
    RID="$(_running_appid)"
    if [ -n "$RID" ]; then
        [ "$RID" = "$APPID" ]
        return $?
    fi
    # fallback si no hay registry.vdf legible
    pgrep -f "SteamLaunch AppId=$APPID" > /dev/null 2>&1
}}

_close_launcher_if_needed() {{
    if [ "$CLOSE_LAUNCHER" = "true" ]; then
        echo "[steam-wrapper] Cerrando Steam (close_game_launcher=true)..."
        "$STEAM_BIN" -shutdown > /dev/null 2>&1 &
    fi
}}

START=$(date +%s)
_elapsed_total() {{ echo $(( $(date +%s) - START )); }}

# Espera a que aparezca el juego (con timeout dado). Devuelve 0 si aparece, 1 si no.
_wait_appear() {{
    TIMEOUT="$1"
    DEADLINE=$(( $(date +%s) + TIMEOUT ))
    while [ "$(date +%s)" -lt "$DEADLINE" ]; do
        if [ "$(_elapsed_total)" -ge "$MAX_TOTAL" ]; then
            return 1
        fi
        if _appid_is_running; then
            return 0
        fi
        sleep "$POLL"
    done
    return 1
}}

ATTEMPT=1
while [ "$ATTEMPT" -le "$MAX_DETECT_ATTEMPTS" ]; do

    if [ "$ATTEMPT" -eq 1 ]; then
        echo "[steam-wrapper] Esperando arranque del juego (AppId=$APPID)..."
        _wait_appear "$FIRST_DETECT_TIMEOUT"
    else
        echo "[steam-wrapper] Cierre sospechoso (posibles shaders), reintentando detección (intento $ATTEMPT/$MAX_DETECT_ATTEMPTS)..."
        _wait_appear "$REDETECT_TIMEOUT"
    fi

    if [ "$?" -ne 0 ]; then
        echo "[steam-wrapper] Juego no detectado, saliendo."
        exit 0
    fi

    DETECT_TS=$(date +%s)
    echo "[steam-wrapper] Juego detectado, monitorizando cierre..."

    # Esperar a que el AppId deje de estar activo
    while _appid_is_running; do
        if [ "$(_elapsed_total)" -ge "$MAX_TOTAL" ]; then
            echo "[steam-wrapper] Timeout global, saliendo."
            _close_launcher_if_needed
            exit 0
        fi
        sleep "$POLL"
    done

    LIVED=$(( $(date +%s) - DETECT_TS ))
    echo "[steam-wrapper] AppId=$APPID dejó de detectarse tras ${{LIVED}}s."

    if [ "$LIVED" -lt "$SHADER_GRACE" ] && [ "$ATTEMPT" -lt "$MAX_DETECT_ATTEMPTS" ]; then
        # Cierre demasiado rápido: probablemente compilación de shaders. Reintentar.
        ATTEMPT=$(( ATTEMPT + 1 ))
        continue
    fi

    if [ "$LIVED" -lt "$SHADER_GRACE" ]; then
        echo "[steam-wrapper] Segundo cierre rápido (${{LIVED}}s), se asume fallo de arranque o shaders bloqueados."
    else
        echo "[steam-wrapper] Juego AppId=$APPID terminado normalmente."
    fi

    _close_launcher_if_needed
    exit 0
done
"""

    script = f"""#!/usr/bin/env bash
set -uo pipefail
trap 'rm -f "$0"' EXIT
echo "[steam-wrapper] Lanzando Steam..."
{launch_cmd}
{monitor}
exit 0
"""
    fd, path = tempfile.mkstemp(prefix="steam_wrapper_", suffix=".sh", dir=RUNTIME_DIR)
    os.write(fd, script.encode())
    os.close(fd)
    os.chmod(path, stat.S_IRWXU)
    return path

class SteamGenerator(Generator):

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        for old in glob.glob(str(RUNTIME_DIR / "steam_wrapper_*.sh")):
            try:
                os.remove(old)
            except OSError:
                pass

        steam_bin = _find_steam_binary()
        app_id: str | None = None
        big_picture = _is_bigpicture_rom(rom)

        if not big_picture:
            with rom.open() as f:
                first_line = f.readline().strip()
            # first_line: "steam://rungameid/24780"
            if first_line.startswith("steam://rungameid/"):
                app_id = first_line.removeprefix("steam://rungameid/")

        close_launcher = system.config.get_bool(
            "close_game_launcher", False, return_values=(True, False)
        )

        wrapper_path = _make_wrapper(
            steam_bin, app_id, big_picture=big_picture, close_launcher=close_launcher
        )

        #env = {"SDL_JOYSTICK_HIDAPI_XBOX": "0"}
        env = {}
        # runCommand hará Popen([wrapper_path]) + communicate() → bloqueante
        return Command.Command(array=[wrapper_path], env=env)

    def getMouseMode(self, config, rom):
        return True

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "steam",
            "keys": {"exit": ["KEY_LEFTALT", "KEY_F4"]},
        }