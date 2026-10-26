#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Uso: $0 <archivo_sistemas.xml> [directorio_base]"
    exit 1
fi

XML_FILE="$1"
BASE_DIR="${2:-ymls}"

mkdir -p "$BASE_DIR"

python3 - "$XML_FILE" "$BASE_DIR" << 'EOF'
import sys
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
import yaml

xml_file = sys.argv[1]
base_dir = sys.argv[2]

def slugify(text):
    if not text:
        return "unknown"
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = text.lower()
    text = re.sub(r'[^a-z0-9]', '', text)
    return text if text else "unknown"

try:
    tree = ET.parse(xml_file)
    root = tree.getroot()
except Exception as e:
    print(f"Error al parsear el XML: {e}")
    sys.exit(1)

for system in root.findall('system'):
    sys_data = {}
    sys_name = None
    manufacturer = None

    for child in system:
        tag = child.tag
        text = child.text.strip() if child.text else ""

        if tag == 'name':
            sys_name = text
            sys_data['name'] = text
        elif tag == 'manufacturer':
            manufacturer = text
            sys_data['manufacturer'] = text
        elif tag == 'release':
            try:
                sys_data[tag] = int(text)
            except ValueError:
                sys_data[tag] = text
        elif tag in ['platform', 'extension']:
            # Convertir cadenas con espacios o comas en listas YAML
            if ',' in text:
                sys_data[tag] = [p.strip() for p in text.split(',')]
            else:
                sys_data[tag] = [p.strip() for p in text.split()]
        elif tag == 'emulators':
            emulators_dict = {}
            for emulator in child.findall('emulator'):
                emu_name = emulator.get('name')
                cores_dict = {}
                
                cores = emulator.findall('.//core')
                if cores:
                    for core in cores:
                        core_name = core.text.strip() if core.text else ""
                        is_default = core.get('default') == 'true'
                        incompatible = core.get('incompatible_extensions')

                        core_props = {}
                        if is_default:
                            core_props['default'] = True
                        if incompatible:
                            if ',' in incompatible:
                                core_props['incompatible_extensions'] = [i.strip() for i in incompatible.split(',')]
                            else:
                                core_props['incompatible_extensions'] = [i.strip() for i in incompatible.split()]

                        # Inicializamos un diccionario de opciones vacío por defecto para cada core
                        if core_name not in cores_dict:
                            cores_dict[core_name] = core_props
                
                # Agrupamos los cores bajo la clave explícita 'cores'
                emulators_dict[emu_name] = {'cores': cores_dict}
            sys_data['emulators'] = emulators_dict
        else:
            sys_data[tag] = text

    if not sys_name:
        continue

    norm_manufacturer = slugify(manufacturer)
    target_dir = os.path.join(base_dir, norm_manufacturer)
    os.makedirs(target_dir, exist_ok=True)

    file_content = {sys_name: {k: v for k, v in sys_data.items() if k != 'name'}}

    output_path = os.path.join(target_dir, f"{sys_name}.yaml")
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(file_content, f, sort_keys=False, allow_unicode=True, width=1000)

print(f"Conversión completada. Estructura generada en '{base_dir}/<manufacturer>/'.")
EOF
