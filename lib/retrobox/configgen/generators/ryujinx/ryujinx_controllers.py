from collections import defaultdict
from ctypes import create_string_buffer
import logging
import os
import re

import sdl2
from sdl2 import joystick

from ...controller import evdev_to_hidraw
from ...Emulator import Emulator

_logger = logging.getLogger(__name__)


def sdl_guid_to_ryujinx_guid(sdl_guid):
    g = sdl_guid.lower().replace('-', '')
    if len(g) != 32:
        return sdl_guid
    b = [g[i:i+2] for i in range(0, 32, 2)]

    bus_le = b[0:2]
    b[0] = '00'
    b[1] = '00'
    b[2] = bus_le[1]
    b[3] = bus_le[0]
    b[4], b[5] = b[5], b[4]
    return ''.join(b)


def _is_valid_sdl_guid(g):
    if not g:
        return False
    g = re.sub(r'[^0-9a-f]', '', str(g).lower())
    if len(g) != 32:
        return False
    if g.startswith("00000000"):
        return False
    return True


"""Traduce el nombre de botón SDL_GameController (minúscula, vocabulario SDL)
al nombre interno que espera el JSON de Ryujinx (PascalCase, vocabulario propio
de Ryujinx: GamepadInputId). No son intercambiables salvo para a/b/x/y, donde
coinciden por casualidad."""
_SDL_TO_RYUJINX_NAME = {
    'a': 'A', 'b': 'B', 'x': 'X', 'y': 'Y',
    'start': 'Start', 'back': 'Back',
    'leftshoulder': 'LeftShoulder', 'rightshoulder': 'RightShoulder',
    'lefttrigger': 'LeftTrigger', 'righttrigger': 'RightTrigger',
    'leftstick': 'LeftStick', 'rightstick': 'RightStick',
    'guide': 'Guide',
}


def _sdl_mapping_to_input_lookup(mapping_str: str) -> dict[tuple[str, str], str]:
    """A partir de 'a:b1,b:b0,lefttrigger:a2,...' devuelve
    {(kind, id_crudo): nombre_sdl}, con kind en {'button', 'axis'}.

    Este lookup es la pieza clave para respetar es_input.cfg (fuente de verdad
    posicional de EmulationStation) frente a mandos cuya entrada en la SDL
    GameControllerDB resuelve algunos nombres por etiqueta física en vez de
    por posición (p.ej. mandos Nintendo con el hint USE_BUTTON_LABELS, que
    afecta a a/b/x/y).
    """
    lookup: dict[tuple[str, str], str] = {}
    if not mapping_str:
        return lookup
    for part in mapping_str.split(','):
        if ':' not in part:
            continue
        name, phys = part.split(':', 1)
        if phys.startswith('b'):
            lookup[('button', phys[1:])] = name
        elif phys.startswith('a'):
            raw_id = phys[1:]
            if raw_id and raw_id[0] in '+-':
                raw_id = raw_id[1:]
            raw_id = raw_id.rstrip('~')
            lookup[('axis', raw_id)] = name
    return lookup





def list_sdl_gamepads(sdlversion):

    os.environ["SDL_JOYSTICK_HIDAPI"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_PS4"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_PS5"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_SWITCH"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_XBOX"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_STEAMDECK"] = "0"

    sdl2.SDL_ClearError()

    if sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER) != 0:
        _logger.error("SDL init failed: %s", sdl2.SDL_GetError().decode())
        return {}

    sdl_devices = {}

    count = joystick.SDL_NumJoysticks()

    for i in range(count):

        if sdl2.SDL_IsGameController(i) != 1:
            continue

        pad = sdl2.SDL_GameControllerOpen(i)

        if not pad:
            continue

        try:
            # IMPORTANTE:
            # usar DeviceGUID y NO JoystickGUID
            guid = joystick.SDL_JoystickGetDeviceGUID(i)

            buff = create_string_buffer(33)
            joystick.SDL_JoystickGetGUIDString(guid, buff, 33)

            guidstring = (
                bytes(buff)
                .decode("utf-8")
                .split('\x00', 1)[0]
                .lower()
            )
            guidstring = guidstring.replace("-", "").strip()

            name = sdl2.SDL_GameControllerName(pad)
            if isinstance(name, bytes):
                name = name.decode()

            mapping = sdl2.SDL_GameControllerMapping(pad)
            if isinstance(mapping, bytes):
                mapping = mapping.decode()
            _logger.debug("SDL MAPPING guid=%s mapping=%s", guidstring, mapping)

            try:
                joy_path = joystick.SDL_JoystickPathForIndex(i)
                if isinstance(joy_path, bytes):
                    joy_path = joy_path.decode()
            except Exception:
                joy_path = f"sdl-{i}"

            sdl_devices[joy_path] = {
                "guid": guidstring,
                "name": name,
                "mapping": mapping,
                "path": joy_path,
                "sdl_index": i,
            }
            _logger.debug("SDL DEVICE index=%d name='%s' guid='%s'", i, name, guidstring)

        finally:
            sdl2.SDL_GameControllerClose(pad)

    sdl2.SDL_Quit()

    return sdl_devices


