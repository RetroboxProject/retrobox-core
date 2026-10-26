
from ctypes import create_string_buffer
import glob
import logging
import os

import sdl2
from sdl2 import joystick
from ...controller import _DEFAULT_SDL_MAPPING, Controllers, evdev_to_hidraw
from .edenPaths import EDEN_RARE_DPAD_GUIDS
from ...input import Input
from retrobox.paths import DEFAULTS_DIR

_logger = logging.getLogger(__name__)

eden_buttons_mapping = {
        "button_a":      "a",
        "button_b":      "b",
        "button_x":      "x",
        "button_y":      "y",
        "button_dup":    "up",
        "button_ddown":  "down",
        "button_dleft":  "left",
        "button_dright": "right",
        "button_l":      "pageup",
        "button_r":      "pagedown",
        "button_plus":   "start",
        "button_minus":  "select",
        "button_slleft": "pageup",
        "button_srleft": "pagedown",
        "button_slright": "pageup",
        "button_srright": "pagedown",
        "button_zl":     "l2",
        "button_zr":     "r2",
        "button_lstick": "l3",
        "button_rstick": "r3",
        "button_home":   "hotkey"
}

edenAxisMapping = {
        "lstick":    "joystick1",
        "rstick":    "joystick2"
}

def hidraw_get_guid(devpath) -> str:
    try:
        vid = pid = None
        p = devpath
        while p != "/" and p:
            if os.path.exists(os.path.join(p, "idVendor")):
                with open(os.path.join(p, "idVendor")) as f:
                    vid = f.read().strip()
                with open(os.path.join(p, "idProduct")) as f:
                    pid = f.read().strip()
                break
            p = os.path.dirname(p)
        if not vid or not pid:
            return "00000000000000000000000000000000"
        return f"{vid}{pid}000000000000000000000000"
    except Exception:
        return "00000000000000000000000000000000"

def list_hidraw_devices():
    devices = []
    for h in glob.glob("/sys/class/hidraw/hidraw*"):
        dev = os.path.basename(h)
        devpath = os.path.realpath(os.path.join(h, "device"))
        name = "unknown"
        try:
            with open(os.path.join(devpath, "uevent")) as f:
                for line in f:
                    if line.startswith("HID_NAME="):
                        name = line.strip().split("=", 1)[1]
        except:
            pass
        bus = os.path.basename(devpath).split(":")[0]
        guid = hidraw_get_guid(devpath)
        devices.append({
            "hidraw": f"/dev/{dev}",
            "name": name,
            "bus": bus,
            "guid": guid
        })
    return devices

def apply_rare_dpad_fix(inputs: dict, guid: str) -> None:
    """Algunos mandos concretos (EDEN_RARE_DPAD_GUIDS) no exponen el D-Pad
    como hat en la SDL_GameControllerMapping. Se fuerza el mapeo a los
    índices de botón conocidos para esos GUID."""
    normalized_guid = guid.lower()
    normalized_guid = normalized_guid[:4] + "0000" + normalized_guid[8:]
    if normalized_guid not in EDEN_RARE_DPAD_GUIDS:
        return

    dpad_sdl_buttons = {
        'up':    sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP,
        'down':  sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN,
        'left':  sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT,
        'right': sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT,
    }
    for direction, btn_idx in dpad_sdl_buttons.items():
        inputs[direction] = Input(name=direction, type="button", id=str(btn_idx), value="1", code="0")
        _logger.debug("dpad fix: %s → %d", direction, btn_idx)

def sdlmapping_to_controller(mapping, guid):
    elements = mapping.split(',')
    current_controller = {"guid": guid, "platform": "", "inputs": {}}

    for element in elements[2:]:
        if not element:
            continue

        if element.startswith('platform:'):
            current_controller["platform"] = element[9:]
        elif ':' in element:
            logical_name, physical_mapping = element.split(':', 1)
            input_type = "unknown"
            clean_value = physical_mapping

            if physical_mapping.startswith('b'):
                input_type = "button"
                clean_value = physical_mapping[1:]
                input_obj = Input(name=logical_name, type=input_type, id=clean_value, value="1", code="0")
            elif physical_mapping.startswith('a'):
                input_type = "axis"
                clean_value = physical_mapping[1:]
                input_obj = Input(name=logical_name, type=input_type, id=clean_value, value="1", code="0")
            elif physical_mapping.startswith('h'):
                input_type = "hat"
                clean_value = physical_mapping[1:]
                clean_value_mask, clean_value_dir = clean_value.split('.')
                input_obj = Input(name=logical_name, type=input_type, id=clean_value_mask, value=clean_value_dir, code="0")
            else:
                continue

            if logical_name in _DEFAULT_SDL_MAPPING:
                logical_name = _DEFAULT_SDL_MAPPING[logical_name]
                input_obj = Input(name=logical_name, type=input_obj.type, id=input_obj.id, value=input_obj.value, code="0")

            current_controller["inputs"][logical_name] = input_obj

    return current_controller

