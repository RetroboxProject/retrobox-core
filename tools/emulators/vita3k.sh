#!/usr/bin/env bash
## INSTALADOR DE VITA3K
## FECHA DE CREACIÓN: 4 de agosto de 2026
set -eo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/vita3k"
SRC_DIR="${RETROBOX_EMULATORS_DIR}/_src"
VITA3K_SRC="${SRC_DIR}/Vita3K"
TMP_DIR="$(mktemp -d)"
REPO="https://github.com/Vita3K/Vita3K.git"
RELEASE_BASE="https://github.com/Vita3K/Vita3K/releases/download/continuous"
ARCH="$(uname -m)"

# Rama a compilar con "-c". Cámbiala aquí si quieres seguir otra rama u otro fork.
BRANCH="master"

# Versión mínima de Qt que exige Vita3K y dónde se guarda si hay que descargarla
# (persistente entre ejecuciones para no volver a bajar ~300 MB cada vez).
QT_VERSION="6.11.0"
QT_DIR="${SCRIPT_DIR}/_qt6"

## FUNCIONES

function error() {
  echo "[ERROR] $*." >&2
  exit 1
}

function vita3k_uninstall() {
  rm -r "${INSTALL_DIR}"
}

function resolve_arch() {
  case "${ARCH}" in
    x86_64|amd64)
      APPIMAGE_NAME="Vita3K-x86_64.AppImage"
      ZIP_NAME="ubuntu-latest.zip"
      ;;
    aarch64|arm64)
      APPIMAGE_NAME="Vita3K-aarch64.AppImage"
      ZIP_NAME="ubuntu-aarch64-latest.zip"
      ;;
    *)
      error "Arquitectura no soportada: ${ARCH}"
      ;;
  esac
}

function vita3k_appimage_inst(){
  resolve_arch

  if ! command -v curl &> /dev/null; then
    sudo dnf install -y curl || sudo apt-get install -y curl
  fi

  mkdir -p "${INSTALL_DIR}"

  echo "[INFO] Descargando ${APPIMAGE_NAME} (continuous)..."
  curl -L "${RELEASE_BASE}/${APPIMAGE_NAME}" -o "${TMP_DIR}/vita3k.AppImage"

  mv "${TMP_DIR}/vita3k.AppImage" "${INSTALL_DIR}/vita3k.AppImage"
  chmod +x "${INSTALL_DIR}/vita3k.AppImage"

  echo "[INFO] Extrayendo AppImage..."
  (
    cd "${INSTALL_DIR}" || exit 1
    "${INSTALL_DIR}/vita3k.AppImage" --appimage-extract >/dev/null 2>&1
    mv "${INSTALL_DIR}/squashfs-root" "${INSTALL_DIR}/app"
    rm "${INSTALL_DIR}/vita3k.AppImage"
  )

  rm -rf "${TMP_DIR}"
  echo "[INFO] Instalación (AppImage descomprimida, ${ARCH}) completada."
}

function vita3k_binary_inst(){
  resolve_arch

  if ! command -v curl &> /dev/null; then
    sudo dnf install -y curl || sudo apt-get install -y curl
  fi
  if ! command -v unzip &> /dev/null; then
    sudo dnf install -y unzip || sudo apt-get install -y unzip
  fi

  mkdir -p "${INSTALL_DIR}/app"

  echo "[INFO] Descargando ${ZIP_NAME} (continuous)..."
  curl -L "${RELEASE_BASE}/${ZIP_NAME}" -o "${TMP_DIR}/vita3k.zip"

  echo "[INFO] Descomprimiendo..."
  unzip -q "${TMP_DIR}/vita3k.zip" -d "${INSTALL_DIR}/app"
  chmod +x "${INSTALL_DIR}/app/Vita3K"

  rm -rf "${TMP_DIR}"
  echo "[INFO] Instalación (binario ubuntu-latest, ${ARCH}) completada."
}

