#!/usr/bin/env bash
# Retrobox standalone installer. Leaves the same environment as the .deb:
# a read-only project tree, udev rules, a launcher and the optional
# /etc/retrobox layer; user data lives in ~/.config|.local/share/retrobox.
#
#   curl -fsSL https://github.com/RetroboxProject/retrobox-core/releases/latest/download/install.sh | bash
#   curl -fsSL .../install.sh | bash -s -- --prefix /srv/retrobox --version 1.2.3
#
# Options:
#   --prefix DIR      install the project in DIR (default: /opt/retrobox, or
#                     /var/opt/retrobox if /opt is not writable, as on some
#                     immutable distros)
#   --user            no root: install under ~/.local (opt/retrobox, bin/,
#                     share/), no udev rules, no /etc
#   --version X.Y.Z   install that release instead of the latest
#   --tarball FILE    install from a local retrobox-core-all.tar.gz
#                     (skips the download; checksum checked if a SHA256SUMS
#                     file sits next to it)
#   --base-url URL    download from URL instead of the GitHub release
#   --with NAME[=SRC] also install the optional component NAME: its own installer, `install.sh` at the
#                     root of github.com/<owner>/retrobox-NAME, or SRC = a URL
#                     or a local path to that install.sh. Repeatable. A
#                     component already installed is updated together with
#                     the core.
#   --no-deps         don't install system dependencies
#   --uninstall       remove what this script installed (user data and
#                     /etc/retrobox are kept)
#   -h, --help
#
# Components (EmulationStation, MangoHud, ...) live in their own repositories
# and bring their own `install.sh`, which this script downloads and runs as
#
#   install.sh --prefix DIR --bin-dir DIR [--no-deps] [--user]
#   install.sh --uninstall --prefix DIR --bin-dir DIR
#
# with RETROBOX_PREFIX, RETROBOX_BIN_DIR, RETROBOX_ARCH (amd64 | arm64 | the
# raw `uname -m`) and RETROBOX_CORE_VERSION in the environment. A component
# installer must only write below --prefix (and its commands into --bin-dir),
# must pick the build for RETROBOX_ARCH, and must remove everything it
# installed on --uninstall, leaving no helper files behind in the tree. A copy
# of it is kept in <prefix>/.components/<name>/ for updates and --uninstall.
# (The .deb/.rpm packages of the components do the same without any script.)
#
# Dependencies: on Debian/Ubuntu/Fedora systems with a normal root
# filesystem they come from apt/dnf, exactly as with the packages. On
# immutable systems (Silverblue, Bazzite, ...) or with --no-deps the Python
# ones go into a self-contained virtualenv in the install tree; system
# libraries (SDL2, VLC...) you must layer yourself (the script prints them).
set -euo pipefail

REPO="RetroboxProject/retrobox-core"
ASSET="retrobox-core-all.tar.gz"

PREFIX=""
USER_MODE=0
VERSION=""
TARBALL=""
BASE_URL=""
DO_DEPS=1
UNINSTALL=0
declare -a COMPONENTS=()

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then B=$'\033[1m'; R=$'\033[0m'; else B=""; R=""; fi
info() { echo "${B}[INFO]${R} $*"; }
ok()   { echo "${B}[ OK ]${R} $*"; }
warn() { echo "${B}[WARN]${R} $*" >&2; }
die()  { echo "${B}[ERR ]${R} $*" >&2; exit 1; }

usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]:-$0}" 2>/dev/null | sed '$d; s/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)    PREFIX="${2:?--prefix needs a directory}"; shift 2 ;;
        --user)      USER_MODE=1; shift ;;
        --version)   VERSION="${2:?--version needs a value}"; shift 2 ;;
        --tarball)   TARBALL="${2:?--tarball needs a file}"; shift 2 ;;
        --base-url)  BASE_URL="${2:?--base-url needs a URL}"; shift 2 ;;
        --with)
            [[ "${2:?--with needs a component name}" =~ ^[a-z0-9][a-z0-9-]*(=.*)?$ ]] \
                || die "--with: invalid component name '${2}'"
            COMPONENTS+=("$2"); shift 2 ;;
        --no-deps)   DO_DEPS=0; shift ;;
        --uninstall) UNINSTALL=1; shift ;;
        -h|--help)   usage; exit 0 ;;
        *) die "unknown option: $1 (see --help)" ;;
    esac
