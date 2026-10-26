#!/usr/bin/env bash
## INSTALADOR DE CEMU
## FECHA DE CREACIÓN: 19 de mayo de 2026
## FECHAS DE MODIFICACIÓN: Creado con soporte para AppImage (x86_64) y Flatpak

## VARIABLES
RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
GITHUB_REPO="cemu-project/Cemu"
APPIMAGE_DIR="${RETROBOX_EMULATORS_DIR}/cemu"
BIN_LINK="/usr/local/bin/cemu"

## FUNCIONES

function error(){
    echo "[ERROR] $*. F"
    exit 1
}

function install_appimage(){
    echo "[INFO] Buscando la última versión de Cemu AppImage (x86_64) en GitHub..."

    # Obtener la URL de descarga del último release usando la API de GitHub (filtrando por AppImage y x86_64)
    DOWNLOAD_URL=$(curl -s "https://api.github.com/repos/$GITHUB_REPO/releases/latest" | grep -i "x86_64" | grep "browser_download_url.*\.AppImage" | cut -d '"' -f 4 | head -n 1)

    if [ -z "${DOWNLOAD_URL}" ]; then
        error "No se pudo obtener la URL de descarga del AppImage desde GitHub"
    fi

    echo "[INFO] Descargando: ${DOWNLOAD_URL}"
    mkdir -p "${APPIMAGE_DIR}"
    curl -L "${DOWNLOAD_URL}" -o "${APPIMAGE_DIR}/cemu.AppImage"

    if [ $? -ne 0 ]; then
        error "Error durante la descarga del AppImage"
    fi

    echo "[INFO] Configurando permisos y enlaces..."
    chmod +x "${APPIMAGE_DIR}/cemu.AppImage"
    mkdir -p "${APPIMAGE_DIR}/config"

    echo "[INFO] Instalación de AppImage completada."
}

function uninstall_app(){
    echo "[INFO] Buscando instalaciones de Cemu..."
    local found=0

    # Comprobar y desinstalar AppImage
    if [ -f "$APPIMAGE_DIR/cemu.AppImage" ] || [ -f "$BIN_LINK" ]; then
        echo "[INFO] Desinstalando versión AppImage..."
        rm -f "$BIN_LINK"
        rm -rf "$APPIMAGE_DIR"
        rm -f "$DESKTOP_FILE"
        rm -f "${ICON_PATH}"
        found=1
    fi

    if [ $found -eq 0 ]; then
        echo "[INFO] No se encontró ninguna instalación de Cemu."
    else
        echo "[INFO] Desinstalación completada."
    fi
}

## LLAMADAS


if [ -z "$1" ]; then
    echo "Uso: $0 [-f | -i | -u]"
    echo "  -i : Instalar usando AppImage (x86_64 desde GitHub)"
    echo "  -u : Desinstalar"
    exit 1
fi

echo "[INFO] Ejecutando acción para el parámetro: $1"

case $1 in
    "-i") install_appimage;;
    "-u") uninstall_app;;
    *)
        echo "[ERROR] Parámetro no reconocido."
        exit 1
        ;;
esac

exit 0