def detect_bus_from_hidraw(hidraw_path: str):
    hidraw_device = os.path.basename(hidraw_path)
    sysfs_path = f"/sys/class/hidraw/{hidraw_device}/device"

    if not os.path.exists(sysfs_path):
        return f"Device {hidraw_device} not found in sysfs"

    try:
        real_device_path = os.path.realpath(sysfs_path)
        bus_prefix = os.path.basename(real_device_path).split(":")[0]
    except Exception as e:
        return f"Error reading device path: {e}"

    return bus_prefix[2:]

def eden_list_sdl_gamepads():
    os.environ["SDL_JOYSTICK_HIDAPI"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_PS4"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_PS5"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_SWITCH"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_XBOX"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_STEAMDECK"] = "0"
    os.environ["SDL_GAMECONTROLLERCONFIG_FILE"] = f"{DEFAULTS_DIR}/data/switch/sdl2/gamecontrollerdb.txt"
    
    sdl2.SDL_ClearError()
    try:
        sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER)
    except:
        print("An exception occurred")

    count = joystick.SDL_NumJoysticks()
    sdl_devices = {}

    for i in range(count):
        if sdl2.SDL_IsGameController(i) == 1:
            pad = sdl2.SDL_GameControllerOpen(i)
            joy_guid = joystick.SDL_JoystickGetDeviceGUID(i)
            buff = create_string_buffer(33)
            joystick.SDL_JoystickGetGUIDString(joy_guid, buff, 33)
            guidstring = ((bytes(buff)).decode()).split('\x00', 1)[0]
            joy_path = joystick.SDL_JoystickPathForIndex(i).decode()

            if 'hidraw' in joy_path:
                bustype = detect_bus_from_hidraw(joy_path)
                guidstring = bustype + guidstring[2:]

            mapping = sdl2.SDL_GameControllerMapping(pad)
            controller = sdlmapping_to_controller(str(mapping), guidstring)
            controller['sdl_index'] = i

            apply_rare_dpad_fix(controller['inputs'], guidstring)

            sdl_devices[joy_path] = controller

    sdl2.SDL_Quit()
    return sdl_devices

    
@staticmethod
def setButton(emulator, key, padGuid, padInputs, port):
    if key in padInputs:
        input_data = padInputs[key]
        _logger.debug("setButton: key=%s type=%s id=%s value=%s",
                    key, input_data.type, input_data.id, input_data.value)
        if input_data.type == "button":
            return f"engine:sdl,port:{port},guid:{padGuid},button:{input_data.id}"
        elif input_data.type == "hat":
            direction = hatdirectionvalue(input_data.value)
            return f"engine:sdl,guid:{padGuid},port:{port},pad:0,hat:{input_data.id},direction:{direction}"
        elif input_data.type == "axis":
            return f"engine:sdl,port:{port},guid:{padGuid},axis:{input_data.id},threshold:0.500000,invert:+"
    return "[empty]"

def hatdirectionvalue(value):
    try:
        val = int(value)
        mapping = {1: "up", 4: "down", 2: "right", 8: "left"}
        return mapping.get(val, "unknown")
    except:
        return "unknown"
    
def setAxis(key, padGuid, padInputs, port):
    inputx = "0"
    inputy = "0"

    left_key = "joystick1left" if key == "joystick1" else "joystick2left"
    up_key = "joystick1up" if key == "joystick1" else "joystick2up"

    if left_key in padInputs and padInputs[left_key].id is not None:
        inputx = padInputs[left_key].id
    if up_key in padInputs and padInputs[up_key].id is not None:
        inputy = padInputs[up_key].id

    return f"engine:sdl,port:{port},guid:{padGuid},axis_x:{inputx},axis_y:{inputy},offset_x:-0.000000,offset_y:0.000000,invert_x:+,invert_y:+,deadzone:0.150000"

