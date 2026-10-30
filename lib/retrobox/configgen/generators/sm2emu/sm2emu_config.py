"""Writing of sm2-emu.ini from the options of the game.

sm2-emu reads ``key = value`` lines and ignores which tab section
(``[video]``, ``[audio]``...) they are in, but for the gamepad keys of a game
family section. It rewrites the whole file when its overlay saves on exit, so
only the keys Retrobox manages are replaced here: anything else the user set
in the overlay (per-game pad layouts, link settings...) is kept.
"""

from __future__ import annotations

import configparser
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final

from retrobox.paths import ROMS, ensure_parents_and_open

from ...controller import evdev_to_hidraw
from ...utils import vulkan
from ...utils.audio_gain import gain_to_percent
from .sm2emu_controls import layout_settings
from .sm2emu_games import game_family, game_set
from .sm2emu_paths import (
    SM2EMU_BUILD_INFO,
    SM2EMU_CFG,
    SM2EMU_NVRAM,
    SM2EMU_SCREENSHOTS,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ...config import SystemConfig
    from ...controller import Controller, Controllers
    from ...Emulator import Emulator
    from ...typedefs import DeviceInfoMapping, Resolution

_logger = logging.getLogger(__name__)

BACKEND_OPENGL: Final = "opengl"
BACKEND_VULKAN: Final = "vulkan"
BACKEND_SOFTWARE: Final = "software"
_BACKENDS: Final = (BACKEND_OPENGL, BACKEND_VULKAN, BACKEND_SOFTWARE)

ASPECT_4_3: Final = "4:3"
ASPECT_16_9: Final = "16:9"
ASPECT_SQUARE: Final = "square"
ASPECT_STRETCH: Final = "stretch"
_NATIVE_WIDTH: Final = 496  # the picture of the hardware, in square pixels
_NATIVE_HEIGHT: Final = 384

_MAX_VOLUME: Final = 150  # sm2-emu caps the volume of a game family at 150 %
_PLAYERS: Final = 2  # Model 2 cabinets have at most two players

# The keys sm2-emu ships with. They are written every time because the
# gamepad profile (share/pad2key/profiles/sm2-emu.keys) presses them: a key
# rebound in the overlay would leave a hotkey dead.
_DEFAULT_KEYS: Final[Mapping[str, str]] = {
    "key_exit": "Escape",
    "key_quit": "F9",
    "key_overlay": "F10",
    "key_fullscreen": "F11",
    "key_screenshot": "F12",
    "key_pause": "P",
    "key_quick_save": "F6",
    "key_quick_load": "F7",
    "key_fps": "F8",
    "key_fast_forward": "Tab",
    "key_rewind": "Backspace",
}

# ES input names of the wheel controls, in the order they are looked for
_STEER_INPUTS: Final = ("joystick1left", "joystick1right")
_ACCEL_INPUTS: Final = ("r2", "right_trigger")
_BRAKE_INPUTS: Final = ("l2", "left_trigger")
_GEAR_UP_INPUTS: Final = ("pagedown", "r1", "right_shoulder")
_GEAR_DOWN_INPUTS: Final = ("pageup", "l1", "left_shoulder")
# sm2-emu wheel button -> ES input names (Model 2 buttons 1-4 follow the pad's)
_WHEEL_BUTTONS: Final[Mapping[str, tuple[str, ...]]] = {
    "wheel_button_start": ("start",),
    "wheel_button_coin": ("select",),
    "wheel_button_1": ("b",),
    "wheel_button_2": ("a",),
    "wheel_button_3": ("y",),
    "wheel_button_4": ("x",),
    "wheel_button_gear_up": _GEAR_UP_INPUTS,
    "wheel_button_gear_down": _GEAR_DOWN_INPUTS,
}
_UNSET: Final = "-1"

# the sections sm2-emu names after the tabs of its overlay; any other one is
# the layout of a game family, where only the pad layout keys belong to it
_TAB_SECTIONS: Final = frozenset(
    ("video", "audio", "paths", "gamepad", "wheel", "lightgun", "network", "system")
)
_PAD_KEY_PREFIXES: Final = ("pad1_button_", "pad2_button_", "pad1_axis_", "pad2_axis_")


def _ini_bool(value: bool) -> str:
    """Return a boolean the way sm2-emu writes it."""
    return "true" if value else "false"


# ---------------------------------------------------------------------------
# Graphics
# ---------------------------------------------------------------------------


def _binary_has_vulkan() -> bool:
    """Tell whether the installed binary was built with the Vulkan backend.

    The installer records it in ``retrobox-build.ini``. Without that file the
    binary is taken to be an upstream release, which always carries Vulkan.
    """
    if not SM2EMU_BUILD_INFO.is_file():
        return True
    parser = configparser.ConfigParser()
    try:
        parser.read(SM2EMU_BUILD_INFO, encoding="utf-8")
    except configparser.Error:
        return True
    return parser.getboolean("build", "vulkan", fallback=True)


def resolve_backend(config: SystemConfig) -> str:
    """Return the renderer sm2-emu will use: "opengl", "vulkan" or "software".

    OpenGL is the default. Vulkan falls back to OpenGL when the system has no
    Vulkan driver or when the binary was built without the backend.
    """
    requested = config.get_str("sm2_graphics_backend", BACKEND_OPENGL)
    if requested not in _BACKENDS:
        return BACKEND_OPENGL
    if requested == BACKEND_VULKAN:
        if not _binary_has_vulkan():
            _logger.debug("sm2-emu was built without Vulkan. Using OpenGL instead.")
            return BACKEND_OPENGL
        if not vulkan.is_available():
            _logger.debug("Vulkan driver is not available on the system. Using OpenGL instead.")
            return BACKEND_OPENGL
    return requested


def uses_opengl(config: SystemConfig) -> bool:
    """Tell whether the picture goes through OpenGL (the software renderer presents with it)."""
    return resolve_backend(config) != BACKEND_VULKAN


def _gpu_name(backend: str) -> str:
    """Return the Vulkan device to render on: the discrete GPU, if any, or SDL's choice."""
    if backend != BACKEND_VULKAN or not vulkan.has_discrete_gpu():
        return ""
    return vulkan.get_discrete_gpu_name() or ""


def aspect_mode(config: SystemConfig) -> str:
    """Return the shape the picture is fit into."""
    mode = config.get_str("sm2_aspect_mode", ASPECT_4_3)
    return mode if mode in (ASPECT_4_3, ASPECT_16_9, ASPECT_SQUARE, ASPECT_STRETCH) else ASPECT_4_3


def bezel_fits(config: SystemConfig) -> bool:
    """Tell whether the picture is 4:3, the only shape a bezel is made for."""
    return aspect_mode(config) == ASPECT_4_3


def get_in_game_ratio(config: SystemConfig, resolution: Resolution) -> float:
    """Return the aspect ratio of the picture sm2-emu shows."""
    mode = aspect_mode(config)
    if mode == ASPECT_16_9:
        return 16 / 9
    if mode == ASPECT_SQUARE:
        return _NATIVE_WIDTH / _NATIVE_HEIGHT
    if mode == ASPECT_STRETCH:
        # fills the window, so it depends on the physical screen
        return resolution["width"] / resolution["height"]
    return 4 / 3


def _video_settings(config: SystemConfig, resolution: Resolution) -> dict[str, str]:
    """Return the [video] keys: renderer, scaling and enhancements."""
    backend = resolve_backend(config)
    return {
        "graphics_backend": backend,
        "gpu": _gpu_name(backend),
        "fullscreen": "true",
        "window_width": str(resolution["width"]),
        "window_height": str(resolution["height"]),
        "vsync": _ini_bool(config.get_bool("sm2_vsync", False)),
        "render_scale": config.get_str("sm2_render_scale", "1"),
        "scaling_method": config.get_str("sm2_scaling_method", "sharp"),
        "aspect_mode": aspect_mode(config),
        "texture_filter": config.get_str("sm2_texture_filter", "faithful"),
        "anisotropy": config.get_str("sm2_anisotropy", "4"),
        "upscale_2d": config.get_str("sm2_upscale_2d", "faithful"),
        "translucency": config.get_str("sm2_translucency", "stipple"),
        "extended_draw_distance": _ini_bool(config.get_bool("sm2_draw_distance", True)),
        "crt_enabled": _ini_bool(config.get_bool("sm2_crt_enabled", False)),
        "show_notifications": _ini_bool(config.get_bool("sm2_notifications", True)),
        # MangoHud draws the FPS counter (hud) and the bezels (bezel) of Retrobox
        "show_fps": "false",
        "bezel": "false",
    }


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------


def _audio_settings(config: SystemConfig, rom: Path | None) -> dict[str, str]:
    """Return the volume of the game family, when the game sets an audio gain.

    sm2-emu has no master volume, only a volume per game family (100 % by
    default, 150 % at most) used when ``game_volume`` is on. Without a gain
    set for the game, or for an archive whose game is not identified, the
    volumes chosen in the overlay are left as they are.
    """
    gain = config.get("sm2_audio_gain")
    if gain is config.MISSING or rom is None:
        return {}
    if (family := game_family(rom)) is None:
        return {}
    return {
        "game_volume": "true",
        f"volume_{family}": str(gain_to_percent(gain, _MAX_VOLUME)),
    }


# ---------------------------------------------------------------------------
# Controllers
# ---------------------------------------------------------------------------


def _event_node(device_path: str) -> str:
    """Return the /dev/input/eventN node of a pad, the path SDL reports with HIDAPI off."""
    if device_path.startswith("/dev/input/event"):
        return device_path
    if device_path.startswith("/dev/hidraw"):
        events = sorted(ev for ev, hid in evdev_to_hidraw().items() if hid == device_path)
        if events:
            return events[0]
    return ""


def _pad_devices(controllers: Controllers, wheels: DeviceInfoMapping) -> list[str]:
    """Return the event node of the pad of each player, in EmulationStation's order.

    Without them sm2-emu numbers the pads in the order SDL finds them. An empty
    node leaves the slot to the first free pad.
    """
    pads = sorted(
        (pad for pad in controllers if pad.device_path not in wheels),
        key=lambda pad: pad.player_number,
    )
    nodes = [_event_node(pad.device_path) for pad in pads[:_PLAYERS]]
    return nodes + [""] * (_PLAYERS - len(nodes))


def _button_id(pad: Controller, names: tuple[str, ...]) -> str:
    """Return the joystick button bound to the first of ``names`` the wheel has."""
    for name in names:
        if (bound := pad.inputs.get(name)) is not None and bound.type == "button":
            return str(bound.id)
    return _UNSET


def _axis(pad: Controller, names: tuple[str, ...]) -> tuple[str, str] | None:
    """Return the ES name and the joystick axis of the first of ``names`` the wheel has."""
    for name in names:
        if (bound := pad.inputs.get(name)) is not None and bound.type == "axis":
            return name, str(bound.id)
    return None


def _wheel_axes(wheel: Controller) -> dict[str, str]:
    """Return the steering and pedal axes of a wheel, as EmulationStation calibrated them."""
    steer = _axis(wheel, _STEER_INPUTS)
    accel = _axis(wheel, _ACCEL_INPUTS)
    brake = _axis(wheel, _BRAKE_INPUTS)
    if steer is None and accel is None and brake is None:
        return {}  # nothing mapped: keep sm2-emu's own detection and calibration

    # pedals sharing one axis use half of it each
    shared = accel is not None and brake is not None and accel[1] == brake[1]
    try:
        relaxed = wheel.get_mapping_axis_relaxed_values()
    except (OSError, ValueError, IndexError) as error:
        _logger.debug("no axis rest values for %s: %s", wheel.real_name, error)
        relaxed = {}

    def inverted(found: tuple[str, str] | None) -> str:
        # sm2-emu inverts a pedal that rests at the positive end of its axis
        if found is None:
            return "false"
        if shared:
            return _ini_bool(int(wheel.inputs[found[0]].value) < 0)
        return _ini_bool(bool(relaxed.get(found[0], {}).get("reversed", False)))

    return {
        "wheel_steer_axis": steer[1] if steer else _UNSET,
        "wheel_accel_axis": accel[1] if accel else _UNSET,
        "wheel_brake_axis": brake[1] if brake else _UNSET,
        "wheel_accel_invert": inverted(accel),
        "wheel_brake_invert": inverted(brake),
        "wheel_accel_half": _ini_bool(shared),
        "wheel_brake_half": _ini_bool(shared),
    }


def _wheel_settings(
    config: SystemConfig, controllers: Controllers, wheels: DeviceInfoMapping
) -> dict[str, str]:
    """Return the [wheel] keys: buttons and axes of the wheel, rotation and force feedback."""
    settings = {
        "wheel_ffb": _ini_bool(config.get_bool("sm2_wheel_ffb", True)),
        "wheel_ffb_strength": config.get_str("sm2_wheel_ffb_strength", "50"),
    }
    if (rotation := config.get_str("wheel_rotation", "")) != "":
        settings["wheel_steer_degrees"] = rotation
        settings["wheel_lock_degrees"] = rotation

    wheel = next((pad for pad in controllers if pad.device_path in wheels), None)
    if wheel is None:
        return settings

    settings.update({key: _button_id(wheel, names) for key, names in _WHEEL_BUTTONS.items()})
    settings["wheel_button_menu"] = _UNSET  # the overlay is opened with the hotkeys
    settings.update(_wheel_axes(wheel))
    return settings


def _input_settings(
    config: SystemConfig, rom: Path | None, controllers: Controllers, wheels: DeviceInfoMapping
) -> dict[str, str]:
    """Return the [gamepad] keys: player order, button layout, rumble, sticks and shortcuts.

    The configuration GUI (no ``rom``) gets the default layout.
    """
    pad1, pad2 = _pad_devices(controllers, wheels)
    layout = layout_settings(
        config,
        game_set(rom) if rom is not None else None,
        game_family(rom) if rom is not None else None,
    )
    return {
        **layout,
        "pad1_device": pad1,
        "pad2_device": pad2,
        # the Guide chords would fire twice: gamepadly maps the hotkeys to the keys
        "pad_shortcuts": "false",
        "pad_rumble": _ini_bool(config.get_bool("sm2_pad_rumble", True)),
        "pad_rumble_strength": config.get_str("sm2_pad_rumble_strength", "50"),
        "pad_stick_deadzone": config.get_str("sm2_pad_stick_deadzone", "5"),
        "lightgun_pad_centred": _ini_bool(config.get_bool("sm2_pad_centred_aim", False)),
        # Retrobox does not detect light guns: the mouse and the sticks aim
        "lightgun": "false",
        **_DEFAULT_KEYS,
    }


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


def _system_settings(config: SystemConfig) -> dict[str, str]:
    """Return the [system] and [paths] keys."""
    return {
        "rewind": _ini_bool(config.get_bool("rewind", False)),
        "rewind_buffer_mb": config.get_str("sm2_rewind_memory", "128"),
        "software_async": _ini_bool(config.get_bool("sm2_software_async", True)),
        "throttle": "true",
        "rom_dir": str(ROMS / "model2"),
        "nvram_dir": str(SM2EMU_NVRAM),
        "screenshot_dir": str(SM2EMU_SCREENSHOTS),
    }


# ---------------------------------------------------------------------------
# sm2-emu.ini
# ---------------------------------------------------------------------------


def _key_of(line: str) -> str | None:
    """Return the key of a ``key = value`` line, or None for a comment or a section."""
    stripped = line.strip()
    if not stripped or stripped[0] in "#;[" or "=" not in stripped:
        return None
    return stripped.split("=", 1)[0].strip().lower()


def _section_of(line: str) -> str | None:
    """Return the name of a ``[section]`` line, or None for any other line."""
    stripped = line.strip()
    if not stripped.startswith("["):
        return None
    return stripped[1:].split("]", 1)[0].strip().lower()


def _is_family_section(section: str) -> bool:
    """Tell whether a section is the layout of a game family rather than a tab."""
    return section != "" and section not in _TAB_SECTIONS


def family_sections(text: str) -> set[str]:
    """Return the game families that have their own pad layout in sm2-emu.ini."""
    sections = (_section_of(line) for line in text.splitlines())
    return {section for section in sections if section is not None and _is_family_section(section)}


def merge_ini(existing: str, managed: Mapping[str, str]) -> str:
    """Return ``existing`` with the ``managed`` keys set.

    A key already in the file is replaced where it is. The pad layout keys of
    a game family section are the user's layout of that game and are never
    touched. The keys not found are added before the first section, where
    every key applies to all the games.
    """
    remaining = dict(managed)
    lines: list[str] = []
    section = ""
    for line in existing.splitlines():
        if (name := _section_of(line)) is not None:
            section = name
        key = _key_of(line)
        owned_by_family = (
            key is not None and _is_family_section(section) and key.startswith(_PAD_KEY_PREFIXES)
        )
        if key is not None and key in remaining and not owned_by_family:
            lines.append(f"{key} = {remaining.pop(key)}")
        else:
            lines.append(line)

    first_section = next(
        (index for index, line in enumerate(lines) if line.strip().startswith("[")), len(lines)
    )
    lines[first_section:first_section] = [f"{key} = {value}" for key, value in remaining.items()]
    return "\n".join((*lines, ""))


# the arguments are the ones of Generator.generate this module needs
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def write_config(
    system: Emulator,
    rom: Path | None,
    controllers: Controllers,
    wheels: DeviceInfoMapping,
    resolution: Resolution,
) -> None:
    """Write sm2-emu.ini for the game (``rom`` is None for the configuration GUI)."""
    config = system.config
    managed = {
        **_video_settings(config, resolution),
        **_audio_settings(config, rom),
        **_input_settings(config, rom, controllers, wheels),
        **_wheel_settings(config, controllers, wheels),
        **_system_settings(config),
    }

    existing = SM2EMU_CFG.read_text(encoding="utf-8") if SM2EMU_CFG.exists() else ""
    if rom is not None and (family := game_family(rom)) in family_sections(existing):
        _logger.info(
            "sm2-emu.ini has its own [%s] pad layout (saved from the overlay): it is kept", family
        )
    with ensure_parents_and_open(SM2EMU_CFG, "w") as ini:
        ini.write(merge_ini(existing, managed))
