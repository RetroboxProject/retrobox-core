import json
import logging
import os

from ...controller import generate_sdl_game_controller_config
from ..eden.edenPaths import SWITCH_ROMS
from .ryujinxPaths import RYUJINX_CONFIG_FILE, RYUJINX_CONFIG_FILE_TPL
from .ryujinx_controllers import _ryujinx_gen_gamepad_config

_logger = logging.getLogger(__name__)

def writeRyujinxConfig(RyujinxConfigFile, RyujinxConfigFileBefore, RyujinxConfigTemplateFile, system, playersControllers):
    _logger.debug(RyujinxConfigTemplateFile)
    data = {}

    if os.path.exists(f"{RYUJINX_CONFIG_FILE_TPL}"):
        with open(f"{RYUJINX_CONFIG_FILE_TPL}", "r+", encoding="utf-8") as read_file:
            data = json.load(read_file)

    # if manual controller configuration, keep current config
    if system.isOptSet('ryu_auto_controller_config') and system.config["ryu_auto_controller_config"] == "0":
        if os.path.exists(f"{RYUJINX_CONFIG_FILE}"):
            with open(f"{RYUJINX_CONFIG_FILE}", "r+", encoding="utf-8") as read_file:
                current_data = json.load(read_file)
                data['input_config'] = current_data['input_config']

    if system.isOptSet('res_scale'):
        data['res_scale'] = int(system.config["res_scale"])
    else:
        data['res_scale'] = 1

    if system.isOptSet('max_anisotropy'):
        data['max_anisotropy'] = int(system.config["max_anisotropy"])
    else:
        data['max_anisotropy'] = -1 

    if system.isOptSet('aspect_ratio'):
        data['aspect_ratio'] = system.config["aspect_ratio"]
    else:
        data['aspect_ratio'] = 'Fixed16x9'

    if system.isOptSet('system_language'):
        data['system_language'] = system.config["system_language"]
    else:
        data['system_language'] = 'AmericanEnglish'

    if system.isOptSet('system_region'):
        data['system_region'] = system.config["system_region"]
    else:
        data['system_region'] = 'USA'

    # discord integration
    data['enable_discord_integration'] = system.config.get_bool('discordrpc', True, return_values=(True, False))
    
    # docked mode
    data['docked_mode'] = system.config.get_bool('ryu_docked_mode', True, return_values=(True, False))

    # V-Sync
    data['enable_vsync'] = system.config.get_bool("use_vsync", True, return_values=(True, False))

    # graphics backend
    if system.isOptSet('ryu_backend'):
        data['graphics_backend'] = system.config["ryu_backend"]
    else:
        data['graphics_backend'] = 'Vulkan'

    data['language_code'] = str(get_lang_from_sys_env())
    data['game_dirs'] = [f"{SWITCH_ROMS}"]

    data['input_config'] = _ryujinx_gen_gamepad_config(system, playersControllers)
    sdl_mapping = generate_sdl_game_controller_config(playersControllers)

    if not system.isOptSet('ryu_auto_controller_config') or system.config["ryu_auto_controller_config"] != "0":
        sdl_mapping = ""

    # Resolution Scale
    if system.isOptSet('ryu_resolution_scale'):
        if system.config["ryu_resolution_scale"] in {'1.0', '2.0', '3.0', '4.0', 1.0, 2.0, 3.0, 4.0}:
            data['res_scale_custom'] = 1
            if system.config["ryu_resolution_scale"] in {'1.0', 1.0}:
                data['res_scale'] = 1
            if system.config["ryu_resolution_scale"] in {'2.0', 2.0}:
                data['res_scale'] = 2
            if system.config["ryu_resolution_scale"] in {'3.0', 3.0}:
                data['res_scale'] = 3
            if system.config["ryu_resolution_scale"] in {'4.0', 4.0}:
                data['res_scale'] = 4
        else:
            data['res_scale_custom'] = float(system.config["ryu_resolution_scale"])
            data['res_scale'] = -1
    else:
        data['res_scale_custom'] = 1
        data['res_scale'] = 1

    # Texture Recompression
    if system.isOptSet('ryu_texture_recompression'):
        if system.config["ryu_texture_recompression"] in {"true", "1", 1}:
            data['enable_texture_recompression'] = True
        elif system.config["ryu_texture_recompression"] in {"false", "0", 0}:
            data['enable_texture_recompression'] = False
    else:
        data['enable_texture_recompression'] = False

    with open(RyujinxConfigFile, "w", encoding="utf-8") as outfile:
        outfile.write(json.dumps(data, indent=2))

    # just to be able to do diff to be sure than the emu is not changing values
    with open(RyujinxConfigFileBefore, "w", encoding="utf-8") as outfile:
        outfile.write(json.dumps(data, indent=2))

    return sdl_mapping

def get_lang_from_sys_env():
    """Checks the current system locale and if it's available for the emulator and games.
    If not, we fallback to en_US.
    """

    lang = os.environ['LANG'][:5]
    available_langs = [
        "en_US",
        "pt_BR",
        "es_ES",
        "fr_FR",
        "de_DE",
        "it_IT",
        "el_GR",
        "tr_TR",
        "zh_CN"
    ]

    if lang in available_langs:
        return lang
    else:
        return "en_US"