#!/usr/bin/env bash
## INSTALADOR DE DOLPHIN
## FECHA DE CREACIÓN: 1 de noviembre de 2025
## FECHA DE MODIFICACIÓN: 4 de agosto de 2026 (reescrito al estilo del resto de instaladores;
##   la instalación por source ahora usa "cmake --install" con prefijo dentro de
##   INSTALL_DIR/app, así queda autocontenida y no depende de que el clon de git siga existiendo)
set -eo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/dolphin-emu"
SRC_DIR="${RETROBOX_EMULATORS_DIR}/_src"
DOLPHIN_SRC="${SRC_DIR}/dolphin-emu"
TMP_DIR="$(mktemp -d)"
ARCH="$(uname -m)"

# AppImage de terceros (Dolphin oficial no publica AppImage propia)
APPIMAGE_REPO="pkgforge-dev/Dolphin-emu-AppImage"
APPIMAGE_API_URL="https://api.github.com/repos/${APPIMAGE_REPO}/releases/latest"

# Repo oficial para compilar desde source
SOURCE_UPSTREAM="https://github.com/dolphin-emu/dolphin.git"

## FUNCIONES

function error() {
  echo "[ERROR] $*." >&2
  exit 1
}

function desinstalar() {
  rm -r "${INSTALL_DIR}"
}

function appimage_install(){
  if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]]; then
    error "El AppImage de Dolphin solo está disponible para x86_64 (arquitectura detectada: ${ARCH})"
  fi

  if ! command -v curl &> /dev/null; then
    sudo dnf install -y curl || sudo apt-get install -y curl
  fi

  echo "[INFO] Buscando la última versión de Dolphin AppImage en GitHub..."
  DOWNLOAD_URL=$(curl -s "${APPIMAGE_API_URL}" | grep x86_64 | grep "browser_download_url.*\.AppImage" | cut -d '"' -f 4 | head -n1)

  if [[ -z "${DOWNLOAD_URL}" ]]; then
    error "No se pudo obtener la URL de descarga del AppImage desde GitHub"
  fi

  mkdir -p "${INSTALL_DIR}"

  echo "[INFO] Descargando: ${DOWNLOAD_URL}"
  curl -L "${DOWNLOAD_URL}" -o "${TMP_DIR}/dolphin.AppImage"
  chmod +x "${TMP_DIR}/dolphin.AppImage"

  echo "[INFO] Extrayendo AppImage..."
  (
    cd "${TMP_DIR}" || exit 1
    ./dolphin.AppImage --appimage-extract >/dev/null 2>&1
    mv AppDir "${INSTALL_DIR}/app"
  )

  rm -rf "${TMP_DIR}"
  echo "[INFO] Instalación (AppImage descomprimida) completada."
}

function check_deps() {
  echo "[INFO] Comprobando dependencias de compilación..."
  if command -v dnf &> /dev/null; then
    sudo dnf install -y \
      gcc-c++ cmake ninja-build git \
      pkgconf-pkg-config mesa-libGL-devel libX11-devel libXrandr-devel libXi-devel \
      mesa-libEGL-devel libavcodec-free-devel libavformat-free-devel libavutil-free-devel \
      libswresample-free-devel libswscale-free-devel systemd-devel libevdev-devel \
      SDL3-devel fmt-devel glslang-devel pugixml-devel enet-devel xxhash-devel \
      bzip2-devel xz-devel libzstd-devel zlib-devel minizip-ng-devel lzo-devel lz4-devel \
      libspng-devel cubeb-devel libusb1-devel miniupnpc-devel libcurl-devel hidapi-devel \
      gtest-devel alsa-lib-devel pulseaudio-libs-devel llvm-devel bluez-libs-devel \
      qt6-qtbase-devel qt6-qtbase-private-devel qt6-qtsvg-devel gettext \
      || error "No se pudieron instalar las dependencias de compilación (dnf)"
  else
    sudo apt-get install -y \
      build-essential cmake ninja-build git \
      pkg-config libgl1-mesa-dev libx11-dev libxrandr-dev libxi-dev \
      libegl1-mesa-dev libavcodec-dev libavformat-dev libavutil-dev \
      libswresample-dev libswscale-dev libudev-dev libevdev-dev \
      libsdl3-dev libfmt-dev glslang-dev glslang-tools libpugixml-dev libenet-dev libxxhash-dev \
      libbz2-dev liblzma-dev libzstd-dev zlib1g-dev libminizip-ng-dev liblzo2-dev liblz4-dev \
      libspng-dev libcubeb-dev libusb-1.0-0-dev libminiupnpc-dev libcurl4-openssl-dev libhidapi-dev \
      libgtest-dev libasound2-dev libpulse-dev llvm-dev libbluetooth-dev \
      qt6-base-dev qt6-base-private-dev qt6-svg-dev gettext librsvg2-bin \
      || error "No se pudieron instalar las dependencias de compilación (apt)"
  fi
}

function cmake_extra_flags() {
  # Fedora y Debian/Ubuntu no traen versiones compatibles de SFML 3.x, MbedTLS 2.x
  # ni libmgba reciente, así que se vendorizan igual que hace el paquete oficial.
  # Debian además necesita minizip-ng vendorizado (solo está "en pruebas" en el repo).
  if command -v dnf &> /dev/null; then
    echo "-DUSE_SYSTEM_SFML=OFF -DUSE_SYSTEM_MBEDTLS=OFF -DUSE_SYSTEM_LIBMGBA=OFF"
  else
    echo "-DUSE_SYSTEM_MINIZIP-NG=OFF -DUSE_SYSTEM_SFML=OFF -DUSE_SYSTEM_MBEDTLS=OFF -DUSE_SYSTEM_LIBMGBA=OFF"
  fi
}

function install_source() {
  mkdir -p "${SRC_DIR}"
  check_deps

  echo "[INFO] Clonando Dolphin (esto puede tardar, el repo es grande)..."
  git clone --recursive "${SOURCE_UPSTREAM}" "${DOLPHIN_SRC}"

  local extra_flags
  extra_flags="$(cmake_extra_flags)"

  echo "[INFO] Configurando y compilando (prefijo de instalación: ${INSTALL_DIR}/app)..."
  mkdir -p "${DOLPHIN_SRC}/build"
  (
    cd "${DOLPHIN_SRC}/build" || exit 1
    # shellcheck disable=SC2086
    cmake .. -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX="${INSTALL_DIR}/app" \
      ${extra_flags} \
      || exit 1
    ninja || exit 1
    ninja install || exit 1
  ) || error "Fallo al compilar/instalar Dolphin. Revisa la salida de cmake/ninja arriba"

  # "ninja install" coloca bin/dolphin-emu y share/dolphin-emu/{sys,...} dentro del
  # prefijo, con la ruta de datos ya resuelta a absoluta en tiempo de compilación:
  # el resultado en INSTALL_DIR/app es autocontenido, no depende de _src/
  [[ -x "${INSTALL_DIR}/app/bin/dolphin-emu" ]] \
    || error "El build terminó pero no encuentro el binario instalado en ${INSTALL_DIR}/app/bin/dolphin-emu"

  echo "[INFO] Limpiando fuentes temporales..."
  rm -rf "${SRC_DIR}"
  echo "[INFO] Compilación desde source completada. Binario: ${INSTALL_DIR}/app/bin/dolphin-emu"
}

## LLAMADAS
case "$1" in
"-i") appimage_install;;
"-s") install_source;;
"-u"|"-d") desinstalar;;
*)  exit 1;;
esac

exit 0