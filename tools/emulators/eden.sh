#!/usr/bin/env bash
## INSTALADOR DE EMULADOR DE SWITCH - EDEN (FORGEJO API VERSION)
## FECHA DE MODIFICACIÓN: 2026 (Adaptado para git.eden-emu.dev)
set -o pipefail

## VARIABLES
RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/eden-emu"
TMP_DIR="$(mktemp -d)"
REPO_OWNER="eden-emu"
REPO_NAME="eden"
API_URL="https://git.eden-emu.dev/api/v1/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest"

## FUNCIONES
function error() {
    echo "[ERROR] $*"
    exit 1
}

function appimage_install(){
    # 3. Comprobar dependencias críticas (curl y jq)
    if ! command -v curl &> /dev/null; then
        echo "Instalando curl..."
        if command -v dnf &> /dev/null; then dnf install -y curl; else apt-get update && apt-get install -y curl; fi
    fi
    
    if ! command -v jq &> /dev/null; then
        echo "Instalando jq..."
        if command -v dnf &> /dev/null; then dnf install -y jq; else apt-get update && apt-get install -y jq; fi
    fi

    # 4. Obtener JSON desde la API de Forgejo
    echo "Conectando con la API de git.eden-emu.dev..."
    json=$(curl -sL -H "Accept: application/json" "$API_URL")

    if [[ -z "$json" || "$json" == *"404 Not Found"* ]]; then
        error "No se pudo conectar a la API o el repositorio no existe."
    fi

    # 5. Extraer tag_name
    TAG_NAME=$(echo "$json" | jq -r '.tag_name')
    echo "Última versión detectada: $TAG_NAME"

    # 6. Extraer URL del AppImage desde los assets de Forgejo
    # Filtramos por .AppImage, que no sea zsync y que sea para x86_64
    APPIMAGE_URL=$(echo "$json" | jq -r '.assets[] | 
        select(.name | endswith(".AppImage") 
        and (contains("arm") or contains("aarch") or contains("AppImage.zsync") | not)) 
        | .browser_download_url' | head -n 1)

    if [[ -z "$APPIMAGE_URL" || "$APPIMAGE_URL" == "null" ]]; then
        error "No se encontró ningún AppImage válido en la última release de Forgejo."
    fi

    echo "Descargando desde: $APPIMAGE_URL"

    # 7. Preparar directorio de instalación
    mkdir -p "${INSTALL_DIR}/config"

    # 8. Descargar y mover
    curl -L "${APPIMAGE_URL}" -o "${TMP_DIR}/eden-emu.AppImage" || error "Error al descargar el archivo."

    mv "$TMP_DIR/eden-emu.AppImage" "${INSTALL_DIR}/eden-emu.AppImage"
    chmod +x "${INSTALL_DIR}/eden-emu.AppImage"

    # 9. Limpiar temporal inicial
    rm -rf "${TMP_DIR}"

    echo "¡Eden Emulator ($TAG_NAME) instalado con éxito!"
}

function desinstalar() {
    echo "Desinstalando Eden Emulator..."
    rm -rf "${INSTALL_DIR}"
    echo "Desinstalación completa."
}

case "$1" in
    -i) appimage_install ;;
    -u) desinstalar ;;
    *) echo "Uso: $0 {-i (instalar) | -u (desinstalar)}" ; exit 1 ;;
esac

exit 0
