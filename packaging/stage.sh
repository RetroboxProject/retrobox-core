#!/usr/bin/env bash
# Stage Retrobox's installation tree into DESTDIR.
#
# Format-agnostic on purpose: build-deb.sh uses it today, and an .rpm
# builder (e.g. nfpm) can reuse it as-is later. It only lays files out; it
# knows nothing about package metadata.
#
#   packaging/stage.sh DESTDIR
#
# Layout produced (paths are relative to DESTDIR):
#   ${INSTALL_ROOT}/                       the project (default /opt/retrobox)
#   ${INSTALL_ROOT}/VERSION                the version string (PKG_VERSION)
#   ${SYSCONF_DIR}/retrobox.ini            commented template (admin config)
#   ${SYSCONF_DIR}/retrobox.ini.d/         drop-ins (empty)
#   ${BIN_LINK}                            symlink -> ${INSTALL_ROOT}/bin/retrobox
#   /usr/lib/udev/rules.d/                 udev rules
#   /usr/share/polkit-1/rules.d/           polkit rules
#   /usr/share/applications/retrobox.desktop
#   /usr/share/icons/hicolor/<N>x<N>/apps/retrobox.png   (menu icon, see below)
#   /usr/share/doc/retrobox-core/copyright
#
# Nothing in the tree is ever written to at runtime: user data lives in the
# XDG directories (see lib/retrobox/paths/_base.py), the same ones as for any
# other kind of install.
#
# Environment: PKG_VERSION   written to ${INSTALL_ROOT}/VERSION (default: git describe)
#              SYSCONF_DIR   default /etc/retrobox
#
# The file list comes from `git ls-files --recurse-submodules`, so only
# tracked files (including checked-out submodules) are shipped: no .git,
# no build leftovers, no local junk. Initialise the submodules you want in
# the package before running this.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd -P)"
DESTDIR="${1:?usage: $(basename "$0") DESTDIR}"
INSTALL_ROOT="${INSTALL_ROOT:-/opt/retrobox}"
BIN_LINK="${BIN_LINK:-/usr/bin/retrobox}"
SYSCONF_DIR="${SYSCONF_DIR:-/etc/retrobox}"

# Tracked files that must NOT end up in the package.
# What does NOT go into /opt/retrobox. The packages ship what runs, nothing
# else: no docs, no build/dev files, no installer-only material (the
# dependency lists and requirements.txt are only needed by install.sh, which
# gets them through the tarball's extras/; setup-debian/fedora.sh are for git
# checkouts; the udev rules are installed into /usr/lib/udev below).
EXCLUDE_RE='^(\.vscode/|\.github/|packaging/|dev/|system/|LICENSE$|install\.sh$|\.gitmodules$|tools/setup-(debian|fedora)\.sh$|tools/deps/|tools/lib/deps\.sh$)|(^|/)(README(\.md)?|requirements\.txt|\.gitignore|\.gitattributes|\.gitkeep)$'

ROOT_IN_PKG="${DESTDIR}${INSTALL_ROOT}"

if [[ -e "${DESTDIR}" ]] && [[ -n "$(ls -A "${DESTDIR}" 2>/dev/null)" ]]; then
    echo "stage.sh: ${DESTDIR} exists and is not empty" >&2
    exit 1
fi
mkdir -p "${ROOT_IN_PKG}"

# --- 1. The project tree ----------------------------------------------------
git -C "${SRC}" ls-files -z --recurse-submodules \
    | { grep -zvE "${EXCLUDE_RE}" || true; } \
    | tar --null -C "${SRC}" -T - -cf - \
    | tar -xf - -C "${ROOT_IN_PKG}"

echo "${PKG_VERSION:-$(git -C "${SRC}" describe --tags --always 2>/dev/null || echo unknown)}" \
    > "${ROOT_IN_PKG}/VERSION"

# System-wide configuration layer: a commented template, and the drop-in dir.
mkdir -p "${DESTDIR}${SYSCONF_DIR}/retrobox.ini.d"
cat > "${DESTDIR}${SYSCONF_DIR}/retrobox.ini" <<'EOF'
# Retrobox system-wide configuration.
#
# Read before ~/.config/retrobox/retrobox.ini, which overrides it key by key.
# Drop-in files in retrobox.ini.d/*.ini (read in alphabetical order) override
# this file. Nothing is written here by Retrobox; everything below is optional
# and shows the default.
#
# The same layering applies to share/ (systems_config/, emu_features/,
# hooks/retrohook.d/...): a file under /etc/retrobox/<same relative path>, or
# under ~/.config/retrobox/<same relative path>, replaces the shipped one.

