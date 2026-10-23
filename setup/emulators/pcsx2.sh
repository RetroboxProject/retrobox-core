#!/usr/bin/env bash
## INSTALADOR DE PCSX2
## FECHA DE CREACIÓN: 1 de noviembre de 2025
set -eo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/setup/lib/paths.sh"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/pcsx2"
TMP_DIR="$(mktemp -d)"
REPO="PCSX2/pcsx2"
API_URL="https://api.github.com/repos/$REPO/releases"

## FUNCIONES

function error() {
    echo "[ERROR] $*. F"
    exit 1
}

function desinstalar() {
    rm -r "${INSTALL_DIR}/app"
}

function appimage_install(){
  # 3. Comprobar curl
  for i in curl jq; do
    if ! command -v $i &> /dev/null; then
      sudo dnf install -y $i || sudo apt-get install -y $i
    fi
  done 

  releases=$(curl -sL "${API_URL}?per_page=10")
  
  # 6. Extraer URL del AppImage del primer elemento del array (la última release)
  APPIMAGE_URL=$(echo "$releases" | jq -r '
    .[0].assets[] | select(.name | contains(".AppImage") and (contains("arm") | not)) | .browser_download_url
  ' | head -n1)

  if [[ -z "${APPIMAGE_URL}" ]]; then
    error "No se encontró ningún AppImage en la última release disponible."
  fi
  
  # 7. Preparar directorio de instalación
  mkdir -p "${INSTALL_DIR}"

  # 8. Descargar y mover
  curl -L "${APPIMAGE_URL}" -o "${TMP_DIR}/pcsx2.AppImage"

  mv "${TMP_DIR}/pcsx2.AppImage" "${INSTALL_DIR}/pcsx2.AppImage"
  chmod +x "${INSTALL_DIR}/pcsx2.AppImage"
  mkdir -p "${INSTALL_DIR}/config"
  echo "[INFO] Extrayendo AppImage..."
  (
      cd "${INSTALL_DIR}" || exit 1
      "${INSTALL_DIR}/pcsx2.AppImage" --appimage-extract >/dev/null 2>&1
      mv "${INSTALL_DIR}/squashfs-root" "${INSTALL_DIR}/app"
      rm "${INSTALL_DIR}/pcsx2.AppImage"
  )

  # 9. Limpiar
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
