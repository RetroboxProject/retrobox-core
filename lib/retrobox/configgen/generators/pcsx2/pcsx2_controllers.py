import logging
from typing import Mapping

from retrobox.configgen.config import SystemConfig
from retrobox.configgen.input import Input
from retrobox.configgen.utils.configparser import CaseSensitiveConfigParser

from ...Emulator import Emulator
from ...typedefs import DeviceInfoMapping
from ...controller import Controllers
from ...gun import Guns


_logger = logging.getLogger(__name__)

VALID_SONY_GUIDS = [
    # ds3
    "030000004c0500006802000011010000",
    "030000004c0500006802000011810000",
    "050000004c0500006802000000800000",
    "050000004c0500006802000000000000",
    # ds4
    "030000004c050000c405000011810000",
    "050000004c050000c405000000810000",
    "030000004c050000cc09000011010000",
    "050000004c050000cc09000000010000",
    "030000004c050000cc09000011810000",
    "050000004c050000cc09000000810000",
    "030000004c050000a00b000011010000",
    "030000004c050000a00b000011810000",
    # ds5
    "030000004c050000e60c000011810000",
    "050000004c050000e60c000000810000",
]

wheelTypeMapping = {
    "DrivingForce": "0",
    "DrivingForcePro": "1",
    "GTForce": "3",
}

WHEEL_INPUT_MAPPING = {
    "DrivingForcePro": {
        "up": "Pad_DPadUp",
        "down": "Pad_DPadDown",
        "left": "Pad_DPadLeft",
        "right": "Pad_DPadRight",
        "start": "Pad_Start",
        "select": "Pad_Select",
        "a": "Pad_Circle",
        "b": "Pad_Cross",
        "x": "Pad_Triangle",
        "y": "Pad_Square",
        "pageup": "Pad_L1",
        "pagedown": "Pad_R1",
    },
    "DrivingForce": {
        "up": "Pad_DPadUp",
        "down": "Pad_DPadDown",
        "left": "Pad_DPadLeft",
        "right": "Pad_DPadRight",
        "start": "Pad_Start",
        "select": "Pad_Select",
        "a": "Pad_Circle",
        "b": "Pad_Cross",
        "x": "Pad_Triangle",
        "y": "Pad_Square",
        "pageup": "Pad_L1",
        "pagedown": "Pad_R1",
    },
    "GTForce": {
        "a": "Pad_Y",
        "b": "Pad_B",
        "x": "Pad_X",
        "y": "Pad_A",
        "pageup": "Pad_MenuDown",
        "pagedown": "Pad_MenuUp",
    },
}

# fixed DualShock2 tuning values, identical for every pad regardless of the input source
PAD_FIXED_SETTINGS = {
    "Type": "DualShock2",
    "InvertL": "0",
    "InvertR": "0",
    "Deadzone": "0",
    "AxisScale": "1.33",
    "TriggerDeadzone": "0",
    "TriggerScale": "1",
    "LargeMotorScale": "1",
    "SmallMotorScale": "1",
    "ButtonDeadzone": "0",
    "PressureModifier": "0.5",
}

# digital buttons: pcsx2 option -> SDL button name
PAD_SDL_BUTTON_MAPPING = {
    "Up": "DPadUp",
    "Right": "DPadRight",
    "Down": "DPadDown",
    "Left": "DPadLeft",
    "Triangle": "FaceNorth",
    "Circle": "FaceEast",
    "Cross": "FaceSouth",
    "Square": "FaceWest",
    "Select": "Back",
    "Start": "Start",
    "L1": "LeftShoulder",
    "R1": "RightShoulder",
    "L2": "+LeftTrigger",
    "R2": "+RightTrigger",
    "L3": "LeftStick",
    "R3": "RightStick",
    "LUp": "-LeftY",
    "LRight": "+LeftX",
    "LDown": "+LeftY",
    "LLeft": "-LeftX",
    "RUp": "-RightY",
    "RRight": "+RightX",
    "RDown": "+RightY",
    "RLeft": "-RightX",
    "Analog": "Guide",
    "LargeMotor": "LargeMotor",
    "SmallMotor": "SmallMotor",
}

