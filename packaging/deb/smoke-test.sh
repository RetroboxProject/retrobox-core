#!/usr/bin/env bash
# Smoke test for the retrobox .deb. Meant for a throwaway container/VM:
# it installs the package system-wide and purges it afterwards.
#
#   sudo packaging/deb/smoke-test.sh path/to/retrobox_X_amd64.deb
#
# Checks, in order:
#   1. apt resolves every Depends from the distro's own repositories.
#   2. /usr/bin/retrobox works through its symlink.
#   3. As an UNPRIVILEGED user (so /opt/retrobox is effectively read-only),
#      `retrobox` warns that EmulationStation is missing, generates its
#      configuration under that user's XDG directories and fails only
#      because the EmulationStation binary isn't part of this package,
#      which is the expected outcome.
#   4. Nothing was written inside /opt/retrobox while doing so.
#   5. Purging removes /opt/retrobox completely.
set -euo pipefail

DEB="${1:?usage: $(basename "$0") path/to/retrobox.deb}"
[[ "${EUID}" -eq 0 ]] || { echo "smoke-test: run as root" >&2; exit 1; }

fail() { echo "SMOKE TEST FAILED: $*" >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq "$(readlink -f "${DEB}")"

echo "--- /usr/bin/retrobox --help / --version"
retrobox --help | head -3
retrobox --version
[[ -f /etc/retrobox/retrobox.ini ]] || fail "/etc/retrobox/retrobox.ini was not installed"
grep -q '^/etc/retrobox/retrobox.ini$' /var/lib/dpkg/info/retrobox.conffiles \
    || fail "/etc/retrobox/retrobox.ini is not a conffile"

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
grep -q '^system.themes=/opt/retrobox/frontend/themes$' \
    "${user_home}/.config/retrobox/frontend/.emulationstation/emulationstation.ini" \
    || fail "emulationstation.ini does not point system.themes at the shipped themes"
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

echo "--- purge"
apt-get purge -y -qq retrobox
[[ ! -e /opt/retrobox ]] || fail "/opt/retrobox still exists after purge: $(ls -A /opt/retrobox)"
[[ ! -e /usr/bin/retrobox ]] || fail "/usr/bin/retrobox still exists after purge"

echo "SMOKE TEST OK"
