# shellcheck shell=bash
# Shared code of the emulator installers (tools/emulators/<name>.sh).
#
# An installer sets who it installs, defines the install methods it has and
# hands over to installer_main:
#
#   EMULATOR="dolphin-emu"      its folder: <emulators>/dolphin-emu
#   LABEL="Dolphin"             its name in messages
#   source "<root>/tools/lib/installer.sh"
#   install_appimage() { ...; }   the release AppImage, extracted
#   install_archive()  { ...; }   a prebuilt release archive (tarball, zip)
#   install_source()   { ...; }   a build from source
#   installer_main "$@"
#
# Options (the same for every installer):
#   -i   install with the best method this machine can use, in this order:
#        the extracted AppImage, the release archive, the source build
#   -a   only the AppImage        -t   only the archive        -s   only the source build
#   -u   uninstall: the program goes, the configuration and saves stay
#   -l   print the methods the installer has, in that order
#
# A method installs into ${STAGE} (an empty folder) and returns. installer_main
# then swaps it in as <emulators>/<EMULATOR>/app in one rename, so a failed
# install keeps the installed version working. When a method can't be used here
# (no build for this architecture) it calls `unavailable "why"`: -i then
# tries the next method. Any other failure stops the install.
#
# Optional, set by the installer before installer_main:
#   PORTABLE=1        the emulator keeps its data next to the executable
#                     (Redream, Supermodel): the program files are copied to
#                     the top of its folder instead of app/, and listed in
#                     .retrobox-files so -u removes exactly those
#   KEEP=(...)        with PORTABLE: files never overwritten once they exist
#   LEGACY=(...)      files or folders of older layouts, relative to the
#                     emulator's folder, removed by an install and by -u
#   after_install()   run once the new version is in place
#   before_uninstall()
#
# Environment:
#   JOBS                            parallel build jobs (default: nproc)
#   KEEP_SRC=1                      keep the source tree of a build
#   GITHUB_TOKEN                    used for the GitHub API (rate limits)
#   RETROBOX_EMULATORS_FINAL_DIR    where the install ends up when
#                                   RETROBOX_EMULATORS_DIR is a staging
#                                   folder (an update): builds bake it in

set -euo pipefail

_INSTALLER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." >/dev/null 2>&1 && pwd -P)"
# shellcheck source=tools/lib/paths.sh
source "${_INSTALLER_ROOT}/tools/lib/paths.sh"
# shellcheck source=tools/lib/log.sh
source "${_INSTALLER_ROOT}/tools/lib/log.sh"

: "${EMULATOR:?the installer must set EMULATOR before sourcing installer.sh}"
: "${LABEL:=${EMULATOR}}"
: "${PORTABLE:=0}"
[[ -v KEEP ]] || KEEP=()
[[ -v LEGACY ]] || LEGACY=()

INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/${EMULATOR}"
APP_DIR="${INSTALL_DIR}/app"
STAGE="${INSTALL_DIR}/app.new"
# the app folder where the install will finally live (an update stages it elsewhere)
FINAL_APP_DIR="${RETROBOX_EMULATORS_FINAL_DIR:-${RETROBOX_EMULATORS_DIR}}/${EMULATOR}/app"
SRC_DIR="${RETROBOX_EMULATORS_DIR}/_src/${EMULATOR}"
JOBS="${JOBS:-$(nproc)}"
KEEP_SRC="${KEEP_SRC:-0}"
_MANIFEST="${INSTALL_DIR}/.retrobox-files"
_METHODS=(appimage archive source)
_UNAVAILABLE=2

case "$(uname -m)" in
    x86_64 | amd64) ARCH="x86_64" ;;
    aarch64 | arm64) ARCH="aarch64" ;;
    *) ARCH="$(uname -m)" ;;
esac
# shellcheck disable=SC2034  # read by the installers
readonly ARCH

SUDO=""
if [[ "${EUID}" -ne 0 ]]; then
    SUDO="sudo"
fi

TMP_DIR="$(mktemp -d)"
_STAGING=0
# shellcheck disable=SC2329  # called by the EXIT trap
function _cleanup() {
    rm -rf "${TMP_DIR}"
    # an install that did not get to the end leaves nothing behind
    if [[ "${_STAGING}" == "1" ]]; then
        rm -rf "${STAGE}"
        [[ "${KEEP_SRC}" == "1" ]] || rm -rf "${SRC_DIR}"
        rmdir "${INSTALL_DIR}" 2>/dev/null || true
    fi
}
trap _cleanup EXIT

## Messages ----------------------------------------------------------------

function die() {
    log_err "$*"
    exit 1
}

