#!/usr/bin/env bash
## INSTALADOR DE RPCS3
## FECHA DE CREACIÓN: 4 de agosto de 2026
set -eo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/setup/lib/paths.sh"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/rpcs3"
TMP_DIR="$(mktemp -d)"
REPO="RPCS3/rpcs3-binaries-linux"
API_URL="https://api.github.com/repos/$REPO/releases"
ARCH="$(uname -m)"

## FUNCIONES

function error() {
  echo "[ERROR] $*." >&2
  exit 1
}

function desinstalar() {
  rm -r "${INSTALL_DIR}"
}

function appimage_install(){
  # Por ahora RPCS3 solo publica AppImage de Linux para x86_64 ("linux64")
  if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]]; then
    error "RPCS3 solo distribuye AppImage Linux para x86_64 por ahora (arquitectura detectada: ${ARCH})"
  fi

  if ! command -v curl &> /dev/null; then
    sudo dnf install -y curl || sudo apt-get install -y curl
  fi
  if ! command -v jq &> /dev/null; then
    sudo dnf install -y jq || sudo apt-get install -y jq
  fi

  # El nombre del AppImage lleva versión, build y hash de commit
  # (p. ej. rpcs3-v0.0.39-18703-abcdef01_linux64.AppImage), así que hay que
  # resolverlo contra la última release en vez de construir la URL a mano.
  releases=$(curl -sL "${API_URL}?per_page=5")
  APPIMAGE_URL=$(echo "$releases" | jq -r '
    .[0].assets[] | select(.name | endswith("_linux64.AppImage")) | .browser_download_url
  ' | head -n1)

  if [[ -z "${APPIMAGE_URL}" ]]; then
    error "No se encontró ningún AppImage linux64 en la última release disponible"
  fi

  mkdir -p "${INSTALL_DIR}"

  echo "[INFO] Descargando $(basename "${APPIMAGE_URL}")..."
  curl -L "${APPIMAGE_URL}" -o "${TMP_DIR}/rpcs3.AppImage"

  mv "${TMP_DIR}/rpcs3.AppImage" "${INSTALL_DIR}/rpcs3.AppImage"
  chmod +x "${INSTALL_DIR}/rpcs3.AppImage"

  echo "[INFO] Extrayendo AppImage..."
  (
    cd "${INSTALL_DIR}" || exit 1
    "${INSTALL_DIR}/rpcs3.AppImage" --appimage-extract >/dev/null 2>&1
    mv "${INSTALL_DIR}/squashfs-root" "${INSTALL_DIR}/app"
    rm "${INSTALL_DIR}/rpcs3.AppImage"
  )

  rm -rf "${TMP_DIR}"
  echo "[INFO] Instalación completada."
}

## LLAMADAS
case "$1" in
"-i") appimage_install;;
"-u"|"-d") desinstalar;;
*)  exit 1;;
esac

exit 0