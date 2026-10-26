from __future__ import annotations

import codecs
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypedDict

from retrobox.paths import mkdir_if_not_exists
from .rpcs3Paths import _RPCS3_CFGDIR

if TYPE_CHECKING:
    from ...controller import Controllers
    from ...Emulator import Emulator

_logger = logging.getLogger(__name__)

_RPCS3_INPUT_DIR: Final = _RPCS3_CFGDIR / "input_configs" / "global"

class _InputMapping(TypedDict):
    config_name: str
    event_variations: list[tuple[str, str]]

def _get_kernel_evdev_name(device_path: str) -> str | None:
    """Read the raw device name as reported by the kernel (EVIOCGNAME) for
    a given /dev/input/eventN node, via sysfs.

    This is the exact string RPCS3's Evdev handler matches against the
    "Device" field in Default.yml. It is NOT the same thing as a
    "friendly"/marketing product name (e.g. one looked up from a
    gamecontrollerdb-style GUID table) - those can differ from what the
    kernel driver itself reports, which is why using such a friendly name
    for Device silently produces a pad that RPCS3 never recognizes.
    """
    try:
        event_node = Path(device_path).name  # e.g. "event13"
        name_file = Path("/sys/class/input") / event_node / "device" / "name"
        return name_file.read_text(encoding="utf-8").strip()
    except OSError:
        _logger.warning("Could not read evdev device name from sysfs for %s", device_path)
        return None