# This method can't be used on this machine: -i goes on with the next one.
function unavailable() {
    log_warn "$*" >&2
    exit "${_UNAVAILABLE}"
}

## Packages ----------------------------------------------------------------

function package_manager() {
    if command -v apt-get &>/dev/null; then
        echo "apt"
    elif command -v dnf &>/dev/null; then
        echo "dnf"
    else
        echo "unknown"
    fi
}

function _deb_installed() {
    dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q "ok installed"
}

# install_packages "<apt packages>" "<dnf packages>"
# Each list is space-separated; "a|b" picks the first one apt knows about.
# Only what is missing is installed.
function install_packages() {
    local apt_list="$1" dnf_list="$2" manager
    manager="$(package_manager)"
    case "${manager}" in
        apt)
            local -a wanted=()
            local package alternative picked
            for package in ${apt_list}; do
                # an alternative already installed is enough, and is left alone
                # (apt would mark it as manually installed)
                picked=""
                for alternative in ${package//|/ }; do
                    if _deb_installed "${alternative}"; then
                        picked="-"
                        break
                    fi
                done
                [[ "${picked}" == "-" ]] && continue
                for alternative in ${package//|/ }; do
                    if apt-cache show "${alternative}" &>/dev/null; then
                        picked="${alternative}"
                        break
                    fi
                done
                if [[ -n "${picked}" ]]; then
                    wanted+=("${picked}")
                else
                    log_warn "No package ${package} in apt, skipping it."
                fi
            done
            [[ ${#wanted[@]} -eq 0 ]] && return 0
            if [[ -z "${_APT_UPDATED:-}" ]]; then
                ${SUDO} apt-get update -qq || log_warn "apt-get update failed."
                _APT_UPDATED=1
            fi
            log_info "Installing packages: ${wanted[*]}"
            ${SUDO} apt-get install -y "${wanted[@]}" || die "Could not install the packages (apt)"
            ;;
        dnf)
            local -a missing=()
            local package
            for package in ${dnf_list}; do
                rpm -q --whatprovides "${package}" &>/dev/null || missing+=("${package}")
            done
            [[ ${#missing[@]} -eq 0 ]] && return 0
            log_info "Installing packages: ${missing[*]}"
            ${SUDO} dnf install -y "${missing[@]}" || die "Could not install the packages (dnf)"
            ;;
        *)
            log_warn "Unknown package manager: make sure these are installed: ${apt_list}"
            ;;
    esac
}

# need <command>...: install the commands that are missing.
function need() {
    local command apt_list="" dnf_list=""
    for command in "$@"; do
        command -v "${command}" &>/dev/null && continue
        case "${command}" in
            7z) apt_list+=" 7zip|p7zip-full"; dnf_list+=" p7zip p7zip-plugins" ;;
            *) apt_list+=" ${command}"; dnf_list+=" ${command}" ;;
        esac
    done
    if [[ -n "${apt_list}" ]]; then
        install_packages "${apt_list}" "${dnf_list}"
    fi
}

## Downloads ---------------------------------------------------------------

function fetch() {
    local url="$1" destination="$2"
    log_info "Downloading ${url}"
    curl -fL --retry 3 --progress-bar -o "${destination}" "${url}" \
        || die "The download of ${url} failed"
}

# release_asset <forge> <regex> [any]
# Print the download URL of the newest release asset whose name matches
# <regex> (Python syntax, case-insensitive). <forge> is github:<owner>/<repo>
# or forgejo:<host>/<owner>/<repo>. Prereleases count only with "any".
# Calls `unavailable` when no release has a matching asset.
function release_asset() {
    local forge="$1" pattern="$2" prereleases="${3:-}" api
    local -a headers=(-H "Accept: application/json")
    case "${forge}" in
        github:*)
            api="https://api.github.com/repos/${forge#github:}/releases?per_page=20"
            if [[ -n "${GITHUB_TOKEN:-}" ]]; then
                headers+=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
            fi
            ;;
        forgejo:*)
            local rest="${forge#forgejo:}"
            api="https://${rest%%/*}/api/v1/repos/${rest#*/}/releases?limit=20"
            ;;
        *) die "release_asset: unknown forge ${forge}" ;;
    esac
    log_info "Looking for the latest ${LABEL} release (${forge#*:})..." >&2
    local json status=0 url
    json="$(curl -fsSL --retry 3 "${headers[@]}" "${api}")" \
        || die "Could not read the releases of ${forge#*:} (network down or API rate limit?)"
    url="$(python3 -I -c '
import json, re, sys
pattern = re.compile(sys.argv[1], re.IGNORECASE)
prereleases = sys.argv[2] == "any"
for release in json.loads(sys.stdin.read()):
    if release.get("draft") or (release.get("prerelease") and not prereleases):
        continue
    for asset in release.get("assets") or []:
        if pattern.search(asset.get("name", "")):
            print(asset["browser_download_url"])
            sys.exit(0)
sys.exit(3)' "${pattern}" "${prereleases}" <<<"${json}")" || status=$?
    case "${status}" in
        0) echo "${url}" ;;
        3) unavailable "No ${LABEL} release has a download for this machine (${ARCH})." ;;
        *) die "Could not read the releases of ${forge#*:}" ;;
    esac
}