done

[[ "$(uname -s)" == "Linux" ]] || die "Retrobox only runs on Linux."

# The core is architecture-independent (Python); the components are not.
case "$(uname -m)" in
    x86_64|amd64)  RETROBOX_ARCH="amd64" ;;
    aarch64|arm64) RETROBOX_ARCH="arm64" ;;
    *)             RETROBOX_ARCH="$(uname -m)" ;;
esac

# --- privileges --------------------------------------------------------------
# priv CMD...: run as root (directly, or through sudo).
if [[ "${EUID}" -eq 0 ]]; then
    priv() { "$@"; }
    HAVE_ROOT=1
elif [[ "${USER_MODE}" -eq 0 ]] && command -v sudo >/dev/null 2>&1; then
    priv() { sudo "$@"; }
    HAVE_ROOT=1
else
    HAVE_ROOT=0
fi
if [[ "${HAVE_ROOT}" -eq 0 && "${USER_MODE}" -eq 0 ]]; then
    warn "Not root and no sudo available: falling back to a per-user install (--user)."
    USER_MODE=1
fi
if [[ "${USER_MODE}" -eq 1 ]]; then
    HAVE_ROOT=0
    priv() { "$@"; }  # nothing is installed outside $HOME
fi

# can_write DIR: can we really create files in DIR (or its nearest existing
# parent)? Probed with an actual write, since read-only mounts, ostree and
# SELinux make permission bits unreliable.
can_write() {
    local dir="$1" probe
    while [[ ! -d "${dir}" ]]; do dir="$(dirname "${dir}")"; done
    probe="$(priv mktemp "${dir}/.retrobox-probe.XXXXXX" 2>/dev/null)" || return 1
    priv rm -f "${probe}"
}

is_immutable() {
    [[ -e /run/ostree-booted || "${RETROBOX_ASSUME_IMMUTABLE:-0}" == "1" ]]
}

# --- layout -------------------------------------------------------------------
if [[ "${USER_MODE}" -eq 1 ]]; then
    PREFIX="${PREFIX:-${HOME}/.local/opt/retrobox}"
    BIN_DIR="${HOME}/.local/bin"
    SHARE_DIR="${HOME}/.local/share"
    UDEV_DIR=""
    SYSCONF_DIR=""
else
    if [[ -z "${PREFIX}" ]]; then
        if can_write /opt; then
            PREFIX="/opt/retrobox"
        elif can_write /var/opt; then
            PREFIX="/var/opt/retrobox"
            info "/opt is not writable here; using /var/opt/retrobox."
        else
            die "Neither /opt nor /var/opt is writable. Use --prefix DIR or --user."
        fi
    fi
    BIN_DIR="/usr/local/bin"
    can_write "${BIN_DIR}" || BIN_DIR="${HOME}/.local/bin"
    SHARE_DIR="/usr/local/share"
    can_write "${SHARE_DIR}" || SHARE_DIR="${HOME}/.local/share"
    if can_write /usr/lib/udev/rules.d; then UDEV_DIR=/usr/lib/udev/rules.d; else UDEV_DIR=/etc/udev/rules.d; fi
    SYSCONF_DIR="/etc/retrobox"
fi
PREFIX="$(realpath -m "${PREFIX}")"
case "${PREFIX}" in
    /|/usr|/usr/*|/etc|/etc/*|/home|"${HOME}") die "Refusing to install into ${PREFIX}." ;;
esac
can_write "${PREFIX}" || die "${PREFIX} is not writable. Choose another --prefix, or --user."
MANIFEST="${PREFIX}/.install-manifest"

# --- uninstall ----------------------------------------------------------------
if [[ "${UNINSTALL}" -eq 1 ]]; then
    [[ -f "${MANIFEST}" ]] || die "No install found in ${PREFIX} (missing .install-manifest)."
    info "Removing Retrobox from ${PREFIX}..."
    for inst in "${PREFIX}"/.components/*/install.sh; do
        [[ -f "${inst}" ]] || continue
        name="$(basename "$(dirname "${inst}")")"
        info "Removing component '${name}'..."
        priv env RETROBOX_PREFIX="${PREFIX}" RETROBOX_BIN_DIR="${BIN_DIR}" RETROBOX_ARCH="${RETROBOX_ARCH}" \
            bash "${inst}" --uninstall --prefix "${PREFIX}" --bin-dir "${BIN_DIR}" \
            || warn "The uninstaller of '${name}' failed; some of its files may be left."
    done
    while IFS= read -r f; do
        [[ -n "${f}" ]] && priv rm -f "${f}"
    done < "${MANIFEST}"
    priv rm -rf "${PREFIX}"
    command -v udevadm >/dev/null 2>&1 && priv udevadm control --reload-rules >/dev/null 2>&1 || true
    ok "Removed. Your data in ~/.config/retrobox and ~/.local/share/retrobox, and ${SYSCONF_DIR:-/etc/retrobox}, were kept."
    exit 0