def generateControllerConfig(system: Emulator, controllers: Controllers, rom: Path):

    mkdir_if_not_exists(_RPCS3_INPUT_DIR)

    valid_sony_guids = [
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
        "050000004c050000e60c000000810000"
    ]

    # may need to expand this to support more controllers
    # from evdev_joystick_handler.h
    input_mapping = [
        ("up", "Up", [("BTN_DPAD_UP", "D-Pad Up"), ("ABS_HAT0Y", "Hat0 Y-")]),
        ("down", "Down", [("BTN_DPAD_DOWN", "D-Pad Down"), ("ABS_HAT0Y", "Hat0 Y+")]),
        ("left", "Left", [("BTN_DPAD_LEFT", "D-Pad Left"), ("ABS_HAT0X", "Hat0 X-")]),
        ("right", "Right", [("BTN_DPAD_RIGHT", "D-Pad Right"), ("ABS_HAT0X", "Hat0 X+")]),
        ("l2", "L2", [("BTN_TL2", "TL 2"), ("ABS_Z", "LZ+")]),
        ("r2", "R2", [("BTN_TR2", "TR 2"), ("ABS_RZ", "RZ+")]),
        ("a", "Cross", [("BTN_A", "A")]),
        ("b", "Circle", [("BTN_B", "B")]),
        ("x", "Square", [("BTN_X", "X")]),
        ("y", "Triangle", [("BTN_Y", "Y")]),
        ("joystick1up", "Left Stick Up", [("ABS_Y", "LY-")]),
        ("joystick1left", "Left Stick Left", [("ABS_X", "LX-")]),
        ("joystick2up", "Right Stick Up", [("ABS_RY", "RY-")]),
        ("joystick2left", "Right Stick Left", [("ABS_RX", "RX-")])
    ]

    mapping_dict: dict[str, _InputMapping] = {}
    for input_name, config_name, event_variations in input_mapping:
        mapping_dict[input_name] = {
            "config_name": config_name,
            "event_variations": event_variations,
        }

    nplayer, ds3player, ds4player, dsplayer = 1, 1, 1, 1
    controller_counts = {}
    evdev_device_counts: dict[str, int] = {}

    configFileName = _RPCS3_INPUT_DIR / "Default.yml"
    with codecs.open(str(configFileName), "w", encoding="utf_8_sig") as f:
        for nplayer, pad in enumerate(controllers[:7], start=1):
            _logger.debug("Controller #%s - %s", nplayer, pad.guid)
            # check for DualShock / DualSense
            controller_type = system.config.get(f"rpcs3_controller{nplayer}")
            rumble = system.config.get_bool(f"rpcs3_rumble{nplayer}", True, return_values=("true", "false"))
            if pad.guid in valid_sony_guids and controller_type == "Sony":
                _logger.debug("*** Using DualShock / DualSense configuration ***")
                # dualshock 3
                if pad.guid in valid_sony_guids[:4]:
                    f.write(f'Player {nplayer} Input:\n')
                    f.write('  Handler: DualShock 3\n')
                    f.write(f'  Device: "DS3 Pad #{ds3player}"\n')
                    ds3player += 1
                # dualshock 4
                elif pad.guid in valid_sony_guids[4:12]:
                    f.write(f'Player {nplayer} Input:\n')
                    f.write('  Handler: DualShock 4\n')
                    f.write(f'  Device: "DS4 Pad #{ds4player}"\n')
                    ds4player += 1
                # dualsense
                else:
                    f.write(f'Player {nplayer} Input:\n')
                    f.write('  Handler: DualSense\n')
                    f.write(f'  Device: "DualSense Pad #{dsplayer}"\n')
                    dsplayer += 1
                f.write('  Config:\n')
                f.write('    Left Stick Left: LS X-\n')
                f.write('    Left Stick Down: LS Y-\n')
                f.write('    Left Stick Right: LS X+\n')
                f.write('    Left Stick Up: LS Y+\n')
                f.write('    Right Stick Left: RS X-\n')
                f.write('    Right Stick Down: RS Y-\n')
                f.write('    Right Stick Right: RS X+\n')
                f.write('    Right Stick Up: RS Y+\n')
                f.write('    Start: Options\n')
                f.write('    Select: Share\n')
                f.write('    PS Button: PS Button\n')
                f.write('    Square: Square\n')
                f.write('    Cross: Cross\n')
                f.write('    Circle: Circle\n')
                f.write('    Triangle: Triangle\n')
                f.write('    Left: Left\n')
                f.write('    Down: Down\n')
                f.write('    Right: Right\n')
                f.write('    Up: Up\n')
                f.write('    R1: R1\n')
                f.write('    R2: R2\n')
                f.write('    R3: R3\n')
                f.write('    L1: L1\n')
                f.write('    L2: L2\n')
                f.write('    L3: L3\n')
                f.write('    Motion Sensor X:\n')
                f.write('      Axis: ""\n')
                f.write('      Mirrored: false\n')
                f.write('      Shift: 0\n')
                f.write('    Motion Sensor Y:\n')
                f.write('      Axis: ""\n')
                f.write('      Mirrored: false\n')
                f.write('      Shift: 0\n')
                f.write('    Motion Sensor Z:\n')
                f.write('      Axis: ""\n')
                f.write('      Mirrored: false\n')
                f.write('      Shift: 0\n')
                f.write('    Motion Sensor G:\n')
                f.write('      Axis: ""\n')
                f.write('      Mirrored: false\n')
                f.write('      Shift: 0\n')
                f.write('    Pressure Intensity Button: ""\n')
                f.write('    Pressure Intensity Percent: 50\n')
                f.write('    Pressure Intensity Toggle Mode: false\n')
                f.write('    Left Stick Multiplier: 100\n')
                f.write('    Right Stick Multiplier: 100\n')
                f.write('    Left Stick Deadzone: 40\n')
                f.write('    Right Stick Deadzone: 40\n')
                f.write('    Left Trigger Threshold: 0\n')
                f.write('    Right Trigger Threshold: 0\n')
                f.write('    Left Pad Squircling Factor: 8000\n')
                f.write('    Right Pad Squircling Factor: 8000\n')
                f.write('    Color Value R: 0\n')
                f.write('    Color Value G: 0\n')
                f.write('    Color Value B: 20\n')
                f.write('    Blink LED when battery is below 20%: true\n')
                f.write('    Use LED as a battery indicator: false\n')
                f.write('    LED battery indicator brightness: 10\n')
                f.write('    Player LED enabled: true\n')
                f.write(f'    Enable Large Vibration Motor: {rumble}\n')
                f.write(f'    Enable Small Vibration Motor: {rumble}\n')
                f.write('    Switch Vibration Motors: false\n')
                f.write('    Mouse Movement Mode: Relative\n')
                f.write('    Mouse Deadzone X Axis: 60\n')
                f.write('    Mouse Deadzone Y Axis: 60\n')
                f.write('    Mouse Acceleration X Axis: 200\n')
                f.write('    Mouse Acceleration Y Axis: 250\n')
                f.write('    Left Stick Lerp Factor: 100\n')
                f.write('    Right Stick Lerp Factor: 100\n')
                f.write('    Analog Button Lerp Factor: 100\n')
                f.write('    Trigger Lerp Factor: 100\n')
                f.write('    Device Class Type: 0\n')
                f.write('    Vendor ID: 1356\n')
                f.write('    Product ID: 616\n')
                f.write('  Buddy Device: ""\n')
            elif controller_type == "SDL":
                # Explicit opt-in only. Not used by default anymore: the RPCS3
                # AppImage build shipped on Retrobox reads pads through evdev
                # device nodes, not through SDL's game-controller layer, so SDL
                # is kept only for setups that explicitly request it (e.g. a
                # non-AppImage / Windows build of RPCS3).
                _logger.debug("*** Using SDL3 configuration (explicitly requested) ***")
                f.write(f'Player {nplayer} Input:\n')
                f.write('  Handler: SDL\n')
                ctrlname = pad.real_name
                # workaround controllers with commas in their name - like Nintendo
                ctrlname = ctrlname.replace(",", ".")
                # rpcs3 appends a unique number per controller name
                if ctrlname in controller_counts:
                    controller_counts[ctrlname] += 1
                else:
                    controller_counts[ctrlname] = 1
                f.write(f'  Device: {ctrlname} {controller_counts[ctrlname]}\n')
                f.write('  Config:\n')
                f.write('    Left Stick Left: LS X-\n')
                f.write('    Left Stick Down: LS Y-\n')
                f.write('    Left Stick Right: LS X+\n')
                f.write('    Left Stick Up: LS Y+\n')
                f.write('    Right Stick Left: RS X-\n')
                f.write('    Right Stick Down: RS Y-\n')
                f.write('    Right Stick Right: RS X+\n')
                f.write('    Right Stick Up: RS Y+\n')
                f.write('    Start: Start\n')
                f.write('    Select: Back\n')
                f.write('    PS Button: Guide\n')
                f.write('    Square: West\n')
                f.write('    Cross: South\n')
                f.write('    Circle: East\n')
                f.write('    Triangle: North\n')
                f.write('    Left: Left\n')
                f.write('    Down: Down\n')
                f.write('    Right: Right\n')
                f.write('    Up: Up\n')
                f.write('    R1: RB\n')
                f.write('    R2: RT\n')
                f.write('    R3: RS\n')
                f.write('    L1: LB\n')
                f.write('    L2: LT\n')
                f.write('    L3: LS\n')
                f.write('    IR Nose: ""\n')
                f.write('    IR Tail: ""\n')
                f.write('    IR Left: ""\n')
                f.write('    IR Right: ""\n')
                f.write('    Tilt Left: ""\n')
                f.write('    Tilt Right: ""\n')
                f.write('    Motion Sensor X:\n')
                f.write('      Axis: X\n')
                f.write('      Mirrored: false\n')
                f.write('      Shift: 0\n')
                f.write('    Motion Sensor Y:\n')
                f.write('      Axis: Y\n')
                f.write('      Mirrored: false\n')
                f.write('      Shift: 0\n')
                f.write('    Motion Sensor Z:\n')
                f.write('      Axis: Z\n')
                f.write('      Mirrored: false\n')
                f.write('      Shift: 0\n')
                f.write('    Motion Sensor G:\n')
                f.write('      Axis: RY\n')
                f.write('      Mirrored: false\n')
                f.write('      Shift: 0\n')
                f.write('    Orientation Reset Button: ""\n')
                f.write('    Orientation Enabled: false\n')
                f.write('    Pressure Intensity Button: ""\n')
                f.write('    Pressure Intensity Percent: 50\n')
                f.write('    Pressure Intensity Toggle Mode: false\n')
                f.write('    Pressure Intensity Deadzone: 0\n')
                f.write('    Analog Limiter Button: ""\n')
                f.write('    Analog Limiter Toggle Mode: false\n')
                f.write('    Left Stick Multiplier: 100\n')
                f.write('    Right Stick Multiplier: 100\n')
                f.write('    Left Stick Deadzone: 8000\n')
                f.write('    Right Stick Deadzone: 8000\n')
                f.write('    Left Stick Anti-Deadzone: 4259\n')
                f.write('    Right Stick Anti-Deadzone: 4259\n')
                f.write('    Left Trigger Threshold: 0\n')
                f.write('    Right Trigger Threshold: 0\n')
                f.write('    Left Pad Squircling Factor: 8000\n')
                f.write('    Right Pad Squircling Factor: 8000\n')
                f.write('    Color Value R: 0\n')
                f.write('    Color Value G: 0\n')
                f.write('    Color Value B: 20\n')
                f.write('    Blink LED when battery is below 20%: true\n')
                f.write('    Use LED as a battery indicator: false\n')
                f.write('    LED battery indicator brightness: 10\n')
                f.write('    Player LED enabled: true\n')
                if rumble == "true":
                    f.write('    Enable Large Vibration Motor: 100\n')
                    f.write('    Enable Small Vibration Motor: 100\n')
                else:
                    f.write('    Enable Large Vibration Motor: 0\n')
                    f.write('    Enable Small Vibration Motor: 0\n')
                f.write('    Switch Vibration Motors: false\n')
                f.write('    Mouse Movement Mode: Relative\n')
                f.write('    Mouse Deadzone X Axis: 60\n')
                f.write('    Mouse Deadzone Y Axis: 60\n')
                f.write('    Mouse Acceleration X Axis: 200\n')
                f.write('    Mouse Acceleration Y Axis: 250\n')
                f.write('    Left Stick Lerp Factor: 100\n')
                f.write('    Right Stick Lerp Factor: 100\n')
                f.write('    Analog Button Lerp Factor: 100\n')
                f.write('    Trigger Lerp Factor: 100\n')
                f.write('    Device Class Type: 0\n')
                f.write('    Vendor ID: 1356\n')
                f.write('    Product ID: 616\n')
                f.write('  Buddy Device: ""\n')
            # Default handler: Evdev.
            # This now covers both an explicit "Evdev" setting and the
            # unconfigured case, since the RPCS3 AppImage build prioritizes
            # raw evdev device nodes over SDL. Using pad.device_path (e.g.
            # "/dev/input/event7") as the Device value also means two or more
            # controllers of the exact same model never collide: each one has
            # its own unique event node, so no name-counter workaround is
            # needed here (unlike the SDL branch above). Mixed setups (e.g.
            # one generic pad + one Sony pad on "Sony" mode) are handled fine
            # too, since each player slot is resolved independently from its
            # own controller_type / guid.
            else:
                _logger.debug("*** Using default Evdev configuration ***")
                f.write(f'Player {nplayer} Input:\n')
                f.write('  Handler: Evdev\n')
                # RPCS3 matches evdev pads by the device NAME reported by the
                # kernel driver itself (EVIOCGNAME, e.g. "PDP Xbox One
                # Controller"). This is NOT pad.real_name: that's a
                # friendlier/marketing name (e.g. "PDP Xbox One Arctic
                # White") that can come from a GUID/gamecontrollerdb lookup
                # and simply doesn't match what RPCS3 looks for, which is
                # why the pad silently did nothing in-game. It's also not
                # the /dev/input/eventN path itself, which isn't stable
                # across reboots/reconnects and isn't what RPCS3 stores
                # either. We read the real kernel name from sysfs instead,
                # falling back to real_name only if that read fails for
                # some reason (e.g. sysfs unavailable in a container).
                evdev_device_name = _get_kernel_evdev_name(pad.device_path) or pad.real_name
                if evdev_device_name in evdev_device_counts:
                    evdev_device_counts[evdev_device_name] += 1
                    evdev_device_name = f"{evdev_device_name} #{evdev_device_counts[evdev_device_name]}"
                else:
                    evdev_device_counts[evdev_device_name] = 1
                f.write(f'  Device: {evdev_device_name}\n')
                f.write('  Config:\n')
                f.write('    Start: Start\n')
                f.write('    Select: Select\n')
                f.write('    PS Button: Mode\n')
                for input_idx in pad.inputs:
                    pad_input = pad.inputs[input_idx]
                    if pad_input.name in mapping_dict:
                        config_name = mapping_dict[pad_input.name]["config_name"]
                        event_variations = mapping_dict[pad_input.name]["event_variations"]
                        for event_type, value_name in event_variations:
                            if ("BTN" in event_type and pad_input.type == "button") or ("HAT" in event_type and pad_input.type == "hat"):
                                f.write(f"    {config_name}: {value_name}\n")
                            elif "ABS" in event_type and pad_input.type == "axis":
                                # handle axis for sticks
                                if config_name == "Left Stick Up":
                                    f.write(f"    {config_name}: {value_name}\n")
                                    # write the down values also
                                    f.write("    Left Stick Down: LY+\n")
                                elif config_name == "Left Stick Left":
                                    f.write(f"    {config_name}: {value_name}\n")
                                    # write the right values also
                                    f.write("    Left Stick Right: LX+\n")
                                # here's the complicated bit, DirectInput uses z axis
                                elif config_name == "Right Stick Up":
                                    f.write(f"    {config_name}: {value_name}\n")
                                    # write the down values
                                    f.write("    Right Stick Down: RY+\n")
                                elif config_name == "Right Stick Left":
                                    f.write(f"    {config_name}: {value_name}\n")
                                    # write the right values
                                    f.write("    Right Stick Right: RX+\n")
                                else:
                                    f.write(f"    {config_name}: {value_name}\n")
                # continue with default settings
                f.write('    R1: TR\n')
                f.write('    R3: Thumb R\n')
                f.write('    L1: TL\n')
                f.write('    L3: Thumb L\n')
                f.write('    Pressure Intensity Button: ""\n')
                f.write('    Pressure Intensity Percent: 50\n')
                f.write('    Left Stick Multiplier: 100\n')
                f.write('    Right Stick Multiplier: 100\n')
                f.write('    Left Stick Deadzone: 30\n')
                f.write('    Right Stick Deadzone: 30\n')
                f.write('    Left Trigger Threshold: 0\n')
                f.write('    Right Trigger Threshold: 0\n')
                f.write('    Left Pad Squircling Factor: 5000\n')
                f.write('    Right Pad Squircling Factor: 5000\n')
                f.write('    Color Value R: 0\n')
                f.write('    Color Value G: 0\n')
                f.write('    Color Value B: 0\n')
                f.write('    Blink LED when battery is below 20%: true\n')
                f.write('    Use LED as a battery indicator: false\n')
                f.write('    LED battery indicator brightness: 50\n')
                f.write(f'    Enable Large Vibration Motor: {rumble}\n')
                f.write(f'    Enable Small Vibration Motor: {rumble}\n')
                f.write('    Switch Vibration Motors: false\n')
                f.write('    Mouse Deadzone X Axis: 60\n')
                f.write('    Mouse Deadzone Y Axis: 60\n')
                f.write('    Mouse Acceleration X Axis: 200\n')
                f.write('    Mouse Acceleration Y Axis: 250\n')
                f.write('    Left Stick Lerp Factor: 100\n')
                f.write('    Right Stick Lerp Factor: 100\n')
                f.write('    Analog Button Lerp Factor: 100\n')
                f.write('    Trigger Lerp Factor: 100\n')
                f.write('    Device Class Type: 0\n')
                f.write('    Vendor ID: 1356\n')
                f.write('    Product ID: 616\n')
                # Note: no "Buddy Device" key here. A manually verified,
                # working Default.yml generated by RPCS3 itself for an Evdev
                # pad never contains this key, so we don't emit it either.