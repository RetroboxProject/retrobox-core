"""RetroArch configuration: builds the ``retroarch.cfg`` settings of a game."""

# the module name follows the <emulator>Config convention of the generators
# pylint: disable=invalid-name

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict

from retrobox.paths import (
    BIOS,
    CHEATS,
    ES_GAMES_METADATA,
    RECORDINGS,
    SAVES,
    SCREENSHOTS,
    mkdir_if_not_exists,
)

from ... import controllersConfig
from ...settings.unixSettings import UnixSettings
from ...utils import bezels as bezels_util
from ...utils import metadata as metadata_utils
from .libretro_bezel import BezelRequest, write_bezel_config
from .libretro_core_options import (
    apply_core_features,
    apply_retroarch_settings,
    load_core_features,
)
from .libretro_ratio import CORE_RATIO_INDEX, RATIO_INDEXES
from .libretroControllers import clearGunInputsForPlayer, configureGunInputsForPlayer
from .libretroPaths import (
    _RETROARCH_CFGDIR,
    _RETROARCH_SHARE,
    RETROARCH_ASSETS,
    RETROARCH_CORE_CUSTOM,
    RETROARCH_CORES,
    RETROARCH_SHADERS,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ...typedefs import DeviceInfoMapping, Resolution
    from ...config import SystemConfig
    from ...controller import Controller, Controllers
    from ...Emulator import Emulator
    from ...gun import Guns
    from ..Generator import Generator

_logger = logging.getLogger(__name__)

_MAX_REMAPPED_PLAYERS = 4
_WIDE_RATIO = 4 / 3


class _GunMappingItem(TypedDict):
    """How a core maps the lightguns to its players."""

    device: NotRequired[int]
    p1: NotRequired[int]
    p2: NotRequired[int]
    p3: NotRequired[int]
    p4: NotRequired[int]
    game_dependant: NotRequired[list[dict[str, Any]]]


@dataclass(frozen=True)
class LibretroInputs:
    """The input devices of a game."""

    controllers: Controllers
    guns: Guns
    wheels: DeviceInfoMapping


@dataclass(frozen=True)
class LibretroDisplay:
    """The display options chosen by the generator."""

    bezel: str | None
    shader_bezel: bool
    gfx_backend: str


@dataclass(frozen=True)
class LibretroLaunch:
    """Everything needed to build the RetroArch settings of one game."""

    generator: Generator
    system: Emulator
    rom: Path
    resolution: Resolution
    metadata: Mapping[str, str]
    inputs: LibretroInputs
    display: LibretroDisplay


CORE_TO_P1_DEVICE = {"atari800": "513", "cap32": "513", "81": "259", "fuse": "769"}
CORE_TO_P2_DEVICE = {"atari800": "513", "fuse": "513"}

SYSTEMS_WITHOUT_REWIND = {
    "sega32x", "psx", "zxspectrum", "n64", "dreamcast", "atomiswave", "naomi", "saturn",
    "dice", "pd777",
}  # fmt: skip

_MD_CORES = ("genesis_plus_gx", "genesis_plus_gx-expanded")
_MD_KNOWN_GUIDS = (
    "05000000c82d00005106000000010000",
    "03000000c82d00000650000011010000",
    "050000005e0400008e02000030110000",
    "03000000c82d00000150000011010000",
    "05000000c82d00000151000000010000",
    "0500000049190000020400001b010000",
)
_MD_KNOWN_NAMES = (
    "8BitDo M30 gamepad",
    "8Bitdo  8BitDo M30 gamepad",
    "8BitDo M30 Modkit",
    "8Bitdo  8BitDo M30 Modkit",
    "Retro Bit Bluetooth Controller",
)
_MD_BUTTONS = {
    "btn_a": "0", "btn_b": "1", "btn_x": "9", "btn_y": "10", "btn_l": "11", "btn_r": "8",
}  # fmt: skip
_N64_KNOWN_GUIDS = (
    "050000007e0500001920000001800000",
    "05000000c82d00006928000000010000",
    "030000007e0500001920000011810000",
    "05000000c82d00001930000001000000",
    "03000000c82d00001930000011010000",
)
_N64_KNOWN_NAMES = (
    "N64 Controller",
    "Nintendo Co., Ltd. N64 Controller",
    "8BitDo N64 Modkit",
    "8BitDo 64 BT",
    "8BitDo 8BitDo 64 Bluetooth Controller",
)
_N64_BUTTONS = {
    "btn_a": "1", "btn_b": "0", "btn_x": "23", "btn_y": "21", "btn_l2": "22", "btn_r2": "20",
    "btn_select": "12",
}  # fmt: skip

_LANGUAGE_FONTS = {
    "1": "/usr/share/fonts/truetype/noto/NotoSansJP-VF.ttf",
    "ja_JP": "/usr/share/fonts/truetype/noto/NotoSansJP-VF.ttf",
    "10": "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "ko_KR": "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "11": "/usr/share/fonts/truetype/noto/NotoSansTC-VF.ttf",
    "zh_TW": "/usr/share/fonts/truetype/noto/NotoSansTC-VF.ttf",
    "12": "/usr/share/fonts/truetype/noto/NotoSansSC-VF.ttf",
    "zh_CN": "/usr/share/fonts/truetype/noto/NotoSansSC-VF.ttf",
}

# Lightgun device mapping per core/system. The "game_dependant" blocks are only
# read, never modified: the table is shared by every launch (module level),
# see _gun_core_settings.
GUN_CORE_MAPPING: dict[str, dict[str, _GunMappingItem]] = {
    "bsnes": {"default": {"device": 260, "p2": 0, "game_dependant": [
        {"key": "type", "value": "justifier", "mapkey": "device", "mapvalue": "516"},
        {
            "key": "reversedbuttons", "value": "true",
            "mapcorekey": "bsnes_touchscreen_lightgun_superscope_reverse", "mapcorevalue": "ON",
        },
    ]}},
    "snes9x": {"default": {"device": 260, "p2": 0, "p3": 1, "game_dependant": [
        {"key": "type", "value": "justifier", "mapkey": "device", "mapvalue": "516"},
        {"key": "type", "value": "justifier", "mapkey": "device_p3", "mapvalue": "772"},
        {"key": "type", "value": "macsrifle", "mapkey": "device", "mapvalue": "1028"},
        {
            "key": "reversedbuttons", "value": "true",
            "mapcorekey": "snes9x_superscope_reverse_buttons", "mapcorevalue": "enabled",
        },
    ]}},
    "fceumm": {"default": {"device": 258, "p2": 0}},
    "genesis_plus_gx": {
        "megadrive": {"device": 516, "p2": 0, "game_dependant": [
            {"key": "type", "value": "justifier", "mapkey": "device", "mapvalue": "772"},
        ]},
        "mastersystem": {"device": 260, "p1": 0, "p2": 1},
    },
    "flycast": {"default": {"device": 4, "p1": 0, "p2": 1, "p3": 2, "p4": 3}},
    "dolphin": {"default": {"device": 769, "p1": 0, "p2": 1, "p3": 2, "p4": 3}},
}

# Fixed retroarch.cfg settings that do not depend on system.config. They are
# rewritten on EVERY launch (as part of the same dict that create_libretro_config
# applies), so they always win over any change the user made from the RetroArch
# menu in the previous session: there is no "first time only" and no separate
# --appendconfig file.
#
# Deliberate trade-off: the user can NO LONGER change these keys from the
# RetroArch menu and have the change persist (for example raising audio_volume
# or touching confirm_close is reverted on the next launch). If one of them
# must be freely editable, remove it from here.
_FIXED_RETROARCH_SETTINGS: dict[str, str] = {
    "menu_driver": '"ozone"',
    "menu_show_load_content_animation": '"false"',
    "content_show_favorites": '"false"',
    "content_show_images": '"false"',
    "content_show_music": '"false"',
    "content_show_video": '"false"',
    "content_show_history": '"false"',
    "content_show_playlists": '"false"',
    "content_show_add": '"false"',
    "menu_show_load_core": '"false"',
    "menu_show_load_content": '"false"',
    "menu_show_online_updater": '"true"',
    "menu_show_core_updater": '"true"',
    "video_aspect_ratio_auto": '"false"',
    "video_gpu_screenshot": '"true"',
    "video_shader_enable": '"false"',
    "aspect_ratio_index": '"22"',
    "audio_volume": '"2.0"',
    "global_core_options": '"true"',
    "config_save_on_exit": '"true"',
    "savestate_auto_save": '"false"',
    "savestate_auto_load": '"false"',
    "menu_swap_ok_cancel_buttons": '"true"',
    "rgui_extended_ascii": '"true"',
    "rgui_show_start_screen": '"false"',
    "video_font_enable": '"true"',
    "savestate_thumbnail_enable": '"true"',
    "all_users_control_menu": '"false"',
    "cheevos_badges_enable": '"true"',
    "builtin_imageviewer_enable": '"false"',
    "fps_update_interval": '"30"',
    "confirm_close": '"false"',
    "confirm_quit": '"false"',
    "video_fullscreen": '"true"',
    "video_windowed_fullscreen": "'true'",
    "sort_savefiles_by_content_enable": '"true"',
    "sort_savestates_by_content_enable": '"true"',
}


def open_unix_settings(path: Path, /) -> UnixSettings:
    """Open a UnixSettings file, recreating it if corrupt, creating its directory.

    Public: LibretroGenerator.generate() also uses it to open retroarch.cfg.
    """
    mkdir_if_not_exists(path.parent)
    try:
        return UnixSettings(path, separator=" ")
    except UnicodeError:
        path.unlink()
        return UnixSettings(path, separator=" ")


def rarch_custom_paths(system: Emulator) -> dict[str, str]:
    """Return the fixed paths of retroarch.cfg.

    Pure function: the caller decides where and when to apply them (see
    LibretroGenerator.generate).
    """
    #mkdir_if_not_exists(BIOS / system.name)
    mkdir_if_not_exists(SAVES / system.name)

    return {
        "core_options_path": f'"{_RETROARCH_CFGDIR}/cores/retroarch-core-options.cfg"',
        "assets_directory": f'"{RETROARCH_ASSETS}"',
        "screenshot_directory": f'"{SCREENSHOTS}/"',
        "recording_output_directory": f'"{RECORDINGS}/"',
        "extraction_directory": f'"{_RETROARCH_SHARE}/extractions/"',
        "cheat_database_path": f'"{CHEATS}/cht/"',
        "cheat_settings_path": f'"{CHEATS}/saves/"',
        "system_directory": f'"{BIOS}/"',
        "joypad_autoconfig_dir": f'"{_RETROARCH_CFGDIR}/autoconfig/"',
        "video_shader_dir": f'"{RETROARCH_SHADERS}/"',
        "video_font_path": '"/usr/share/fonts/liberation-mono-fonts/LiberationMono-Regular.ttf"',
        "video_filter_dir": f'"{_RETROARCH_SHARE}/filters/video"',
        "audio_filter_dir": f'"{_RETROARCH_SHARE}/filters/audio"',
    }


def write_libretro_config(retroconfig: UnixSettings, launch: LibretroLaunch, /) -> None:
    """Build the RetroArch settings of a game and save them in ``retroconfig``."""
    write_libretro_config_to_file(retroconfig, create_libretro_config(launch))


def write_libretro_config_to_file(
    retroconfig: UnixSettings, config: Mapping[str, object], /
) -> None:
    """Save every setting of ``config`` in ``retroconfig``."""
    for setting, value in config.items():
        retroconfig.save(setting, value)


def _apply_base_settings(config: dict[str, object], system: Emulator, gfx_backend: str) -> None:
    """Set the drivers, directories, fonts and other settings common to all cores."""
    config["video_driver"] = f'"{gfx_backend}"'
    config["pause_nonactive"] = "true"
    mkdir_if_not_exists(_RETROARCH_CFGDIR / "cache")
    config["cache_directory"] = _RETROARCH_CFGDIR / "cache"
    config["libretro_directory"] = RETROARCH_CORES
    config["libretro_info_path"] = RETROARCH_CORES
    config["builtin_imageviewer_enable"] = "false"
    config["assets_directory"] = str(RETROARCH_ASSETS)

    # save directories
    config["sort_savefiles_enable"] = "false"
    config["sort_savestates_enable"] = "false"
    config["savestate_directory"] = Path(f"{SAVES}")
    config["savefile_directory"] = Path(f"{SAVES}")

    if system.config.core == "tgbdual":
        config["aspect_ratio_index"] = str(CORE_RATIO_INDEX)

    language = system.config.get_str(
        "retroarch.user_language", system.config.get_str("system.language")
    )
    if language in _LANGUAGE_FONTS:
        config["video_font_path"] = _LANGUAGE_FONTS[language]

    config["load_dummy_on_core_shutdown"] = '"false"'


def _set_device(
    config: dict[str, object], player: int, device: str, analog_dpad: str | None = None
) -> None:
    """Set the RetroArch device of a player, and optionally its analog dpad mode."""
    config[f"input_libretro_device_p{player}"] = device
    if analog_dpad is not None:
        config[f"input_player{player}_analog_dpad_mode"] = analog_dpad


def _chosen(config: SystemConfig, key: str, default: str) -> str:
    """Return a device option, or the default when it is unset or left on "auto"."""
    value = config.get(key, default)
    return default if value in ("", "auto") else value


def _apply_simple_core_inputs(
    config: dict[str, object], system: Emulator, controllers: Controllers
) -> None:
    """Set the devices of the cores that only need a few options."""
    core = system.config.core
    if core in ("puae", "puae2021", "vice_x64"):
        config["input_player1_analog_dpad_mode"] = "3"
        config["input_player2_analog_dpad_mode"] = "3"

    if core in CORE_TO_P1_DEVICE:
        config["input_libretro_device_p1"] = CORE_TO_P1_DEVICE[core]
    if core in CORE_TO_P2_DEVICE:
        config["input_libretro_device_p2"] = CORE_TO_P2_DEVICE[core]

    if core in ("snes9x", "snes9x_next"):
        config["input_libretro_device_p1"] = _chosen(system.config, f"controller1_{core}", "1")
        config["input_libretro_device_p2"] = _chosen(
            system.config, f"controller2_{core}", "257" if len(controllers) > 2 else "1"
        )
        config["input_libretro_device_p3"] = _chosen(system.config, "controller3_snes9x", "1")

    if core == "fceumm":
        config["input_libretro_device_p1"] = system.config.get("controller1_nes", "1")
        config["input_libretro_device_p2"] = system.config.get("controller2_nes", "1")


def _apply_psx_inputs(config: dict[str, object], launch: LibretroLaunch) -> None:
    """Set the devices of the PlayStation cores."""
    system = launch.system
    core = system.config.core
    if core == "mednafen_psx":
        for player in (1, 2):
            if ctrl := system.config.get(f"beetle_psx_hw_Controller{player}"):
                _set_device(config, player, ctrl, "0" if ctrl != "1" else "1")

    if core != "pcsx_rearmed":
        return

    for player in (1, 2):
        if ctrl := system.config.get(f"controller{player}_pcsx"):
            _set_device(config, player, ctrl, "0" if ctrl != "1" else "1")

    if not system.config.use_wheels:
        return
    device_infos = controllersConfig.getDevicesInformation()
    for pad in launch.inputs.controllers:
        if pad.device_path in device_infos and device_infos[pad.device_path].get("isWheel"):
            negcon = launch.metadata.get("wheel_type") == "negcon"
            config[f"input_player{pad.player_number}_analog_dpad_mode"] = "1"
            config[f"input_libretro_device_p{pad.player_number}"] = 773 if negcon else 517


def _apply_flycast_inputs(config: dict[str, object], launch: LibretroLaunch) -> None:
    """Set the devices of the Dreamcast core."""
    system = launch.system
    if system.config.core != "flycast":
        return

    for player in range(1, 5):
        device = system.config.get(f"controller{player}_dc", "1")
        if device == "5":
            _set_device(config, player, "1", "3")
        else:
            _set_device(config, player, device, "0")
    if system.config.use_wheels and launch.inputs.wheels:
        config["input_libretro_device_p1"] = "2049"


@dataclass(frozen=True)
class _PadRemap:
    """A button remap for well known pads."""

    guids: tuple[str, ...]
    names: tuple[str, ...]
    # the user option that forces the remap, with a ``{player}`` field
    option_format: str
    buttons: Mapping[str, str]


def _remap_known_pads(
    config: dict[str, object],
    system: Emulator,
    controllers: Sequence[Controller],
    remap: _PadRemap,
) -> None:
    """Remap the buttons of well known pads, or of those the user asked to remap."""
    for player in range(1, min(_MAX_REMAPPED_PLAYERS + 1, len(controllers) + 1)):
        pad = controllers[player - 1]
        is_known = pad.guid in remap.guids and pad.name in remap.names
        option = remap.option_format.format(player=player)
        if is_known or system.config.get(option, "retropad") != "retropad":
            for button, value in remap.buttons.items():
                config[f"input_player{player}_{button}"] = value


def _apply_megadrive_inputs(
    config: dict[str, object], system: Emulator, controllers: Controllers
) -> None:
    """Set the devices of the Mega Drive and Master System cores."""
    core = system.config.core
    if core in _MD_CORES and system.name == "megadrive":
        config["input_libretro_device_p1"] = system.config.get("controller1_md", "513")
        config["input_libretro_device_p2"] = system.config.get("controller2_md", "513")

    if core in (*_MD_CORES, "picodrive"):
        option = "gx" if core in _MD_CORES else "pd"
        remap = _PadRemap(
            _MD_KNOWN_GUIDS, _MD_KNOWN_NAMES, f"{option}_controller{{player}}_mapping", _MD_BUTTONS
        )
        _remap_known_pads(config, system, controllers, remap)

    if core == "genesis_plus_gx" and system.name == "mastersystem":
        config["input_libretro_device_p1"] = system.config.get("controller1_ms", "769")
        config["input_libretro_device_p2"] = system.config.get("controller2_ms", "769")


def _apply_saturn_and_n64_inputs(
    config: dict[str, object], system: Emulator, controllers: Controllers
) -> None:
    """Set the devices of the Saturn and Nintendo 64 cores."""
    core = system.config.core
    if core in ("yabasanshiro", "beetle-saturn") and system.name == "saturn":
        config["input_libretro_device_p1"] = system.config.get("controller1_saturn", "1")
        config["input_libretro_device_p2"] = system.config.get("controller2_saturn", "1")
        if core == "beetle-saturn" and system.config.use_wheels:
            config["input_libretro_device_p1"] = "517"

    if core in ("mupen64plus_next", "parallel_n64"):
        option = "mupen64plus" if core == "mupen64plus_next" else "parallel-n64"
        remap = _PadRemap(
            _N64_KNOWN_GUIDS, _N64_KNOWN_NAMES, f"{option}-controller{{player}}", _N64_BUTTONS
        )
        _remap_known_pads(config, system, controllers, remap)


def _apply_input_settings(config: dict[str, object], launch: LibretroLaunch) -> None:
    """Set the input drivers and the per-core devices and button remaps.

    The order matters: a later step may override what an earlier one set.
    """
    system = launch.system
    controllers = launch.inputs.controllers

    config["input_joypad_driver"] = "udev"
    config["input_driver"] = "udev"
    config["input_max_users"] = str(max(len(controllers), 1))
    config["input_libretro_device_p1"] = "1"
    config["input_libretro_device_p2"] = "1"

    _apply_simple_core_inputs(config, system, controllers)
    _apply_psx_inputs(config, launch)
    _apply_flycast_inputs(config, launch)
    _apply_megadrive_inputs(config, system, controllers)
    _apply_saturn_and_n64_inputs(config, system, controllers)


def _gun_core_settings(
    system: Emulator, game_metadata: Mapping[str, str]
) -> tuple[dict[str, Any], dict[str, str]]:
    """Return the lightgun mapping of the core, and the core options it needs.

    The shared GUN_CORE_MAPPING table is copied, never modified.
    """
    core = system.config.core
    core_mapping = GUN_CORE_MAPPING[core]
    # not .get(name, mapping["default"]): that evaluates "default" even when the
    # system has its own entry, and some cores (genesis_plus_gx) have no default
    base = core_mapping[system.name] if system.name in core_mapping else core_mapping["default"]
    gun_config: dict[str, Any] = dict(base)
    core_options: dict[str, str] = {}

    for rule in gun_config.get("game_dependant", []):
        if game_metadata.get(f"gun_{rule['key']}") != rule["value"]:
            continue
        if "mapkey" in rule and "mapvalue" in rule:
            gun_config[rule["mapkey"]] = rule["mapvalue"]
        if "mapcorekey" in rule and "mapcorevalue" in rule:
            core_options[rule["mapcorekey"]] = rule["mapcorevalue"]

    if core == "dolphin":
        core_options["dolphin_ir_offset"] = game_metadata.get("gun_vertical_offset", "10")
        core_options["dolphin_ir_yaw"] = game_metadata.get("gun_yaw", "25")
        core_options["dolphin_ir_pitch"] = game_metadata.get("gun_pitch", "20")

    return gun_config, core_options


def _apply_gun_settings(
    config: dict[str, object], launch: LibretroLaunch, core_settings: UnixSettings
) -> None:
    """Map the lightguns to the players, and set the cursor option."""
    system = launch.system
    guns = launch.inputs.guns
    if not system.config.use_guns:
        config["input_overlay_show_mouse_cursor"] = "true"
        return

    for index in range(len(guns)):
        clearGunInputsForPlayer(index + 1, config)

    if system.config.core not in GUN_CORE_MAPPING:
        return

    gun_config, core_options = _gun_core_settings(system, launch.metadata)
    for player in range(1, 4):
        gun_index = gun_config.get(f"p{player}")
        if gun_index is None or len(guns) - 1 < gun_index:
            continue
        device = gun_config.get(f"device_p{player}", gun_config.get("device", ""))
        config[f"input_libretro_device_p{player}"] = device
        configureGunInputsForPlayer(
            player, guns[gun_index], launch.inputs.controllers, config,
            system.config.core, launch.metadata, system,
        )

    for key, value in core_options.items():
        core_settings.save(key, f'"{value}"')
    config["input_overlay_show_mouse_cursor"] = "false"


def _apply_shader_settings(config: dict[str, object], system: Emulator) -> None:
    """Enable or disable the video shader and the integer scaling, and the smoothing."""
    config["video_scale_integer"] = system.config.get_bool(
        "integerscale", return_values=("true", "false")
    )
    config["video_smooth"] = system.config.get_bool("smooth", return_values=("true", "false"))
    if system.renderconfig.get("shader") not in (None, "none") and "shader" in system.renderconfig:
        config["video_shader_enable"] = "true"
        config["video_smooth"] = "false"
    else:
        config["video_shader_enable"] = "false"


def _ratio_hides_bezel(ratio: str) -> bool:
    """Tell whether a game ratio is wider than 4:3, which leaves no room for a bezel."""
    if "/" not in ratio:
        return False
    try:
        numerator, denominator = map(float, ratio.split("/"))
    except (ValueError, TypeError):
        return False
    return denominator != 0 and (numerator / denominator) > _WIDE_RATIO


def _apply_aspect_ratio(config: dict[str, object], launch: LibretroLaunch) -> bool:
    """Set the aspect ratio of the game.

    Returns:
        True when the ratio leaves no room for a bezel.
    """
    system = launch.system
    config["aspect_ratio_index"] = ""
    ratio = system.config.get_str("ratio")
    if not ratio:
        return False

    drop_bezel = ratio == "full"
    index = RATIO_INDEXES.index(ratio) if ratio in RATIO_INDEXES else CORE_RATIO_INDEX
    if not drop_bezel and system.config.get_bool(f"{system.config.core}-autowidescreen"):
        game_metadata = metadata_utils.get_games_meta_data(
            ES_GAMES_METADATA, system.name, launch.rom
        )
        if game_metadata.get("video_widescreen") == "true":
            index = RATIO_INDEXES.index("16/9")
            drop_bezel = True

    drop_bezel = drop_bezel or _ratio_hides_bezel(ratio)
    config["video_aspect_ratio_auto"] = "false"
    config["aspect_ratio_index"] = str(index)
    return drop_bezel


def _apply_ai_service_settings(config: dict[str, object], system: Emulator) -> None:
    """Set the AI translation service options."""
    if not system.config.get_bool("ai_service_enabled"):
        config["ai_service_enable"] = "false"
        return

    config["ai_service_enable"] = "true"
    config["ai_service_mode"] = "0"
    config["ai_service_source_lang"] = "0"
    target_lang = system.config.get("ai_target_lang", "En")
    url = system.config.get("ai_service_url", "http://ztranslate.net/service?api_key=BATOCERA")
    config["ai_service_url"] = f"{url}&mode=Fast&output=png&target_lang={target_lang}"
    config["ai_service_pause"] = system.config.get_bool(
        "ai_service_pause", return_values=("true", "false")
    )


def _apply_savestate_settings(config: dict[str, object], system: Emulator) -> None:
    """Set the savestate and autosave options."""
    autosave = system.config.get_bool("autosave", False, return_values=("true", "false"))
    config["savestate_auto_save"] = autosave
    config["savestate_auto_load"] = autosave

    if system.config.get_bool("incrementalsavestates", True):
        config["savestate_auto_index"] = "true"
        config["savestate_max_keep"] = "0"
    else:
        config["savestate_auto_index"] = "false"
        config["savestate_max_keep"] = "50"

    config["state_slot"] = system.config.get("state_slot", "0")

    state_filename = system.config.get_str("state_filename")
    if state_filename and state_filename.endswith(".auto"):
        config["savestate_auto_load"] = "true"


def _apply_video_and_misc_settings(config: dict[str, object], launch: LibretroLaunch) -> bool:
    """Set the shader, ratio, rewind, audio, translation, savestates and Discord options.

    Returns:
        True when the ratio leaves no room for a bezel.
    """
    system = launch.system
    _apply_shader_settings(config, system)
    drop_bezel = _apply_aspect_ratio(config, launch)

    can_rewind = system.name not in SYSTEMS_WITHOUT_REWIND and system.config.get_bool("rewind")
    config["rewind_enable"] = "true" if can_rewind else "false"
    config["audio_volume"] = system.config.get("audio_volume", "0")

    _apply_ai_service_settings(config, system)
    config["discord_allow"] = system.config.get_bool(
        "discordrpc", True, return_values=("true", "false")
    )
    _apply_savestate_settings(config, system)
    return drop_bezel


def _apply_bezel_settings(
    config: dict[str, object], launch: LibretroLaunch, drop_bezel: bool
) -> None:
    """Configure the overlay, falling back to no bezel if it fails.

    Whether a bezel may be drawn at all is decided by ``bezel_policy`` (the
    generator passes the result in ``launch.display.bezel``).
    """
    system = launch.system
    guns = launch.inputs.guns

    # Default value: centered image. write_bezel_config() only touches these
    # keys when a bezel (or gun borders) with its own viewport needs it. Since
    # UnixSettings only overwrites the keys present in this dict, a
    # video_viewport_bias_x/y = 0.0 left by the bezel of a previous game would
    # otherwise stay forever. Setting it here, BEFORE write_bezel_config(), makes
    # every launch start centered and move only if the current bezel asks to.
    config["video_viewport_bias_x"] = "0.500000"
    config["video_viewport_bias_y"] = "0.500000"

    request = BezelRequest(
        generator=launch.generator,
        system=system,
        rom=launch.rom,
        resolution=launch.resolution,
        bezel=None if drop_bezel else launch.display.bezel,
        shader_bezel=launch.display.shader_bezel,
        gun_borders=bezels_util.gun_borders_for(system, guns),
    )
    try:
        write_bezel_config(request, config)
    except Exception as err:  # pylint: disable=broad-exception-caught
        # best effort: a broken bezel must never prevent the game from starting
        write_bezel_config(replace(request, bezel=None), config)
        _logger.error("Error with bezel %s: %s", request.bezel, err, exc_info=True)


def create_libretro_config(launch: LibretroLaunch, /) -> dict[str, object]:
    """Build the retroarch.cfg settings of a game.

    Args:
        launch: Everything about the game being launched.

    Returns:
        The settings to save in retroarch.cfg.
    """
    system = launch.system
    core_settings = open_unix_settings(RETROARCH_CORE_CUSTOM)

    # Start from the fixed settings (see _FIXED_RETROARCH_SETTINGS): they are
    # rewritten on every launch and win over any change made from the RetroArch
    # menu in the previous session. Every step below may override single keys
    # of this dict depending on the system/core.
    config: dict[str, object] = dict(_FIXED_RETROARCH_SETTINGS)

    _apply_base_settings(config, system, launch.display.gfx_backend)
    features = load_core_features(system.config.core)
    _apply_input_settings(config, launch)
    apply_retroarch_settings(config, system.config, features)
    _apply_gun_settings(config, launch, core_settings)
    apply_core_features(core_settings, system.config, features)
    core_settings.write()

    drop_bezel = _apply_video_and_misc_settings(config, launch)
    _apply_bezel_settings(config, launch, drop_bezel)

    config.update(system.config.items(starts_with="retroarch."))
    return config
