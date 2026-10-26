# Dependency lists (tools/deps/*.list), shared by setup-*.sh, install.sh and
# the .deb build, so the package names live in exactly one place.
#
#   deps_list <file>             package lines, comments/blank lines removed
#                                ("a | b" alternatives kept as written)
#   deps_apt_args <file>         one installable apt package per line: for an
#                                alternative, the first one apt knows about
#   deps_debian_depends <file>   the lines joined as a Depends: field value

deps_list() {
    sed -e 's/#.*//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' "$1" | grep -v '^$' || true
}

deps_apt_args() {
    local line alt
    while IFS= read -r line; do
        if [[ "${line}" == *"|"* ]]; then
            local picked=""
            while IFS= read -r alt; do
                alt="${alt// /}"
                if [[ -z "${picked}" ]] && apt-cache show "${alt}" >/dev/null 2>&1; then
                    picked="${alt}"
                fi
            done < <(tr '|' '\n' <<<"${line}")
            [[ -n "${picked}" ]] && echo "${picked}"
        else
            echo "${line}"
        fi
    done < <(deps_list "$1")
}

deps_debian_depends() {
    deps_list "$1" | paste -sd, - | sed 's/,/, /g'
}
