#!/usr/bin/env bash
# Smoke test for the retrobox-core .rpm. Meant for a throwaway container/VM:
# it installs the package system-wide and purges it afterwards.
#
#   sudo packaging/rpm/smoke-test.sh path/to/retrobox-core-X.x86_64.rpm
#
# Checks, in order:
#   1. dnf resolves every Requires from the distro's own repositories.
#   2. /usr/bin/retrobox works through its symlink.
#   3. As an UNPRIVILEGED user (so /opt/retrobox is effectively read-only),
#      `retrobox` warns that EmulationStation is missing, generates its
#      configuration under that user's XDG directories and fails only
#      because the EmulationStation binary isn't part of this package,
#      which is the expected outcome.
#   4. Nothing was written inside /opt/retrobox while doing so.
#   5. Removing the package removes /opt/retrobox completely.
set -euo pipefail

RPM="${1:?usage: $(basename "$0") path/to/retrobox-core.rpm}"
[[ "${EUID}" -eq 0 ]] || { echo "smoke-test: run as root" >&2; exit 1; }

fail() { echo "SMOKE TEST FAILED: $*" >&2; exit 1; }

dnf install -y -q util-linux
dnf install -y -q --setopt=install_weak_deps=False "$(readlink -f "${RPM}")"

echo "--- /usr/bin/retrobox --help / --version"
retrobox --help | head -3
retrobox --version
[[ -f /etc/retrobox/retrobox.ini ]] || fail "/etc/retrobox/retrobox.ini was not installed"
rpm -qc retrobox-core | grep -qx /etc/retrobox/retrobox.ini \
    || fail "/etc/retrobox/retrobox.ini is not a config file of the package"

echo "--- startup as an unprivileged user"
user_home="$(mktemp -d)"
chown nobody "${user_home}"
set +e
output="$(runuser -u nobody -- env -i HOME="${user_home}" PATH="${PATH}" \
    retrobox 2>&1)"
status=$?
set -e
echo "${output}" | tail -5

[[ "${status}" -eq 1 ]] || fail "expected exit code 1 (no EmulationStation binary), got ${status}"
grep -q "EmulationStation binary not found" <<<"${output}" \
    || fail "startup did not reach the 'binary not found' check"
grep -q "EmulationStation not found" <<<"${output}" \
    || fail "no up-front warning about the missing EmulationStation"
grep -qiE "first-time setup|Running platform setup" <<<"${output}" \
    && fail "retrobox ran a setup on launch"
[[ -d "${user_home}/.config/retrobox/frontend/.emulationstation" ]] \
    || fail "EmulationStation user dir was not created under ~/.config/retrobox"
[[ -f "${user_home}/.config/retrobox/frontend/.emulationstation/collections/now-playing.xcc" ]] \
    || fail "default EmulationStation collections were not seeded"
[[ -d "${user_home}/.local/share/retrobox/roms" ]] \
    || fail "default ROMs directory was not created under ~/.local/share/retrobox"
[[ -L "${user_home}/.local/share/retrobox/themes/es-theme-iconic" ]] \
    || fail "the shipped theme was not linked into ~/.local/share/retrobox/themes"
[[ ! -e "${user_home}/.config/retrobox/retrobox.ini" ]] \
    || fail "retrobox.ini must not be written by retrobox itself"

echo "--- installer helpers work from the read-only install"
as_user() { runuser -u nobody -- env -i HOME="${user_home}" PATH="${PATH}" "$@"; }
listing="$(as_user retrobox --setup-emulator 2>&1)"
grep -q retroarch <<<"${listing}" \
    || fail "retrobox --setup-emulator did not list the installers"

echo "--- layered configuration: /etc and ~/.config overrides"
as_user mkdir -p "${user_home}/.config/retrobox/retrobox.ini.d"
echo -e "[advanced]\nlabwc_tty = 7" > /etc/retrobox/retrobox.ini
cd /opt/retrobox
got="$(runuser -u nobody -- env -i HOME="${user_home}" PATH="${PATH}" \
    python3 -m runtime.paths --get advanced.labwc_tty)"
[[ "${got}" == "7" ]] || fail "/etc/retrobox/retrobox.ini was not honoured (got '${got}')"
echo -e "[advanced]\nlabwc_tty = 9" > "${user_home}/.config/retrobox/retrobox.ini.d/50-test.ini"
got="$(runuser -u nobody -- env -i HOME="${user_home}" PATH="${PATH}" \
    python3 -m runtime.paths --get advanced.labwc_tty)"
[[ "${got}" == "9" ]] || fail "the user's retrobox.ini.d drop-in did not override /etc (got '${got}')"
rm -f "${user_home}/.config/retrobox/retrobox.ini.d/50-test.ini"

echo "--- /opt/retrobox must not have been written to"
written="$(find /opt/retrobox -type f ! -name '*.pyc' -newer /opt/retrobox/VERSION)"
[[ -z "${written}" ]] || fail "files modified inside /opt/retrobox: ${written}"

echo "--- removal"
dnf remove -y -q retrobox-core
[[ ! -e /opt/retrobox ]] || fail "/opt/retrobox still exists after removal: $(ls -A /opt/retrobox)"
[[ ! -e /usr/bin/retrobox ]] || fail "/usr/bin/retrobox still exists after removal"

echo "SMOKE TEST OK"
