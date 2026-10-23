"""Regenerate es_systems.cfg from the current systems_config directory tree."""
import logging
import os
import sys
from pathlib import Path
from typing import Final
import xml.etree.ElementTree as ET
from xml.dom import minidom
import yaml
from yaml.scanner import ScannerError
from yaml.parser import ParserError

# pylint: disable=wrong-import-position
from runtime.paths import (
    IGNORED_SYSTEMS,
    layered_files,
    ES_SYSTEMS_CFG,
    ES_SYSTEMS_TMP,
    RETROBOX_ROOTDIR,
    ROMS,
)
# pylint: enable=wrong-import-position

_logger = logging.getLogger(__name__)

PYTHON_COMMAND: Final = Path(sys.executable or "/usr/bin/python3")
EMULAUNCHER_COMMAND: Final = RETROBOX_ROOTDIR / "runtime" / "launcher" / "emulatorlauncher.py"
DEFAULT_COMMAND = [
    str(PYTHON_COMMAND),
    str(EMULAUNCHER_COMMAND),
    "%CONTROLLERSCONFIG%",
    "-system", "%SYSTEM%",
    "-rom", "%ROM%",
    "-gameinfoxml", "%GAMEINFOXML%",
    "-systemname", "%SYSTEMNAME%"
]

def _build_core_attributes(core_props):
    """Extract and format a core's attributes (default, incompatible_extensions)."""
    core_attrs = {}
    if not isinstance(core_props, dict):
        return core_attrs

    if core_props.get("default") is True:
        core_attrs["default"] = "true"

    incompatibles = core_props.get("incompatible_extensions")
    if incompatibles:
        if isinstance(incompatibles, list):
            core_attrs["incompatible_extensions"] = " ".join(incompatibles)
        else:
            core_attrs["incompatible_extensions"] = str(incompatibles)

    return core_attrs

def _append_emulator_nodes(parent_elem, emulators_data):
    """Process and append emulator nodes and their cores, skipping internal options."""
    if not isinstance(emulators_data, dict):
        return

    for emu_name, emu_data in emulators_data.items():
        emulator_elem = ET.SubElement(parent_elem, "emulator", name=emu_name)

        if not isinstance(emu_data, dict):
            continue

        # Look up the cores section safely
        cores_data = emu_data.get("cores", {})
        if not isinstance(cores_data, dict):
            continue

        for core_name, core_props in cores_data.items():
            # core_props may contain 'default', 'incompatible_extensions' and 'options'
            core_attrs = _build_core_attributes(core_props)
            core_elem = ET.SubElement(emulator_elem, "core", **core_attrs)
            core_elem.text = core_name

def _system_yaml_files(base_path: Path | None) -> list[str]:
    """The system definitions to use, sorted by their relative path.

    Without `base_path`, the layers (shipped resources, /etc/retrobox, the
    user's config) are merged: a file of a later layer replaces the one of the
    same relative path, and extra files add systems.
    """
    if base_path is None:
        found = layered_files("systems_config", "*.yaml")
        if not found:
            raise FileNotFoundError("No systems_config found in any configuration layer")
        return [str(path) for path in found.values()]
    if not os.path.exists(base_path):
        raise FileNotFoundError(f"Systems dir not found: {base_path}")
    if not os.path.isdir(base_path):
        raise NotADirectoryError(f"Systems dir isn't a directory: {base_path}")
    return sorted(str(p) for p in Path(base_path).rglob("*.yaml"))


def generate_es_systems(base_path: Path | None = None, output_path: Path = ES_SYSTEMS_TMP):
    """Rebuild es_systems.cfg from the (layered) systems_config YAML tree."""
    yaml_files = _system_yaml_files(base_path)

    _logger.info("Begin generating %s", output_path)

    if output_path.exists() or output_path.is_symlink():
        output_path.unlink()

    if output_path != ES_SYSTEMS_CFG and \
    (ES_SYSTEMS_CFG.exists() or ES_SYSTEMS_CFG.is_symlink()):
        ES_SYSTEMS_CFG.unlink()

    output_cfg_file: str = str(output_path)

    root = ET.Element("systemList")

    for yaml_path in yaml_files:
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except (ScannerError, ParserError) as e:
            _logger.error("YAML syntax error while reading %s: %s", yaml_path, e)
            continue

        if not isinstance(data, dict) or not data:
            continue

        sys_name, sys_content = next(iter(data.items()))

        if sys_name.lower() in IGNORED_SYSTEMS:
            _logger.info(
                "Skipping '%s' (listed in [core] ignore_systems): %s",
                sys_name, yaml_path,
            )
            continue

        system_elem = ET.SubElement(root, "system")
        name_elem = ET.SubElement(system_elem, "name")
        name_elem.text = sys_name
        if "path" not in sys_content:
            sys_content["path"] = str(Path(f"{ROMS}/{sys_name}"))

        # Ensure the 'command' field is present if it's missing from the YAML
        if "command" not in sys_content:
            sys_content["command"] = " ".join(DEFAULT_COMMAND)

        for key, value in sys_content.items():
            if key == "name":
                continue

            child_elem = ET.SubElement(system_elem, key)

            if key in ["platform", "extension"]:
                child_elem.text = " ".join(value) if isinstance(value, list) else str(value)
            elif key == "emulators":
                _append_emulator_nodes(child_elem, value)
            else:
                child_elem.text = str(value) if value is not None else ""

    rough_string = ET.tostring(root, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="\t", encoding="utf-8")

    decoded_xml = pretty_xml.decode('utf-8')
    clean_lines = []

    for line in decoded_xml.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("<?xml"):
            clean_lines.append(line)

    final_lines = ['<?xml version="1.0" encoding="UTF-8"?>'] + clean_lines
    final_xml = "\n".join(final_lines)

    with open(output_cfg_file, 'w', encoding='utf-8') as f:
        f.write(final_xml)
    _logger.info("Successfully generated: %s", output_cfg_file)

    if output_path != ES_SYSTEMS_CFG:
        try:
            if ES_SYSTEMS_CFG.exists() or ES_SYSTEMS_CFG.is_symlink():
                ES_SYSTEMS_CFG.unlink()
            ES_SYSTEMS_CFG.symlink_to(output_path)
            _logger.info("Successfully linked: %s", ES_SYSTEMS_CFG)
        except FileNotFoundError as e:
            _logger.error(
                "Can't create symlink in %s: %s",
                ES_SYSTEMS_CFG.parent, e
            )
            raise

    _logger.info("=========")