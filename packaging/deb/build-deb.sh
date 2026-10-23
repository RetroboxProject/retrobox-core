#!/usr/bin/env bash
# Build the retrobox .deb (amd64), installing into /opt/retrobox.
#
#   packaging/deb/build-deb.sh [--version VERSION] [--outdir DIR]
#
# Needs: git, dpkg-deb. Submodules must be initialised beforehand if they
# are meant to be in the package (see packaging/stage.sh).
#
# Version, when --version is not given:
#   HEAD is tagged vX.Y.Z      -> X.Y.Z
#   otherwise                  -> <last tag, or 0.0.0>+git<YYYYMMDD>.<sha>
# Hyphens become "~" (v1.0.0-rc1 -> 1.0.0~rc1) so pre-releases sort before
# the final release, as Debian expects for a package without revision.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
SRC="$(cd "${HERE}/../.." >/dev/null 2>&1 && pwd -P)"

VERSION=""
OUTDIR="${SRC}/dist"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) VERSION="${2:?--version needs a value}"; shift 2 ;;
        --outdir)  OUTDIR="${2:?--outdir needs a value}"; shift 2 ;;
        -h|--help) sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

derive_version() {
    local exact base sha date
    if exact="$(git -C "${SRC}" describe --tags --exact-match --match 'v[0-9]*' 2>/dev/null)"; then
        echo "${exact#v}"
        return
    fi
    base="$(git -C "${SRC}" describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || true)"
    base="${base#v}"
    sha="$(git -C "${SRC}" rev-parse --short=7 HEAD)"
    date="$(date -u -d "@$(git -C "${SRC}" log -1 --format=%ct)" +%Y%m%d)"
    echo "${base:-0.0.0}+git${date}.${sha}"
}

[[ -n "${VERSION}" ]] || VERSION="$(derive_version)"
VERSION="${VERSION//-/\~}"
if [[ ! "${VERSION}" =~ ^[0-9][A-Za-z0-9.+~]*$ ]]; then
    echo "build-deb.sh: '${VERSION}' is not a valid Debian version" >&2
    exit 1
fi

# Reproducible mtimes inside the archive.
SOURCE_DATE_EPOCH="$(git -C "${SRC}" log -1 --format=%ct)"
export SOURCE_DATE_EPOCH

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT
PKG="${WORK}/retrobox_${VERSION}_amd64"

PKG_VERSION="${VERSION}" "${SRC}/packaging/stage.sh" "${PKG}"

mkdir -p "${PKG}/DEBIAN"
INSTALLED_SIZE="$(du -sk --exclude=DEBIAN "${PKG}" | cut -f1)"
. "${SRC}/setup/lib/deps.sh"
DEPENDS="$(deps_debian_depends "${SRC}/setup/deps/debian.list")"
RECOMMENDS="$(deps_debian_depends "${SRC}/setup/deps/recommended-debian.list")"
# (parameter expansion rather than sed: the Depends lines contain "|")
control="$(<"${HERE}/control.in")"
control="${control//@VERSION@/${VERSION}}"
control="${control//@INSTALLED_SIZE@/${INSTALLED_SIZE}}"
control="${control//@DEPENDS@/${DEPENDS}}"
control="${control//@RECOMMENDS@/${RECOMMENDS}}"
printf '%s\n' "${control}" > "${PKG}/DEBIAN/control"
for script in postinst prerm postrm; do
    install -m 755 "${HERE}/${script}" "${PKG}/DEBIAN/${script}"
done
(cd "${PKG}" && find . -type f ! -path './DEBIAN/*' -printf '%P\0' | sort -z | xargs -0 md5sum) \
    > "${PKG}/DEBIAN/md5sums"
chmod 644 "${PKG}/DEBIAN/md5sums"
# /etc files are conffiles: dpkg keeps the admin's edits on upgrade.
(cd "${PKG}" && find etc -type f -printf '/%p\n') > "${PKG}/DEBIAN/conffiles"
chmod 644 "${PKG}/DEBIAN/conffiles"

mkdir -p "${OUTDIR}"
DEB="${OUTDIR}/retrobox_${VERSION}_amd64.deb"
dpkg-deb --root-owner-group -Zxz --build "${PKG}" "${DEB}"

echo "build-deb.sh: built ${DEB}"
