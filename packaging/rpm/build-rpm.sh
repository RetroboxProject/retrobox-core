#!/usr/bin/env bash
# Build the retrobox-core .rpm (noarch), installing into /opt/retrobox.
#
#   packaging/rpm/build-rpm.sh [--version VERSION] [--outdir DIR]
#
# Needs: git, rpmbuild (package "rpm" on Debian/Ubuntu, "rpm-build" on Fedora).
# The tree is the same one the .deb ships (packaging/stage.sh). Version rules
# as in build-deb.sh; "-" becomes "~" so pre-releases sort before the final.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
SRC="$(cd "${HERE}/../.." >/dev/null 2>&1 && pwd -P)"

VERSION=""
OUTDIR="${SRC}/dist"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) VERSION="${2:?--version needs a value}"; shift 2 ;;
        --outdir)  OUTDIR="${2:?--outdir needs a value}"; shift 2 ;;
        -h|--help) sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

. "${SRC}/packaging/version.sh"
. "${SRC}/setup/lib/deps.sh"
[[ -n "${VERSION}" ]] || VERSION="$(derive_version "${SRC}")"
VERSION="${VERSION//-/\~}"
if [[ ! "${VERSION}" =~ ^[0-9][A-Za-z0-9.+~]*$ ]]; then
    echo "build-rpm.sh: '${VERSION}' is not a valid RPM version" >&2
    exit 1
fi
command -v rpmbuild >/dev/null || { echo "build-rpm.sh: rpmbuild not found" >&2; exit 1; }

SOURCE_DATE_EPOCH="$(git -C "${SRC}" log -1 --format=%ct)"
export SOURCE_DATE_EPOCH

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT
STAGE="${WORK}/stage"
PKG_VERSION="${VERSION}" "${SRC}/packaging/stage.sh" "${STAGE}" >/dev/null

# Spec: dependency lines come from setup/deps/fedora.list (single source).
REQUIRES="$(deps_list "${SRC}/setup/deps/fedora.list" | sed 's/^/Requires:       /')"
RECOMMENDS="$(deps_list "${SRC}/setup/deps/recommended-fedora.list" | sed 's/^/Recommends:     /')"
spec="$(<"${HERE}/retrobox-core.spec")"
spec="${spec//@VERSION@/${VERSION}}"
spec="${spec//@REQUIRES@/${REQUIRES}}"
spec="${spec//@RECOMMENDS@/${RECOMMENDS}}"
spec="${spec//@CHANGELOG_DATE@/$(LC_ALL=C date -u -d "@${SOURCE_DATE_EPOCH}" '+%a %b %d %Y')}"
printf '%s\n' "${spec}" > "${WORK}/retrobox-core.spec"

mkdir -p "${OUTDIR}"
rpmbuild -bb "${WORK}/retrobox-core.spec" \
    --define "_topdir ${WORK}/rpmbuild" \
    --define "stagedir ${STAGE}" \
    --define "_rpmdir ${OUTDIR}" \
    --define "_build_name_fmt %%{NAME}-%%{VERSION}-%%{RELEASE}.%%{ARCH}.rpm" \
    --define "_buildhost retrobox-build" \
    --define "use_source_date_epoch_as_buildtime 1" \
    --define "clamp_mtime_to_source_date_epoch 1" \
    --define "source_date_epoch_from_changelog 0" \
    >"${WORK}/rpmbuild.log" 2>&1 || { cat "${WORK}/rpmbuild.log" >&2; exit 1; }

echo "build-rpm.sh: built ${OUTDIR}/retrobox-core-${VERSION}-1.noarch.rpm"