# keyboard fallback for player 1 when no controller is connected:
# W/A/S/D face buttons, arrow keys for the d-pad, IJKL / TFGH inverted-T
# clusters for the sticks, Q/E for L1/R1 and Z/X/C/V for L2/L3/R3/R2
PAD1_KEYBOARD_MAPPING = {
    "Up": "Keyboard/Up",
    "Right": "Keyboard/Right",
    "Down": "Keyboard/Down",
    "Left": "Keyboard/Left",
    "Triangle": "Keyboard/W",
    "Circle": "Keyboard/D",
    "Cross": "Keyboard/S",
    "Square": "Keyboard/A",
    "Select": "Keyboard/Backspace",
    "Start": "Keyboard/Return",
    "L1": "Keyboard/Q",
    "R1": "Keyboard/E",
    "L2": "Keyboard/Z",
    "L3": "Keyboard/X",
    "R3": "Keyboard/C",
    "R2": "Keyboard/V",
    "LUp": "Keyboard/I",
    "LRight": "Keyboard/L",
    "LDown": "Keyboard/K",
    "LLeft": "Keyboard/J",
    "RUp": "Keyboard/T",
    "RRight": "Keyboard/H",
    "RDown": "Keyboard/G",
    "RLeft": "Keyboard/F",
}


def _pcsx2_gen_controllers_config(
        ini_config: CaseSensitiveConfigParser,
        system: Emulator,
        controllers: Controllers,
        metadata: Mapping[str, str],
        guns: Guns,
        wheels: DeviceInfoMapping,
        playingWithWheel: bool
    ) -> CaseSensitiveConfigParser:
    # wheels
    wtype = get_wheel_type(metadata, playingWithWheel, system.config, wheelTypeMapping)
    _logger.info("PS2 wheel type is %s", wtype)
    if use_emulator_wheels(playingWithWheel, wtype) and wheels:
        usbx = 1
        for pad in controllers:
            if pad.device_path in wheels:
                if not ini_config.has_section(f"USB{usbx}"):
                    ini_config.add_section(f"USB{usbx}")
                ini_config.set(f"USB{usbx}", "Type", "Pad")

                wheel_type = get_wheel_type(metadata, playingWithWheel, system.config, wheelTypeMapping)
                ini_config.set(f"USB{usbx}", "Pad_subtype", wheelTypeMapping[wheel_type])

                if pad.physical_device_path is not None:  # ffb on the real wheel
                    ini_config.set(f"USB{usbx}", "Pad_FFDevice", f"SDL-{pad.physical_index}")
                else:
                    ini_config.set(f"USB{usbx}", "Pad_FFDevice", f"SDL-{pad.index}")

                for i in pad.inputs:
                    if i in WHEEL_INPUT_MAPPING[wheel_type]:
                        ini_config.set(f"USB{usbx}", WHEEL_INPUT_MAPPING[wheel_type][i], f"SDL-{pad.index}/{input2wheel(pad.inputs[i])}")
                # wheel
                if "joystick1left" in pad.inputs:
                    ini_config.set(f"USB{usbx}", "Pad_SteeringLeft", f"SDL-{pad.index}/{input2wheel(pad.inputs['joystick1left'])}")
                    ini_config.set(f"USB{usbx}", "Pad_SteeringRight", f"SDL-{pad.index}/{input2wheel(pad.inputs['joystick1left'], True)}")
                # pedals
                if "l2" in pad.inputs:
                    ini_config.set(f"USB{usbx}", "Pad_Brake", f"SDL-{pad.index}/{input2wheel(pad.inputs['l2'], None)}")
                if "r2" in pad.inputs:
                    ini_config.set(f"USB{usbx}", "Pad_Throttle", f"SDL-{pad.index}/{input2wheel(pad.inputs['r2'], None)}")
                usbx = usbx + 1

    ## [Pad]
    if not ini_config.has_section("Pad"):
        ini_config.add_section("Pad")

    ini_config.set("Pad", "MultitapPort1", "false")
    ini_config.set("Pad", "MultitapPort2", "false")

    # add multitap as needed
    multiTap = 2
    joystick_count = len(controllers)
    _logger.debug("Number of Controllers = %s", joystick_count)
    multitap_config = system.config.get("pcsx2_multitap")
    if multitap_config == "4":
        if joystick_count > 2 and joystick_count < 5:
            ini_config.set("Pad", "MultitapPort1", "true")
            multiTap = 4
        elif joystick_count > 4:
            ini_config.set("Pad", "MultitapPort1", "true")
            multiTap = 4
            _logger.debug("*** You have too many connected controllers for this option, restricting to 4 ***")
        else:
            multiTap = 2
            _logger.debug("*** You have the wrong number of connected controllers for this option ***")
    elif multitap_config == "8":
        if joystick_count > 4:
            ini_config.set("Pad", "MultitapPort1", "true")
            ini_config.set("Pad", "MultitapPort2", "true")
            multiTap = 8
        elif joystick_count > 2 and joystick_count < 5:
            ini_config.set("Pad", "MultitapPort1", "true")
            multiTap = 4
            _logger.debug("*** You don't have enough connected controllers for this option, restricting to 4 ***")
        else:
            multiTap = 2
            _logger.debug("*** You don't have enough connected controllers for this option ***")
    else:
        multiTap = 2

    # remove the previous [Padx] sections to avoid phantom controllers
    for section_name in ["Pad1", "Pad2", "Pad3", "Pad4", "Pad5", "Pad6", "Pad7", "Pad8"]:
        if ini_config.has_section(section_name):
            ini_config.remove_section(section_name)

    if controllers:
        # Now add Controllers
        for nplayer, pad in enumerate(controllers, start=1):
            ini_config.set("InputSources", "SDLControllerEnhancedMode", "true" if pad.guid in VALID_SONY_GUIDS else "false")

            # only configure the number of controllers set
            if nplayer > multiTap:
                continue

            pad_index = nplayer
            if multiTap == 4 and pad.index != 0:
                # Skip Pad2 in the ini file when MultitapPort1 only
                pad_index = nplayer + 1
            pad_num = f"Pad{pad_index}"
            sdl_num = f"SDL-{pad.index}"

            if not ini_config.has_section(pad_num):
                ini_config.add_section(pad_num)

            for key, value in PAD_FIXED_SETTINGS.items():
                ini_config.set(pad_num, key, value)

            for key, sdl_button in PAD_SDL_BUTTON_MAPPING.items():
                ini_config.set(pad_num, key, f"{sdl_num}/{sdl_button}")
    else:
        # no controller connected: give player 1 a keyboard fallback
        if not ini_config.has_section("Pad1"):
            ini_config.add_section("Pad1")

        for key, value in PAD_FIXED_SETTINGS.items():
            ini_config.set("Pad1", key, value)

        for key, keyboard_key in PAD1_KEYBOARD_MAPPING.items():
            ini_config.set("Pad1", key, keyboard_key)

    return ini_config