## Unpacking ---------------------------------------------------------------

# extract_appimage <file>: the AppImage's files become ${STAGE}.
function extract_appimage() {
    local appimage="$1" work root
    work="$(mktemp -d -p "${TMP_DIR}")"
    chmod +x "${appimage}"
    log_info "Extracting the AppImage..."
    (cd "${work}" && "${appimage}" --appimage-extract >/dev/null) \
        || die "Could not extract ${appimage##*/}"
    # squashfs-root, which some AppImages make a link to an AppDir folder
    if [[ -e "${work}/squashfs-root" ]]; then
        root="$(readlink -f "${work}/squashfs-root")"
    elif [[ -d "${work}/AppDir" ]]; then
        root="${work}/AppDir"
    else
        die "The AppImage extracted into an unexpected layout"
    fi
    [[ -x "${root}/AppRun" ]] || die "The extracted AppImage has no AppRun"
    rm -rf "${STAGE}"
    mv "${root}" "${STAGE}"
}

# extract_archive <file> <folder>: unpack a tarball, zip or 7z into <folder>,
# without the archive's single top-level folder if it has one.
function extract_archive() {
    local archive="$1" destination="$2" work
    work="$(mktemp -d -p "${TMP_DIR}")"
    case "${archive,,}" in
        *.zip) need unzip; unzip -q "${archive}" -d "${work}" ;;
        *.7z) need 7z; 7z x -y -o"${work}" "${archive}" >/dev/null ;;
        *) tar -xf "${archive}" -C "${work}" ;;
    esac || die "Could not extract ${archive##*/}"
    local -a entries
    shopt -s dotglob nullglob
    entries=("${work}"/*)
    if [[ ${#entries[@]} -eq 1 && -d "${entries[0]}" ]]; then
        entries=("${entries[0]}"/*)
    fi
    mkdir -p "${destination}"
    [[ ${#entries[@]} -gt 0 ]] && mv "${entries[@]}" "${destination}/"
    shopt -u dotglob nullglob
}

## Building ----------------------------------------------------------------

# git_clone <url> [ref]: a fresh shallow clone (with submodules) in ${SRC_DIR}.
function git_clone() {
    local url="$1" ref="${2:-}"
    local -a options=(--depth 1 --recurse-submodules --shallow-submodules)
    [[ -n "${ref}" ]] && options+=(--branch "${ref}")
    need git
    rm -rf "${SRC_DIR}"
    mkdir -p "$(dirname "${SRC_DIR}")"
    log_info "Cloning ${url}${ref:+ (${ref})}..."
    git clone "${options[@]}" "${url}" "${SRC_DIR}" || die "Could not clone ${url}"
}

# cmake_build [cmake options...]: configure and build ${SRC_DIR} in
# ${SRC_DIR}/build, with the final prefix baked in.
function cmake_build() {
    local build="${SRC_DIR}/build"
    local -a generator=()
    command -v ninja &>/dev/null && generator=(-G Ninja)
    log_info "Configuring ${LABEL}..."
    cmake -S "${SRC_DIR}" -B "${build}" "${generator[@]}" \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="${FINAL_APP_DIR}" "$@" \
        || die "CMake could not configure ${LABEL}: check the messages above"
    log_info "Building ${LABEL} with ${JOBS} jobs..."
    cmake --build "${build}" -j "${JOBS}" \
        || die "The build failed (lower JOBS if the linker ran out of memory)"
}

# cmake_install: install what cmake_build built into ${STAGE}.
function cmake_install() {
    cmake --install "${SRC_DIR}/build" --prefix "${STAGE}" || die "cmake --install failed"
}

function remove_sources() {
    if [[ "${KEEP_SRC}" == "1" ]]; then
        log_info "Source tree kept in ${SRC_DIR}."
        return 0
    fi
    rm -rf "${SRC_DIR}"
    rmdir "$(dirname "${SRC_DIR}")" 2>/dev/null || true
}

# require_executable <path inside ${STAGE}>: fail unless the install produced it.
function require_executable() {
    [[ -x "${STAGE}/$1" ]] || die "The install did not produce $1"
}

## Installing and removing -------------------------------------------------

function _remove_legacy() {
    local entry
    for entry in "${LEGACY[@]}"; do
        if [[ -e "${INSTALL_DIR}/${entry}" || -L "${INSTALL_DIR}/${entry}" ]]; then
            rm -rf "${INSTALL_DIR:?}/${entry}"
            log_info "Removed ${entry} (an older layout)."
        fi
    done
}

function _kept() {
    local entry
    for entry in "${KEEP[@]}"; do
        [[ "$1" == "${entry}" ]] && return 0
    done
    return 1
}

function _remove_manifest_files() {
    [[ -f "${_MANIFEST}" ]] || return 0
    local file
    while IFS= read -r file; do
        [[ -n "${file}" ]] || continue
        _kept "${file}" || rm -f "${INSTALL_DIR:?}/${file}"
    done <"${_MANIFEST}"
    rm -f "${_MANIFEST}"
}

# Put ${STAGE} in place: as app/, or file by file for a portable emulator.
function _activate() {
    [[ -n "$(ls -A "${STAGE}" 2>/dev/null)" ]] || die "The install produced nothing"
    if [[ "${PORTABLE}" == "1" ]]; then
        local file manifest="${_MANIFEST}.new"
        (cd "${STAGE}" && find . \( -type f -o -type l \) -printf '%P\n' | sort) >"${manifest}"
        _remove_manifest_files
        while IFS= read -r file; do
            if _kept "${file}" && [[ -e "${INSTALL_DIR}/${file}" ]]; then
                continue
            fi
            mkdir -p "$(dirname "${INSTALL_DIR}/${file}")"
            mv -f "${STAGE}/${file}" "${INSTALL_DIR}/${file}"
        done <"${manifest}"
        mv "${manifest}" "${_MANIFEST}"
        rm -rf "${STAGE}"
    else
        local old="${INSTALL_DIR}/app.old"
        rm -rf "${old}"
        [[ -e "${APP_DIR}" ]] && mv "${APP_DIR}" "${old}"
        mv "${STAGE}" "${APP_DIR}"
        rm -rf "${old}"
    fi
    _remove_legacy
}

function _has_method() {
    declare -F "install_$1" >/dev/null
}

function _install_with() {
    local method="$1"
    _has_method "${method}" || die "${LABEL} has no ${method} install"
    mkdir -p "${INSTALL_DIR}"
    rm -rf "${STAGE}"
    mkdir -p "${STAGE}"
    _STAGING=1
    "install_${method}"
    _activate
    _STAGING=0
    if declare -F after_install >/dev/null; then
        after_install
    fi
    log_ok "${LABEL} installed (${method}) in ${INSTALL_DIR}."
}

# -i: each method in its own process, so `unavailable` can hand over to the next.
function _install_preferred() {
    local method flag status
    for method in "${_METHODS[@]}"; do
        _has_method "${method}" || continue
        case "${method}" in
            appimage) flag="-a" ;;
            archive) flag="-t" ;;
            source) flag="-s" ;;
        esac
        status=0
        bash "$0" "${flag}" || status=$?
        case "${status}" in
            0) return 0 ;;
            "${_UNAVAILABLE}") log_info "Trying the next way to install ${LABEL}..." ;;
            *) exit "${status}" ;;
        esac
    done
    die "${LABEL} can't be installed on this machine (${ARCH})"
}

function _uninstall() {
    if declare -F before_uninstall >/dev/null; then
        before_uninstall
    fi
    rm -rf "${APP_DIR}" "${STAGE}" "${INSTALL_DIR}/app.old"
    _remove_manifest_files
    _remove_legacy
    if [[ -d "${INSTALL_DIR}" ]]; then
        find "${INSTALL_DIR}" -depth -type d -empty -delete
    fi
    log_ok "${LABEL} uninstalled (its configuration and saves are kept)."
}

function _usage() {
    cat <<EOF
Usage: $(basename "$0") -i | -a | -t | -s | -u | -l
  -i  install ${LABEL} the best way this machine allows ($(_list_methods))
  -a  the AppImage    -t  the release archive    -s  a build from source
  -u  uninstall (the configuration and saves are kept)
  -l  list the methods this installer has
EOF
}

function _list_methods() {
    local method
    local -a found=()
    for method in "${_METHODS[@]}"; do
        _has_method "${method}" && found+=("${method}")
    done
    echo "${found[*]}"
}

function installer_main() {
    case "${1:-}" in
        -i) _install_preferred ;;
        -a) _install_with appimage ;;
        -t) _install_with archive ;;
        -s) _install_with source ;;
        -u) _uninstall ;;
        -l) _list_methods ;;
        *) _usage; exit 1 ;;
    esac
}
