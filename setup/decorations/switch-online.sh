#!/usr/bin/env bash
## SWITCH-ONLINE BEZEL PACK INSTALLER
## CREATION DATE: September 6, 2026
set -eo pipefail

## VARIABLES
RETROBOX_ROOTDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOTDIR}/setup/lib/paths.sh"
INSTALL_DIR="${RETROBOX_BEZELS_DIR}/switch-online"
TMP_DIR="$(mktemp -d)"
# Nota: Se usa 'main' ya que es la rama por defecto visible en el repo. 
# Si cambia a 'master', ajustar a: refs/heads/master.zip
ZIP_URL="https://github.com/manu-creative-411/batocera-overlay-switchonline/archive/refs/heads/main.zip"
PACK_NAME="switch-online"
MANIFEST_DIR="${RETROBOX_STATEDIR}/packages/decorations"
MANIFEST_FILE="${MANIFEST_DIR}/${PACK_NAME}"

## FUNCTIONS
function error() {
    echo "[ERROR] $*." >&2
    exit 1
}

function install() {
    if ! command -v curl &> /dev/null; then
        echo "[INFO] curl not found. Attempting to install..."
        sudo dnf install -y curl || sudo apt-get install -y curl || error "Failed to install curl"
    fi
    if ! command -v unzip &> /dev/null; then
        echo "[INFO] unzip not found. Attempting to install..."
        sudo dnf install -y unzip || sudo apt-get install -y unzip || error "Failed to install unzip"
    fi

    mkdir -p "${INSTALL_DIR}"
    mkdir -p "${MANIFEST_DIR}"

    echo "[INFO] Downloading ${PACK_NAME} bezel pack..."
    curl -sL "${ZIP_URL}" -o "${TMP_DIR}/pack.zip"

    echo "[INFO] Extracting ${PACK_NAME} to ${INSTALL_DIR}..."
    unzip -q "${TMP_DIR}/pack.zip" -d "${TMP_DIR}"
    
    # Encontrar el directorio extraído (ej. batocera-overlay-switchonline-main)
    local extracted_dir
    extracted_dir="$(find "${TMP_DIR}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    
    if [[ -z "${extracted_dir}" ]]; then
        error "Failed to find extracted directory in zip"
    fi

    # Copiar contenidos al directorio de instalación
    cp -r "${extracted_dir}"/* "${INSTALL_DIR}/"

    echo "[INFO] Generating manifest at ${MANIFEST_FILE}..."
    # Generar manifiesto de archivos instalados relativo al directorio de bezels
    find "${INSTALL_DIR}" -type f | sed "s|^${RETROBOX_BEZELS_DIR}/||" > "${MANIFEST_FILE}"

    rm -rf "${TMP_DIR}"
    echo "[INFO] Installation of ${PACK_NAME} completed."
}

function uninstall() {
    echo "[INFO] Uninstalling ${PACK_NAME}..."
    if [[ ! -f "${MANIFEST_FILE}" ]]; then
        echo "[WARN] Manifest not found at ${MANIFEST_FILE}. Cannot safely uninstall."
        return 1
    fi

    while IFS= read -r file; do
        if [[ -f "${RETROBOX_BEZELS_DIR}/${file}" ]]; then
            rm -f "${RETROBOX_BEZELS_DIR}/${file}"
            echo "[INFO] Removed ${file}"
        fi
    done < "${MANIFEST_FILE}"
    
    # Eliminar el directorio si queda vacío
    rmdir "${INSTALL_DIR}" 2>/dev/null || true
    
    rm -f "${MANIFEST_FILE}"
    echo "[INFO] Uninstallation of ${PACK_NAME} completed."
}

## CALLS
case "$1" in
    "-i") install;;
    "-u"|"-d") uninstall;;
    *) exit 1;;
esac
exit 0