fi

# --- fetch --------------------------------------------------------------------
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

fetch() {  # fetch URL DEST
    if command -v curl >/dev/null 2>&1; then curl -fsSL --retry 3 -o "$2" "$1"
    elif command -v wget >/dev/null 2>&1; then wget -q -O "$2" "$1"
    else die "Neither curl nor wget is installed."; fi
}

if [[ -n "${TARBALL}" ]]; then
    [[ -f "${TARBALL}" ]] || die "${TARBALL}: no such file"
    cp "${TARBALL}" "${WORK}/${ASSET}"
    [[ -f "$(dirname "${TARBALL}")/SHA256SUMS" ]] && cp "$(dirname "${TARBALL}")/SHA256SUMS" "${WORK}/SHA256SUMS"
else
    if [[ -n "${BASE_URL}" ]]; then URL="${BASE_URL%/}"
    elif [[ -n "${VERSION}" ]]; then URL="https://github.com/${REPO}/releases/download/v${VERSION#v}"
    else URL="https://github.com/${REPO}/releases/latest/download"; fi
    info "Downloading ${URL}/${ASSET}..."
    fetch "${URL}/${ASSET}" "${WORK}/${ASSET}" || die "Download failed."
    fetch "${URL}/SHA256SUMS" "${WORK}/SHA256SUMS" || die "Could not download SHA256SUMS."
fi
if [[ -f "${WORK}/SHA256SUMS" ]]; then
    (cd "${WORK}" && grep " ${ASSET}\$" SHA256SUMS | sha256sum -c --quiet -) \
        || die "Checksum mismatch for ${ASSET}."
    ok "Checksum verified."
else
    warn "No SHA256SUMS next to the tarball: not verifying it."
fi

mkdir "${WORK}/x"
tar -xzf "${WORK}/${ASSET}" -C "${WORK}/x" --strip-components=1
[[ -f "${WORK}/x/retrobox/bin/retrobox" ]] || die "The tarball doesn't look like a Retrobox release."
NEW_VERSION="$(head -n1 "${WORK}/x/retrobox/VERSION" 2>/dev/null || echo unknown)"
info "Installing Retrobox ${NEW_VERSION} into ${PREFIX}..."

# --- dependencies ---------------------------------------------------------------
USE_VENV=0
install_deps() {
    local tree="${WORK}/x/extras"
    if is_immutable || [[ "${HAVE_ROOT}" -eq 0 ]]; then
        USE_VENV=1
        return
    fi
    if command -v apt-get >/dev/null 2>&1; then
        # shellcheck source=/dev/null
        source "${tree}/deps.sh"
        priv apt-get update -qq
        mapfile -t pkgs < <(deps_apt_args "${tree}/deps/debian.list")
        priv env DEBIAN_FRONTEND=noninteractive apt-get install -y "${pkgs[@]}"
        mapfile -t rec < <(deps_apt_args "${tree}/deps/recommended-debian.list")
        priv env DEBIAN_FRONTEND=noninteractive apt-get install -y "${rec[@]}" \
            || warn "Some recommended packages could not be installed."
    elif command -v dnf >/dev/null 2>&1; then
        # shellcheck source=/dev/null
        source "${tree}/deps.sh"
        mapfile -t pkgs < <(deps_list "${tree}/deps/fedora.list")
        priv dnf install -y "${pkgs[@]}"
        mapfile -t rec < <(deps_list "${tree}/deps/recommended-fedora.list")
        priv dnf install -y --setopt=strict=0 "${rec[@]}" || warn "Some recommended packages could not be installed."
    else
        warn "No apt or dnf found: using a virtualenv for the Python dependencies."
        USE_VENV=1
    fi
}
if [[ "${DO_DEPS}" -eq 1 ]]; then
    install_deps
