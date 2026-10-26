#!/usr/bin/env bash
## INSTALADOR DE MODEL2EMU (SEGA MODEL 2)
## FECHA DE CREACIÓN: 23 de mayo de 2026
## FECHAS DE MODIFICACIÓN: Configurado para entorno Wine personalizado

## VARIABLES
RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"

DOWNLOAD_URL="https://github.com/batocera-linux/model2emu/raw/refs/heads/main/m2emulator.zip"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/model2emu"
EMU_DIR="$INSTALL_DIR/drive_c/model2emu"

## FUNCIONES

function error(){
    echo "[ERROR] $*. F"
    exit 1
}

function check_dependencies(){
    if ! command -v wine >/dev/null 2>&1; then
        error "Wine no está instalado en el sistema. Instálalo antes de continuar"
    fi
    if ! command -v unzip >/dev/null 2>&1; then
        error "La herramienta 'unzip' no está instalada. Instálala antes de continuar"
    fi
}

function m2emu_wine_install(){
    echo "[INFO] Verificando dependencias del sistema..."
    check_dependencies

    echo "[INFO] Creando directorio e inicializando WINEPREFIX..."
    mkdir -p "$INSTALL_DIR"

    echo "[INFO] Creando el directorio del emulador..."
    mkdir -p "$EMU_DIR"

    echo "[INFO] Descargando m2emulator.zip desde el repositorio de Batocera..."
    TMP_ZIP=$(mktemp /tmp/m2emu_XXXXXX.zip)
    curl -L "$DOWNLOAD_URL" -o "$TMP_ZIP"

    if [ $? -ne 0 ]; then
        rm -f "$TMP_ZIP"
        error "Error durante la descarga del archivo zip"
    fi

    echo "[INFO] Extrayendo archivos en la ruta de destino..."
    unzip -o "$TMP_ZIP" -d "$EMU_DIR" >/dev/null
    rm -f "$TMP_ZIP"

    echo "[INFO] Instalación de Model2Emu completada con éxito."
}

function m2emu_uninstall(){
    echo "[INFO] Buscando instalaciones de Model2Emu..."
    local found=0

    # Comprobar y eliminar estructura Wine/Archivos
    if [ -d "$INSTALL_DIR" ] || [ -f "$BIN_LINK" ]; then
        echo "[INFO] Eliminando WINEPREFIX y archivos de /opt..."
        rm -rf "$INSTALL_DIR"
        found=1
    fi

    if [ $found -eq 0 ]; then
        echo "[INFO] No se encontró ninguna instalación de Model2Emu."
    else
        echo "[INFO] Desinstalación completada."
    fi
}

## LLAMADAS

check_root

if [ -z "$1" ]; then
    echo "Uso: $0 [-i | -u]"
    echo "  -i : Instalar configurando WINEPREFIX propio en /opt y descargando archivos"
    echo "  -u : Desinstalar por completo (elimina archivos, WINEPREFIX, binario y acceso directo)"
    exit 1
fi

echo "[INFO] Ejecutando acción para el parámetro: $1"

case $1 in
    "-i") m2emu_wine_install;;
    "-u") m2emu_uninstall;;
    *)
        echo "[ERROR] Parámetro no reconocido."
        exit 1
        ;;
esac

exit 0
