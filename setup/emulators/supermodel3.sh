#!/usr/bin/env bash
## INSTALADOR DE SUPERMODEL
## FECHA DE CREACIÓN: 30 de julio de 2026
set -eo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/setup/lib/paths.sh"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/supermodel"
TMP_DIR="$(mktemp -d)"
REPO="trzy/Supermodel"
API_URL="https://api.github.com/repos/$REPO/releases"

## FUNCIONES

function error() {
    echo "[ERROR] $*. F"
    exit 1
}

function desinstalar() {
    if [[ -d "${INSTALL_DIR}" ]]; then
        rm -rf "${INSTALL_DIR}"
        echo "[INFO] Desinstalación completada."
    else
        echo "[INFO] El directorio de instalación no existe."
    fi
}

function install_supermodel(){
  # Comprobar curl y jq
  if ! command -v curl &> /dev/null; then
    dnf install -y curl
  fi

  if ! command -v jq &> /dev/null; then
    dnf install -y jq
  fi
  
  response=$(curl -sL "${API_URL}?per_page=10")
  
  # Validar si la respuesta es un array JSON válido
  if ! echo "$response" | jq -e 'type == "array"' >/dev/null 2>&1; then
    error "La API de GitHub no devolvió un array válido. Revisa el límite de peticiones o la URL del repositorio."
  fi
  
  # Extraer URL del tar.gz de Linux
  TAR_URL=$(echo "$response" | jq -r '
    [.[0].assets[]? | select(.name | contains("linux.tar.gz")) | .browser_download_url] | .[0]
  ')

  if [[ -z "${TAR_URL}" || "${TAR_URL}" == "null" ]]; then
    error "No se encontró ningún tar.gz de Linux en la última release disponible."
  fi
  
  # Preparar directorios
  mkdir -p "${TMP_DIR}"
  mkdir -p "${INSTALL_DIR}"

  # Descargar y extraer
  echo "[INFO] Descargando Supermodel..."
  curl -L "${TAR_URL}" -o "${TMP_DIR}/supermodel.tar.gz"

  echo "[INFO] Instalando..."
  tar -xzf "${TMP_DIR}/supermodel.tar.gz" -C "${TMP_DIR}"

  # Mover contenido manteniendo la estructura
  EXTRACTED_DIR=$(find "${TMP_DIR}" -mindepth 1 -maxdepth 1 -type d | head -n1)
  if [[ -n "${EXTRACTED_DIR}" ]]; then
      cp -r "${EXTRACTED_DIR}"/* "${INSTALL_DIR}/"
  else
      error "No se pudo encontrar el directorio extraído."
  fi

  # Limpiar
  rm -rf "${TMP_DIR}"
  echo "[INFO] Instalación completada en ${INSTALL_DIR}."
}

## LLAMADAS
case "$1" in
   "-i") install_supermodel;;
   "-u"|"-d") desinstalar;;
    *)  exit 1;;
esac

exit 0