def _eden_write_controller_config(system, playersControllers: Controllers, emulator, eden_config):
    # controls section
    if not eden_config.has_section("Controls"):
        eden_config.add_section("Controls")
    
    if system.config.get_bool("eden_auto_controller_config", True, return_values=("1", "0")):
        evdev_hidraw = evdev_to_hidraw()
        sdl_gamepads = eden_list_sdl_gamepads()

        for slot in range(8):
            eden_config.set("Controls", f"player_{slot}_connected", "false")
            eden_config.set("Controls", f"player_{slot}_connected\\default", "false")

        sorted_pads = sorted(playersControllers, key=lambda p: p.player_number)

        # Paso 1
        # Paso 1
        pad_sdl_index = {}  # id(pad) -> sdl_index
        for pad in sorted_pads:
            hidraw_path = None
            if pad.device_path in evdev_hidraw:
                hidraw_path = evdev_hidraw[pad.device_path]

            matched = None
            if hidraw_path and hidraw_path in sdl_gamepads:
                matched = sdl_gamepads[hidraw_path]
            elif pad.device_path in sdl_gamepads:
                matched = sdl_gamepads[pad.device_path]
            else:
                for path, gamepad in sdl_gamepads.items():
                    if gamepad['guid'] == pad.guid:
                        matched = gamepad
                        break

            if matched:
                # Solo el GUID "en vivo" (normalizado a bus HIDAPI) y el
                # sdl_index para ordenar puertos. Los "inputs" NO se tocan:
                # se dejan los de es_input.cfg (verdad posicional), igual
                # que en ryujinx_controllers.py, para no heredar el
                # swap A/B - X/Y que aplica SDL por etiqueta física.
                pad.guid = matched['guid']
                pad_sdl_index[id(pad)] = matched.get('sdl_index', 0)
            else:
                pad_sdl_index[id(pad)] = 0

            apply_rare_dpad_fix(pad.inputs, pad.guid)

        # Paso 2: ordenar por sdl_index real, no por player_number
        guid_counter = {}
        guid_port_map = {}
        for pad in sorted(sorted_pads, key=lambda p: pad_sdl_index[id(p)]):
            eden_guid = pad.guid.lower()
            eden_guid = eden_guid[:4] + "0000" + eden_guid[8:]
            if eden_guid not in guid_counter:
                guid_counter[eden_guid] = 0
            guid_port_map[id(pad)] = guid_counter[eden_guid]
            guid_counter[eden_guid] += 1

        # Paso 3: escribir config
        for pad in sorted_pads:
            real_player_index = pad.player_number - 1
            if real_player_index < 0 or real_player_index > 7:
                continue

            player_nb_str = f"player_{real_player_index}"
            current_buttons_mapping = dict(eden_buttons_mapping)

            eden_config.set("Controls", player_nb_str + "_type\\default", "false")
            if system.isOptSet('p{}_pad'.format(real_player_index)):
                eden_config.set("Controls", player_nb_str + "_type", system.config["p{}_pad".format(real_player_index)])
            else:
                eden_config.set("Controls", player_nb_str + "_type", "0")

            eden_guid = pad.guid.lower()
            eden_guid = eden_guid[:4] + "0000" + eden_guid[8:]

            port = guid_port_map[id(pad)]

            eden_inverse_button = system.config.get('eden_inverse_button', 'false').lower() == 'true'
            if eden_inverse_button:
                current_buttons_mapping["button_a"] = "b"
                current_buttons_mapping["button_b"] = "a"
                current_buttons_mapping["button_x"] = "y"
                current_buttons_mapping["button_y"] = "x"

            for x in current_buttons_mapping:
                eden_config.set(
                    "Controls",
                    player_nb_str + "_" + x,
                    '"{}"'.format(
                        setButton(emulator, current_buttons_mapping[x], eden_guid, pad.inputs, port)
                    )
                )
        

            for x in edenAxisMapping:
                eden_config.set("Controls", player_nb_str + "_" + x,
                    '"{}"'.format(setAxis(edenAxisMapping[x],
                                eden_guid, pad.inputs, port)))

       
            eden_config.set("Controls", player_nb_str + "_button_screenshot\\default", "false")
            eden_config.set("Controls", player_nb_str + "_button_screenshot", "[empty]")

            if pad.has_motion_controls():
                eden_config.set("Controls", player_nb_str + "_motionleft", f"engine:sdl,guid:{eden_guid},port:0,pad:0,motion:0")
                eden_config.set("Controls", player_nb_str + "_motionright", f"engine:sdl,guid:{eden_guid},port:0,pad:0,motion:0")
                #eden_config.set("Controls", player_nb_str + "_motionright", "[empty]")

            else:
                eden_config.set("Controls", player_nb_str + "_motionleft", "[empty]")
                eden_config.set("Controls", player_nb_str + "_motionright", "[empty]")

            eden_config.set("Controls", player_nb_str + "_motionleft\\default", "false")
            eden_config.set("Controls", player_nb_str + "_motionright\\default", "false")
            eden_config.set("Controls", player_nb_str + "_connected", "true")
            eden_config.set("Controls", player_nb_str + "_connected\\default", "false")

            if system.isOptSet('eden_rumble'):
                eden_config.set("Controls", player_nb_str + "_vibration_enabled", system.config["eden_rumble"])
                eden_config.set("Controls", player_nb_str + "_vibration_enabled\\default", "false")
            else:
                eden_config.set("Controls", player_nb_str + "_vibration_enabled", "true")
                eden_config.set("Controls", player_nb_str + "_vibration_enabled\\default", "true")

    return eden_config