def _ryujinx_gen_gamepad_config(system: Emulator, playersControllers):
    if not system.config.get_bool('ryu_auto_controller_config', True, return_values=(True, False)):
        return []

    # get the evdev->hidraw mapping
    evdev_hidraw = evdev_to_hidraw()
    # get sdllib hidapi/hidraw + evdev guid
    sdl_gamepads = list_sdl_gamepads(2)

    input_config = []

    # guid resolution for all controllers
    pad_pure_guid = {}
    pad_sdl_index = {}
    pad_face_button_lookup = {}

    for controller in playersControllers:
        matched_sdl_ctrl = None

        hidraw_path = evdev_hidraw.get(controller.device_path)
        if hidraw_path and hidraw_path in sdl_gamepads:
            matched_sdl_ctrl = sdl_gamepads[hidraw_path]
        elif controller.device_path in sdl_gamepads:
            matched_sdl_ctrl = sdl_gamepads[controller.device_path]

        found_sdl_guid = matched_sdl_ctrl.get("guid") if matched_sdl_ctrl else None
        pad_sdl_index[id(controller)] = matched_sdl_ctrl.get("sdl_index", 0) if matched_sdl_ctrl else 0

        mapping_str = matched_sdl_ctrl.get("mapping", "") if matched_sdl_ctrl else ""
        if isinstance(mapping_str, bytes):
            mapping_str = mapping_str.decode(errors="ignore")
        pad_face_button_lookup[id(controller)] = _sdl_mapping_to_input_lookup(mapping_str)

        controller_guid = getattr(controller, 'guid', None)

        if _is_valid_sdl_guid(found_sdl_guid):
            pure_guid = found_sdl_guid
        elif _is_valid_sdl_guid(controller_guid):
            pure_guid = controller_guid
        else:
            pure_guid = "00000000000000000000000000000000"

        pure_guid = re.sub(r'[^0-9a-f]', '', str(pure_guid).lower())
        pure_guid = pure_guid[:32].ljust(32, "0")
        pure_guid = sdl_guid_to_ryujinx_guid(pure_guid)
        pad_pure_guid[id(controller)] = pure_guid

    # relative idx per guid
    guid_groups = defaultdict(list)
    for controller in sorted(playersControllers, key=lambda c: pad_sdl_index[id(c)]):
        guid_groups[pad_pure_guid[id(controller)]].append(controller)

    controller_idx_map = {}
    for guid, group in guid_groups.items():
        for idx, controller in enumerate(group):
            controller_idx_map[id(controller)] = idx

    # --- construir input_config ordenado por player_number ---
    for controller in sorted(playersControllers, key=lambda c: int(c.player_number)):
        pure_guid = pad_pure_guid[id(controller)]
        current_idx = controller_idx_map[id(controller)]

        formatted_guid = (
            f"{pure_guid[0:8]}-"
            f"{pure_guid[8:12]}-"
            f"{pure_guid[12:16]}-"
            f"{pure_guid[16:20]}-"
            f"{pure_guid[20:32]}"
        )
        final_guid = f"{current_idx}-{formatted_guid}"

        left_joycon_stick = {
            'joystick': "Left",
            'rotate90_cw': False,
            'invert_stick_x': False,
            'invert_stick_y': False,
            'stick_button': "LeftStick",
        }

        right_joycon_stick = {
            'joystick': "Right",
            'rotate90_cw': False,
            'invert_stick_x': False,
            'invert_stick_y': False,
            'stick_button': "RightStick",
        }

        motion = {
            'motion_backend': "GamepadDriver",
            'sensitivity': 100,
            'gyro_deadzone': 1,
            'enable_motion': True,
        }

        rumble = {
            'strong_rumble': 1,
            'weak_rumble': 1,
            'enable_rumble': True,
        }

        left_joycon = {
            'button_minus': "Back",
            'button_l': "LeftShoulder",
            'button_zl': "LeftTrigger",
            'button_sl': "SingleLeftTrigger0",
            'button_sr': "SingleRightTrigger0",
            'dpad_up': "DpadUp",
            'dpad_down': "DpadDown",
            'dpad_left': "DpadLeft",
            'dpad_right': "DpadRight",
        }

        right_joycon = {
            'button_plus': "Start",
            'button_r': "RightShoulder",
            'button_zr': "RightTrigger",
            'button_sl': "SingleLeftTrigger1",
            'button_sr': "SingleRightTrigger1",
        }

        # Traduce cada botón lógico de EmulationStation (fuente de verdad
        # posicional) al nombre que Ryujinx espera, pasando por el id crudo
        # (y su tipo, botón o eje) para no depender de si la GameControllerDB
        # resuelve el nombre SDL por posición o por etiqueta para este GUID.
        input_lookup = pad_face_button_lookup.get(id(controller), {})

        def es_input_to_ryujinx_name(es_name: str, default: str) -> str:
            inp = controller.inputs.get(es_name)
            if inp is None:
                return default
            kind = 'button' if inp.type == 'button' else 'axis' if inp.type == 'axis' else None
            if kind is None:
                return default
            sdl_name = input_lookup.get((kind, str(inp.id)))
            if sdl_name is None:
                return default
            return _SDL_TO_RYUJINX_NAME.get(sdl_name, default)

        right_joycon['button_a'] = es_input_to_ryujinx_name('a', 'A')
        right_joycon['button_b'] = es_input_to_ryujinx_name('b', 'B')
        right_joycon['button_x'] = es_input_to_ryujinx_name('x', 'X')
        right_joycon['button_y'] = es_input_to_ryujinx_name('y', 'Y')
        right_joycon['button_plus'] = es_input_to_ryujinx_name('start', 'Start')
        left_joycon['button_minus'] = es_input_to_ryujinx_name('select', 'Back')
        left_joycon['button_l'] = es_input_to_ryujinx_name('pageup', 'LeftShoulder')
        right_joycon['button_r'] = es_input_to_ryujinx_name('pagedown', 'RightShoulder')
        left_joycon['button_zl'] = es_input_to_ryujinx_name('l2', 'LeftTrigger')
        right_joycon['button_zr'] = es_input_to_ryujinx_name('r2', 'RightTrigger')
        left_joycon_stick['stick_button'] = es_input_to_ryujinx_name('l3', 'LeftStick')
        right_joycon_stick['stick_button'] = es_input_to_ryujinx_name('r3', 'RightStick')

        _logger.debug(
            "RYU INPUT LOOKUP player=%s guid=%s lookup=%s -> a=%s b=%s x=%s y=%s "
            "start=%s select=%s l=%s r=%s zl=%s zr=%s l3=%s r3=%s",
            controller.player_number, controller.guid, input_lookup,
            right_joycon['button_a'], right_joycon['button_b'],
            right_joycon['button_x'], right_joycon['button_y'],
            right_joycon['button_plus'], left_joycon['button_minus'],
            left_joycon['button_l'], right_joycon['button_r'],
            left_joycon['button_zl'], right_joycon['button_zr'],
            left_joycon_stick['stick_button'], right_joycon_stick['stick_button'],
        )

        cvalue = {
            'controller_type': "ProController",
            'left_joycon_stick': left_joycon_stick,
            'right_joycon_stick': right_joycon_stick,
            'deadzone_left': 0.1,
            'deadzone_right': 0.1,
            'range_left': 1,
            'range_right': 1,
            'trigger_threshold': 0.5,
            'motion': motion,
            'rumble': rumble,
            'led': {
                'enable_led': False,
                'turn_off_led': False,
                'use_rainbow': False,
                'led_color': 0,
            },
            'left_joycon': left_joycon,
            'right_joycon': right_joycon,
            'version': 1,
            'backend': "GamepadSDL2",
            'id': final_guid,
            'name': f"{getattr(controller, 'real_name', 'Gamepad')} ({current_idx})",
            'player_index': "Player" + str(int(controller.player_number)),
        }

        input_config.append(cvalue)

    return input_config
