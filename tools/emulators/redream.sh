#!/usr/bin/env bash
## INSTALADOR DE REDREAM
## FECHA DE CREACIÓN: 4 de agosto de 2026
set -eo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/redream"
TMP_DIR="$(mktemp -d)"
DOWNLOAD_PAGE="https://redream.io/download"

## FUNCIONES

function error() {
  echo "[ERROR] $*." >&2
  exit 1
}

function desinstalar() {
  rm -r "${INSTALL_DIR}/redream"
}

function tarball_install(){
  # Comprobar curl
  if ! command -v curl &> /dev/null; then
    sudo dnf install -y curl || sudo apt-get install -y curl
  fi

  # redream no tiene API tipo GitHub: hay que parsear la página de descargas.
  # El primer enlace .tar.gz para x86_64-linux que aparece en la página
  # corresponde a la última "Stable Release" (aparece antes que las
  # "Development Releases" en el HTML).
  echo "[INFO] Buscando la última versión de development en ${DOWNLOAD_PAGE}..."
  pagina="$(curl -sL "${DOWNLOAD_PAGE}")"

  # Recortar todo lo anterior a "Development Releases" para no coger
  # por error un tarball de la sección "Stable Releases"
  pagina_dev="$(echo "${pagina}" | sed -n '/Development Releases/,$p')"

  TARBALL_PATH=$(echo "${pagina_dev}" | grep -oP '(?<=href=")/download/redream\.x86_64-linux-v[0-9][^"]*\.tar\.gz(?=")' | head -n1)
if [[ -z "${TARBALL_PATH}" ]]; then
    error "No se encontró ningún tarball de Linux x86_64 en la sección Development Releases"
  fi

  TARBALL_URL="https://redream.io${TARBALL_PATH}"

  # Preparar directorio de instalación
  mkdir -p "${INSTALL_DIR}"

  # Descargar
  echo "[INFO] Descargando ${TARBALL_URL}..."
  curl -L "${TARBALL_URL}" -o "${TMP_DIR}/redream.tar.gz"

  # Extraer
  echo "[INFO] Extrayendo tarball..."
  mkdir -p "${TMP_DIR}/extract"
  tar -xzf "${TMP_DIR}/redream.tar.gz" -C "${TMP_DIR}/extract"

  mkdir -p "${INSTALL_DIR}/"
  mv "${TMP_DIR}/extract"/* "${INSTALL_DIR}/"
  chmod +x "${INSTALL_DIR}/redream"

  # Limpiar
  rm -rf "${TMP_DIR}"
  echo "[INFO] Instalación completada."
}

## LLAMADAS
case "$1" in
"-i") tarball_install;;
"-u"|"-d") desinstalar;;
*)  exit 1;;
esac

exit 0