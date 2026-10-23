#!/usr/bin/env bash
## MULTI-INSTALADOR DE EMULADOR DE SWITCH - RYUJINX / RYUBING
## FECHA DE MODIFICACIÓN: Mayo de 2026
set -o pipefail

## VARIABLES
RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/setup/lib/paths.sh"

REPO_OWNER="projects"
REPO_NAME="Ryubing"
API_URL="https://git.ryujinx.app/api/v1/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest"

INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/ryujinx"
TMP_DIR="$(mktemp -d)"

## FUNCIONES DE CONTROL

function error(){
    echo "[ERROR] $*. F"
    rm -rf "$TMP_DIR" 2>/dev/null
    exit 1
}

function install_dependencies() {
    if ! command -v curl &> /dev/null || ! command -v jq &> /dev/null; then
        echo "[INFO] Instalando dependencias críticas (curl y jq)..."
        if command -v dnf &> /dev/null; then
            dnf install -y curl jq
        elif command -v apt-get &> /dev/null; then
            apt-get update && apt-get install -y curl jq
        elif command -v pacman &> /dev/null; then
            pacman -Sy --noconfirm curl jq
        fi
    fi
}

function get_api_json() {
    install_dependencies
    echo "[INFO] Conectando con la API de git.ryujinx.app..."
    JSON_DATA=$(curl -sL -H "Accept: application/json" "$API_URL")
    if [[ -z "$JSON_DATA" || "$JSON_DATA" == *"404 Not Found"* ]]; then
        error "No se pudo obtener respuesta de la API de Ryujinx."
    fi
    TAG_NAME=$(echo "$JSON_DATA" | jq -r '.tag_name')
}

## MÉTODOS DE INSTALACIÓN

function install_appimage(){
    get_api_json
    echo "[INFO] Filtrando AppImage x64 para la versión: $TAG_NAME"

    DOWNLOAD_URL=$(echo "$JSON_DATA" | jq -r '.assets[] |
        select(.name | endswith(".AppImage") and (contains("arm") or contains("aarch") or contains("zsync") | not))
        | .browser_download_url' | head -n 1)

    if [[ -z "$DOWNLOAD_URL" || "$DOWNLOAD_URL" == "null" ]]; then
        error "No se encontró un AppImage x64 válido en los assets."
    fi

    echo "[INFO] Descargando AppImage..."
    curl -L "$DOWNLOAD_URL" -o "$TMP_DIR/ryujinx.AppImage" || error "Fallo al descargar la AppImage."
    chmod +x "$TMP_DIR/ryujinx.AppImage"

    # Preparar directorio destino limpio
    rm -rf "$INSTALL_DIR" && mkdir -p "${INSTALL_DIR}/config"

    # Reubicar estructura interna
    mv "${TMP_DIR}/ryujinx.AppImage" "${INSTALL_DIR}"
    rm -rf "$TMP_DIR"

    echo "[INFO] Instalación mediante AppImage completada con éxito."
}

function install_tar_gz(){
    get_api_json
    echo "[INFO] Filtrando Tarball (.tar.gz) de Linux x64 para la versión: $TAG_NAME"

    DOWNLOAD_URL=$(echo "$JSON_DATA" | jq -r '.assets[] |
        select(.name | (contains("linux") or contains("Linux")) and endswith(".tar.gz") and (contains("arm") or contains("aarch") | not))
        | .browser_download_url' | head -n 1)

    if [[ -z "$DOWNLOAD_URL" || "$DOWNLOAD_URL" == "null" ]]; then
        error "No se encontró un archivo .tar.gz compatible con Linux x64."
    fi

    echo "[INFO] Descargando binarios compactados..."
    curl -L "$DOWNLOAD_URL" -o "$TMP_DIR/ryujinx.tar.gz" || error "Fallo al descargar el archivo comprimido."

    rm -rf "$INSTALL_DIR" && mkdir -p "$INSTALL_DIR"

    echo "[INFO] Desempaquetando archivos..."
    tar -xzf "$TMP_DIR/ryujinx.tar.gz" -C "$TMP_DIR"

    # Manejo flexible de la raíz interna del archivo comprimido
    if [ -d "$TMP_DIR/publish" ]; then
        mv "$TMP_DIR/publish"/* "$INSTALL_DIR/"
    elif ls "$TMP_DIR"/*/Ryujinx &>/dev/null || ls "$TMP_DIR"/*/Ryubing &>/dev/null; then
        mv "$TMP_DIR"/*/* "$INSTALL_DIR/"
    else
        rm -f "$TMP_DIR/ryujinx.tar.gz"
        mv "$TMP_DIR"/* "$INSTALL_DIR/" 2>/dev/null || true
    fi

    rm -rf "$TMP_DIR"

    # Forzar ejecución en binarios crudos
    find "$INSTALL_DIR" -type f -name "Ryujinx*" -exec chmod +x {} \;
    find "$INSTALL_DIR" -type f -name "Ryubing*" -exec chmod +x {} \;

    create_shortcuts
    echo "[INFO] Instalación mediante tar.gz completada con éxito."
}

function uninstall_all(){
    echo "[INFO] Buscando restos e instalaciones activas..."
    local found=0

    if [ -d "$INSTALL_DIR" ] || [ -f "$BIN_LINK" ]; then
        echo "[INFO] Eliminando instalación local (/var/opt)..."
        rm -rf "$INSTALL_DIR"
        found=1
    fi

    if [ $found -eq 0 ]; then
        echo "[INFO] No se localizó ninguna instalación previa en el sistema."
    fi
}

## CONTROL DE EJECUCIÓN

if [ -z "$1" ]; then
    echo "Uso: $0 [-f | -i | -t | -u]"
    echo "  -i : Instalar vía AppImage extraído (API Forgejo)"
    echo "  -u : Desinstalar limpiamente cualquier método detectado"
    exit 1
fi

case $1 in
    "-i") install_appimage ;;
    "-u") uninstall_all ;;
    *)
        echo "[ERROR] Opción no válida."
        exit 1
        ;;
esac

exit 0
