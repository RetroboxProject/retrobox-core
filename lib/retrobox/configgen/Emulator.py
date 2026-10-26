from __future__ import annotations

import logging
import os
import shlex
import stat
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import InitVar, dataclass, field
from typing import TYPE_CHECKING, Any
from pathlib import Path
import yaml

from retrobox.paths import CONFIG_LAYERS, DEFAULTS_DIR, layered_file, ES_SETTINGS_CFG, _SHADERS_DIR, configure_emulator

from .config import Config, SystemConfig
from .exceptions import MissingEmulator, RetroboxException
from .settings.unixSettings import UnixSettings

if TYPE_CHECKING:
    from argparse import Namespace
    from pathlib import Path
    from typing_extensions import deprecated

    from .gun import Guns

_logger = logging.getLogger(__name__)

# adapted from https://gist.github.com/angstwad/bf22d1822c38a92ec0a9
def _dict_merge(destination: dict[str, Any], source: Mapping[str, Any]) -> None:
    """Recursive dict merge. Inspired by :meth:``dict.update()``, instead of
    updating only top-level keys, dict_merge recurses down into dicts nested
    to an arbitrary depth, updating keys. The ``merge_dct`` is merged into
    ``dct``.
    :param destination: dict onto which the merge is executed
    :param source: dict merged into destination
    :return: None
    """
    for key, value in source.items():
        if key in destination and isinstance(destination[key], dict) and isinstance(value, Mapping):
            _dict_merge(destination[key], value)
        else:
            destination[key] = value

def _load_defaults(system_name: str, default_yml: Path, default_arch_yml: Path, /) -> dict[str, Any]:
    try:
        defaults = yaml.load(default_yml.read_text(), Loader=yaml.CLoader)
    except:
        return {}

    arch_defaults: dict[str, Any] = {}
    if default_arch_yml.exists():
        loaded_arch_defaults = yaml.load(default_arch_yml.read_text(), Loader=yaml.CLoader)
        if loaded_arch_defaults is not None:
            arch_defaults = loaded_arch_defaults

    config: dict[str, Any] = {}

    if 'default' in defaults:
        config = defaults['default']

    if 'default' in arch_defaults:
        _dict_merge(config, arch_defaults['default'])

    if system_name in defaults:
        _dict_merge(config, defaults[system_name])

    if system_name in arch_defaults:
        _dict_merge(config, arch_defaults[system_name])

    return config

