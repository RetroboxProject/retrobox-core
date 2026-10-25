from __future__ import annotations

import glob
import locale
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from runtime.launcher.configgen.utils.language import _detect_language

from ... import Command
from ...exceptions import RetroboxException
from ...controller import generate_sdl_game_controller_config
from ..Generator import Generator
from runtime.paths import RUNTIME_DIR

if TYPE_CHECKING:
    from ...batoceraTypes import HotkeysContext

# Constantes de temporización
POLL_INTERVAL   = 3    # segundos entre comprobaciones
LAUNCH_TIMEOUT  = 90   # máximo esperando a que aparezca el .exe
MAX_TOTAL       = 7200 # timeout global de seguridad (2 h)

# Procesos a purgar al salir, por launcher
UBISOFT_PROCS = [
    "UbisoftConnect.exe",
    "UbisoftGameLauncher.exe",
    "upc.exe",
    "UplayWebCore.exe",
]

EA_PROCS = [
    "EADesktop.exe",
    "EABackgroundService.exe",
    "EALauncher.exe",
    "Origin.exe",
    "OriginWebHelperService.exe",
]

# Binarios "wrapper" que NUNCA deben considerarse como el proceso del juego
WRAPPER_BASENAMES = [
    "steam.exe",
]

# Patrones para detectar prefijos de launchers de terceros en el YML de Lutris.
# Si el prefijo del juego coincide con alguno de estos, se activa el wrapper bash.
# Se usan regex case-insensitive para cubrir variaciones de mayúsculas/rutas.
THIRD_PARTY_PREFIX_PATTERNS: list[tuple[re.Pattern[str], list[str]]] = [
    (
        re.compile(r"ubisoft.connect|uplay", re.IGNORECASE),
        UBISOFT_PROCS,
    ),
    (
        re.compile(r"ea.?desktop|origin|ea.?games", re.IGNORECASE),
        EA_PROCS,
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers Python
# ─────────────────────────────────────────────────────────────────────────────

def _get_lutris_info(game_id: str) -> tuple[str, str]:
    """
    Ejecuta 'lutris -l' y extrae (slug, nombre) para el game_id numérico.
    Formato de línea: ID | slug | Nombre del juego | …
    """
    try:
        output = subprocess.check_output(
            ["lutris", "-l"], text=True, stderr=subprocess.DEVNULL
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RetroboxException(f"No se pudo ejecutar 'lutris -l': {e}")

    for line in output.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3 and parts[0] == game_id:
            return parts[2], parts[1]  # (slug, nombre)

    raise RetroboxException(
        f"No se encontró ningún juego con ID {game_id} en 'lutris -l'"
    )


def _parse_lutris_yml(slug: str) -> tuple[str, str]:
    """
    Localiza el YML más reciente para el slug dado y extrae (exe_name, wine_prefix).
    Devuelve (exe_basename, prefix_path).
    """
    conf_dir = Path.home() / ".local/share/lutris/games"
    candidates = sorted(
        conf_dir.glob(f"{slug}*.yml"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RetroboxException(
            f"No se encontró archivo .yml para el slug '{slug}' en {conf_dir}"
        )

    yml_path = candidates[0]
    exe_path = ""
    wine_prefix = ""

    with yml_path.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("  exe: ") and not exe_path:
                exe_path = line.removeprefix("  exe: ").strip()
            if line.startswith("  prefix: ") and not wine_prefix:
                wine_prefix = line.removeprefix("  prefix: ").strip()

    if not exe_path:
        raise RetroboxException(f"No se encontró 'exe:' en {yml_path}")

    exe_name = Path(exe_path).name
    return exe_name, wine_prefix


def _detect_third_party_launcher(wine_prefix: str) -> list[str] | None:
    """
    Comprueba si el wine_prefix del juego corresponde a un launcher de terceros
    (Ubisoft Connect, EA) mediante regex sobre la ruta del prefijo.

    Devuelve la lista de procesos a purgar si hay coincidencia, o None si el
    juego no usa ningún launcher de terceros conocido (Wine manual, nativo, etc.)
    """
    if not wine_prefix:
        return None

    for pattern, procs in THIRD_PARTY_PREFIX_PATTERNS:
        if pattern.search(wine_prefix):
            return procs

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Generador del wrapper bash (solo para launchers de terceros)
# ─────────────────────────────────────────────────────────────────────────────

def _make_wrapper(
    lutris_link: str,
    exe_name: str,
    wine_prefix: str,
    procs_to_purge: list[str],
) -> str:
    """
    Genera un script bash temporal que:
      1. Lanza el juego vía lutris <link> (fire & forget)
      2. Espera hasta LAUNCH_TIMEOUT a que aparezca el .exe del juego
      3. Vigila el .exe hasta que termine
      4. Purga los procesos del launcher (Ubisoft Connect / EA) y el wineserver

    Solo se llama cuando se detecta un prefijo de launcher de terceros.
    Para juegos sin launcher (nativos, Wine manual) se usa lutris directamente.
    """
    purge_lines = "\n".join(
        f'pkill -f "{proc}" 2>/dev/null || true' for proc in procs_to_purge
    )

    wineserver_kill = (
        f'WINEPREFIX="{wine_prefix}" wineserver -k 2>/dev/null || true'
        if wine_prefix
        else "# (sin prefijo Wine detectado)"
    )

    wrapper_excl = "|".join(re.escape(name) for name in WRAPPER_BASENAMES)

    script = f"""\
#!/usr/bin/env bash
set -uo pipefail
trap 'rm -f "$0"' EXIT

EXE_NAME="{exe_name}"
WRAPPER_EXCL_RE="({wrapper_excl})$"
LAUNCH_TIMEOUT={LAUNCH_TIMEOUT}
POLL={POLL_INTERVAL}
MAX_TOTAL={MAX_TOTAL}
START=$(date +%s)

_elapsed() {{ echo $(( $(date +%s) - START )); }}
_timeout()  {{ [ "$(_elapsed)" -ge "$MAX_TOTAL" ]; }}

_game_running() {{
    local proc cmd base
    for proc in /proc/[0-9]*/cmdline; do
        [ -r "$proc" ] || continue
        cmd=$( {{ tr '\\0' '\\n' < "$proc" 2>/dev/null || true; }} 2>/dev/null | head -n1)
        [ -z "$cmd" ] && continue
        base="${{cmd##*[\\\\/]}}"
        if [[ "$base" =~ $WRAPPER_EXCL_RE ]]; then
            continue
        fi
        if [[ "$cmd" =~ ^[A-Za-z]:.*"$EXE_NAME"$ ]]; then
            return 0
        fi
    done
    return 1
}}

# 1. Lanzar el juego via Lutris (fire & forget)
echo "[lutris-wrapper] Lanzando: lutris {lutris_link}"
lutris "{lutris_link}" > /dev/null 2>&1 &

# 2. Esperar a que aparezca el .exe del juego
echo "[lutris-wrapper] Esperando a que '$EXE_NAME' arranque..."
APPEARED=0
DEADLINE=$(( START + LAUNCH_TIMEOUT ))
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    if _game_running; then
        APPEARED=1
        break
    fi
    sleep "$POLL"
done

if [ "$APPEARED" -eq 0 ]; then
    echo "[lutris-wrapper] Timeout: '$EXE_NAME' no detectado tras ${{LAUNCH_TIMEOUT}}s."
    exit 1
fi

echo "[lutris-wrapper] '$EXE_NAME' detectado. Monitorizando..."

# 3. Vigilar hasta que el juego cierre
while true; do
    _timeout && echo "[lutris-wrapper] Timeout global alcanzado, saliendo." && exit 0

    if ! _game_running; then
        sleep 5
        if ! _game_running; then
            echo "[lutris-wrapper] '$EXE_NAME' ha terminado."
            break
        fi
        echo "[lutris-wrapper] Falsa alarma, '$EXE_NAME' sigue corriendo."
    fi

    sleep "$POLL"
done

# 4. Purga del launcher de terceros
echo "[lutris-wrapper] Purgando procesos del launcher..."
{purge_lines}

echo "[lutris-wrapper] Matando wineserver del prefijo..."
{wineserver_kill}

echo "[lutris-wrapper] Limpieza completada."
exit 0
"""

    fd, path = tempfile.mkstemp(prefix="lutris_wrapper_", suffix=".sh", dir=RUNTIME_DIR)
    os.write(fd, script.encode())
    os.close(fd)
    os.chmod(path, stat.S_IRWXU)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Generador
# ─────────────────────────────────────────────────────────────────────────────

class LutrisGenerator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "wine",
            "keys": {"exit": ["KEY_LEFTALT", "KEY_F4"]},
        }

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        # Limpiar wrappers anteriores huérfanos
        for old in glob.glob(str(RUNTIME_DIR / "lutris_wrapper_*.sh")):
            try:
                os.remove(old)
            except OSError:
                pass

        # Leer el enlace del .rom
        try:
            with open(rom, "r", encoding="utf-8") as f:
                lutris_link = f.read().strip()
        except OSError as e:
            raise RetroboxException(f"No se pudo leer el archivo .rom: {e}")

        if not lutris_link.startswith("lutris:rungameid/"):
            raise RetroboxException(
                f"Formato de enlace no reconocido: '{lutris_link}'"
            )

        game_id = lutris_link.removeprefix("lutris:rungameid/")

        # Resolver ID → (slug, nombre) → YML → exe + prefix
        slug, _game_name      = _get_lutris_info(game_id)
        exe_name, wine_prefix = _parse_lutris_yml(slug)

        # Entorno común
        lang = _detect_language()
        environment: dict[str, str] = {
            "LANG":   f"{lang}.UTF-8",
            "LC_ALL": f"{lang}.UTF-8",
        }

        if system.config.get_bool("sdl_config", True):
            environment.update({
                "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(playersControllers),
                "SDL_JOYSTICK_HIDAPI": "0",
            })

        # ── Decisión: ¿necesitamos wrapper o lutris directo? ──────────────────
        procs_to_purge = _detect_third_party_launcher(wine_prefix)

        if procs_to_purge is not None:
            # Juego con launcher de terceros (Ubisoft Connect, EA):
            # necesitamos el wrapper para detectar el fin del juego y purgar
            wrapper_path = _make_wrapper(lutris_link, exe_name, wine_prefix, procs_to_purge)
            return Command.Command(array=[wrapper_path], env=environment)
        else:
            # Juego nativo Linux, Wine sin launcher, instalación manual, etc.:
            # lutris se encarga solo de la espera y la vuelta a EmulationStation
            return Command.Command(
                array=["lutris", lutris_link],
                env=environment,
            )

    def getMouseMode(self, config, rom):
        return config.get_bool("force_mouse")