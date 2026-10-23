"""Core options of the libretro cores, driven by the feature YAML files.

Every feature of a ``libretro_<core>.yaml`` file sets a core option, and the
choice picked in EmulationStation is written as it is, so the choice values must
be what the core expects. The option is looked up in this order (the generator of
es_features.cfg ignores these keys)::

    core_options:          # the choice sets several options (the value is a free name)
      2x: {melonds_render_mode: opengl, melonds_opengl_resolution: "2"}
    core_option: name      # the option has this name
    value: name            # otherwise the option is named like the feature

``value`` is the key EmulationStation stores for the game, so it must be unique
among the cores of a system: write ``core_option`` only when the two names
differ (two cores share an option name with other values, or the name has
characters the settings file cannot keep). An empty ``core_option`` is the same
as none. ``core_option: false`` says it is not a core option: other launcher
code reads that feature.

A feature can also set a setting of retroarch.cfg instead, the same way (the
choice is written as it is)::

    retroarch_option: input_libretro_device_p1    # a controller device, for example

A game that leaves the feature unset (or on ``auto``) gets the core default:
the options the feature manages are removed from the core options file, so a
value picked for another game never leaks into this one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from runtime.paths import layered_file
from runtime.utils.features_yaml import load_feature_yaml

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from ...config import SystemConfig
    from ...settings.unixSettings import UnixSettings

_logger = logging.getLogger(__name__)

# the values a feature has when the user did not choose: the core default is used
_DEFAULT_VALUES = ("", "auto")
_CORE_OPTION_KEY = "core_option"
_CORE_OPTIONS_KEY = "core_options"
_RETROARCH_OPTION_KEY = "retroarch_option"


@dataclass(frozen=True)
class CoreFeature:
    """A feature that sets core options.

    Attributes:
        feature: The name of the feature (its key in the game configuration).
        option: The core option that takes the chosen value as it is.
        choices: The options each choice sets, when a choice sets several; the
            ``option`` is not used then.
        in_retroarch_cfg: True when ``option`` is a setting of retroarch.cfg and
            not a core option.
    """

    feature: str
    option: str = ""
    choices: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    in_retroarch_cfg: bool = False

    @property
    def managed_options(self) -> set[str]:
        """Every option this feature may write."""
        if not self.choices:
            return {self.option}
        return {option for choice in self.choices.values() for option in choice}

    def options_for(self, selected: str | None) -> dict[str, str]:
        """Return the options to write for the selected choice.

        Args:
            selected: The value of the feature in the game, None if unset.

        Returns:
            The options to write; empty when the core default must be used.
        """
        if selected is None or selected in _DEFAULT_VALUES:
            return {}
        if not self.choices:
            return {self.option: selected}
        return dict(self.choices.get(selected, {}))


def _iter_items(data: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    """Yield every feature item of a YAML file."""
    for group in (data.get("groups") or {}).values():
        for items in (group.get("submenus") or {}).values():
            yield from items or []
        yield from group.get("items") or []


def _feature_of(item: Mapping[str, Any]) -> CoreFeature | None:
    """Return the core option feature an item describes, or None if it is not one."""
    name = str(item.get("value") or "").strip()
    if not name:
        return None

    if choices := item.get(_CORE_OPTIONS_KEY):
        return CoreFeature(
            name,
            choices={
                str(choice): {str(key): str(value) for key, value in options.items()}
                for choice, options in choices.items()
            },
        )

    if retroarch_option := str(item.get(_RETROARCH_OPTION_KEY) or "").strip():
        return CoreFeature(name, option=retroarch_option, in_retroarch_cfg=True)

    declared = item.get(_CORE_OPTION_KEY)
    if declared is False:
        return None
    return CoreFeature(name, option=str(declared or "").strip() or name)


def parse_core_features(data: Mapping[str, Any]) -> list[CoreFeature]:
    """Collect the features of a YAML file that set core options."""
    features = (_feature_of(item) for item in _iter_items(data))
    return [feature for feature in features if feature is not None]


def _core_yaml_path(core: str, features_dir: Path | None = None) -> Path | None:
    """Find the YAML file of a core: the file name may use "-" where the core uses "_".

    Without `features_dir`, the highest-priority configuration layer wins.
    """
    for stem in (core, core.replace("_", "-")):
        name = f"libretro_{stem}.yaml"
        if features_dir is None:
            candidate = layered_file(f"emu_features/{name}")
            if candidate is not None:
                return candidate
        elif (features_dir / name).is_file():
            return features_dir / name
    return None


def load_core_features(core: str, features_dir: Path | None = None) -> list[CoreFeature]:
    """Load the core option features of a core, or an empty list if it has none."""
    path = _core_yaml_path(core, features_dir)
    if path is None:
        return []
    try:
        with path.open(encoding="utf-8") as file:
            data = load_feature_yaml(file) or {}
        return parse_core_features(data)
    except (OSError, yaml.YAMLError, KeyError, AttributeError, TypeError) as err:
        # best effort: a broken feature file must never prevent the game from starting
        _logger.error("Unable to read the core options of %s: %s", path, err)
        return []


def apply_core_features(
    core_settings: UnixSettings, config: SystemConfig, features: list[CoreFeature]
) -> None:
    """Write (or remove) the core options of the features for the current game.

    Args:
        core_settings: The core options file, updated in place.
        config: The configuration of the running game.
        features: The core option features of the core.
    """
    for feature in features:
        if feature.in_retroarch_cfg:
            continue
        selected = config.get(feature.feature)
        wanted = feature.options_for(None if selected is config.MISSING else str(selected))
        for option in feature.managed_options - wanted.keys():
            core_settings.remove(option)
        for option, value in wanted.items():
            core_settings.save(option, f'"{value}"')


def apply_retroarch_settings(
    retroarch_config: dict[str, object], config: SystemConfig, features: list[CoreFeature]
) -> None:
    """Set the retroarch.cfg settings of the features the game has a value for.

    A game that leaves the feature unset (or on ``auto``) keeps the value the
    launcher already chose for the setting.

    Args:
        retroarch_config: The retroarch.cfg settings, updated in place.
        config: The configuration of the running game.
        features: The features of the core.
    """
    for feature in features:
        if not feature.in_retroarch_cfg:
            continue
        selected = config.get(feature.feature)
        if selected is config.MISSING or str(selected) in _DEFAULT_VALUES:
            continue
        retroarch_config[feature.option] = str(selected)
