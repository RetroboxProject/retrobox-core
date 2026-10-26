"""Regenerate es_features.cfg from the YAML feature files.

Each YAML file describes the features of one emulator (``emulator_name``), of
one of its cores (``emulator_name`` + ``core_name``) or the features every
emulator can share (``emulator_name: _global_config``).

The groups and submenus of the menu follow one vocabulary, declared in the
``vocabulary`` section of ``_global_config.yaml``. It is checked for the
emulators it lists in ``enforce`` (or for all of them with ``enforce: all``,
except the ones in ``exempt``): a name outside the vocabulary only logs a
warning.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.dom import minidom

from yaml.parser import ParserError
from yaml.scanner import ScannerError

from retrobox.paths import ES_FEATURES_CFG, ES_FEATURES_TMP, layered_files
from retrobox.utils.features_yaml import load_feature_yaml

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping

_logger = logging.getLogger(__name__)

_GLOBAL_CONFIG_NAME = "_global_config"
_GENERAL_GROUP = "GENERAL"  # the features of this group have no "group" attribute
_NO_SUBMENU = "NONE"
# keys of the YAML that are not attributes of the element they describe
_LAUNCHER_KEYS = ("core_option", "core_options", "retroarch_option")  # read by the launcher only
_STRUCTURE_KEYS = ("emulator_name", "core_name", "features", "sharedFeatures", "systems", "groups")


@dataclass(frozen=True)
class Vocabulary:
    """The groups and submenus the menu is allowed to use.

    Attributes:
        groups: The allowed group names.
        submenus: The allowed submenu names of each group.
        enforced: The emulators that must use the vocabulary.
        enforce_all: Whether every emulator must use it, but the exempt ones.
        exempt: The emulators that are not checked when ``enforce_all`` is on.
    """

    groups: frozenset[str]
    submenus: Mapping[str, frozenset[str]]
    enforced: frozenset[str]
    enforce_all: bool = False
    exempt: frozenset[str] = frozenset()

    @classmethod
    def from_config(cls, global_config: Mapping[str, Any] | None) -> Vocabulary | None:
        """Read the vocabulary from ``_global_config.yaml``, or None if it has none."""
        data = (global_config or {}).get("vocabulary")
        if not isinstance(data, dict):
            return None
        return cls(
            groups=frozenset(map(str, data.get("groups") or [])),
            submenus={
                str(group): frozenset(map(str, names or []))
                for group, names in (data.get("submenus") or {}).items()
            },
            enforced=frozenset(
                map(str, data["enforce"] if isinstance(data.get("enforce"), list) else [])
            ),
            enforce_all=data.get("enforce") == "all",
            exempt=frozenset(map(str, data.get("exempt") or [])),
        )

    def applies_to(self, emulator: str) -> bool:
        """Tell whether the vocabulary is checked for an emulator."""
        if emulator == _GLOBAL_CONFIG_NAME:
            return True
        if self.enforce_all:
            return emulator not in self.exempt
        return emulator in self.enforced

    def problem(self, group: str, submenu: str | None) -> str | None:
        """Describe what is outside the vocabulary, or return None if all is fine."""
        if group not in self.groups:
            return f"group '{group}'"
        if submenu not in (None, _NO_SUBMENU) and submenu not in self.submenus.get(group, ()):
            return f"submenu '{submenu}' of group '{group}'"
        return None


@dataclass
class _Sources:
    """The parsed YAML files, by role."""

    global_config: dict[str, Any] | None = None
    emulators: dict[str, dict[str, Any]] = field(default_factory=dict)
    cores: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


@dataclass
class _Context:
    """What the builders need to know while writing the XML."""

    vocabulary: Vocabulary | None
    emulator: str = ""
    known_shared: set[str] = field(default_factory=set)
    warnings: set[str] = field(default_factory=set)

    def check(self, group: str, submenu: str | None) -> None:
        """Remember a warning if the placement is outside the vocabulary."""
        if self.vocabulary is None:
            return
        if not self.vocabulary.applies_to(self.emulator):
            return
        if (problem := self.vocabulary.problem(group, submenu)) is not None:
            self.warnings.add(f"{self.emulator}: {problem} is not in the vocabulary")


def _set_attributes(elem: ET.Element, data: Mapping[str, Any], skip: Iterable[str] = ()) -> None:
    """Set the non-empty values of ``data`` as attributes of ``elem``."""
    for key, value in data.items():
        if key not in skip and value is not None:
            elem.set(str(key), str(value))


def _append_feature(
    parent: ET.Element,
    item: Mapping[str, Any],
    group: str,
    submenu: str | None,
    context: _Context,
) -> None:
    """Append a <feature>, with its <choice> children, to ``parent``."""
    context.check(group, submenu)
    feature = ET.SubElement(parent, "feature")
    if group != _GENERAL_GROUP:
        feature.set("group", str(group))
    if submenu not in (None, _NO_SUBMENU):
        feature.set("submenu", str(submenu))
    _set_attributes(feature, item, skip=("choices", *_LAUNCHER_KEYS))

    choices = item.get("choices")
    if choices and isinstance(choices, list):
        for choice in choices:
            _set_attributes(ET.SubElement(feature, "choice"), choice)


def _append_shared_feature(
    parent: ET.Element, entry: str | Mapping[str, Any], context: _Context
) -> None:
    """Append a <sharedFeature> that points to a shared feature.

    An entry is the name of the shared feature, or a mapping with its ``value``
    and the ``group``, ``submenu`` and ``order`` it takes in this emulator.
    """
    shared = ET.SubElement(parent, "sharedFeature")
    if not isinstance(entry, dict):
        shared.set("value", str(entry))
        return

    if "group" in entry:
        context.check(str(entry["group"]), entry.get("submenu"))
    shared.set("value", str(entry["value"]))
    for key in ("group", "submenu", "order"):
        if entry.get(key) is not None and not (key == "group" and entry[key] == _GENERAL_GROUP):
            shared.set(key, str(entry[key]))


def _append_groups(parent: ET.Element, groups: Any, context: _Context) -> None:
    """Append the features of the ``groups`` section: submenu items first, then plain items."""
    if not groups or not isinstance(groups, dict):
        return

    for group_name, group_content in groups.items():
        if not isinstance(group_content, dict):
            continue

        for submenu_name, items in (group_content.get("submenus") or {}).items():
            if isinstance(items, list):
                for item in items:
                    _append_feature(parent, item, str(group_name), str(submenu_name), context)

        items = group_content.get("items") or []
        if isinstance(items, list):
            for item in items:
                _append_feature(parent, item, str(group_name), None, context)


def _append_features(parent: ET.Element, data: Mapping[str, Any], context: _Context) -> None:
    """Set the ``features`` attribute and append the shared features and groups."""
    if features := data.get("features"):
        if isinstance(features, list):
            parent.set("features", ", ".join(map(str, features)))
        else:
            parent.set("features", str(features))

    for entry in data.get("sharedFeatures") or []:
        _append_shared_feature(parent, entry, context)

    _append_groups(parent, data.get("groups"), context)


def _append_systems(parent: ET.Element, systems: Any, context: _Context) -> None:
    """Append a <systems> block with one <system> per entry."""
    if not systems or not isinstance(systems, list):
        return
    container = ET.SubElement(parent, "systems")
    for system_data in systems:
        system = ET.SubElement(container, "system")
        _set_attributes(system, system_data, skip=("features", "groups", "sharedFeatures"))
        _append_features(system, system_data, context)


def _append_emulator(
    root: ET.Element,
    name: str,
    data: Mapping[str, Any],
    cores: list[dict[str, Any]],
    context: _Context,
) -> None:
    """Append an <emulator>, with its systems and cores."""
    context.emulator = name
    emulator = ET.SubElement(root, "emulator")
    emulator.set("name", name)
    _set_attributes(emulator, data, skip=_STRUCTURE_KEYS)
    _append_features(emulator, data, context)
    _append_systems(emulator, data.get("systems"), context)

    if not cores:
        return
    container = ET.SubElement(emulator, "cores")
    for core_data in cores:
        core = ET.SubElement(container, "core")
        core.set("name", str(core_data.get("core_name")))
        _set_attributes(core, core_data, skip=_STRUCTURE_KEYS)
        _append_features(core, core_data, context)
        _append_systems(core, core_data.get("systems"), context)


def _append_global_features(
    root: ET.Element, global_config: Mapping[str, Any], context: _Context
) -> None:
    """Append the <sharedFeatures> definitions and the <globalFeatures> list."""
    context.emulator = _GLOBAL_CONFIG_NAME
    if global_config.get("groups"):
        shared = ET.SubElement(root, "sharedFeatures")
        _append_groups(shared, global_config["groups"], context)

    if global_features := global_config.get("sharedFeatures"):
        container = ET.SubElement(root, "globalFeatures")
        for entry in global_features:
            _append_shared_feature(container, entry, context)


def _load_sources(yaml_files: Iterable[Path]) -> _Sources:
    """Parse every YAML file given and sort it by role."""
    sources = _Sources()
    for yaml_file in yaml_files:
        try:
            with yaml_file.open(encoding="utf-8") as file:
                data = load_feature_yaml(file)
        except (ScannerError, ParserError) as err:
            _logger.error("Error parsing YAML file %s: %s", yaml_file.name, err)
            continue
        if not data or not isinstance(data, dict):
            continue

        emulator_name = data.get("emulator_name")
        if emulator_name == _GLOBAL_CONFIG_NAME:
            sources.global_config = data
        elif data.get("core_name"):
            sources.cores.setdefault(emulator_name, []).append(data)
        else:
            sources.emulators[emulator_name] = data
    return sources


def _defined_shared_features(global_config: Mapping[str, Any] | None) -> set[str]:
    """Return the shared features that exist: defined in the groups or in the global list."""
    known: set[str] = set()
    if not global_config:
        return known
    for group in (global_config.get("groups") or {}).values():
        items = list(group.get("items") or [])
        for submenu_items in (group.get("submenus") or {}).values():
            items.extend(submenu_items or [])
        known.update(str(item["value"]) for item in items)
    for entry in global_config.get("sharedFeatures") or []:
        known.add(str(entry["value"] if isinstance(entry, dict) else entry))
    return known


def _iter_references(root: ET.Element) -> Iterator[tuple[str, str]]:
    """Yield the (emulator, shared feature) pairs referenced by the emulators."""
    for emulator in root.findall("emulator"):
        for shared in emulator.iter("sharedFeature"):
            yield emulator.get("name", ""), shared.get("value", "")


def _warn_dangling_references(root: ET.Element, known_shared: set[str]) -> None:
    """Warn about the shared features that are referenced but defined nowhere."""
    dangling: dict[str, set[str]] = {}
    for emulator, value in _iter_references(root):
        if value not in known_shared:
            dangling.setdefault(emulator, set()).add(value)
    for emulator, values in sorted(dangling.items()):
        _logger.warning(
            "%s refers to undefined shared features: %s", emulator, ", ".join(sorted(values))
        )


def _build_tree(sources: _Sources) -> ET.Element:
    """Build the XML tree of es_features.cfg."""
    context = _Context(Vocabulary.from_config(sources.global_config))
    root = ET.Element("features")

    if sources.global_config:
        _append_global_features(root, sources.global_config, context)

    for name, data in sources.emulators.items():
        _append_emulator(root, name, data, sources.cores.get(name, []), context)

    for warning in sorted(context.warnings):
        _logger.warning("features vocabulary: %s", warning)
    _warn_dangling_references(root, _defined_shared_features(sources.global_config))
    return root


def _pretty_xml(root: ET.Element) -> str:
    """Indent the tree and drop the blank lines minidom adds."""
    pretty = minidom.parseString(ET.tostring(root, encoding="utf-8")).toprettyxml(
        indent="  ", encoding="utf-8"
    )
    lines = [line for line in pretty.decode("utf-8").splitlines() if line.strip()]
    return "\n".join(lines) + "\n"


def _link_features_file(output_path: Path) -> None:
    """Make ES_FEATURES_CFG a symlink to ``output_path``.

    Raises:
        FileNotFoundError: If the folder of ES_FEATURES_CFG does not exist.
    """
    try:
        if ES_FEATURES_CFG.exists() or ES_FEATURES_CFG.is_symlink():
            ES_FEATURES_CFG.unlink()
        ES_FEATURES_CFG.symlink_to(output_path)
        _logger.info("Successfully linked: %s", ES_FEATURES_CFG)
    except FileNotFoundError as err:
        _logger.error("Can't create symlink in %s: %s", ES_FEATURES_CFG.parent, err)
        raise


def _feature_yaml_files(yaml_dir: Path | None) -> list[Path]:
    """The feature YAML files to use, sorted by name.

    Without `yaml_dir` the layers (shipped resources, /etc/retrobox, the user's
    config) are merged: a file of a later layer replaces the one with the same
    name and extra files add features.
    """
    if yaml_dir is None:
        found = {
            rel: path for rel, path in layered_files("emu_features", "*.yaml").items() if "/" not in rel
        }
        if not found:
            raise FileNotFoundError("No emu_features found in any configuration layer")
        return list(found.values())
    if not yaml_dir.exists():
        raise FileNotFoundError(f"Features dir not found: {yaml_dir}")
    if not yaml_dir.is_dir():
        raise NotADirectoryError(f"Features dir isn't a directory: {yaml_dir}")
    return sorted(yaml_dir.glob("*.yaml"))


def generate_es_features(yaml_dir: Path | None = None, output_path: Path = ES_FEATURES_TMP) -> None:
    """Entry point for the es_features.cfg generator.

    Args:
        yaml_dir: Directory holding the per-emulator/core feature YAML files.
            None (default) merges emu_features/ across the configuration layers.
        output_path: Where to write the generated es_features.cfg.

    Raises:
        FileNotFoundError: If there are no feature files (or `yaml_dir` doesn't exist).
        NotADirectoryError: If `yaml_dir` exists but isn't a directory.
    """
    yaml_files = _feature_yaml_files(yaml_dir)

    if output_path.exists() or output_path.is_symlink():
        output_path.unlink()

    if output_path != ES_FEATURES_CFG and (
        ES_FEATURES_CFG.exists() or ES_FEATURES_CFG.is_symlink()
    ):
        ES_FEATURES_CFG.unlink()

    _logger.info("Begin generating: %s", output_path)
    final_xml = _pretty_xml(_build_tree(_load_sources(yaml_files)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(final_xml, encoding="utf-8")
    _logger.info("Successfully generated: %s", output_path)

    if output_path != ES_FEATURES_CFG:
        _link_features_file(output_path)
    _logger.info("=========")
