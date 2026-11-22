# shellcheck shell=bash
# Shared code of the emulator installers (tools/emulators/<name>.sh).
#
# An installer sets who it installs, defines the install methods it has and
# hands over to installer_main:
#
#   EMULATOR="dolphin-emu"      its folder: <emulators>/dolphin-emu
#   LABEL="Dolphin"             its name in messages
#   source "<root>/tools/lib/installer.sh"
#   install_appimage() { ...; }   the release AppImage, extracted
#   install_archive()  { ...; }   a prebuilt release archive (tarball, zip)
#   install_source()   { ...; }   a build from source
#   installer_main "$@"
#
# Options (the same for every installer):
#   -i   install with the best method this machine can use, in this order:
#        the extracted AppImage, the release archive, the source build
#   -a   only the AppImage        -t   only the archive        -s   only the source build
#   -u   uninstall: the program goes, the configuration and saves stay
#   -l   print the methods the installer has, in that order
#
# A method installs into ${STAGE} (an empty folder) and returns. installer_main
# then swaps it in as <emulators>/<EMULATOR>/app in one rename, so a failed
# install keeps the installed version working. When a method can't be used here
# (no build for this architecture) it calls `unavailable "why"`: -i then
# tries the next method. Any other failure stops the install.
#
# Optional, set by the installer before installer_main:
#   PORTABLE=1        the emulator keeps its data next to the executable
#                     (Redream, Supermodel): the program files are copied to
#                     the top of its folder instead of app/, and listed in
#                     .retrobox-files so -u removes exactly those
#   KEEP=(...)        with PORTABLE: files never overwritten once they exist
#   LEGACY=(...)      files or folders of older layouts, relative to the
#                     emulator's folder, removed by an install and by -u
#   after_install()   run once the new version is in place
#   before_uninstall()
#
# Environment:
#   JOBS                            parallel build jobs (default: nproc)
#   KEEP_SRC=1                      keep the source tree of a build
#   NO_SYSROOT=1                    fail when apt cannot install a package,
#                                   instead of building against its files
#                                   unpacked in a folder of their own
#   GITHUB_TOKEN                    used for the GitHub API (rate limits)
#   RETROBOX_EMULATORS_FINAL_DIR    where the install ends up when
#                                   RETROBOX_EMULATORS_DIR is a staging
#                                   folder (an update): builds bake it in
set -euo pipefail
_INSTALLER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." >/dev/null 2>&1 && pwd -P)"
# shellcheck source=tools/lib/paths.sh
source "${_INSTALLER_ROOT}/tools/lib/paths.sh"
# shellcheck source=tools/lib/log.sh
source "${_INSTALLER_ROOT}/tools/lib/log.sh"
: "${EMULATOR:?the installer must set EMULATOR before sourcing installer.sh}"
: "${LABEL:=${EMULATOR}}"
: "${PORTABLE:=0}"
[[ -v KEEP ]] || KEEP=()
[[ -v LEGACY ]] || LEGACY=()
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/${EMULATOR}"
APP_DIR="${INSTALL_DIR}/app"
STAGE="${INSTALL_DIR}/app.new"
# the app folder where the install will finally live (an update stages it elsewhere)
FINAL_APP_DIR="${RETROBOX_EMULATORS_FINAL_DIR:-${RETROBOX_EMULATORS_DIR}}/${EMULATOR}/app"
SRC_DIR="${RETROBOX_EMULATORS_DIR}/_src/${EMULATOR}"
JOBS="${JOBS:-$(nproc)}"
KEEP_SRC="${KEEP_SRC:-0}"
_MANIFEST="${INSTALL_DIR}/.retrobox-files"
_METHODS=(appimage archive source)
_UNAVAILABLE=2
case "$(uname -m)" in
    x86_64 | amd64) ARCH="x86_64" ;;
    aarch64 | arm64) ARCH="aarch64" ;;
    *) ARCH="$(uname -m)" ;;
esac
# shellcheck disable=SC2034  # read by the installers
readonly ARCH
SUDO=""
if [[ "${EUID}" -ne 0 ]]; then
    SUDO="sudo"
