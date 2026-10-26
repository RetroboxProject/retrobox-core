# Retrobox directories for bash scripts.
#
# Source this file, don't execute it:
#   source "<root>tools/lib/paths.sh"
#
# It exports the RETROBOX_* variables (RETROBOX_ROOTDIR, RETROBOX_DATADIR,
# RETROBOX_ROMS_DIR, ...; see lib/retrobox/paths/_env.py for the full list) by
# asking retrobox.paths, which owns every location. There is deliberately no
# second copy of the resolution logic here.
#
# If the variables are already in the environment (the launcher and
# retrobox export them to everything they start) nothing is run.
# RETROBOX_PYTHON selects the interpreter (default: python3 on PATH).
# Safe under `set -eu`. Returns 1 with a message when python3 is missing.

_retrobox_paths_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." >/dev/null 2>&1 && pwd -P)"

if [[ -z "${RETROBOX_DATADIR:-}" || -z "${RETROBOX_BIOS_DIR:-}" || -z "${RETROBOX_INI:-}" ]]; then
    # RETROBOX_PYTHON: set by retrobox (the install's own venv, if any).
    : "${RETROBOX_PYTHON:=$(command -v python3 || true)}"
    if [[ -z "${RETROBOX_PYTHON}" ]]; then
        echo "ERROR: python3 is required to locate Retrobox's directories." >&2
        unset _retrobox_paths_root
        return 1
    fi
    _retrobox_paths_env="$(PYTHONPATH="${_retrobox_paths_root}/lib${PYTHONPATH:+:${PYTHONPATH}}" "${RETROBOX_PYTHON}" -W ignore -m retrobox.paths --shell)" || {
        echo "ERROR: could not resolve Retrobox's directories (python3 -m retrobox.paths)." >&2
        unset _retrobox_paths_root _retrobox_paths_env
        return 1
    }
    eval "${_retrobox_paths_env}"
    unset _retrobox_paths_env
fi
unset _retrobox_paths_root