else
    USE_VENV=1
fi

# --- install the tree (swap in, keep the old one until the new one is in place) --
# Components of the install being replaced come back with the new core.
for dir in "${PREFIX}"/.components/*/; do
    [[ -d "${dir}" ]] || continue
    c="$(basename "${dir}")"
    already=0
    for have in "${COMPONENTS[@]}"; do [[ "${have%%=*}" == "${c}" ]] && already=1; done
    [[ "${already}" -eq 1 ]] && continue
    src="$(cat "${dir}/source" 2>/dev/null || true)"
    COMPONENTS+=("${c}${src:+=${src}}")
done

priv mkdir -p "$(dirname "${PREFIX}")"
STAGING="${PREFIX}.new.$$"
priv rm -rf "${STAGING}"
priv cp -a "${WORK}/x/retrobox" "${STAGING}"
if [[ "${EUID}" -eq 0 ]]; then priv chown -R root:root "${STAGING}"; fi

if [[ "${USE_VENV}" -eq 1 ]]; then
    command -v python3 >/dev/null 2>&1 || die "python3 is required."
    info "Creating the Python environment (virtualenv)..."
    priv python3 -m venv "${STAGING}/venv" \
        || die "Could not create a virtualenv (is the python3 venv module installed?)."
    priv "${STAGING}/venv/bin/pip" install -q -r "${WORK}/x/extras/requirements.txt" \
        || warn "pip could not install every Python dependency."
    if [[ "${DO_DEPS}" -eq 1 ]]; then
        if is_immutable; then
            warn "Immutable system: layer the libraries Retrobox needs with your package manager, e.g."
            warn "  rpm-ostree install $(grep -v '^python3' "${WORK}/x/extras/deps/fedora.list" | sed -e 's/#.*//' | tr '\n' ' ')"
            warn "and reboot."
        else
            warn "Install these system libraries with your package manager: $(grep -v '^python3' "${WORK}/x/extras/deps/fedora.list" | sed -e 's/#.*//' | tr '\n' ' ')"
        fi
    fi
    PYTHON="${STAGING}/venv/bin/python3"
else
    PYTHON="$(command -v python3 || true)"
fi

# Byte-compile: the tree is read-only for users, so Python could never cache
# it on its own and every game launch would re-parse the modules.
if [[ -n "${PYTHON:-}" ]]; then
    priv "${PYTHON}" -m compileall -q "${STAGING}/lib" >/dev/null 2>&1 || true
fi

# Make the tree readable (and traversable) by every user.
priv chmod -R a+rX,go-w "${STAGING}"
if [[ -e "${PREFIX}" ]]; then
    # Remove the old install's files; the tree itself is replaced as a whole.
    priv rm -rf "${PREFIX}.old.$$"
    priv mv "${PREFIX}" "${PREFIX}.old.$$"
fi
priv mv "${STAGING}" "${PREFIX}"
if [[ -d "${PREFIX}/venv/bin" ]]; then
    # The virtualenv was created under the staging name: fix its scripts.
    grep -rlI --exclude-dir=__pycache__ -- "${STAGING}" "${PREFIX}/venv/bin" 2>/dev/null \
        | while IFS= read -r f; do priv sed -i "s|${STAGING}|${PREFIX}|g" "${f}"; done || true
fi
priv rm -rf "${PREFIX}.old.$$"

# --- the rest of the system -------------------------------------------------------
: > "${WORK}/manifest"
record() { echo "$1" >> "${WORK}/manifest"; }