def _load_system_config(system_name: str, rom: Path) -> dict[str, Any]:
    data: dict[str, Any] = {
        'emulator': None,
        'core': None,
    }

    if rom.suffix == ".menu":
        rom_name = rom.stem

        if "_" in rom.stem:
            data['emulator'], data['core'] = rom_name.split("_", 1)
        else:
            data['emulator'] = rom_name
            data['core'] = ""
        return data

    # 1. Cargar las opciones globales desde defaults.yml si existe en _ES_SYSTEMS_DIR
    defaults_path = layered_file("systems_config/defaults.yml")
    if defaults_path is not None:
        try:
            with open(defaults_path, 'r', encoding='utf-8') as f:
                defaults_content = yaml.safe_load(f)
                if isinstance(defaults_content, dict) and 'default' in defaults_content:
                    default_block = defaults_content['default']
                    # Extraer emulator y core globales si los hubiera
                    if 'emulator' in default_block:
                        data['emulator'] = default_block['emulator']
                    if 'core' in default_block:
                        data['core'] = default_block['core']
                    # Aplanar el bloque 'options' global si existe
                    if 'options' in default_block and isinstance(default_block['options'], dict):
                        _dict_merge(data, default_block['options'])
        except Exception as e:
            _logger.error("Error reading defaults.yml: %s", e)
            raise RetroboxException("Error reading default configs file") from e

    # 2. Buscar el archivo YAML del sistema específico dentro de la estructura de _ES_SYSTEMS_DIR
    # (the file of the highest-priority layer: user > /etc > shipped)
    sys_yaml_path = None
    for layer in reversed(CONFIG_LAYERS):
        found = next((layer / "systems_config").glob(f"**/{system_name}.yaml"), None)
        if found is not None:
            sys_yaml_path = found
            break

    if not sys_yaml_path or not sys_yaml_path.exists():
        _logger.error("YAML not found for system %s", system_name)
        raise RetroboxException(f"YAML not found for {system_name}")

    try:
        with open(sys_yaml_path, 'r', encoding='utf-8') as f:
            yaml_content = yaml.safe_load(f)            
    except Exception as e:
        _logger.error("Error reading system YAML %s: %s", system_name, e)
        raise RetroboxException(f"Error reading YAML for {system_name}") from e

    file_stem = Path(sys_yaml_path).stem
    if not yaml_content \
    or next(iter(yaml_content)) != file_stem \
    or next(iter(yaml_content)) != system_name \
    or file_stem != system_name:
        raise RetroboxException(
            f"YML for '{system_name}'|'{file_stem}' not well formed. Check first key")
    
    if not isinstance(yaml_content, dict) or system_name not in yaml_content:
        return data

    emulators_data = yaml_content[system_name] \
        .get('emulators', {})

    # 3. Buscar cuál es el emulador y core por defecto (marcado con default: true)
    selected_emulator = None
    selected_core = None
    core_options = {}

    for emu_name, emu_content in emulators_data.items():
        if not isinstance(emu_content, dict):
            continue

        cores_data = emu_content.get('cores', {})
        if not isinstance(cores_data, dict):
            continue

        for core_name, core_props in cores_data.items():
            if isinstance(core_props, dict) and core_props.get('default') is True:
                selected_emulator = emu_name
                selected_core = core_name
                if 'options' in core_props and isinstance(core_props['options'], dict):
                    core_options = core_props['options']
                break
        if selected_emulator:
            break

    # Si ningún core está marcado explícitamente como default, cogemos el primero por defecto
    if not selected_emulator and emulators_data:
        for emu_name, emu_content in emulators_data.items():
            if isinstance(emu_content, dict):
                cores_data = emu_content.get('cores', {})
                if cores_data:
                    selected_emulator = emu_name
                    selected_core = list(cores_data.keys())[0]
                    first_props = cores_data[selected_core]
                    if isinstance(first_props, dict) and 'options' in first_props:
                        core_options = first_props['options']
                    break

    if selected_emulator:
        data['emulator'] = selected_emulator
    if selected_core:
        data['core'] = selected_core

    # 4. Aplanar las opciones específicas del core para que sobrescriban a los valores de defaults.yml
    if core_options:
        _dict_merge(data, core_options)

    return data

def generate_bash_wrapper(
    emu_name: str,
    emu_bin: Path,
    emu_args: list[str],
    unset_vars: list[str] | None = None,
    force_x11: bool = False,
    force_gamescope: bool = False
    ) -> str:
    """This function is used to wrap emulator commands to bash scripts.
    Useful when an emulator needs to run on a pure shell context
    to retain environment variables or something else.
    Created as a workaround for running emulators with OpenGL
    and MangoHud (a combo that doesn't work by default on AppImage emulators).
    """

    env_lines = 'export SHARUN_ALLOW_LD_PRELOAD=1\n'
    if force_x11:
        env_lines += "export SDL_VIDEODRIVER=x11\n"
        env_lines += "export GDK_BACKEND=x11\n"
        env_lines += "export WAYLAND_DISPLAY=\n"

    gamescope_run = ""
    if force_gamescope:
        gamescope_run = "gamescope -f -- "
    
    if unset_vars:
        for var in unset_vars:
            env_lines += f'unset {shlex.quote(var)}\n'

    quoted_args = " ".join(shlex.quote(str(a)) for a in emu_args)
    script = f"""#!/usr/bin/env bash
set -uo pipefail
trap 'rm -f -- "$0"' EXIT
{env_lines}
{shlex.quote(str(emu_bin))} {quoted_args}
exit $?
"""
    fd, path = tempfile.mkstemp(prefix=f"{emu_name}_wrapper_", suffix=".sh")
    os.write(fd, script.encode())
    os.close(fd)
    os.chmod(path, stat.S_IRWXU)
    return path

