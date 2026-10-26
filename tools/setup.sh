#!/usr/bin/env bash
# Retrobox setup orchestrator.
# Meant to be sourced by retrobox (not executed directly), which is why
# there's no shebang and no `set -euo pipefail` here: those would leak into
# whatever sources this file. Callers are expected to check return codes.
# Exposes:
# full_setup                 -> runs platform setup + git submodules (only
#                               needed for a git checkout: packages and
#                               install.sh bring their own dependencies)
# setup_emulator <name>      -> builds tools/emulators/<name>.sh from
#                               source, auto-detecting which flag it wants
# list_available_emulators   -> prints every tools/emulators/*.sh found,
#                               with the flag each would be called with
# setup_util <name>          -> runs tools/utils/<name>.sh, auto-detecting
#                               which flag it wants (same convention as
#                               setup_emulator)
# list_available_utils       -> prints every tools/utils/*.sh found, with
#                               the flag each would be called with
# setup_music <name>         -> runs tools/music/<name>.sh, auto-detecting
#                               which flag it wants (same convention as
#                               setup_emulator)
# list_available_music       -> prints every tools/music/*.sh found, with
#                               the flag each would be called with
# setup_bezeles <name>         -> runs tools/decorations/<name>.sh, auto-detecting
#                                which flag it wants (same convention as
#                                setup_emulator)
# list_available_bezels        -> prints every tools/decorations/*.sh found, with
#                                the flag each would be called with

TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
RETROBOX_ROOTDIR="$(cd "${TOOLS_DIR}/.." >/dev/null 2>&1 && pwd -P)"

# shellcheck source=lib/log.sh
source "${TOOLS_DIR}/lib/log.sh"

# ---------------------------------------------------------------------------
# Flag detection.
# No per-emulator table to keep in sync: each installer's accepted flags are
# read straight from its own `case "$1" in ... esac` dispatch block.
# We use a simple POSIX ERE grep to extract flags like "-i", '"-u"', etc.
# This is far more robust than PCRE lookarounds across different OS/grep versions.
# ---------------------------------------------------------------------------
readonly -a _SOURCE_BUILD_FLAG_PRIORITY=("-s" "-c")
readonly -a _INSTALL_FALLBACK_FLAG_PRIORITY=("-i" "-a" "-b")

function _installer_flags() {
    local script="$1"
    # Extract the case block, then find any quoted or unquoted single-letter flag
    sed -n -E '/case[[:space:]]+"?\$1"?[[:space:]]+in/,/esac/p' "${script}" \
    | grep -oE '"?-[a-zA-Z]"?' \
    | tr -d '"' \
    | sort -u
}

function _pick_flag() {
    local script="$1"
    shift
    local -a available
    mapfile -t available < <(_installer_flags "${script}")
    local candidate
    for candidate in "$@"; do
        local a
        for a in "${available[@]}"; do
            [[ "${a}" == "${candidate}" ]] && { echo "${candidate}"; return 0; }
        done
    done
    return 1
}

function _source_build_flag() {
    local script="$1"
    _pick_flag "${script}" "${_SOURCE_BUILD_FLAG_PRIORITY[@]}" || echo "none"
}

function _fallback_install_flag() {
    local script="$1"
    local flag
    if flag="$(_pick_flag "${script}" "${_INSTALL_FALLBACK_FLAG_PRIORITY[@]}")"; then
        echo "${flag}"
        return 0
    fi
    local a
    while IFS= read -r a; do
        [[ "${a}" == "-u" || "${a}" == "-d" ]] && continue
        echo "${a}"
        return 0
    done < <(_installer_flags "${script}")
    return 1
}

function detect_distro_family() {
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        source /etc/os-release
        local ids="${ID:-} ${ID_LIKE:-}"
        if grep -qiE '(^|[[:space:]])fedora([[:space:]]|$)' <<<"${ids}"; then
             echo "fedora"
             return
         fi
         if grep -qiE '(^|[[:space:]])debian([[:space:]]|$)' <<<"${ids}"; then
             echo "debian"
             return
         fi
     fi
     if command -v dnf &>/dev/null; then
         echo "fedora"
     elif command -v apt-get &>/dev/null; then
         echo "debian"
     else
         echo "unknown"
     fi
}

