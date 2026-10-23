#!/usr/bin/env bash
# Build the install.sh payload: retrobox-linux-amd64.tar.gz (+ SHA256SUMS).
#
#   packaging/tarball/build-tarball.sh [--version VERSION] [--outdir DIR]
#
# Same file set as the .deb (it comes from packaging/stage.sh), laid out so
# install.sh can put each part where the target system wants it:
#
#   retrobox/            the project tree (-> the install prefix)
#   extras/udev/         udev rules
#   extras/etc/retrobox/ system-wide configuration template
#   extras/retrobox.desktop.in, extras/retrobox.svg
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
SRC="$(cd "${HERE}/../.." >/dev/null 2>&1 && pwd -P)"

VERSION=""
OUTDIR="${SRC}/dist"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) VERSION="${2:?--version needs a value}"; shift 2 ;;
        --outdir)  OUTDIR="${2:?--outdir needs a value}"; shift 2 ;;
        -h|--help) sed -n '2,5p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "${VERSION}" ]]; then
    if exact="$(git -C "${SRC}" describe --tags --exact-match --match 'v[0-9]*' 2>/dev/null)"; then
        VERSION="${exact#v}"
    else
        base="$(git -C "${SRC}" describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || true)"
        VERSION="${base#v}"
        VERSION="${VERSION:-0.0.0}+git$(date -u -d "@$(git -C "${SRC}" log -1 --format=%ct)" +%Y%m%d).$(git -C "${SRC}" rev-parse --short=7 HEAD)"
    fi
fi

SOURCE_DATE_EPOCH="$(git -C "${SRC}" log -1 --format=%ct)"
export SOURCE_DATE_EPOCH

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT
STAGE="${WORK}/stage"
TOP="${WORK}/retrobox-linux-amd64"

PKG_VERSION="${VERSION}" "${SRC}/packaging/stage.sh" "${STAGE}" >/dev/null

mkdir -p "${TOP}/extras/udev" "${TOP}/extras/etc"
mv "${STAGE}/opt/retrobox" "${TOP}/retrobox"
cp "${STAGE}"/usr/lib/udev/rules.d/*.rules "${TOP}/extras/udev/"
cp -a "${STAGE}/etc/retrobox" "${TOP}/extras/etc/retrobox"
cp "${SRC}/packaging/retrobox.desktop.in" "${TOP}/extras/retrobox.desktop.in"
cp "${STAGE}/usr/share/icons/hicolor/scalable/apps/retrobox.svg" "${TOP}/extras/retrobox.svg"

mkdir -p "${OUTDIR}"
OUT="${OUTDIR}/retrobox-linux-amd64.tar.gz"
tar --sort=name --owner=0 --group=0 --numeric-owner \
    --mtime="@${SOURCE_DATE_EPOCH}" -C "${WORK}" -cf - retrobox-linux-amd64 \
    | gzip -n -9 > "${OUT}"
(cd "${OUTDIR}" && sha256sum retrobox-linux-amd64.tar.gz > SHA256SUMS)

echo "build-tarball.sh: built ${OUT} (version ${VERSION})"
