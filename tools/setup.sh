# shellcheck shell=bash
# Install and remove emulators and bezel packs with their installers:
# tools/emulators/<name>.sh and tools/decorations/<name>.sh, which all take
# -i (install) and -u (uninstall). Sourced by bin/retrobox.
#
#   run_installer <emulators|decorations> <name> <-i|-u>
#   list_installers <emulators|decorations>

SETUP_TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"

# shellcheck source=tools/lib/log.sh
source "${SETUP_TOOLS_DIR}/lib/log.sh"

function run_installer() {
    local kind="$1" name="$2" flag="$3"
    local script="${SETUP_TOOLS_DIR}/${kind}/${name}.sh"
    if [[ ! -f "${script}" ]]; then
        log_err "There is no installer for '${name}' (see: retrobox --install-$(_installer_noun "${kind}"))."
        return 1
    fi
    bash "${script}" "${flag}"
}

function list_installers() {
    local kind="$1" script name
    shopt -s nullglob
    local -a scripts=("${SETUP_TOOLS_DIR}/${kind}"/*.sh)
    shopt -u nullglob
    if [[ ${#scripts[@]} -eq 0 ]]; then
        log_warn "No installers in ${SETUP_TOOLS_DIR}/${kind}/."
        return 0
    fi
    if [[ "${kind}" == "emulators" ]]; then
        echo "Available emulators (how each installs, preferred first):"
    else
        echo "Available bezel packs:"
    fi
    for script in "${scripts[@]}"; do
        name="$(basename "${script}" .sh)"
        if [[ "${kind}" == "emulators" ]]; then
            printf '  %-14s %s\n' "${name}" "$(bash "${script}" -l 2>/dev/null | tr ' ' ',')"
        else
            printf '  %s\n' "${name}"
        fi
    done
}

function _installer_noun() {
    [[ "$1" == "emulators" ]] && echo "emulator" || echo "bezels"
}
