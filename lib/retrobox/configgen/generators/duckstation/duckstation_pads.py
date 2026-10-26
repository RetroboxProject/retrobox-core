"""Controllers and lightguns of DuckStation (``[Pad1]``..``[Pad8]``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ...config import SystemConfig
    from ...controller import Controller
    from ...gun import Guns
    from ...utils.configparser import CaseSensitiveConfigParser

MAX_PADS = 8
_MULTITAP_PORT1_FROM = 3
_MULTITAP_BOTH_FROM = 5

# (DuckStation button, SDL input): the same for every controller
_PAD_BUTTONS = (
    ("Up", "DPadUp"),
    ("Right", "DPadRight"),
    ("Down", "DPadDown"),
    ("Left", "DPadLeft"),
    ("Triangle", "Y"),
    ("Circle", "B"),
    ("Cross", "A"),
    ("Square", "X"),
    ("Select", "Back"),
    ("Start", "Start"),
    ("L1", "LeftShoulder"),
    ("R1", "RightShoulder"),
    ("L2", "+LeftTrigger"),
    ("R2", "+RightTrigger"),
    ("L3", "LeftStick"),
    ("R3", "RightStick"),
    ("LLeft", "-LeftX"),
    ("LRight", "+LeftX"),
    ("LDown", "+LeftY"),
    ("LUp", "-LeftY"),
    ("RLeft", "-RightX"),
    ("RRight", "+RightX"),
    ("RDown", "+RightY"),
    ("RUp", "-RightY"),
    ("SmallMotor", "SmallMotor"),
    ("LargeMotor", "LargeMotor"),
)
_NEGCON_BUTTONS = (
    ("A", "B"),
    ("B", "Y"),
    ("I", "+RightTrigger"),
    ("II", "+LeftTrigger"),
    ("L", "LeftShoulder"),
    ("R", "RightShoulder"),
    ("SteeringLeft", "-LeftX"),
    ("SteeringRight", "+LeftX"),
)
# the pedal keys of each lightgun player, used as button A
_PEDAL_KEYS = {1: "c", 2: "v", 3: "b", 4: "n"}
# BGR color code of the crosshair: player 1 red, the others blue
_CROSSHAIR_PLAYER1 = "0000FF"
_CROSSHAIR_OTHERS = "FF0000"


def _set_buttons(
    settings: CaseSensitiveConfigParser,
    pad_section: str,
    sdl_input: str,
    buttons: Sequence[tuple[str, str]],
) -> None:
    """Map DuckStation buttons to the SDL inputs of a controller."""
    for button, sdl_button in buttons:
        settings.set(pad_section, button, f"{sdl_input}/{sdl_button}")


def _configure_pad(
    settings: CaseSensitiveConfigParser, config: SystemConfig, nplayer: int, pad: Controller
) -> None:
    """Configure the pad of one player from its SDL controller."""
    pad_section = f"Pad{nplayer}"
    sdl_input = f"SDL-{pad.index}"
    pad_type_key = f"duckstation_Controller{nplayer}"
    pad_type = config.get(pad_type_key)

    # SDL2 configs are always the same for controllers
    settings.set(pad_section, "Type", config.get(pad_type_key, "DigitalController"))
    _set_buttons(settings, pad_section, sdl_input, _PAD_BUTTONS)
    settings.set(pad_section, "VibrationBias", "8")

    # D-Pad to Joystick
    digital_mode = config.get("duckstation_digitalmode")
    settings.set(pad_section, "AnalogDPadInDigitalMode", digital_mode or "false")
    if digital_mode and pad_type == "AnalogController":
        settings.set(pad_section, "Analog", f"{sdl_input}/Guide")

    if pad_type == "NeGcon":
        _set_buttons(settings, pad_section, sdl_input, _NEGCON_BUTTONS)

    if pad_type == "PlayStationMouse":
        settings.set(pad_section, "Right", f"{sdl_input}/B")
        settings.set(pad_section, "Left", f"{sdl_input}/A")
        settings.set(pad_section, "RelativeMouseMode", "true")


def _configure_guns(
    settings: CaseSensitiveConfigParser,
    config: SystemConfig,
    guns: Guns,
    metadata: Mapping[str, str],
) -> None:
    """Configure the lightguns, based on the detected guns and not on the controllers."""
    if not (config.use_guns and guns):
        return

    for nplayer in range(1, len(guns[:MAX_PADS]) + 1):
        pad_section = f"Pad{nplayer}"
        gun_input = f"Pointer-{nplayer - 1}"
        # Gun mapping is hardcoded into patch.
        # Justifier ROM mapping: BTN_LEFT = Trigger | BTN_RIGHT = Back | BTN_MIDDLE = Start
        if metadata.get("gun_type") == "justifier":
            settings.set(pad_section, "Type", "Justifier")
        else:
            # GunCon ROM mapping: BTN_LEFT = Trigger | BTN_RIGHT = A | BTN_MIDDLE = B
            settings.set(pad_section, "Type", "GunCon")
            # Pedal key for button A
            pedal_key = config.get(f"controllers.pedals{nplayer}", _PEDAL_KEYS.get(nplayer))
            if pedal_key:
                settings.set(
                    pad_section, "A", f"{gun_input}/RightButton & Keyboard/{pedal_key.upper()}"
                )
            else:
                settings.set(pad_section, "A", f"{gun_input}/RightButton")
        settings.set(pad_section, "CrosshairScale", config.get("duckstation_crosshair", "0"))
        settings.set(
            pad_section,
            "CrosshairColor",
            _CROSSHAIR_PLAYER1 if nplayer == 1 else _CROSSHAIR_OTHERS,
        )


def configure_pads(
    settings: CaseSensitiveConfigParser,
    config: SystemConfig,
    controllers: Sequence[Controller],
    guns: Guns,
    metadata: Mapping[str, str],
) -> None:
    """Write the ``[Pad1]``..``[Pad8]`` sections and the multitap mode.

    Args:
        settings: The DuckStation settings, updated in place.
        config: The configuration of the running game.
        controllers: The player controllers.
        guns: The detected lightguns.
        metadata: The game metadata.
    """
    # clear existing Pad(x) configs, then create Pad1 - 8 as None to start
    for index in range(1, MAX_PADS + 1):
        if settings.has_section(f"Pad{index}"):
            settings.remove_section(f"Pad{index}")
    for index in range(1, MAX_PADS + 1):
        settings.add_section(f"Pad{index}")
        settings.set(f"Pad{index}", "Type", "None")

    # start with multitap disabled
    settings.set("ControllerPorts", "MultitapMode", "Disabled")

    # now add the controller config based on the ES type & number connected
    for nplayer, pad in enumerate(controllers[:MAX_PADS], start=1):
        # automatically add the multi-tap
        if nplayer >= _MULTITAP_PORT1_FROM:
            settings.set("ControllerPorts", "MultitapMode", "Port1Only")
            if nplayer >= _MULTITAP_BOTH_FROM:
                settings.set("ControllerPorts", "MultitapMode", "BothPorts")
        _configure_pad(settings, config, nplayer, pad)

    _configure_guns(settings, config, guns, metadata)
