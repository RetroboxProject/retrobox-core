#!/usr/bin/env bash
# Retrobox entrypoint.
#
# On a normal launch it checks that the essentials are in place (warning,
# never stopping, if something is missing) and starts the frontend. The
# install itself is read-only: nothing is written next to this script.
#
#   retrobox.sh --setup                     install the system dependencies
#                                            (git checkouts only; packages and
#                                            install.sh already bring them)
#   retrobox.sh --setup-emulator <name>      build a single emulator from
#                                            source (repeatable)
#   retrobox.sh --setup-emulator             list available emulators
#   retrobox.sh --setup-util <name>          run a single utility installer
#                                            (e.g. mangohud) (repeatable)
#   retrobox.sh --setup-util                 list available utility installers
#   retrobox.sh --setup-music <name>         install a single music pack
#                                            (e.g. music-pack-2). Can be
#                                            repeated. Called with no name,
#                                            lists every installer available
#                                            under setup/music/.
#   retrobox.sh --setup-bezel <name>         install a bezel/decoration pack
#   retrobox.sh --version                    print the installed version
#
# All of the above are maintenance operations: they run and then exit,
# they don't start the frontend afterwards. Any other argument is passed
# through to runtime/startup/retrobox_run.py untouched — this includes
# --pcgames-sync, which is not handled here but recognized by
# retrobox_run.py itself: it enables syncing installed PC games (Steam,
# Lutris, Heroic) before starting the frontend, and is stripped before the
# remaining arguments reach EmulationStation. Without it, the sync is
# skipped.
set -eo pipefail
# readlink -f (not just dirname) so this also works when invoked through a
# symlink such as /usr/bin/retrobox -> /opt/retrobox/retrobox.sh.
RETROBOX_SELF="$(readlink -f "${BASH_SOURCE[0]}")"
RETROBOX_ROOTDIR="$(dirname "${RETROBOX_SELF}")"
SETUP_DIR="${RETROBOX_ROOTDIR}/setup"
RUN_SCRIPT="${RETROBOX_ROOTDIR}/runtime/startup/retrobox_run.py"

# Interpreter: the install's own virtualenv when there is one (install.sh on
# systems where the distro packages can't be used), else the system python3.
if [[ -x "${RETROBOX_ROOTDIR}/venv/bin/python3" ]]; then
    RETROBOX_PYTHON="${RETROBOX_ROOTDIR}/venv/bin/python3"
else
    RETROBOX_PYTHON="$(command -v python3 || true)"
fi
export RETROBOX_PYTHON

# shellcheck source=setup/lib/paths.sh
source "${SETUP_DIR}/lib/paths.sh"
# shellcheck source=setup/setup.sh
source "${SETUP_DIR}/setup.sh"

function retrobox_version() {
    if [[ -r "${RETROBOX_ROOTDIR}/VERSION" ]]; then
        head -n1 "${RETROBOX_ROOTDIR}/VERSION"
    elif git -C "${RETROBOX_ROOTDIR}" describe --tags --always --dirty 2>/dev/null; then
        :
    else
        echo "unknown"
    fi
}

# Warn (never abort) about what is missing, so a half-installed system says
# so up front instead of failing deep inside the launcher.
function preflight() {
    if [[ -z "${RETROBOX_PYTHON}" ]]; then
        log_err "python3 not found. Install it with your package manager."
        exit 1
    fi
    if [[ ! -x "${RETROBOX_ES_EXECUTABLE}" ]]; then
        log_warn "EmulationStation not found at ${RETROBOX_ES_EXECUTABLE}."
        log_warn "Install the retrobox-emulationstation package (or, from a checkout: sudo retrobox --setup-util emulationstation)."
    fi
    local missing
    missing="$("${RETROBOX_PYTHON}" -W ignore -c '
import importlib.util as u
mods = ["yaml", "evdev", "pyudev", "sdl2", "PIL", "ruamel.yaml"]
print(" ".join(m for m in mods if u.find_spec(m) is None))' 2>/dev/null || true)"
    if [[ -n "${missing}" ]]; then
        log_warn "Missing Python modules: ${missing}. Install the dependencies (see README) or re-run install.sh."
    fi
}

