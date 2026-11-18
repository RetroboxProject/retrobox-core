#!/usr/bin/env bash
# Vita3K (PlayStation Vita): the AppImage of the continuous build, its plain
# binary build, or a build from source.
#
#   VITA3K_BRANCH   branch of a source build (default: master)
EMULATOR="vita3k"
LABEL="Vita3K"
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

readonly RELEASES="https://github.com/Vita3K/Vita3K/releases/download/continuous"
# the oldest Qt Vita3K builds with, and where a downloaded one is kept between
# runs (~300 MB; emulator_update shares it with its staging folder)
readonly QT_VERSION="6.11.0"
readonly QT_DIR="${RETROBOX_EMULATORS_DIR}/_qt6"

function supported_arch() {
    case "${ARCH}" in
        x86_64 | aarch64) ;;
        *) unavailable "Vita3K publishes no build for ${ARCH}." ;;
    esac
}

function install_appimage() {
    supported_arch
    fetch "${RELEASES}/Vita3K-${ARCH}.AppImage" "${TMP_DIR}/vita3k.AppImage"
    extract_appimage "${TMP_DIR}/vita3k.AppImage"
}

function install_archive() {
    supported_arch
    local name="ubuntu-latest.zip"
    [[ "${ARCH}" == "aarch64" ]] && name="ubuntu-aarch64-latest.zip"
    fetch "${RELEASES}/${name}" "${TMP_DIR}/vita3k.zip"
    extract_archive "${TMP_DIR}/vita3k.zip" "${STAGE}"
    chmod +x "${STAGE}/Vita3K"
    require_executable Vita3K
}

# Export Qt6_ROOT when the system Qt is older than QT_VERSION.
function ensure_qt6() {
    local system_version
    system_version="$(pkg-config --modversion Qt6Core 2>/dev/null || echo 0)"
    if [[ "${system_version}" != "0" \
        && "$(printf '%s\n%s\n' "${QT_VERSION}" "${system_version}" | sort -V | head -n 1)" == "${QT_VERSION}" ]]; then
        log_info "The system Qt ${system_version} is recent enough."
        return 0
    fi
    if [[ ! -d "${QT_DIR}/${QT_VERSION}" ]]; then
        local qt_host="linux" qt_arch="linux_gcc_64"
        if [[ "${ARCH}" == "aarch64" ]]; then
            qt_host="linux_arm64" qt_arch="linux_gcc_arm64"
        fi
        log_info "The system Qt is too old: downloading Qt ${QT_VERSION} with aqtinstall..."
        python3 -m venv "${TMP_DIR}/aqt" || die "python3-venv is needed to download Qt"
        "${TMP_DIR}/aqt/bin/pip" install --quiet aqtinstall || die "Could not install aqtinstall"
        "${TMP_DIR}/aqt/bin/aqt" install-qt "${qt_host}" desktop "${QT_VERSION}" "${qt_arch}" \
            --outputdir "${QT_DIR}" || die "Could not download Qt ${QT_VERSION}"
    fi
    Qt6_ROOT="$(find "${QT_DIR}/${QT_VERSION}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    [[ -n "${Qt6_ROOT}" ]] || die "No Qt ${QT_VERSION} in ${QT_DIR}"
    export Qt6_ROOT
    log_info "Using Qt from ${Qt6_ROOT}."
}

function install_source() {
    install_packages \
        "git cmake ninja-build pkg-config clang lld libsdl2-dev libgtk-3-dev libssl-dev
         openssl xdg-desktop-portal qt6-base-dev python3-venv" \
        "git cmake ninja-build pkgconf-pkg-config clang lld SDL2-devel gtk3-devel
         openssl-devel openssl xdg-desktop-portal libstdc++-static qt6-qtbase-devel"
    ensure_qt6
    git_clone https://github.com/Vita3K/Vita3K.git "${VITA3K_BRANCH:-master}"
    log_info "Building Vita3K with ${JOBS} jobs..."
    (cd "${SRC_DIR}" && cmake --preset linux-ninja-clang \
        && cmake --build build/linux-ninja-clang -j "${JOBS}") \
        || die "The Vita3K build failed: check the messages above"
    local binary
    binary="$(find "${SRC_DIR}/build/linux-ninja-clang" -maxdepth 6 -type f -name Vita3K -perm -u+x \
        | head -n 1)"
    [[ -n "${binary}" ]] || die "The build produced no Vita3K binary"
    # the binary reads its data/ and lang/ folders from next to it
    cp -a "$(dirname "${binary}")/." "${STAGE}/"
    require_executable Vita3K
    remove_sources
}

installer_main "$@"