#[core]
## Create the default directories when a configured path is missing/invalid.
#autocorrect_paths = true
## Systems to hide from the menu, e.g. gba,psp
#ignore_systems =
## Add the installed PC games of each launcher to its system on every start
#steam_sync  = false
#heroic_sync = false
#lutris_sync = false

#[paths]
## Move everything Retrobox keeps (default: ~/.local/share/retrobox and
## ~/.local/state/retrobox). roms/saves/bios follow data_dir unless set below.
#data_dir  = /srv/games/retrobox
#state_dir = /srv/games/retrobox-state
## Where the big content lives (default: <data_dir>/<name>)
#roms_dir  = /srv/games/roms
#saves_dir = /srv/games/saves
#bios_dir  = /srv/games/bios

#[advanced]
## Virtual terminal of the labwc gaming session (retrobox-labwc component)
#labwc_tty = 1

#[environ]
## Literal environment variables for every Retrobox process.
#STEAM_LIBRARY_DIR = /srv/games/steam
EOF
chmod 644 "${DESTDIR}${SYSCONF_DIR}/retrobox.ini"

# Normalise modes: directories 755, executables 755, everything else 644.
find "${ROOT_IN_PKG}" -type d -exec chmod 755 {} +
find "${ROOT_IN_PKG}" -type f -perm /111 -exec chmod 755 {} +
find "${ROOT_IN_PKG}" -type f ! -perm /111 -exec chmod 644 {} +

# --- 2. Launcher symlink ----------------------------------------------------
mkdir -p "${DESTDIR}$(dirname "${BIN_LINK}")"
ln -s "${INSTALL_ROOT}/bin/retrobox" "${DESTDIR}${BIN_LINK}"

# --- 3. udev rules ----------------------------------------------------------
UDEV_DIR="${DESTDIR}/usr/lib/udev/rules.d"
mkdir -p "${UDEV_DIR}"
install -m 644 "${SRC}/system/udev/64-retrobox.rules" "${UDEV_DIR}/64-retrobox.rules"

# --- 3b. polkit rules (start/stop nvidia-powerd without a password) ----------
POLKIT_DIR="${DESTDIR}/usr/share/polkit-1/rules.d"
mkdir -p "${POLKIT_DIR}"
install -m 644 "${SRC}/system/polkit/50-retrobox-nvidia-powerd.rules" \
    "${POLKIT_DIR}/50-retrobox-nvidia-powerd.rules"

# --- 4. Desktop entry + icon ------------------------------------------------
# The logo's neon glow is an SVG blur filter, which Qt (KDE's menus) doesn't
# draw: the icon goes in as PNGs at the usual sizes (packaging/icons, made by
# dev/render_icons.py), not as a scalable SVG. The 512 px one is the logo's
# own export inside the tree, linked rather than copied.
mkdir -p "${DESTDIR}/usr/share/applications"
sed -e "s|@BIN@|${BIN_LINK}|g" \
    "${SRC}/packaging/retrobox.desktop.in" \
    > "${DESTDIR}/usr/share/applications/retrobox.desktop"
chmod 644 "${DESTDIR}/usr/share/applications/retrobox.desktop"
for icon in "${SRC}"/packaging/icons/hicolor/*/apps/retrobox.png; do
    size_dir="$(basename "$(dirname "$(dirname "${icon}")")")"
    install -D -m 644 "${icon}" "${DESTDIR}/usr/share/icons/hicolor/${size_dir}/apps/retrobox.png"
done
mkdir -p "${DESTDIR}/usr/share/icons/hicolor/512x512/apps"
ln -s "${INSTALL_ROOT}/share/icons/retrobox_logo.png" \
    "${DESTDIR}/usr/share/icons/hicolor/512x512/apps/retrobox.png"

# --- 5. Licence -------------------------------------------------------------
mkdir -p "${DESTDIR}/usr/share/doc/retrobox-core"
install -m 644 "${SRC}/LICENSE" "${DESTDIR}/usr/share/doc/retrobox-core/copyright"

echo "stage.sh: staged ${INSTALL_ROOT} into ${DESTDIR}"