declare -a FAILED_COMPONENTS=()
install_component() {  # install_component NAME[=SRC]
    local name="${1%%=*}" src="" url script cdir="${WORK}/c-${1%%=*}"
    [[ "$1" == *=* ]] && src="${1#*=}"
    script="${cdir}/install.sh"
    mkdir -p "${cdir}"
    info "Installing component '${name}'..."
    if [[ -f "${src}" ]]; then
        cp "${src}" "${script}"
    elif [[ -n "${src}" && -f "${src}/install.sh" ]]; then
        cp "${src}/install.sh" "${script}"
    else
        url="${src:-https://raw.githubusercontent.com/${REPO%%/*}/retrobox-${name}/HEAD/install.sh}"
        info "Fetching ${url}"
        fetch "${url}" "${script}" || { warn "Could not download the installer of '${name}'."; FAILED_COMPONENTS+=("${name}"); return 0; }
    fi
    [[ "$(head -c2 "${script}")" == "#!" ]] \
        || { warn "The installer of '${name}' is not a script; skipping it."; FAILED_COMPONENTS+=("${name}"); return 0; }
    local -a args=(--prefix "${PREFIX}" --bin-dir "${BIN_DIR}")
    if [[ "${USE_VENV}" -eq 1 || "${DO_DEPS}" -eq 0 ]]; then args+=(--no-deps); fi
    if [[ "${USER_MODE}" -eq 1 ]]; then args+=(--user); fi
    if ! priv env RETROBOX_PREFIX="${PREFIX}" RETROBOX_BIN_DIR="${BIN_DIR}" \
            RETROBOX_ARCH="${RETROBOX_ARCH}" RETROBOX_CORE_VERSION="${NEW_VERSION}" \
            bash "${script}" "${args[@]}"; then
        warn "The installer of '${name}' failed."
        FAILED_COMPONENTS+=("${name}")
        return 0
    fi
    priv mkdir -p "${PREFIX}/.components/${name}"
    priv install -m 755 "${script}" "${PREFIX}/.components/${name}/install.sh"
    printf '%s\n' "${src}" > "${cdir}/source"
    priv install -m 644 "${cdir}/source" "${PREFIX}/.components/${name}/source"
    ok "Component '${name}' installed."
}

priv mkdir -p "${BIN_DIR}"
priv ln -sfn "${PREFIX}/bin/retrobox" "${BIN_DIR}/retrobox"
record "${BIN_DIR}/retrobox"

priv mkdir -p "${SHARE_DIR}/applications" "${SHARE_DIR}/icons/hicolor/scalable/apps"
sed "s|@BIN@|${BIN_DIR}/retrobox|g" "${WORK}/x/extras/retrobox.desktop.in" > "${WORK}/retrobox.desktop"
priv install -m 644 "${WORK}/retrobox.desktop" "${SHARE_DIR}/applications/retrobox.desktop"
priv install -m 644 "${WORK}/x/extras/retrobox.svg" "${SHARE_DIR}/icons/hicolor/scalable/apps/retrobox.svg"
record "${SHARE_DIR}/applications/retrobox.desktop"
record "${SHARE_DIR}/icons/hicolor/scalable/apps/retrobox.svg"

if [[ -n "${UDEV_DIR}" ]]; then
    for rules in "${WORK}"/x/extras/udev/*.rules; do
        priv install -m 644 "${rules}" "${UDEV_DIR}/$(basename "${rules}")"
        record "${UDEV_DIR}/$(basename "${rules}")"
    done
    if command -v udevadm >/dev/null 2>&1; then
        priv udevadm control --reload-rules >/dev/null 2>&1 || true
        priv udevadm trigger --subsystem-match=input --subsystem-match=hidraw --action=change >/dev/null 2>&1 || true
    fi
fi

if [[ -n "${SYSCONF_DIR}" && ! -e "${SYSCONF_DIR}/retrobox.ini" ]]; then
    priv mkdir -p "${SYSCONF_DIR}"
    priv cp -a "${WORK}/x/extras/etc/retrobox/." "${SYSCONF_DIR}/"
fi

for c in "${COMPONENTS[@]}"; do install_component "${c}"; done
priv chmod -R a+rX,go-w "${PREFIX}"

priv cp "${WORK}/manifest" "${MANIFEST}"
priv chmod 644 "${MANIFEST}"

ok "Retrobox ${NEW_VERSION} installed in ${PREFIX}."
[[ ":${PATH}:" == *":${BIN_DIR}:"* ]] || warn "${BIN_DIR} is not in your PATH; run ${BIN_DIR}/retrobox."
if [[ -n "${UDEV_DIR}" ]]; then
    info "For gamepad-to-keyboard remapping: sudo usermod -aG input \$USER, then log in again."
fi
if [[ "${#FAILED_COMPONENTS[@]}" -gt 0 ]]; then
    die "Retrobox is installed, but these components failed: ${FAILED_COMPONENTS[*]}"
fi
