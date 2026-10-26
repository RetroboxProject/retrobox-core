#!/bin/bash
# ==============================================================================
# Script Name: es_features_split.sh
# Description: Splits an EmulationStation 'es_features.cfg' XML file into 
#              separate YAML files for the emulator and individual cores ({emu}_{core}.yaml),
#              also capturing top-level elements like <sharedFeatures> and <globalFeatures>.
# Usage: ./es_features_split.sh [input_file] [output_directory]
# ==============================================================================

set -euo pipefail

INPUT_FILE="${1:-es_features.cfg}"
OUTPUT_DIR="${2:-yaml_features_output}"

if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: Input file '$INPUT_FILE' not found!" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
echo "=> Splitting $INPUT_FILE into YAML files (including global features and individual core files) in: $OUTPUT_DIR"

python3 - "$INPUT_FILE" "$OUTPUT_DIR" << 'EOF'
import sys
import os
import xml.etree.ElementTree as ET

input_file = sys.argv[1]
output_dir = sys.argv[2]

try:
    tree = ET.parse(input_file)
    root = tree.getroot()
except Exception as e:
    print(f"Error parsing XML: {e}", file=sys.stderr)
    sys.exit(1)

def parse_choices(elem):
    choices = []
    for choice in elem.findall('choice'):
        c_dict = {}
        for k, v in choice.attrib.items():
            c_dict[k] = v
        choices.append(c_dict)
    return choices

def parse_features_list_attr(elem):
    feat_val = elem.attrib.get('features', '')
    if feat_val:
        return [f.strip() for f in feat_val.split(',') if f.strip()]
    return []

def parse_hierarchical_features(element_container):
    groups = {}
    for feat in element_container.findall('feature'):
        f_data = {}
        for k, v in feat.attrib.items():
            if k not in ('group', 'submenu'):
                f_data[k] = v
        
        choices = parse_choices(feat)
        if choices:
            f_data['choices'] = choices
            
        group = feat.attrib.get('group', 'GENERAL')
        submenu = feat.attrib.get('submenu', 'NONE')
        
        if group not in groups:
            groups[group] = {'submenus': {}, 'items': []}
            
        if submenu != 'NONE':
            if submenu not in groups[group]['submenus']:
                groups[group]['submenus'][submenu] = []
            groups[group]['submenus'][submenu].append(f_data)
        else:
            groups[group]['items'].append(f_data)
            
    cleaned_groups = {}
    for g_key, g_val in groups.items():
        cleaned_groups[g_key] = {}
        if g_val['submenus']:
            cleaned_groups[g_key]['submenus'] = g_val['submenus']
        if g_val['items']:
            cleaned_groups[g_key]['items'] = g_val['items']
            
    return cleaned_groups if cleaned_groups else None

def parse_system(sys_elem):
    sys_data = {}
    for k, v in sys_elem.attrib.items():
        if k != 'features':
            sys_data[k] = v
            
    feats_attr = parse_features_list_attr(sys_elem)
    if feats_attr:
        sys_data['features'] = feats_attr
        
    hier_feats = parse_hierarchical_features(sys_elem)
    if hier_feats:
        sys_data['groups'] = hier_feats
    return sys_data

def format_yaml(data, indent=0):
    lines = []
    space = "  " * indent
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict):
                if not v:
                    lines.append(f"{space}{k}: {{}}")
                else:
                    lines.append(f"{space}{k}:")
                    lines.append(format_yaml(v, indent + 1))
            elif isinstance(v, list):
                if not v:
                    lines.append(f"{space}{k}: []")
                else:
                    lines.append(f"{space}{k}:")
                    lines.append(format_yaml(v, indent + 1))
            else:
                v_str = str(v)
                if any(char in v_str for char in [':', '#', '{', '}', '[', ']', ',', '&', '*', '?', '|', '-', '<', '>', '=', '!', '%', '@', '`']) or v_str == "":
                    v_str = f'"{v_str.replace("\"", "\\\"")}"'
                lines.append(f"{space}{k}: {v_str}")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                first = True
                for sub_k, sub_v in item.items():
                    if first:
                        if isinstance(sub_v, (dict, list)):
                            lines.append(f"{space}- {sub_k}:")
                            lines.append(format_yaml(sub_v, indent + 2))
                        else:
                            sub_v_str = str(sub_v)
                            if any(char in sub_v_str for char in [':', '#', '{', '}', '[', ']', ',', '&', '*', '?', '|', '-', '<', '>', '=', '!', '%', '@', '`']) or sub_v_str == "":
                                sub_v_str = f'"{sub_v_str.replace("\"", "\\\"")}"'
                            lines.append(f"{space}- {sub_k}: {sub_v_str}")
                        first = False
                    else:
                        sub_space = "  " * (indent + 1)
                        if isinstance(sub_v, (dict, list)):
                            lines.append(f"{sub_space}{sub_k}:")
                            lines.append(format_yaml(sub_v, indent + 2))
                        else:
                            sub_v_str = str(sub_v)
                            if any(char in sub_v_str for char in [':', '#', '{', '}', '[', ']', ',', '&', '*', '?', '|', '-', '<', '>', '=', '!', '%', '@', '`']) or sub_v_str == "":
                                sub_v_str = f'"{sub_v_str.replace("\"", "\\\"")}"'
                            lines.append(f"{sub_space}{sub_k}: {sub_v_str}")
            else:
                item_str = str(item)
                if any(char in item_str for char in [':', '#', '{', '}', '[', ']', ',', '&', '*', '?', '|', '-', '<', '>', '=', '!', '%', '@', '`']) or item_str == "":
                    item_str = f'"{item_str.replace("\"", "\\\"")}"'
                lines.append(f"{space}- {item_str}")
    return "\n".join(filter(None, lines))

