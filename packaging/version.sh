# shellcheck shell=bash
# Version derivation shared by the package builders. Source it:
#   . packaging/version.sh; VERSION="$(derive_version "${SRC}")"
#
#   HEAD is tagged vX.Y.Z      -> X.Y.Z
#   otherwise                  -> <last tag, or 0.0.0>+git<YYYYMMDD>.<sha>
derive_version() {
    local src="$1" exact base sha date
    if exact="$(git -C "${src}" describe --tags --exact-match --match 'v[0-9]*' 2>/dev/null)"; then
        echo "${exact#v}"
        return
    fi
    base="$(git -C "${src}" describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || true)"
    base="${base#v}"
    sha="$(git -C "${src}" rev-parse --short=7 HEAD)"
    date="$(date -u -d "@$(git -C "${src}" log -1 --format=%ct)" +%Y%m%d)"
    echo "${base:-0.0.0}+git${date}.${sha}"
}
