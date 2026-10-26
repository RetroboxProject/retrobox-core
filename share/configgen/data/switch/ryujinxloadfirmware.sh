#!/bin/bash

# --- Mesurer le temps d'exécution ---
start=$(date +%s.%N)

# --- Répertoires ---
NCA_SRC_DIR="${RETROBOX_BIOS_DIR}/switch/firmware"
KEYS_SRC_DIR="${RETROBOX_BIOS_DIR}/switch/keys"
RYUJINX_SYSTEM_DIR="${RETROBOX_EMUCONFIG_DIR}/ryujinx/Ryujinx/system"
REGISTERED_DIR="${RETROBOX_EMUCONFIG_DIR}/ryujinx/Ryujinx/bis/system/Contents/registered"
CHECKSUM_FILE="${RETROBOX_EMUCONFIG_DIR}/ryujinx/Ryujinx/checksum_firmware.txt"

# --- Copier les keys (inchangé) ---
if [ -d "$KEYS_SRC_DIR" ]; then
    mkdir -p "$RYUJINX_SYSTEM_DIR"
    for f in "$KEYS_SRC_DIR"/*; do
        if [ -f "$f" ]; then
            cp -p "$f" "$RYUJINX_SYSTEM_DIR/"
        fi
    done
fi

# --- Calcul du checksum du dossier NCA ---
if [ -d "$NCA_SRC_DIR" ]; then
    cd "$NCA_SRC_DIR" || exit 1
    TMP_CHECKSUM=$(find . -type f -exec sha256sum {} + | sort | sha256sum | awk '{print $1}')

    # --- Vérifier le checksum existant ---
    if [ -f "$CHECKSUM_FILE" ]; then
        STORED_CHECKSUM=$(cat "$CHECKSUM_FILE")
        if [ "$TMP_CHECKSUM" == "$STORED_CHECKSUM" ]; then
            echo "Aucun changement détecté dans le dossier NCA, copie ignorée."
        else
            echo "Changements détectés, mise à jour des fichiers NCA."

            # --- Préparer registered ---
            mkdir -p "$REGISTERED_DIR"
            rm -rf "$REGISTERED_DIR"/*

            # --- Copier les fichiers .nca ---
            for f in "$NCA_SRC_DIR"/*.nca; do
                [ -f "$f" ] || continue
                filename=$(basename "$f")
                dst_dir="$REGISTERED_DIR/$filename"
                mkdir -p "$dst_dir"
                cp -p "$f" "$dst_dir/00"
                echo "[NCA] $filename → $dst_dir/00"
            done

            # --- Mettre à jour le checksum ---
            echo "$TMP_CHECKSUM" > "$CHECKSUM_FILE"
            echo "Checksum mis à jour dans $CHECKSUM_FILE"
        fi
    else
        echo "Checksum absent, première copie nécessaire."

        mkdir -p "$REGISTERED_DIR"
        rm -rf "$REGISTERED_DIR"/*

        for f in "$NCA_SRC_DIR"/*.nca; do
            [ -f "$f" ] || continue
            filename=$(basename "$f")
            dst_dir="$REGISTERED_DIR/$filename"
            mkdir -p "$dst_dir"
            cp -p "$f" "$dst_dir/00"
            echo "[NCA] $filename → $dst_dir/00"
        done

        echo "$TMP_CHECKSUM" > "$CHECKSUM_FILE"
        echo "Checksum créé dans $CHECKSUM_FILE"
    fi
fi

# --- Fin du script, calcul du temps ---
end=$(date +%s.%N)
runtime=$(echo "$end - $start" | bc)
# echo "Runtimes: $runtime secondes"