function check_deps() {
  echo "[INFO] Comprobando dependencias de compilación..."
  sudo dnf install -y \
    git cmake ninja-build SDL2-devel pkg-config gtk3-devel clang lld \
    xdg-desktop-portal openssl openssl-devel libstdc++-static qt6-qtbase-devel \
    || sudo apt-get install -y \
    git cmake ninja-build libsdl2-dev pkg-config libgtk-3-dev clang lld \
    xdg-desktop-portal openssl libssl-dev qt6-base-dev
}

function ensure_qt6() {
  local system_version
  system_version="$(pkg-config --modversion Qt6Core 2>/dev/null || echo "0")"

  if [[ "$(printf '%s\n%s\n' "${QT_VERSION}" "${system_version}" | sort -V | head -n1)" == "${QT_VERSION}" && "${system_version}" != "0" ]]; then
    echo "[INFO] Qt6 del sistema (${system_version}) cumple el mínimo (${QT_VERSION})."
    return
  fi

  echo "[INFO] Qt6 del sistema es insuficiente o no está instalado."
  echo "[INFO] Descargando Qt ${QT_VERSION} (qtbase) precompilado con aqtinstall..."

  if ! command -v python3 &> /dev/null; then
    sudo dnf install -y python3 python3-pip || sudo apt-get install -y python3 python3-pip python3-venv
  fi

  if [[ ! -d "${QT_DIR}/${QT_VERSION}" ]]; then
    mkdir -p "${QT_DIR}"
    local aqt_arch
    case "${ARCH}" in
      x86_64|amd64) aqt_arch="linux_gcc_64";;
      aarch64|arm64) aqt_arch="linux_arm64";;
      *) error "Arquitectura no soportada para Qt6 precompilado: ${ARCH}";;
    esac
    python3 -m venv "${TMP_DIR}/aqt-venv"
    (
      source "${TMP_DIR}/aqt-venv/bin/activate"
      pip install --quiet aqtinstall
      aqt install-qt linux desktop "${QT_VERSION}" "${aqt_arch}" --outputdir "${QT_DIR}"
    )
  fi

  Qt6_ROOT="$(find "${QT_DIR}/${QT_VERSION}" -maxdepth 1 -mindepth 1 -type d | head -n1)"
  [[ -n "${Qt6_ROOT}" ]] || error "No se ha podido localizar la instalación de Qt6 descargada"
  export Qt6_ROOT
  echo "[INFO] Usando Qt6_ROOT=${Qt6_ROOT}"
}

function vita3k_source_build() {
  mkdir -p "${SRC_DIR}"
  check_deps
  ensure_qt6

  echo "[INFO] Clonando Vita3K (rama: ${BRANCH}) con submódulos..."
  git clone --recursive --shallow-submodules --depth 1 -b "${BRANCH}" "${REPO}" "${VITA3K_SRC}"

  echo "[INFO] Generando proyecto (preset linux-ninja-clang)..."
  (
    cd "${VITA3K_SRC}"
    cmake --preset linux-ninja-clang
    cmake --build "build/linux-ninja-clang"
  )

  echo "[INFO] Instalando binario compilado en ${INSTALL_DIR}..."
  mkdir -p "${INSTALL_DIR}/app"

  local bin
  bin="$(find "${VITA3K_SRC}/build/linux-ninja-clang" -maxdepth 6 -type f -name 'Vita3K' -perm -u+x | head -n1)"
  [[ -n "${bin}" ]] || error "No se ha encontrado el binario Vita3K tras la compilación"
  cp "${bin}" "${INSTALL_DIR}/app/Vita3K"

  echo "[INFO] Limpiando fuentes temporales..."
  rm -rf "${SRC_DIR}"
  echo "[INFO] Compilación completada (rama: ${BRANCH})."
}

## LLAMADAS
case "$1" in
  "-i") vita3k_appimage_inst;;
  "-b") vita3k_binary_inst;;
  "-s") vita3k_source_build;;
  "-u") vita3k_uninstall;;
  *)  exit 1;;
esac

exit 0