@dataclass(slots=True)
class Emulator:
    args: InitVar[Namespace]
    rom: InitVar[Path]

    name: str = field(init=False)
    config: SystemConfig = field(init=False)
    renderconfig: Config = field(init=False)
    game_info_xml: str = field(init=False)
    __es_game_info: dict[str, str] | None = field(init=False, default=None)

    @property
    def es_game_info(self) -> Mapping[str, str]:
        if self.__es_game_info is not None:
            return self.__es_game_info

        self.__es_game_info = {}
        vals = self.__es_game_info

        try:
            tree = ET.parse(self.game_info_xml)
            root = tree.getroot()
            for child in root:
                for metadata in child:
                    vals[metadata.tag] = metadata.text or ''
        except Exception:
            _logger.debug("An error occurred while reading ES metadata")

        return vals

    def __post_init__(self, args: Namespace, rom: Path, /) -> None:
        self.name = args.system
        self.game_info_xml = args.gameinfoxml

        # read the configuration from the system name
        system_data = _load_system_config(args.system, rom)

        # sanitize rule by EmulationStation
        # see FileData::getConfigurationName() on batocera-emulationstation
        gsname = rom.name.replace('=', '').replace('#', '')
        _logger.info('game settings name: %s', gsname)

        # load configuration from batocera.conf
        settings = UnixSettings(ES_SETTINGS_CFG)

        global_settings = settings.get_all('global')
        system_settings = settings.get_all(args.system)
        folder_settings = settings.get_all(f'{args.system}.folder["{rom.parent}"]')
        game_settings = settings.get_all(f'{args.system}["{gsname}"]')

        # update config
        system_data.update(settings.get_all_iter('display', keep_name=True, keep_defaults=True))
        system_data.update(settings.get_all_iter('controllers', keep_name=True))

        language = settings.config.get('DEFAULT', 'system.language', fallback=None)
        if language is not None:
            # A few emulators have config options named "language", so "system.language" is chosen
            # in order to prevent conflicts with config options from es_features.yaml
            system_data['system.language'] = language

        system_data.update(global_settings)
        system_data.update(system_settings)
        system_data.update(folder_settings)
        system_data.update(game_settings)

        if not system_data['emulator']:
            if not configure_emulator(rom):
                _logger.error('no emulator defined. exiting.')
                raise MissingEmulator

        try:
            es_config = ET.parse(ES_SETTINGS_CFG)

            # showFPS
            drawframerate_node = es_config.find('./bool[@name="DrawFramerate"]')
            drawframerate_value = drawframerate_node.attrib['value'] if drawframerate_node is not None else 'false'
            if drawframerate_value not in ['false', 'true']:
                drawframerate_value = 'false'

            system_data['showFPS'] = drawframerate_value == 'true'

            # uimode
            uimode_node = es_config.find('./string[@name="UIMode"]')
            uimode_value = uimode_node.attrib['value'] if uimode_node is not None else 'Full'
            if uimode_value not in ['Full', 'Kiosk', 'Kid']:
                uimode_value = 'Full'

            system_data['uimode'] = uimode_value
        except Exception:
            system_data['showFPS'] = False
            system_data['uimode'] = 'Full'

        _logger.debug('uimode: %s', system_data['uimode'])

        system_data['emulator-forced'] = (
            'emulator' in global_settings
            or 'emulator' in system_settings
            or 'emulator' in game_settings
            or args.emulator is not None
        )
        system_data['core-forced'] = (
            'core' in global_settings
            or 'core' in system_settings
            or 'core' in game_settings
            or args.core is not None
        )

        if args.emulator is not None:
            system_data['emulator'] = args.emulator

        if args.core is not None:
            system_data['core'] = args.core

        if 'use_guns' not in system_data and args.lightgun:
            system_data['use_guns'] = True
        elif 'use_guns' in system_data:
            if args.lightgun:
                _logger.warning("use_guns manually set to '%s' to flagged game (auto-detection overridden)", system_data['use_guns'])
            else:
                _logger.info("use_guns manually set to '%s' to flagless game", system_data['use_guns'])

        if 'use_wheels' not in system_data and args.wheel:
            system_data['use_wheels'] = True
        elif 'use_wheels' in system_data:
            if args.wheel:
                _logger.warning("use_wheels manually set to '%s' to flagged game (auto-detection overridden)", system_data['use_wheels'])
            else:
                _logger.info("use_wheels manually set to '%s' to flagless game", system_data['use_wheels'])

        # network options
        if args.netplaymode is not None:
            system_data['netplay.mode'] = args.netplaymode

        if args.netplaypass is not None:
            system_data['netplay.password'] = args.netplaypass

        if args.netplayip is not None:
            system_data['netplay.server.ip'] = args.netplayip

        if args.netplayport is not None:
            system_data['netplay.server.port'] = args.netplayport

        if args.netplaysession is not None:
            system_data['netplay.server.session'] = args.netplaysession

        # autosave arguments
        if args.state_slot is not None:
            system_data['state_slot'] = args.state_slot

        if args.autosave is not None:
            system_data['autosave'] = args.autosave

        if args.state_filename is not None:
            system_data['state_filename'] = args.state_filename

        self.config = SystemConfig(system_data)

        render_data: dict[str, Any] = {}
        if (shader_set := self.config.get('shaderset')) is not self.config.MISSING:
            if shader_set == 'none':
                rendering_defaults = _SHADERS_DIR / 'configs' / 'rendering-defaults.yml'
            else:
                rendering_defaults = _SHADERS_DIR / 'configs' / shader_set / 'rendering-defaults.yml'
                if not rendering_defaults.exists():
                    rendering_defaults = _SHADERS_DIR / 'configs' / shader_set / 'rendering-defaults.yml'

            render_data = _load_defaults(
                args.system, rendering_defaults, rendering_defaults.with_name('rendering-defaults-arch.yml')
            )

        # es only allow to update systemSettings and gameSettings in fact for the moment

        # for compatibility with earlier Batocera versions, let's keep -renderer
        # but it should be reviewed when we refactor configgen (to Python3?)
        # so that we can fetch them from system.shader without -renderer
        try:
            render_data.update(settings.get_all_iter(f'{args.system}-renderer'))
            render_data.update(settings.get_all_iter(f'{args.system}["{gsname}"]-renderer'))
        except:
            pass

        self.renderconfig = Config(render_data or {})

    if TYPE_CHECKING:
        @deprecated('Use "key" in config')
        def isOptSet(self, key: str) -> bool: ...

        @deprecated('Use config.get_bool()')
        def getOptBoolean(self, key: str) -> bool: ...

        @deprecated('Use config.get_str()')
        def getOptString(self, key: str) -> str: ...

    else:
        def isOptSet(self, key: str) -> bool:
            return key in self.config

        def getOptBoolean(self, key: str) -> bool:
            true_values = {'1', 'true', 'on', 'enabled', True}
            value = self.config.get(key)

            if isinstance(value, str):
                value = value.lower()

            return value in true_values

        def getOptString(self, key: str) -> str:
            if key in self.config:  # noqa: SIM102
                if self.config[key]:
                    return self.config[key]
            return ""

    # returns None if no border is wanted
    def guns_borders_size_name(self, guns: Guns) -> str | None:
        borders_size: str = self.config.get('controllers.guns.borderssize', 'medium')

        # overridden by specific options
        borders_mode = 'normal'
        if (config_borders_mode := (self.config.get('controllers.guns.bordersmode') or 'auto')) != 'auto':
            borders_mode = config_borders_mode
        if (config_borders_mode := (self.config.get('bordersmode') or 'auto')) != 'auto':
            borders_mode = config_borders_mode

        # others are gameonly and normal
        if borders_mode == 'hidden':
            return None

        if borders_mode == 'force':
            return borders_size

        for gun in guns:
            if gun.needs_borders:
                return borders_size

        return None

    # returns None to follow the bezel overlay size by default
    def guns_border_ratio_type(self, guns: Guns) -> str | None:
        return self.config.get('controllers.guns.bordersratio', None)