# 0. Extraer los bloques raíz globales (<sharedFeatures> y <globalFeatures>) si existen
global_meta = {}

shared_features_elem = root.find('sharedFeatures')
if shared_features_elem is not None:
    # Reutilizamos la lógica de parse_hierarchical_features para procesar las features globales
    global_groups = parse_hierarchical_features(shared_features_elem)
    if global_groups:
        global_meta['groups'] = global_groups

global_features_elem = root.find('globalFeatures')
if global_features_elem is not None:
    g_shared = [sf.attrib.get('value') for sf in global_features_elem.findall('sharedFeature') if sf.attrib.get('value')]
    if g_shared:
        global_meta['sharedFeatures'] = g_shared

if global_meta:
    global_meta['emulator_name'] = '_global_config'
    global_yaml_text = format_yaml(global_meta)
    global_out_path = os.path.join(output_dir, "_global_config.yaml")
    with open(global_out_path, 'w', encoding='utf-8') as f:
        f.write(global_yaml_text + "\n")
    print(f"  -> Generated Global Root Config: {global_out_path}")

# 1. Procesar emuladores individuales
for emulator in root.findall('emulator'):
    emu_name = emulator.attrib.get('name', 'unknown_emulator')
    safe_emu_name = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in emu_name)
    
    emu_data = {'emulator_name': emu_name}
    for k, v in emulator.attrib.items():
        if k not in ('name', 'features'):
            emu_data[k] = v
            
    emu_feats = parse_features_list_attr(emulator)
    if emu_feats:
        emu_data['features'] = emu_feats
            
    shared = [sf.attrib.get('value') for sf in emulator.findall('sharedFeature')]
    if shared:
        emu_data['sharedFeatures'] = shared
        
    systems = []
    for sys_elem in emulator.findall('systems/system'):
        systems.append(parse_system(sys_elem))
    if systems:
        emu_data['systems'] = systems
        
    hier_feats = parse_hierarchical_features(emulator)
    if hier_feats:
        emu_data['groups'] = hier_feats
        
    emu_yaml_text = format_yaml(emu_data)
    out_path = os.path.join(output_dir, f"{safe_emu_name}.yaml")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(emu_yaml_text + "\n")
    print(f"  -> Generated Emulator Global: {out_path}")

    # 2. Generar un YAML independiente por cada core ({emulador}_{core}.yaml)
    for core_elem in emulator.findall('cores/core'):
        core_name = core_elem.attrib.get('name', 'unknown_core')
        safe_core_name = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in core_name)
        
        core_data = {'emulator_name': emu_name, 'core_name': core_name}
        for k, v in core_elem.attrib.items():
            if k not in ('name', 'features'):
                core_data[k] = v
                
        core_feats = parse_features_list_attr(core_elem)
        if core_feats:
            core_data['features'] = core_feats
        
        core_shared = [sf.attrib.get('value') for sf in core_elem.findall('sharedFeature')]
        if core_shared:
            core_data['sharedFeatures'] = core_shared
            
        core_hier_feats = parse_hierarchical_features(core_elem)
        if core_hier_feats:
            core_data['groups'] = core_hier_feats
            
        core_systems = []
        for sys_elem in core_elem.findall('.//system'):
            core_systems.append(parse_system(sys_elem))
        if core_systems:
            core_data['systems'] = core_systems
            
        core_yaml_text = format_yaml(core_data)
        core_out_path = os.path.join(output_dir, f"{safe_emu_name}_{safe_core_name}.yaml")
        with open(core_out_path, 'w', encoding='utf-8') as f:
            f.write(core_yaml_text + "\n")
        print(f"  -> Generated Core Specific: {core_out_path}")

print("=> Splitting completed successfully!")
EOF