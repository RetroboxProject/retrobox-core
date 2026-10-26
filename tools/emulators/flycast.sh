#!/usr/bin/env bash
## INSTALADOR DE FLYCAST (STANDALONE)
## FECHA DE CREACIÓN: 23 de agosto de 2026
## Compila flycast standalone desde fuente para cualquier arquitectura que
## soporte tu toolchain (pensado principalmente para x86_64 y aarch64).
## También conserva la descarga del AppImage oficial (solo x86_64) y la
## desinstalación, heredadas de la versión anterior de este script.
set -eo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
GITHUB_REPO="flyinghead/flycast"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/flycast"
SRC_DIR="${RETROBOX_EMULATORS_DIR}/_src"
FLYCAST_SRC="${SRC_DIR}/flycast"
SOURCE_UPSTREAM="https://github.com/flyinghead/flycast.git"
ARCH="$(uname -m)"

# Flags de optimización para la propia compilación. -march=native asume que
# compilas en la misma máquina/placa donde vas a ejecutar flycast (nada de
# cross-compiling); si no es tu caso, edita esta variable antes de lanzar -s.
EXTRA_CFLAGS="-O3 -march=native -pipe"

# Nº de jobs para la compilación. Se puede sobreescribir con la variable de
# entorno JOBS (útil en placas ARM con poca RAM donde "nproc" a full puede
# hacer OOM durante el link de los ficheros más pesados, p.ej. el renderer
# de Vulkan).
JOBS="${JOBS:-$(nproc)}"

## FUNCIONES

function error() {
  echo "[ERROR] $*." >&2
  exit 1
}

function desinstalar() {
  rm -rf "${INSTALL_DIR}/app"
}

function check_deps() {
  echo "[INFO] Comprobando dependencias de compilación..."
  if command -v dnf &> /dev/null; then
    sudo dnf install -y \
      gcc-c++ cmake make git pkgconf-pkg-config \
      SDL2-devel vulkan-loader-devel vulkan-headers \
      mesa-libGL-devel mesa-libEGL-devel mesa-libGLES-devel libX11-devel \
      libpng-devel libzip-devel libcurl-devel \
      alsa-lib-devel pipewire-devel libevdev-devel \
      || error "No se pudieron instalar las dependencias de compilación (dnf)"
  else
    sudo apt-get install -y \
      build-essential cmake make git pkg-config \
      libsdl2-dev libvulkan-dev \
      libgl1-mesa-dev libegl1-mesa-dev libgles2-mesa-dev libx11-dev \
      libpng-dev libzip-dev libcurl4-openssl-dev \
      libasound2-dev libpipewire-0.3-dev libevdev-dev \
      || error "No se pudieron instalar las dependencias de compilación (apt)"
  fi
  # Esta lista es orientativa (no viene de un requirements.txt oficial de
  # flycast). Si al configurar con cmake se queja de alguna lib que falta,
  # instala el paquete -dev/-devel correspondiente y vuelve a lanzar -s.
}

function install_source() {
  mkdir -p "${SRC_DIR}"
  check_deps

  echo "[INFO] Arquitectura detectada: ${ARCH}"
  echo "[INFO] Clonando flycast..."
  [[ -d "${FLYCAST_SRC}" ]] && rm -rf "${FLYCAST_SRC}"
  git clone "${SOURCE_UPSTREAM}" "${FLYCAST_SRC}" \
    || error "Fallo al clonar flycast"

  echo "[INFO] Inicializando submódulos (tarda un rato, flycast trae varios)..."
  (
    cd "${FLYCAST_SRC}" || exit 1
    git submodule update --init --recursive
  ) || error "Fallo al inicializar los submódulos de flycast"

  echo "[INFO] Configurando y compilando (arch: ${ARCH}, ${JOBS} jobs)..."
  (
    cd "${FLYCAST_SRC}" || exit 1
    mkdir -p build && cd build || exit 1
    CFLAGS="${EXTRA_CFLAGS}" CXXFLAGS="${EXTRA_CFLAGS}" cmake .. \
      -DCMAKE_BUILD_TYPE=Release \
      || exit 1
    cmake --build . -j"${JOBS}" || exit 1
  ) || error "Fallo al compilar flycast. Revisa la salida de cmake/make arriba"

  local bin_out="${FLYCAST_SRC}/build/flycast"
  [[ -x "${bin_out}" ]] \
    || error "El build terminó pero no encuentro el binario en ${bin_out} (puede que el CMakeLists de esta versión lo nombre distinto; revisa dentro de ${FLYCAST_SRC}/build)"

  echo "[INFO] Instalando en ${INSTALL_DIR}/app..."
  mkdir -p "${INSTALL_DIR}/app/bin"
  cp "${bin_out}" "${INSTALL_DIR}/app/bin/flycast"

  echo "[INFO] Limpiando fuentes temporales..."
  rm -rf "${SRC_DIR}"

  echo "[INFO] Instalación desde source completada. Binario: ${INSTALL_DIR}/app/bin/flycast"
  echo "[INFO] Nota: la config/BIOS/etc de flycast standalone NO se guardan aquí,"
  echo "[INFO] sino en \$HOME/.local/share/flycast o \$HOME/.config/flycast (según distro)."
}

function install_appimage() {
  if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]]; then
    error "El AppImage oficial de flycast solo se publica para x86_64 (arquitectura detectada: ${ARCH}); usa -s para compilar desde fuente"
  fi

  echo "[INFO] Buscando la última versión de Flycast AppImage (x86_64) en GitHub..."
  local download_url
  download_url=$(curl -s "https://api.github.com/repos/${GITHUB_REPO}/releases/latest" \
    | grep -i x86_64 | grep "browser_download_url.*\.AppImage" | cut -d '"' -f 4 | head -n 1)

  [[ -n "${download_url}" ]] || error "No se pudo obtener la URL de descarga del AppImage desde GitHub"

  echo "[INFO] Descargando: ${download_url}"
  mkdir -p "${INSTALL_DIR}/app/bin" "${INSTALL_DIR}/config"
  curl -fL "${download_url}" -o "${INSTALL_DIR}/app/bin/flycast.AppImage" \
    || error "Error durante la descarga del AppImage"

  chmod +x "${INSTALL_DIR}/app/bin/flycast.AppImage"
  echo "[INFO] Instalación de AppImage completada. Binario: ${INSTALL_DIR}/app/bin/flycast.AppImage"
}

## LLAMADAS

case "$1" in
"-s") install_source;;
"-i") install_appimage;;
"-u"|"-d") desinstalar;;
*)
  echo "Uso: $0 [-s | -i | -u]"
  echo "  -s : Compilar flycast standalone desde fuente (cualquier arquitectura; pensado para x86_64/aarch64)"
  echo "  -i : Instalar el AppImage oficial (solo x86_64, desde GitHub)"
  echo "  -u : Desinstalar"
  exit 1
  ;;
esac

exit 0