def input2wheel(input: Input, reversedAxis: bool | None = False) -> str | None:
    if input.type == "button":
        pcsx2_magic_button_offset = 21  # PCSX2/SDLInputSource.cpp : const u32 button = ev->button + std::size(s_sdl_button_names)
        return f"Button{int(input.id) + pcsx2_magic_button_offset}"
    if input.type == "hat":
        dir = "unknown"
        if input.value == '1':
            dir = "North"
        elif input.value == '2':
            dir = "East"
        elif input.value == '4':
            dir = "South"
        elif input.value == '8':
            dir = "West"
        return f"Hat{input.id}{dir}"
    if input.type == "axis":
        pcsx2_magic_axis_offset = 6  # PCSX2/SDLInputSource.cpp : const u32 axis = ev->axis + std::size(s_sdl_axis_names);
        if reversedAxis is None:
            return f"FullAxis{int(input.id) + pcsx2_magic_axis_offset}~"
        dir = "+" if reversedAxis else "-"
        return f"{dir}Axis{int(input.id) + pcsx2_magic_axis_offset}"
    return None


def is_playing_with_wheel(system: Emulator, wheels: DeviceInfoMapping):
    return bool(system.config.use_wheels and wheels)


def use_emulator_wheels(playingWithWheel: bool, wheel_type: str):
    if playingWithWheel is False:
        return False
    # the virtual type is the virtual wheel that use a physical wheel to manipulate the pad
    return wheel_type != "Virtual"


def get_wheel_type(metadata: Mapping[str, str], playingWithWheel: bool, config: SystemConfig, wheelTypeMapping):
    wheel_type = "Virtual"
    if playingWithWheel is False:
        return wheel_type
    if "wheel_type" in metadata:
        wheel_type = metadata["wheel_type"]
    if config_wheel_type := config.get("pcsx2_wheel_type"):
        wheel_type = config_wheel_type
    if wheel_type not in wheelTypeMapping:
        wheel_type = "Virtual"
    return wheel_type