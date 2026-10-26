#!/usr/bin/env bash
# Deploys the labwc gaming-session configuration:
#   * renders the *.in templates, replacing @RETROBOX_ROOT@ with this
#     checkout's real path, into ~/.config/labwc
#   * symlinks the path-free configs into ~/.config/labwc
#   * installs go2tty system-wide
#   * installs the ~/.bashrc.d hook that starts the session on the TTY
#     configured in retrobox.ini ([advanced] labwc_tty)
#
# Nothing under share/labwc/ hardcodes a path: adjusting them is
# this script's job. Idempotent: safe to re-run.
#
# Usage: labwc-config.sh -i    install/refresh
#        labwc-config.sh -u    remove
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
readonly SCRIPT_DIR
RETROBOX_ROOTDIR="$(cd "${SCRIPT_DIR}/../.." >/dev/null 2>&1 && pwd -P)"
readonly RETROBOX_ROOTDIR

# shellcheck source=../lib/log.sh
source "${SCRIPT_DIR}/../lib/log.sh"

readonly RETROBOX_LABWC_DIR="${RETROBOX_ROOTDIR}/share/labwc"
readonly LABWC_CONFIG_DIR="${HOME}/.config/labwc"
readonly GO2TTY_TARGET="/usr/local/bin/go2tty"
readonly BASHRC_D_DIR="${HOME}/.bashrc.d"
readonly BASHRC_HOOK="${BASHRC_D_DIR}/64_retrobox"
readonly SUDOERS_FILE="/etc/sudoers.d/retrobox-go2tty"
readonly INSTALL_USER="$(id -un)"

# Path-free configs: symlinked, so edits in the repo apply right away.
readonly LABWC_LINKED_FILES=(
    "environment"
    "themerc-override"
)

# Templates with @RETROBOX_ROOT@: rendered as regular files.
# source-template:destination-name
readonly LABWC_TEMPLATES=(
    "rc.xml.in:rc.xml"
    "autostart.in:autostart"
)

readonly EXECUTABLES=(
    "go2tty"
    "retrobox-enter-tty"
    "retrobox-exit-tty"
    "retrobox-labwc-session"
    "retrobox-switch-display"
    "retrobox-switch-audio-out"
)

# render <template> <destination>
# Substitutes @RETROBOX_ROOT@ with this checkout's path.
function render_template() {
    local src="$1"
    local dst="$2"
    local escaped_root

    # Escape the sed replacement metacharacters that can appear in a path.
    escaped_root="${RETROBOX_ROOTDIR//\\/\\\\}"
    escaped_root="${escaped_root//|/\\|}"
    escaped_root="${escaped_root//&/\\&}"

    sed "s|@RETROBOX_ROOT@|${escaped_root}|g" "${src}" >"${dst}"
}

function install_labwc_config() {
    log_info "Linking labwc configs into ${LABWC_CONFIG_DIR}..."
    mkdir -p "${LABWC_CONFIG_DIR}"

    local name
    for name in "${LABWC_LINKED_FILES[@]}"; do
        ln -sf "${RETROBOX_LABWC_DIR}/${name}" "${LABWC_CONFIG_DIR}/${name}"
    done

    log_info "Rendering labwc templates with RETROBOX_ROOT=${RETROBOX_ROOTDIR}..."
    local pair src_name dst_name
    for pair in "${LABWC_TEMPLATES[@]}"; do
        src_name="${pair%%:*}"
        dst_name="${pair##*:}"
        # A leftover symlink from an older install would be followed.
        rm -f "${LABWC_CONFIG_DIR}/${dst_name}"
        render_template "${RETROBOX_LABWC_DIR}/${src_name}" \
            "${LABWC_CONFIG_DIR}/${dst_name}"
    done

    local exe
    for exe in "${EXECUTABLES[@]}"; do
        chmod +x "${RETROBOX_LABWC_DIR}/${exe}"
    done

    log_info "Installing go2tty to ${GO2TTY_TARGET}..."
    sudo ln -sf "${RETROBOX_LABWC_DIR}/go2tty" "${GO2TTY_TARGET}"

    install_bashrc_hook
    install_sudoers_rule

    log_ok "labwc config installed."
    log_warn "Autologin on the gaming TTY is still a manual, one-time step" \
        "— see the comment at the top of share/labwc/go2tty."
}