function usage() {
cat <<EOF
Usage: $(basename "${BASH_SOURCE[0]}") [OPTIONS] [-- ARGS...]
--setup                     Install the system dependencies, udev rules
                            and git submodules. Only for a git checkout:
                            the .deb and install.sh do this themselves.
--setup-emulator <name>     Build/install a single emulator from source
                            (e.g. --setup-emulator retroarch). Can be
                            repeated to install several at once. Called
                            with no name, lists every installer available
                            under setup/emulators/.
--setup-util <name>         Run a single utility installer (e.g.
                            --setup-util mangohud). Can be repeated to
                            install several at once. Called with no name,
                            lists every installer available under
                            setup/utils/.
--setup-music <name>        Install a single music pack (e.g.
                            --setup-music music-pack-2). Can be
                            repeated to install several at once. Called
                            with no name, lists every installer available
                            under setup/music/.
--setup-bezel <name>        Install a single bezel/decoration pack (e.g.
                            --setup-bezel switch-online). Can be
                            repeated to install several at once. Called
                            with no name, lists every installer available
                            under setup/decorations/.
--version                   Print the installed version and exit.
-h, --help                  Show this help and exit.

Anything else is forwarded as-is to runtime/startup/retrobox_run.py,
which in turn passes it to the frontend (EmulationStation) — with one
exception:

--pcgames-sync              Sync installed PC games (Steam, Lutris,
                            Heroic) into their EmulationStation ROM
                            directories before starting the frontend.
                            Without it, the sync is skipped. Handled by
                            retrobox_run.py, not forwarded to
                            EmulationStation.

With no options, Retrobox runs the platform setup automatically the first
time (and only the first time) it's launched, then starts the frontend.
EOF
}

force_setup=0
declare -a emulators_to_setup=()
declare -a utils_to_setup=()
declare -a music_to_setup=()
declare -a bezels_to_setup=()
declare -a frontend_args=()

while [[ $# -gt 0 ]]; do
case "$1" in
--setup)
    force_setup=1
    shift
    ;;
--setup-emulator)
    if [[ -z "${2:-}" || "${2:0:1}" == "-" ]]; then
        list_available_emulators
        exit 0
    fi
    emulators_to_setup+=("$2")
    shift 2
    ;;
--setup-util)
    if [[ -z "${2:-}" || "${2:0:1}" == "-" ]]; then
        list_available_utils
        exit 0
    fi
    utils_to_setup+=("$2")
    shift 2
    ;;
--setup-music)
    if [[ -z "${2:-}" || "${2:0:1}" == "-" ]]; then
        list_available_music
        exit 0
    fi
    music_to_setup+=("$2")
    shift 2
    ;;
--setup-bezel)
    if [[ -z "${2:-}" || "${2:0:1}" == "-" ]]; then
        list_available_bezels
        exit 0
    fi
    bezels_to_setup+=("$2")
    shift 2
    ;;
--version)
    retrobox_version
    exit 0
    ;;
-h | --help)
    usage
    exit 0
    ;;
--)
    shift
    frontend_args+=("$@")
    break
    ;;
*)
    frontend_args+=("$1")
    shift
    ;;
esac
done

did_maintenance=0

if [[ "${force_setup}" -eq 1 ]]; then
    log_info "Forcing platform setup..."
    full_setup
    did_maintenance=1
fi

if [[ "${#emulators_to_setup[@]}" -gt 0 ]]; then
    status=0
    for name in "${emulators_to_setup[@]}"; do
        setup_emulator "${name}" || status=1
    done
    did_maintenance=1
    [[ "${status}" -eq 0 ]] || exit "${status}"
fi

if [[ "${#utils_to_setup[@]}" -gt 0 ]]; then
    status=0
    for name in "${utils_to_setup[@]}"; do
        setup_util "${name}" || status=1
    done
    did_maintenance=1
    [[ "${status}" -eq 0 ]] || exit "${status}"
fi

if [[ "${#music_to_setup[@]}" -gt 0 ]]; then
    status=0
    for name in "${music_to_setup[@]}"; do
        setup_music "${name}" || status=1
    done
    did_maintenance=1
    [[ "${status}" -eq 0 ]] || exit "${status}"
fi

if [[ "${#bezels_to_setup[@]}" -gt 0 ]]; then
    status=0
    for name in "${bezels_to_setup[@]}"; do
        setup_bezeles "${name}" || status=1
    done
    did_maintenance=1
    [[ "${status}" -eq 0 ]] || exit "${status}"
fi

if [[ "${did_maintenance}" -eq 1 ]]; then
    exit 0
fi

preflight

exec "${RETROBOX_PYTHON}" "${RUN_SCRIPT}" "${frontend_args[@]}"
