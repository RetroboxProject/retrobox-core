"""Regenerate es_systems.cfg from the current systems_config directory tree."""
import logging
import os
from pathlib import Path
from typing import Final
import xml.etree.ElementTree as ET
from xml.dom import minidom
import yaml
from yaml.scanner import ScannerError
from yaml.parser import ParserError

from retrobox.configgen.utils.logger import OK
from retrobox.paths import (
    BIN_DIR,
    IGNORED_SYSTEMS,
    layered_files,
    ES_SYSTEMS_CFG,
    ES_SYSTEMS_TMP,
    ROMS,
)
from retrobox.startup.frontend_conf.pcgames_paths import PCGAMES_SYSTEMS, pcgames_roms_dir

_logger = logging.getLogger(__name__)

# bin/retrobox-launch picks the right interpreter (the install's own venv, if
# any) and sets up PYTHONPATH, so the command needs no python of its own.
EMULAUNCHER_COMMAND: Final = BIN_DIR / "retrobox-launch"
DEFAULT_COMMAND = [
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


def _load_system(yaml_path: str) -> tuple[str, dict] | None:
    """
    Read one system definition.

    Args:
        yaml_path: The system's YAML file.

    Returns:
        (system name, its settings), or None if the file is invalid, empty
        or the system is listed in [core] ignore_systems.
    """
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (ScannerError, ParserError) as e:
        _logger.error("YAML syntax error while reading %s: %s", yaml_path, e)
        return None

    if not isinstance(data, dict) or not data:
        return None

    sys_name, sys_content = next(iter(data.items()))
    if not isinstance(sys_content, dict):
        return None
    if sys_name.lower() in IGNORED_SYSTEMS:
        _logger.info(
            "Skipping '%s' (listed in [core] ignore_systems): %s", sys_name, yaml_path
        )
        return None
    return sys_name, sys_content


def _append_system(root: ET.Element, sys_name: str, sys_content: dict) -> None:
    """Append the <system> node of one system to `root`, filling in defaults."""
    if sys_name in PCGAMES_SYSTEMS:
        # Must match where the PC-games sync writes ([core] <system>_sync).
        sys_content["path"] = str(pcgames_roms_dir(sys_name))
    else:
        sys_content.setdefault("path", str(ROMS / sys_name))
    sys_content.setdefault("command", " ".join(DEFAULT_COMMAND))

    system_elem = ET.SubElement(root, "system")
    ET.SubElement(system_elem, "name").text = sys_name

    for key, value in sys_content.items():
        if key == "name":
            continue

        child_elem = ET.SubElement(system_elem, key)
        if key in ("platform", "extension"):
            child_elem.text = " ".join(value) if isinstance(value, list) else str(value)
        elif key == "emulators":
            _append_emulator_nodes(child_elem, value)
        else:
            child_elem.text = str(value) if value is not None else ""


def _to_pretty_xml(root: ET.Element) -> str:
    """Serialize `root` indented with tabs, without blank lines."""
    pretty_xml = minidom.parseString(ET.tostring(root, "utf-8")).toprettyxml(indent="\t")
    lines = [
        line for line in pretty_xml.splitlines()
        if line.strip() and not line.lstrip().startswith("<?xml")
    ]
    return "\n".join(['<?xml version="1.0" encoding="UTF-8"?>', *lines])


def _unlink_if_present(path: Path) -> None:
    """Remove a file or symlink (even a dangling one) if it exists."""
    if path.exists() or path.is_symlink():
        path.unlink()


def generate_es_systems(base_path: Path | None = None, output_path: Path = ES_SYSTEMS_TMP):
    """Rebuild es_systems.cfg from the (layered) systems_config YAML tree."""
    yaml_files = _system_yaml_files(base_path)

    _logger.debug("Generating %s", output_path)

    _unlink_if_present(output_path)
    if output_path != ES_SYSTEMS_CFG:
        _unlink_if_present(ES_SYSTEMS_CFG)

    root = ET.Element("systemList")
    for yaml_path in yaml_files:
        system = _load_system(yaml_path)
        if system is not None:
            _append_system(root, *system)

    output_path.write_text(_to_pretty_xml(root), encoding="utf-8")
    _logger.log(OK, "Generated %s", output_path.name)

    if output_path != ES_SYSTEMS_CFG:
        try:
            ES_SYSTEMS_CFG.symlink_to(output_path)
            _logger.debug("Linked %s -> %s", ES_SYSTEMS_CFG, output_path)
        except FileNotFoundError as e:
            _logger.error("Can't create symlink in %s: %s", ES_SYSTEMS_CFG.parent, e)
            raise