# retrobox-exit-tty (and go2tty itself) need root for chvt/systemctl, and
# the gaming TTY's autologin shell is a fresh, non-interactive session
# with no cached sudo ticket, so every VT switch would block on a
# password prompt nobody can answer. Grant NOPASSWD for exactly this one
# binary (any of its own arguments, since it needs the target TTY and
# sometimes -n) — nothing broader, and no other command gets NOPASSWD.
# True if sudo already lets INSTALL_USER run GO2TTY_TARGET without a
# password, from any existing rule anywhere in the sudoers config (this
# repo's own drop-in or one the user maintains by hand). Checked with
# "sudo -l" itself rather than by grepping files, so it reflects sudo's
# actual resolution (includes Defaults, groups, etc.) instead of a
# textual guess.
already_has_nopasswd_go2tty() {
    sudo -n -l -U "${INSTALL_USER}" 2>/dev/null |
        grep -qF "NOPASSWD: ${GO2TTY_TARGET}"
}

function install_sudoers_rule() {
    if already_has_nopasswd_go2tty; then
        log_info "${INSTALL_USER} already has passwordless sudo for" \
            "go2tty (found in the existing sudoers config); leaving it" \
            "as is."
        return 0
    fi

    log_info "Granting ${INSTALL_USER} passwordless sudo for go2tty..."

    local tmp
    tmp="$(mktemp)"
    printf '%s ALL=(root) NOPASSWD: %s\n' "${INSTALL_USER}" "${GO2TTY_TARGET}" >"${tmp}"

    if ! visudo -cf "${tmp}" >/dev/null 2>&1; then
        rm -f "${tmp}"
        log_err "generated sudoers rule failed validation; not installing it"
        log_warn "you'll be prompted for a password on every TTY switch" \
            "until this is fixed by hand."
        return 1
    fi

    sudo install -o root -g root -m 0440 "${tmp}" "${SUDOERS_FILE}"
    rm -f "${tmp}"
}

function uninstall_sudoers_rule() {
    # Only ours to remove; a rule the user set up by hand elsewhere is
    # left alone.
    [[ -e "${SUDOERS_FILE}" ]] || return 0
    log_info "Removing ${SUDOERS_FILE}..."
    sudo rm -f "${SUDOERS_FILE}"
}

function install_bashrc_hook() {
    log_info "Installing the session hook at ${BASHRC_HOOK}..."
    mkdir -p "${BASHRC_D_DIR}"
    rm -f "${BASHRC_HOOK}"
    render_template "${RETROBOX_LABWC_DIR}/bashrc-hook.in" "${BASHRC_HOOK}"
    # Executable: some ~/.bashrc.d loaders only pick up executable
    # fragments, and the hook carries a shebang.
    chmod 755 "${BASHRC_HOOK}"

    if ! grep -qs '\.bashrc\.d' "${HOME}/.bashrc"; then
        log_warn "${HOME}/.bashrc doesn't seem to source ~/.bashrc.d;" \
            "add something like:" \
            "for f in \"\${HOME}\"/.bashrc.d/*; do [ -r \"\${f}\" ] && . \"\${f}\"; done"
    fi
}

function uninstall_labwc_config() {
    log_info "Removing labwc config from ${LABWC_CONFIG_DIR}..."
    local name pair
    for name in "${LABWC_LINKED_FILES[@]}"; do
        rm -f "${LABWC_CONFIG_DIR}/${name}"
    done
    for pair in "${LABWC_TEMPLATES[@]}"; do
        rm -f "${LABWC_CONFIG_DIR}/${pair##*:}"
    done

    log_info "Removing ${BASHRC_HOOK}..."
    rm -f "${BASHRC_HOOK}"

    uninstall_sudoers_rule

    log_info "Removing ${GO2TTY_TARGET}..."
    sudo rm -f "${GO2TTY_TARGET}"

    log_ok "labwc config removed."
}

case "$1" in
    -i)
        install_labwc_config
        ;;
    -u)
        uninstall_labwc_config
        ;;
    *)
        log_err "Usage: $(basename "${BASH_SOURCE[0]}") -i|-u"
        exit 1
        ;;
esac