fi
# The output of apt and dpkg is parsed below ("Candidate:", the lines of the
# solver's errors...), and apt translates it ("Candidato:" in Spanish). Every
# call whose output is read goes through this prefix, which forces the
# untranslated text. `env` (not a plain assignment) so that it also survives
# sudo, which cleans the environment. LANGUAGE is set too: gettext gives it
# priority over the locale variables in locales other than "C".
_C_ENV=(env LC_ALL=C LANGUAGE=C)
TMP_DIR="$(mktemp -d)"
_STAGING=0
# shellcheck disable=SC2329  # called by the EXIT trap
function _cleanup() {
    rm -rf "${TMP_DIR}"
    # an install that did not get to the end leaves nothing behind
    if [[ "${_STAGING}" == "1" ]]; then
        rm -rf "${STAGE}"
        [[ "${KEEP_SRC}" == "1" ]] || rm -rf "${SRC_DIR}"
        rmdir "${INSTALL_DIR}" 2>/dev/null || true
    fi
}
trap _cleanup EXIT
## Messages ----------------------------------------------------------------
function die() {
    log_err "$*"
    exit 1
}
# This method can't be used on this machine: -i goes on with the next one.
function unavailable() {
    log_warn "$*" >&2
    exit "${_UNAVAILABLE}"
}
## Packages ----------------------------------------------------------------
function package_manager() {
    if command -v apt-get &>/dev/null; then
        echo "apt"
    elif command -v dnf &>/dev/null; then
        echo "dnf"
    else
        echo "unknown"
    fi
}
# The package checks are two commands for the whole list, not one command per
# package: a single `apt-cache show` took long enough on a slow disk (the
# Switch's SD card) to look like a hung installer, and nothing was printed
# while it ran. Both fill a global associative array, read by install_packages.
declare -gA _INSTALLED=() _CANDIDATE=()
# _read_installed <packages...>: installed version of each (empty when it isn't).
function _read_installed() {
    _INSTALLED=()
    [[ $# -gt 0 ]] || return 0
    local line name version status
    while IFS= read -r line; do
        # the three words dpkg keeps: what was asked for, how it went, what is
        # on the disk now ("install ok installed", "hold ok installed"...)
        name="${line%% *}"
        version="${line#* }"
        status="${version#* }"
        version="${version%% *}"
        # every state dpkg leaves files in, but a half-installed package
        case "${status}" in
            *ok\ installed | *ok\ unpacked | *ok\ half-configured)
                _INSTALLED["${name}"]="${version}"
                ;;
        esac
    done < <("${_C_ENV[@]}" dpkg-query -W -f='${Package} ${Version} ${Status}\n' "$@" 2>/dev/null)
    return 0
}
# _read_candidates <packages...>: version apt would install for each
# (empty when no repository has it).
function _read_candidates() {
    _CANDIDATE=()
    [[ $# -gt 0 ]] || return 0
    local name="" line
    while IFS= read -r line; do
        if [[ "${line}" != [[:space:]]* ]]; then
            name="${line%%:*}"
        elif [[ -n "${name}" && "${line}" == *"Candidate:"* ]]; then
            line="${line#*Candidate:}"
            line="${line## }"
            [[ "${line}" == "(none)" ]] || _CANDIDATE["${name}"]="${line}"
            name=""
        fi
    done < <("${_C_ENV[@]}" apt-cache policy "$@" 2>/dev/null)
    return 0
}
# _apt_versions <packages...>: every version of every package the lists have,
# newest first, as "package version" lines (the version table apt-cache policy
# prints, whose order is apt's own).
function _apt_versions() {
    [[ $# -gt 0 ]] || return 0
    "${_C_ENV[@]}" apt-cache policy "$@" 2>/dev/null | awk '
        # "name:" starts a package, "  1.2-3 500" is a version of it, and
        # "*** 1.2-3 500" is the installed one (the first the lists have of it)
        /^[[:space:]]*\*\*\*/ { if (name != "") print name, $2; next }
        /^[^[:space:]]/ { if ($1 ~ /:$/) name = substr($1, 1, length($1) - 1); next }
        NF >= 2 && $2 ~ /^[0-9]/ && $1 !~ /:$/ { if (name != "") print name, $1 }
    '
    return 0
}
function _apt_has_version() {
    local pkg="$1" target="$2" line
    while IFS= read -r line; do
        [[ "${line}" == "${pkg} ${target}" ]] && return 0
    done < <(_apt_versions "${pkg}")
    return 1
}
# _apt_pin_pairs <apt output>: "package version" lines where apt says a
# package failed because its candidate asks for another version of a library
# than the one the system already runs ("pkg : Depends: lib (= a) but b is to
# be installed").
function _apt_pin_pairs() {
    awk '
        /^[[:space:]]+[a-z0-9][a-z0-9.+:-]*[[:space:]]*:[[:space:]]*(Pre-?)?Depends:/ {
            pkg = $1
            sub(/:.*/, "", pkg)
        }
        !/Depends:/ { pkg = "" }
        /Depends:.*but [^[:space:]]+ is to be installed/ && pkg != "" {
            for (i = 1; i <= NF; i++) {
                if ($i == "but" && (i + 1) <= NF) {
                    print pkg, $(i + 1)
                    break
                }
            }
        }
    ' <<<"$1" | sort -u
    return 0
}
# _apt_pin_mismatched <packages...>: when a repository with higher priority
# (such as the L4T repo on Nintendo Switch images) makes apt pick a "-l4t"
# candidate of a -dev package while the system runs the distribution's newer
# runtime library, and the matching version of that -dev package is also in the
# repositories, pin `<pkg>=<installed_runtime_version>` so apt installs it
# cleanly. Fills _PINNED_WANTED and returns 0 when the list resolves.
declare -ga _PINNED_WANTED=()
function _apt_pin_mismatched() {
    _PINNED_WANTED=("$@")
    [[ ${#_PINNED_WANTED[@]} -gt 0 ]] || return 0
    local round=0 output="" status=0 pkg ver dep sub_out changed i
    local -A pinned=()
    while [[ "${round}" -lt 8 ]]; do
        round=$((round + 1))
        status=0
        output="$(${SUDO} "${_C_ENV[@]}" apt-get install -y -s "${_PINNED_WANTED[@]}" 2>&1)" || status=$?
        [[ "${status}" -eq 0 ]] && return 0
        changed=0
        while read -r pkg ver; do
            [[ -n "${pkg}" && -n "${ver}" ]] || continue
            [[ -v pinned["${pkg}"] ]] && continue
            if _apt_has_version "${pkg}" "${ver}"; then
                pinned["${pkg}"]="${ver}"
                log_info "Selecting ${pkg}=${ver} to match the installed system library."
                local found=0
                for i in "${!_PINNED_WANTED[@]}"; do
                    if [[ "${_PINNED_WANTED[${i}]%%=*}" == "${pkg}" ]]; then
                        _PINNED_WANTED[i]="${pkg}=${ver}"
                        found=1
                        break
                    fi
                done
                [[ "${found}" -eq 1 ]] || _PINNED_WANTED+=("${pkg}=${ver}")
                changed=1
            fi
        done < <(
            _apt_pin_pairs "${output}"
            while IFS= read -r dep; do
                [[ -n "${dep}" ]] || continue
                sub_out="$(${SUDO} "${_C_ENV[@]}" apt-get install -y -s "${dep}" 2>&1 || true)"
                _apt_pin_pairs "${sub_out}"
            done < <(
                awk '
                    /Depends:.*but it is not going to be installed/ {
                        for (i = 1; i <= NF; i++) {
                            if ($i ~ /^(Pre-?)?Depends:$/) {
                                dep = $(i + 1)
                                sub(/:.*/, "", dep)
                                print dep
                                break
                            }
                        }
                    }
                ' <<<"${output}" | sort -u | head -n 6
            )
        )
        [[ "${changed}" -eq 1 ]] || return 1
    done
    status=0
    ${SUDO} "${_C_ENV[@]}" apt-get install -y -s "${_PINNED_WANTED[@]}" &>/dev/null || status=$?
    [[ "${status}" -eq 0 ]]
}
# _apt_update_once: the lists are read before the packages are chosen, so a
# first install does not pick from whatever the last `apt-get update` left.
function _apt_update_once() {
    [[ -z "${_APT_UPDATED:-}" ]] || return 0
    _APT_UPDATED=1
    log_info "Updating the package lists (apt-get update)..."
    ${SUDO} apt-get update -qq || log_warn "apt-get update failed: the lists already there are used."
    return 0
}
# _apt_broken <packages...>: what apt makes of the list, before anything is
# downloaded. Prints the packages the failure is about, one per line:
#   0  apt cannot install these (each one fails on its own too)
#   2  apt cannot install the list, and no package of it is to blame
#   1  the list resolves
# apt's own answer goes to stderr as it comes. The solver then runs again for
# the packages apt's answer names (a few, not the whole list: it is slow), so
# a package that is only the victim of another one is not reported and is
# installed with the rest.
function _apt_broken() {
    local output="" status=0 package base suspect tries=0 confirmed=0
    local -a offenders=()
    output="$(${SUDO} "${_C_ENV[@]}" apt-get install -y -s "$@" 2>&1)" || status=$?
    [[ "${status}" -eq 0 ]] && return 1
    printf '%s\n' "${output}" >&2
    # the packages apt could not work with, as its answer names them (the
    # lines are the same in every language: only the words around them change)
    local -a suspects=()
    while IFS= read -r suspect; do
        [[ -n "${suspect}" ]] || continue
        for package in "$@"; do
            base="${package%%=*}"
            [[ "${base}" == "${suspect}" ]] || continue
            [[ " ${suspects[*]-} " == *" ${base} "* ]] || suspects+=("${base}")
        done
    done < <(
        {
            sed -n 's/^[[:space:]]*\([a-z0-9][a-z0-9.+-]*\)[[:space:]]*:.*/\1/p' <<<"${output}"
            sed -n 's/.*[[:space:]]\([a-z0-9][a-z0-9.+-]*\)[[:space:]][^[:space:]]*$/\1/p' <<<"${output}"
        } | grep -E '^[a-z0-9][a-z0-9.+-]*$' | sort -u
    )
    # nothing was named: the packages asked for are the suspects (the loop
    # below stops after six of them, so a long list stays affordable)
    if [[ ${#suspects[@]} -eq 0 ]]; then
        for package in "$@"; do
            suspects+=("${package%%=*}")
        done
    fi
    for suspect in "${suspects[@]}"; do
        [[ "${tries}" -lt 6 ]] || break
        tries=$((tries + 1))
        log_info "Asking apt about ${suspect} on its own..." >&2
        if ! ${SUDO} "${_C_ENV[@]}" apt-get install -y -s "${suspect}" &>/dev/null; then
            offenders+=("${suspect}")
            confirmed=1
        fi
    done
    [[ "${confirmed}" -eq 1 ]] || return 2
    printf '%s\n' "${offenders[@]}"
    return 0
}
# _runtime_names <development package>: the names the library it develops can
# have (libx11-dev -> libx11, libx11-6, libx110, libx111, libx11t64).
function _runtime_names() {
    printf '%s\n' "${1%-dev}" "${1%-dev}-6" "${1%-dev}0" "${1%-dev}1" "${1%-dev}t64"
    return 0
}
# _apt_hint <package>: one line about the usual reason apt cannot install it,
# when the lists show that reason: a repository other than the distribution's
# (the L4T one of the Nintendo Switch images) winning the choice of a library
# the system already runs, at a version that does not fit it.
function _apt_hint() {
    local candidate installed="" suffix name
    local -a runtimes=()
    candidate="${_CANDIDATE[$1]:-}"
    mapfile -t runtimes < <(_runtime_names "$1")
    _read_installed "${runtimes[@]}"
    for name in "${runtimes[@]}"; do
        if [[ -n "${_INSTALLED[${name}]:-}" ]]; then
            installed="${_INSTALLED[${name}]}"
            break
        fi
    done
    [[ -n "${candidate}" && -n "${installed}" ]] || return 0
    suffix="${candidate##*-}"
    [[ "${suffix}" == *"${installed##*-}" ]] && return 0
    log_warn "apt picks ${candidate} of $1 (a '${suffix}' build), not the one that goes with the"
    log_warn "${installed} the system runs: that version asks for its own library, and apt has none."
    return 0
}
# _runtime_of <development package>: the version installed of the library it
# develops (libx11-dev -> libx11-6, libgl-dev -> libgl1, libfoo-dev -> libfoo0),
# which is the version its headers have to match. Empty when it is not there.
function _runtime_of() {
    local runtime
    while IFS= read -r runtime; do
        _read_installed "${runtime}"
        if [[ -n "${_INSTALLED[${runtime}]:-}" ]]; then
            printf '%s' "${_INSTALLED[${runtime}]}"
            return 0
        fi
    done < <(_runtime_names "$1")
    return 0
}
# _depends_of <packages...>: the names their Depends and Pre-Depends ask for,
# one per line, versions dropped, alternatives kept in their order ("a", then
# "b" of "a | b"): the caller takes the first one apt has.
function _depends_of() {
    [[ $# -gt 0 ]] || return 0
    "${_C_ENV[@]}" apt-cache show "$@" 2>/dev/null |
        sed -n 's/^\(Pre-\)\?Depends: //p' |
        tr ',' '\n' |
        sed -e 's/([^)]*)//g' -e 's/:[a-z0-9-]*$//' \
            -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' |
        tr -s ' ' '\n' |
        sed -e '/^$/d'
    return 0
}
# _provides_of <packages...>: "package provided-name" for every virtual package
# they provide, so a dependency on one (xorg-dev) is known to be covered.
function _provides_of() {
    [[ $# -gt 0 ]] || return 0
    "${_C_ENV[@]}" apt-cache show "$@" 2>/dev/null | awk '
        /^Package: / { pkg = $2 }
        /^Provides: / {
            line = substr($0, 10)
            gsub(/\([^)]*\)/, "", line)
            n = split(line, parts, /[ ,]+/)
            for (i = 1; i <= n; i++) if (parts[i] != "") print pkg, parts[i]
        }
    '
    return 0
}
# _apt_sysroot <packages...>: the files of packages apt refuses to install,
# unpacked in a folder of their own for the build to compile against.
#
# Some systems cannot install a development package at all: a repository next
# to the distribution's own (the L4T one of the Nintendo Switch images, with
# its libx11 tied to its own libx11-6) leaves apt with dependencies it cannot
# satisfy, whatever it is asked for. Installing those packages is not the
# installer's business, and a build only needs their headers and libraries:
# they are downloaded (which resolves nothing, so it works where `install`
# does not), unpacked outside the system, and the compiler and cmake are
# pointed at them. The system itself is left exactly as it was.
#
# Returns 1 when it could not help (the caller then fails the install).
function _apt_sysroot() {
    [[ "${NO_SYSROOT:-0}" == "1" ]] && return 1
    command -v dpkg-deb &>/dev/null || return 1
    local sysroot="${TMP_DIR}/sysroot" debs="${TMP_DIR}/sysroot-debs"
    local package dependency provided spec version runtime="" status=0
    local -a names=() versions=() round=() dependencies=()
    declare -A have=() pick=() taken=() provides=()
    # What is unpacked: the packages themselves and the dependencies the system
    # does not have, two levels deep (a development package, and the development
    # packages it needs, which is where the headers and the .so links are). What
    # the system has is left out: a second copy of a library in the sysroot is a
    # second chance of linking against the wrong one. apt is not asked to plan
    # the install, which is exactly what it cannot do here.
    _read_installed "$@"
    for package in "$@"; do
        have["${package}"]="${_INSTALLED[${package}]:-}"
        taken["${package}"]=1
        names+=("${package}")
    done
    round=("$@")
    # two rounds: the packages, then the packages they need
    local rounds=2
    while [[ "${rounds}" -gt 0 ]]; do
        rounds=$((rounds - 1))
        [[ ${#round[@]} -gt 0 ]] || break
        dependencies=()
        while IFS= read -r dependency; do
            [[ -n "${dependency}" ]] || continue
            # an alternative of a dependency already taken is not needed twice
            [[ "${dependency}" == "|" ]] && continue
            [[ -v taken["${dependency}"] ]] && continue
            taken["${dependency}"]=1
            dependencies+=("${dependency}")
        done < <(_depends_of "${round[@]}")
        [[ ${#dependencies[@]} -gt 0 ]] || break
        _read_installed "${dependencies[@]}"
        _read_candidates "${dependencies[@]}"
        # the virtual packages the ones already chosen cover
        while read -r package provided; do
            [[ -n "${provided}" ]] || continue
            [[ -v provides["${provided}"] ]] || provides["${provided}"]="${package}"
        done < <(_provides_of "${names[@]}" "${dependencies[@]}")
        round=()
        for dependency in "${dependencies[@]}"; do
            if [[ -n "${_INSTALLED[${dependency}]:-}" ]]; then
                have["${dependency}"]="${_INSTALLED[${dependency}]}"
                continue
            fi
            if [[ -z "${_CANDIDATE[${dependency}]:-}" ]]; then
                # a name no package has: a virtual one, covered or not
                if [[ -v provides["${dependency}"] ]]; then
                    log_info "${dependency} is provided by ${provides[${dependency}]}, already there."
                else
                    log_warn "Nothing in apt provides ${dependency}: the build may miss it."
                fi
                continue
            fi
            have["${dependency}"]=""
            names+=("${dependency}")
            round+=("${dependency}")
        done
    done
    # Which version of each: apt would hand over the one its preferences pick,
    # and that is the very one that does not fit the system (the L4T libx11-dev
    # of the Switch images, tied to its own libx11-6). The headers have to be
    # those of the library the system runs, so that version is looked for in the
    # lists; the newest one is the fallback.
    mapfile -t versions < <(_apt_versions "${names[@]}")
    for package in "${names[@]}"; do
        runtime="${have[${package}]:-}"
        [[ -n "${runtime}" ]] || runtime="$(_runtime_of "${package}")"
        pick["${package}"]=""
        for version in "${versions[@]}"; do
            [[ "${version%% *}" == "${package}" ]] || continue
            version="${version#* }"
            if [[ -z "${pick[${package}]}" ]]; then
                pick["${package}"]="${version}"    # the newest the lists have
            fi
            if [[ -n "${runtime}" && "${version}" == "${runtime}" ]]; then
                pick["${package}"]="${version}"    # the one the system runs
                break
            fi
        done
    done
    log_warn "That is the system's own doing, not ${LABEL}'s: either a repository next to"
    log_warn "the distribution's offers the same libraries at versions that cannot be"
    log_warn "together ('apt-cache policy $1' says which one wins, and the files in"
    log_warn "/etc/apt/preferences.d why), or they are held broken ('apt-get check')."
    if [[ ${#names[@]} -gt 40 ]]; then
        log_warn "That is ${#names[@]} packages: only the first 40 are unpacked."
        names=("${names[@]:0:40}")
    fi
    log_info "Unpacking ${#names[@]} packages into a build sysroot: ${names[*]}"
    mkdir -p "${debs}" "${sysroot}"
    status=0
    for package in "${names[@]}"; do
        spec="${package}"
        [[ -n "${pick[${package}]:-}" ]] && spec="${package}=${pick[${package}]}"
        log_info "Downloading ${spec}"
        (cd "${debs}" && apt-get download "${spec}") || status=1
    done
    if [[ "${status}" -ne 0 ]]; then
        log_warn "Some of those packages could not be downloaded."
    fi
    local deb found=0
    for deb in "${debs}"/*.deb; do
        [[ -f "${deb}" ]] || continue
        dpkg-deb -x "${deb}" "${sysroot}" || log_warn "Could not unpack ${deb##*/}."
        found=1
    done
    [[ "${found}" -eq 1 ]] || return 1
    # A -dev package ships a relative symlink (libX11.so -> libX11.so.6.4.0)
    # whose target belongs to the runtime package installed in /usr/lib, not
    # in the sysroot: point dangling symlinks at the host library when it is
    # there, so the linker and cmake's find_library see a valid file.
    local link target host_target
    if [[ -d "${sysroot}/usr/lib" ]]; then
        while IFS= read -r -d '' link; do
            [[ -e "${link}" ]] && continue
            target="$(readlink "${link}")"
            if [[ "${target}" == /* ]]; then
                host_target="${target}"
            else
                host_target="$(dirname "/${link#"${sysroot}/"}")/${target}"
            fi
            if [[ -e "${host_target}" ]]; then
                ln -snf "${host_target}" "${link}"
            fi
        done < <(find "${sysroot}/usr/lib" -type l -print0 2>/dev/null)
    fi
    # where the compiler and cmake look from now on (this build only)
    local multiarch="" directory
    multiarch="$(dpkg-architecture -qDEB_HOST_MULTIARCH 2>/dev/null || true)"
    [[ -n "${multiarch}" ]] || multiarch="$(gcc -dumpmachine 2>/dev/null || true)"
    _prepend_path CPATH "${sysroot}/usr/include"
    [[ -n "${multiarch}" ]] && _prepend_path CPATH "${sysroot}/usr/include/${multiarch}"
    _prepend_path LIBRARY_PATH "${sysroot}/usr/lib"
    _prepend_path PKG_CONFIG_PATH "${sysroot}/usr/lib/pkgconfig" "${sysroot}/usr/share/pkgconfig"
    _prepend_path CMAKE_PREFIX_PATH "${sysroot}/usr"
    for directory in "${sysroot}/usr/lib/"*; do
        # the multiarch folder of the libraries (x86_64-linux-gnu, aarch64-...)
        [[ -d "${directory}" && "${directory##*/}" == *-*-* ]] || continue
        _prepend_path LIBRARY_PATH "${directory}"
        _prepend_path PKG_CONFIG_PATH "${directory}/pkgconfig"
        _prepend_path CMAKE_PREFIX_PATH "${directory}"
    done
    log_warn "Building against ${sysroot}: the packages above are NOT installed in the system."
    return 0
}
# _prepend_path VAR <dir>...: the directories that exist, in front of VAR.
function _prepend_path() {
    local variable="$1" directory added=""
    shift
    for directory in "$@"; do
        [[ -d "${directory}" ]] || continue
        added="${added:+${added}:}${directory}"
    done
    [[ -n "${added}" ]] || return 0
    printf -v "${variable}" '%s' "${added}${!variable:+:${!variable}}"
    export "${variable?}"
    log_info "${variable} += ${added}"
    return 0
}
# install_packages "<apt packages>" "<dnf packages>"
# Each list is space-separated; "a|b" picks the first one apt knows about.
# Only what is missing is installed, and every step says what it found.
function install_packages() {
    local apt_list="$1" dnf_list="$2" manager
    manager="$(package_manager)"
    case "${manager}" in
        apt)
            _apt_update_once
            local -a asked=() wanted=() installable=() broken=() names=()
            local package alternative picked already=0
            # the list is written on several lines: every word of every line
            # shellcheck disable=SC2086  # a list of package names
            readarray -t asked <<<"$(printf '%s\n' ${apt_list})"
            [[ -n "${apt_list// /}" ]] || asked=()
            log_info "Checking ${#asked[@]} packages against the installed ones..."
            for package in "${asked[@]}"; do
                for alternative in ${package//|/ }; do
                    names+=("${alternative}")
                done
            done
            _read_installed "${names[@]}"
            _read_candidates "${names[@]}"
            for package in "${asked[@]}"; do
                # an alternative already installed is enough, and is left alone
                # (apt would mark it as manually installed)
                picked=""
                for alternative in ${package//|/ }; do
                    if [[ -n "${_INSTALLED[${alternative}]:-}" ]]; then
                        log_info "${alternative}: installed (${_INSTALLED[${alternative}]}), nothing to do."
                        picked="-"
                        already=$((already + 1))
                        break
                    fi
                done
                [[ "${picked}" == "-" ]] && continue
                for alternative in ${package//|/ }; do
                    if [[ -n "${_CANDIDATE[${alternative}]:-}" ]]; then
                        picked="${alternative}"
                        break
                    fi
                done
                if [[ -n "${picked}" ]]; then
                    log_info "${picked}: missing, ${_CANDIDATE[${picked}]} is to be installed."
                    wanted+=("${picked}")
                else
                    log_warn "No package ${package} in apt, skipping it."
                fi
            done
            [[ "${already}" -gt 0 ]] &&
                log_info "${already} of the ${#asked[@]} packages are already there."
            if [[ ${#wanted[@]} -eq 0 ]]; then
                log_info "Nothing to install."
                return 0
            fi
            # the solver runs before anything is downloaded, so an impossible
            # install is known (and named) here, not after a long download
            log_info "Asking apt about: ${wanted[*]}"
            if _apt_pin_mismatched "${wanted[@]}"; then
                installable=("${_PINNED_WANTED[@]}")
            else
                local rejected="" status=0
                rejected="$(_apt_broken "${_PINNED_WANTED[@]}")" || status=$?
                installable=("${_PINNED_WANTED[@]}")
                if [[ "${status}" -eq 2 ]]; then
                    die "apt cannot install these packages together: ${wanted[*]}"
                elif [[ "${status}" -eq 0 ]]; then
                    installable=()
                    readarray -t broken <<<"${rejected}"
                    for package in "${_PINNED_WANTED[@]}"; do
                        local skip=0
                        for alternative in "${broken[@]}"; do
                            [[ "${package%%=*}" == "${alternative}" ]] && skip=1
                        done
                        [[ "${skip}" -eq 0 ]] && installable+=("${package}")
                    done
                    # any remaining package that depends on a broken one cannot
                    # be installed by apt either: move it to broken as well
                    if [[ ${#installable[@]} -gt 0 ]] &&
                        ! ${SUDO} "${_C_ENV[@]}" apt-get install -y -s "${installable[@]}" &>/dev/null; then
                        local -a kept=()
                        for package in "${installable[@]}"; do
                            if ${SUDO} "${_C_ENV[@]}" apt-get install -y -s "${package}" &>/dev/null; then
                                kept+=("${package}")
                            else
                                broken+=("${package%%=*}")
                            fi
                        done
                        installable=("${kept[@]}")
                    fi
                    if [[ ${#installable[@]} -gt 0 ]]; then
                        log_warn "apt cannot install: ${broken[*]} (the rest is installed anyway)"
                    else
                        log_warn "apt cannot install: ${broken[*]}"
                    fi
                    _apt_hint "${broken[0]}"
                    _apt_sysroot "${broken[@]}" \
                        || die "Could not install the packages (apt): ${broken[*]}"
                fi
            fi
            if [[ ${#installable[@]} -gt 0 ]]; then
                log_info "Installing packages: ${installable[*]}"
                ${SUDO} apt-get install -y "${installable[@]}" \
                    || die "Could not install the packages (apt)"
            fi
            ;;
        dnf)
            local -a asked=() missing=()
            local package
            # shellcheck disable=SC2086  # a list of package names
            readarray -t asked <<<"$(printf '%s\n' ${dnf_list})"
            [[ -n "${dnf_list// /}" ]] || asked=()
            log_info "Checking ${#asked[@]} packages against the installed ones..."
            for package in "${asked[@]}"; do
                if rpm -q --whatprovides "${package}" &>/dev/null; then
                    log_info "${package}: installed, nothing to do."
                else
                    log_info "${package}: missing, to be installed."
                    missing+=("${package}")
                fi
            done
            if [[ ${#missing[@]} -eq 0 ]]; then
                log_info "Nothing to install."
                return 0
            fi
            log_info "Installing packages: ${missing[*]}"
            ${SUDO} dnf install -y "${missing[@]}" || die "Could not install the packages (dnf)"
            ;;
        *)
            log_warn "Unknown package manager: make sure these are installed: ${apt_list}"
            ;;
    esac
    return 0
}
# need <command>...: install the commands that are missing.
function need() {
    local command apt_list="" dnf_list=""
    for command in "$@"; do
        command -v "${command}" &>/dev/null && continue
        case "${command}" in
            7z) apt_list+=" 7zip|p7zip-full"; dnf_list+=" p7zip p7zip-plugins" ;;
            *) apt_list+=" ${command}"; dnf_list+=" ${command}" ;;
        esac
    done
    if [[ -n "${apt_list}" ]]; then
        install_packages "${apt_list}" "${dnf_list}"
    fi
}
## Downloads ---------------------------------------------------------------
function fetch() {
    local url="$1" destination="$2"
    log_info "Downloading ${url}"
    curl -fL --retry 3 --progress-bar -o "${destination}" "${url}" \
        || die "The download of ${url} failed"
}
# release_asset <forge> <regex> [any]
# Print the download URL of the newest release asset whose name matches
# <regex> (Python syntax, case-insensitive). <forge> is github:<owner>/<repo>
# or forgejo:<host>/<owner>/<repo>. Prereleases count only with "any".
# Calls `unavailable` when no release has a matching asset.
function release_asset() {
    local forge="$1" pattern="$2" prereleases="${3:-}" api
    local -a headers=(-H "Accept: application/json")
    case "${forge}" in
        github:*)
            api="https://api.github.com/repos/${forge#github:}/releases?per_page=20"
            if [[ -n "${GITHUB_TOKEN:-}" ]]; then
                headers+=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
            fi
            ;;
        forgejo:*)
            local rest="${forge#forgejo:}"
            api="https://${rest%%/*}/api/v1/repos/${rest#*/}/releases?limit=20"
            ;;
        *) die "release_asset: unknown forge ${forge}" ;;
    esac
    log_info "Looking for the latest ${LABEL} release (${forge#*:})..." >&2
    local json status=0 url
    json="$(curl -fsSL --retry 3 "${headers[@]}" "${api}")" \
        || die "Could not read the releases of ${forge#*:} (network down or API rate limit?)"
    url="$(python3 -I -c '
import json, re, sys
pattern = re.compile(sys.argv[1], re.IGNORECASE)
prereleases = sys.argv[2] == "any"
for release in json.loads(sys.stdin.read()):
    if release.get("draft") or (release.get("prerelease") and not prereleases):
        continue
    for asset in release.get("assets") or []:
        if pattern.search(asset.get("name", "")):
            print(asset["browser_download_url"])
            sys.exit(0)
sys.exit(3)' "${pattern}" "${prereleases}" <<<"${json}")" || status=$?
    case "${status}" in
        0) echo "${url}" ;;
        3) unavailable "No ${LABEL} release has a download for this machine (${ARCH})." ;;
        *) die "Could not read the releases of ${forge#*:}" ;;
    esac
}
## Unpacking ---------------------------------------------------------------
# extract_appimage <file>: the AppImage's files become ${STAGE}.
function extract_appimage() {
    local appimage="$1" work root
    work="$(mktemp -d -p "${TMP_DIR}")"
    chmod +x "${appimage}"
    log_info "Extracting the AppImage..."
    (cd "${work}" && "${appimage}" --appimage-extract >/dev/null) \
        || die "Could not extract ${appimage##*/}"
    # squashfs-root, which some AppImages make a link to an AppDir folder
    if [[ -e "${work}/squashfs-root" ]]; then
        root="$(readlink -f "${work}/squashfs-root")"
    elif [[ -d "${work}/AppDir" ]]; then
        root="${work}/AppDir"
    else
        die "The AppImage extracted into an unexpected layout"
    fi
    [[ -x "${root}/AppRun" ]] || die "The extracted AppImage has no AppRun"
    rm -rf "${STAGE}"
    mv "${root}" "${STAGE}"
}
# extract_archive <file> <folder>: unpack a tarball, zip or 7z into <folder>,
# without the archive's single top-level folder if it has one.
function extract_archive() {
    local archive="$1" destination="$2" work
    work="$(mktemp -d -p "${TMP_DIR}")"
    case "${archive,,}" in
        *.zip) need unzip; unzip -q "${archive}" -d "${work}" ;;
        *.7z) need 7z; 7z x -y -o"${work}" "${archive}" >/dev/null ;;
        *) tar -xf "${archive}" -C "${work}" ;;
    esac || die "Could not extract ${archive##*/}"
    local -a entries
    shopt -s dotglob nullglob
    entries=("${work}"/*)
    if [[ ${#entries[@]} -eq 1 && -d "${entries[0]}" ]]; then
        entries=("${entries[0]}"/*)
    fi
    mkdir -p "${destination}"
    [[ ${#entries[@]} -gt 0 ]] && mv "${entries[@]}" "${destination}/"
    shopt -u dotglob nullglob
}
## Building ----------------------------------------------------------------
# git_clone <url> [ref]: a fresh shallow clone (with submodules) in ${SRC_DIR}.
function git_clone() {
    local url="$1" ref="${2:-}"
    local -a options=(--depth 1 --recurse-submodules --shallow-submodules)
    [[ -n "${ref}" ]] && options+=(--branch "${ref}")
    need git
    rm -rf "${SRC_DIR}"
    mkdir -p "$(dirname "${SRC_DIR}")"
    log_info "Cloning ${url}${ref:+ (${ref})}..."
    git clone "${options[@]}" "${url}" "${SRC_DIR}" || die "Could not clone ${url}"
}
# cmake_build [cmake options...]: configure and build ${SRC_DIR} in
# ${SRC_DIR}/build, with the final prefix baked in.
function cmake_build() {
    local build="${SRC_DIR}/build"
    local -a generator=()
    command -v ninja &>/dev/null && generator=(-G Ninja)
    log_info "Configuring ${LABEL}..."
    cmake -S "${SRC_DIR}" -B "${build}" "${generator[@]}" \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="${FINAL_APP_DIR}" "$@" \
        || die "CMake could not configure ${LABEL}: check the messages above"
    log_info "Building ${LABEL} with ${JOBS} jobs..."
    cmake --build "${build}" -j "${JOBS}" \
        || die "The build failed (lower JOBS if the linker ran out of memory)"
}
# cmake_install: install what cmake_build built into ${STAGE}.
function cmake_install() {
    cmake --install "${SRC_DIR}/build" --prefix "${STAGE}" || die "cmake --install failed"
}
function remove_sources() {
    if [[ "${KEEP_SRC}" == "1" ]]; then
        log_info "Source tree kept in ${SRC_DIR}."
        return 0
    fi
    rm -rf "${SRC_DIR}"
    rmdir "$(dirname "${SRC_DIR}")" 2>/dev/null || true
}
# require_executable <path inside ${STAGE}>: fail unless the install produced it.
function require_executable() {
    [[ -x "${STAGE}/$1" ]] || die "The install did not produce $1"
}
## Installing and removing -------------------------------------------------
function _remove_legacy() {
    local entry
    for entry in "${LEGACY[@]}"; do
        if [[ -e "${INSTALL_DIR}/${entry}" || -L "${INSTALL_DIR}/${entry}" ]]; then
            rm -rf "${INSTALL_DIR:?}/${entry}"
            log_info "Removed ${entry} (an older layout)."
        fi
    done
}
function _kept() {
    local entry
    for entry in "${KEEP[@]}"; do
        [[ "$1" == "${entry}" ]] && return 0
    done
    return 1
}
function _remove_manifest_files() {
    [[ -f "${_MANIFEST}" ]] || return 0
    local file
    while IFS= read -r file; do
        [[ -n "${file}" ]] || continue
        _kept "${file}" || rm -f "${INSTALL_DIR:?}/${file}"
    done <"${_MANIFEST}"
    rm -f "${_MANIFEST}"
}
# Put ${STAGE} in place: as app/, or file by file for a portable emulator.
function _activate() {
    [[ -n "$(ls -A "${STAGE}" 2>/dev/null)" ]] || die "The install produced nothing"
    if [[ "${PORTABLE}" == "1" ]]; then
        local file manifest="${_MANIFEST}.new"
        (cd "${STAGE}" && find . \( -type f -o -type l \) -printf '%P\n' | sort) >"${manifest}"
        _remove_manifest_files
        while IFS= read -r file; do
            if _kept "${file}" && [[ -e "${INSTALL_DIR}/${file}" ]]; then
                continue
            fi
            mkdir -p "$(dirname "${INSTALL_DIR}/${file}")"
            mv -f "${STAGE}/${file}" "${INSTALL_DIR}/${file}"
        done <"${manifest}"
        mv "${manifest}" "${_MANIFEST}"
        rm -rf "${STAGE}"
    else
        local old="${INSTALL_DIR}/app.old"
        rm -rf "${old}"
        [[ -e "${APP_DIR}" ]] && mv "${APP_DIR}" "${old}"
        mv "${STAGE}" "${APP_DIR}"
        rm -rf "${old}"
    fi
    _remove_legacy
}
function _has_method() {
    declare -F "install_$1" >/dev/null
}
function _install_with() {
    local method="$1"
    _has_method "${method}" || die "${LABEL} has no ${method} install"
    mkdir -p "${INSTALL_DIR}"
    rm -rf "${STAGE}"
    mkdir -p "${STAGE}"
    _STAGING=1
    "install_${method}"
    _activate
    _STAGING=0
    if declare -F after_install >/dev/null; then
        after_install
    fi
    log_ok "${LABEL} installed (${method}) in ${INSTALL_DIR}."
}
# -i: each method in its own process, so `unavailable` can hand over to the next.
function _install_preferred() {
    local method flag status
    for method in "${_METHODS[@]}"; do
        _has_method "${method}" || continue
        case "${method}" in
            appimage) flag="-a" ;;
            archive) flag="-t" ;;
            source) flag="-s" ;;
        esac
        status=0
        bash "$0" "${flag}" || status=$?
        case "${status}" in
            0) return 0 ;;
            "${_UNAVAILABLE}") log_info "Trying the next way to install ${LABEL}..." ;;
            *) exit "${status}" ;;
        esac
    done
    die "${LABEL} can't be installed on this machine (${ARCH})"
}
function _uninstall() {
    if declare -F before_uninstall >/dev/null; then
        before_uninstall
    fi
    rm -rf "${APP_DIR}" "${STAGE}" "${INSTALL_DIR}/app.old"
    _remove_manifest_files
    _remove_legacy
    if [[ -d "${INSTALL_DIR}" ]]; then
        find "${INSTALL_DIR}" -depth -type d -empty -delete
    fi
    log_ok "${LABEL} uninstalled (its configuration and saves are kept)."
}
function _usage() {
    cat <<EOF
Usage: $(basename "$0") -i | -a | -t | -s | -u | -l
  -i  install ${LABEL} the best way this machine allows ($(_list_methods))
  -a  the AppImage    -t  the release archive    -s  a build from source
  -u  uninstall (the configuration and saves are kept)
  -l  list the methods this installer has
EOF
}
function _list_methods() {
    local method
    local -a found=()
    for method in "${_METHODS[@]}"; do
        _has_method "${method}" && found+=("${method}")
    done
    echo "${found[*]}"
}
function installer_main() {
    case "${1:-}" in
        -i) _install_preferred ;;
        -a) _install_with appimage ;;
        -t) _install_with archive ;;
        -s) _install_with source ;;
        -u) _uninstall ;;
        -l) _list_methods ;;
        *) _usage; exit 1 ;;
    esac
}