function init_submodules() {
    if [[ ! -f "${RETROBOX_ROOTDIR}/.gitmodules" ]]; then
        log_info "No .gitmodules found, skipping git submodule init."
        return 0
    fi
    if ! command -v git &>/dev/null; then
        log_warn "git not found on PATH, cannot initialize submodules."
        return 0
    fi
    log_info "Initializing git submodules..."
    if (cd "${RETROBOX_ROOTDIR}" && git submodule update --init --recursive); then
        log_ok "Git submodules ready."
    else
        log_err "Failed to initialize git submodules."
        return 1
    fi
}

function run_platform_setup() {
    local family="$1"
    case "${family}" in
        debian)
            log_info "Detected a Debian-based system."
            bash "${TOOLS_DIR}/setup-debian.sh"
            ;;
        fedora)
            log_info "Detected a Fedora-based system."
            bash "${TOOLS_DIR}/setup-fedora.sh"
            ;;
        *)
            log_err "Could not detect a supported distro family (Debian- or Fedora-based). Skipping platform setup."
            log_warn "You can still install individual emulators with: retrobox --setup-emulator <name>"
            return 1
            ;;
    esac
}

function _run_installer() {
    local kind="$1" script="$2" name="$3"
    local flag
    flag="$(_source_build_flag "${script}")"
    if [[ "${flag}" == "none" ]]; then
        local fallback
        if ! fallback="$(_fallback_install_flag "${script}")"; then
            log_err "Could not find any usable flag for '${name}' (checked its case \"\$1\" dispatch)."
            return 1
        fi
        log_warn "'${name}' has no source-build option in its installer, falling back to ${fallback} (prebuilt/AppImage)."
        flag="${fallback}"
    fi
    log_info "Running ${kind} installer for '${name}' (${flag})..."
    if bash "${script}" "${flag}"; then
        log_ok "'${name}' installed."
    else
        log_err "Installer for '${name}' failed."
        return 1
    fi
}

function setup_emulator() {
    local name="$1"
    local script="${TOOLS_DIR}/emulators/${name}.sh"
    if [[ ! -f "${script}" ]]; then
        log_err "No installer found for emulator '${name}' (expected ${script})."
        return 1
    fi
    _run_installer "emulator" "${script}" "${name}"
}

function setup_util() {
    local name="$1"
    local script="${TOOLS_DIR}/utils/${name}.sh"
    if [[ ! -f "${script}" ]]; then
        log_err "No installer found for utility '${name}' (expected ${script})."
        return 1
    fi
    _run_installer "utility" "${script}" "${name}"
}

function setup_music() {
    local name="$1"
    local script="${TOOLS_DIR}/music/${name}.sh"
    if [[ ! -f "${script}" ]]; then
        log_err "No installer found for music pack '${name}' (expected ${script})."
        return 1
    fi
    _run_installer "music" "${script}" "${name}"
}

function setup_bezeles() {
    local name="$1"
    local script="${TOOLS_DIR}/decorations/${name}.sh"
    if [[ ! -f "${script}" ]]; then
        log_err "No installer found for bezel pack '${name}' (expected ${script})."
        return 1
    fi
    _run_installer "bezel" "${script}" "${name}"
}

function _list_available_installers() {
    local dir="$1" label="$2"
    shopt -s nullglob
    local -a scripts=("${dir}"/*.sh)
    shopt -u nullglob
    if [[ "${#scripts[@]}" -eq 0 ]]; then
        log_warn "No ${label} installers found in ${dir}/."
        return 0
    fi
    log_info "Available ${label} installers:"
    local f name flag
    for f in "${scripts[@]}"; do
        name="$(basename "${f}" .sh)"
        flag="$(_source_build_flag "${f}")"
        if [[ "${flag}" == "none" ]]; then
            flag="$(_fallback_install_flag "${f}")" || flag="?"
            printf '  - %-14s (no source build; installs with %s)\n' "${name}" "${flag}"
        else
            printf '  - %-14s (source build: %s)\n' "${name}" "${flag}"
        fi
    done
}

function list_available_emulators() {
    _list_available_installers "${TOOLS_DIR}/emulators" "emulator"
}

function list_available_utils() {
    _list_available_installers "${TOOLS_DIR}/utils" "utility"
}

function list_available_music() {
    _list_available_installers "${TOOLS_DIR}/music" "music"
}

function list_available_bezels() {
    _list_available_installers "${TOOLS_DIR}/decorations" "bezel"
}

function full_setup() {
    local family status=0
    family="$(detect_distro_family)"
    run_platform_setup "${family}" || status=1
    init_submodules || status=1
    if [[ "${status}" -eq 0 ]]; then
        log_ok "Retrobox setup complete."
    else
        log_err "Retrobox setup finished with errors."
    fi
    return "${status}"
}
