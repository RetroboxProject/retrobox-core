from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Literal, Mapping

import pyudev

from retrobox.configgen.gun import Gun
from retrobox.configgen.controller import getJoystickHardwareIds
from retrobox.configgen.generators.libretro.libretroPaths import _RETROARCH_CFGDIR

from ...controllersConfig import getAssociatedMouse, getDevicesInformation
_logger = logging.getLogger(__name__)

if TYPE_CHECKING:

    from ...controller import Controller, Controllers
    from ...Emulator import Emulator
    from ...input import Input
    from ...settings.unixSettings import UnixSettings

# Map an emulationstation direction to the corresponding retroarch
retroarchdirs = {'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right'}

# Map an emulationstation joystick to the corresponding retroarch
retroarchjoysticks = {'joystick1up': 'l_y', 'joystick1left': 'l_x', 'joystick2up': 'r_y', 'joystick2left': 'r_x'}

# Map an emulationstation input type to the corresponding retroarch type
typetoname = {'button': 'btn', 'hat': 'btn', 'axis': 'axis', 'key': 'key'}

# Map an emulationstation input hat to the corresponding retroarch hat value
hatstoname = {'1': 'up', '2': 'right', '4': 'down', '8': 'left'}

def _get_retroarch_udev_order() -> dict[str, int]:
    context = pyudev.Context()
    order: dict[str, int] = {}
    idx = 0
    for device in context.list_devices(subsystem='input'):
        if device.get('ID_INPUT_JOYSTICK') != '1':
            continue
        devname = device.get('DEVNAME')
        if not devname or not re.match(r'/dev/input/event\d+$', devname):
            continue
        order[devname] = idx
        idx += 1
    return order

def _get_joypad_index_by_devpath(controllers) -> dict[int, int]:
    context = pyudev.Context()
    udev_order = _get_retroarch_udev_order()

    # inputNN (syspath padre) -> eventN asociado con ID_INPUT_JOYSTICK=1
    parent_to_event: dict[str, str] = {}
    for device in context.list_devices(subsystem='input'):
        if device.get('ID_INPUT_JOYSTICK') != '1':
            continue
        devname = device.get('DEVNAME')
        if not devname or not re.match(r'/dev/input/event\d+$', devname):
            continue
        parent = device.find_parent('input')
        if parent is not None:
            parent_to_event[parent.sys_path] = devname

    result: dict[int, int] = {}
    for controller in controllers:
        try:
            dev = pyudev.Devices.from_device_file(context, controller.device_path)
            parent = dev.find_parent('input') or dev
            event_devname = parent_to_event.get(parent.sys_path)
            if event_devname and event_devname in udev_order:
                result[controller.player_number] = udev_order[event_devname]
                continue
        except (pyudev.DeviceNotFoundByFileError, OSError):
            pass
        result[controller.player_number] = controller.index

    return result

# Write a configuration for a specified controller
# Warning, function used by amiberry because it reads the same retroarch formatting
def writeControllersConfig(
    retroconfig: UnixSettings,
    system: Emulator,
    controllers: Controllers,
    lightgun: bool,
    /,
) -> None:
    cleanControllerConfig(retroconfig, controllers)

    # hotkeys, forced to match with the hotkeys system
    retroconfig.save('input_enable_hotkey',       '"shift"')
    retroconfig.save('input_menu_toggle',         '"f1"')
    retroconfig.save('input_fps_toggle',          '"f2"')
    retroconfig.save('input_exit_emulator',       '"escape"')
    retroconfig.save('input_pause_toggle',        '"p"')
    retroconfig.save('input_save_state',          '"f3"')
    retroconfig.save('input_load_state',          '"f4"')
    retroconfig.save('input_state_slot_decrease', '"f5"')
    retroconfig.save('input_state_slot_increase', '"f6"')
    retroconfig.save('input_ai_service',          '"f9"')
    retroconfig.save('input_reset',               '"f10"')
    retroconfig.save('input_rewind',              '"f11"')

    # See if FF is toggle or hold
    ff_action = 'toggle_fast_forward' if (
        system.isOptSet('toggle_fast_forward')
        and system.getOptBoolean('toggle_fast_forward')
    ) else 'hold_fast_forward'

    retroconfig.save(f'input_{ff_action}',        '"f12"')
    retroconfig.save('input_screenshot',          '"nul"')
    retroconfig.save('input_audio_mute',          '"nul"')
    retroconfig.save('input_grab_mouse_toggle',   '"nul"')

    udev_indices = _get_joypad_index_by_devpath(controllers)

    for controller in controllers:
        mouseIndex: str | None = None
        if system.name in ['nds', '3ds']:
            deviceList = getDevicesInformation()
            mouseIndex = getAssociatedMouse(deviceList, controller.device_path)
        if mouseIndex is None:
            mouseIndex = '0'
            
        joypad_index = str(udev_indices.get(controller.player_number, controller.index))
        writeControllerConfig(retroconfig, controller, controller.player_number, system, joypad_index, lightgun, mouseIndex)

    #pdb.set_trace()

# Remove all controller configurations
def cleanControllerConfig(retroconfig: UnixSettings, controllers: Controllers, /) -> None:
    retroconfig.disable_all('input_player')
    retroconfig.disable_all('input_hotkey')
    retroconfig.disable_all('input_enable_hotkey_btn')

    for x in [
            'state_slot_increase',  'load_state',        'save_state',
            'state_slot_decrease',  'reset',             'exit_emulator',
            'rewind',               'hold_fast_forward', 'toggle_fast_forward',
            'screenshot',           'disk_prev',         'disk_next',
            'disk_eject_toggle',    'shader_prev',       'shader_next',
            'ai_service',           'menu_toggle'
    ]:
        retroconfig.disable_all(f'input_{x}')

# Write the hotkey for player 1
def _hotkey_save(key: str, input_obj: Input, config: dict[str, object] | None = None, /) -> tuple[str, str]:
    """Devuelve la tupla (clave, valor) con el sufijo correcto buscando en el Plan B o en el objeto Input."""

    # RAMA PLAN B: Buscamos en las claves que el parseador del archivo ya inyectó en config
    if config is not None:
        # Traducimos el nombre genérico de ES (pagedown/pageup) al botón real de RetroArch (r/l)
        ra_btn = (
            'r' if input_obj.name == 'pagedown' else
            'l' if input_obj.name == 'pageup' else
            input_obj.name  # <-- era input_obj, pero ya queremos el nombre (str)
        )

        btn_key  = f"input_player1_{ra_btn}_btn"   # ra_btn ya es str, sin .name
        axis_key = f"input_player1_{ra_btn}_axis"

        if btn_key in config and (value := config[btn_key]) is not None:
            return f"{key}_btn", str(value)
        if axis_key in config and (value := config[axis_key]) is not None:
            return f"{key}_axis", str(value)

        # Fallback de seguridad
        return "", ""

    # RAMA PLAN A: Mapeo tradicional por EmulationStation
    value = getConfigValue(input_obj) or ""
    suffix = '_axis' if input_obj.type == 'axis' else '_btn'
    return f'{key}{suffix}', value

def writeHotKeyConfig(controller: Controller, manual_config: bool, config: dict[str, object] | None = None, /) -> dict[str, str]:
    """Genera el diccionario de hotkeys desde EmulationStation sin romper bucles."""
    hotkeys = {}
    if not controller:
        return hotkeys
    
    pad = controller.inputs
    chosen_hotkey = pad.get('hotkey') or pad.get('select')
    if not chosen_hotkey or chosen_hotkey.type != 'button':
        return hotkeys

    if not manual_config:
        hotkeys['input_enable_hotkey_btn'] = getConfigValue(chosen_hotkey)

    hotkey_map = {
        'start':    'input_exit_emulator',
        'b':        'input_pause_toggle',
        'x':        'input_screenshot',
        'a':        'input_reset',
        'r2':       'input_save_state',
        'l2':       'input_load_state',
        'right':    'input_hold_fast_forward',
        'left':     'input_rewind',
        'up':       'input_disk_eject_toggle',
        'pagedown': 'input_disk_next',
        'pageup':   'input_disk_prev',
    }

    for btn, rakey in hotkey_map.items():
        if btn in pad:
            k, v = _hotkey_save(rakey, pad[btn], config)
            # Transformamos 'input_exit_emulator_btn' en 'input_player1_exit_emulator_btn'
            # Cortamos a partir del carácter 6 ('input_') y le metemos el prefijo del player 1
            hotkeys[k] = v
            
    return hotkeys            

# Write a configuration for a specified controller
def writeControllerConfig(
    retroconfig: UnixSettings,
    controller: Controller,
    playerIndex: int,
    system: Emulator,
    joypad_index: str,
    lightgun: bool,
    mouseIndex: str,
    /,
):
    generatedConfig = generateControllerConfig(controller, system, lightgun, mouseIndex)
    for key in generatedConfig:
        retroconfig.save(key, generatedConfig[key])

    retroconfig.save(f'input_player{playerIndex}_joypad_index', str(joypad_index))
    retroconfig.save(f'input_player{playerIndex}_analog_dpad_mode', getAnalogMode(controller, system))
    
# Create a configuration for a given controller
def generateControllerConfig(
    controller: Controller,
    system: Emulator,
    lightgun: bool,
    mouseIndex: str,
    /,
) -> dict[str, object]:

    config: dict[str, object] = {}
    hw_ids = getJoystickHardwareIds(controller.device_path)
    
    if hw_ids:
        vendor_dec, product_dec = hw_ids
        
        hw_cfg_name = f"{vendor_dec}-{product_dec}.cfg"
        hw_cfg_path = _RETROARCH_CFGDIR / 'autoconfig' / hw_cfg_name
        
        if hw_cfg_path.exists():
            p_num = controller.player_number
            _logger.debug("Aplicando perfil %s al Player %s", hw_cfg_name, p_num)
            
            cfg_hotkey = None
            cfg_select = None
            
            try:
                with open(hw_cfg_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith(('#', ';')):
                            continue
                        if '=' in line:
                            k, v = line.split('=', 1)
                            k, v = k.strip(), v.strip()
                            
                            if k in ('input_driver', 'input_device', 'input_device_display_name', 'input_vendor_id', 'input_product_id'):
                                continue

                            if k.startswith('input_'):
                                # Capturamos los valores limpios que usaremos para la hotkey de respaldo
                                if k == 'input_enable_hotkey_btn':
                                    cfg_hotkey = v
                                elif k == 'input_select_btn':
                                    cfg_select = v
                                
                                suffix = k[6:]
                                config[f"input_player{p_num}_{suffix}"] = v        
                
                # Al salir del archivo, si eres Player 1, metemos la hotkey global de tu .cfg
                if p_num == 1:
                    config['input_enable_hotkey_btn'] = cfg_hotkey or cfg_select
                    config.update(writeHotKeyConfig(controller, True, config))

                if not lightgun:
                    config[f'input_player{p_num}_mouse_index'] = mouseIndex
                    
                return config
                
            except Exception as e:
                _logger.debug("Falló la lectura del perfil %s: %s", hw_cfg_name, e)
    # Si no detectamos mapping manual de mando, seguimos
    # Map an emulationstation button name to the corresponding retroarch name
    retroarchbtns = {'a': 'a', 'b': 'b', 'x': 'x', 'y': 'y', \
                     'pageup': 'l', 'pagedown': 'r', 'l2': 'l2', 'r2': 'r2', \
                     'l3': 'l3', 'r3': 'r3', \
                     'start': 'start', 'select': 'select'}

    # X Y L1 L2  ---> X Y R1 L1
    # A B R1 R2  ---> A B R2 L2
    if system.config.get('altlayout') == 'fightstick':
        retroarchbtns['pageup'] = 'l2'
        retroarchbtns['pagedown'] = 'l'
        retroarchbtns['l2'] = 'r2'
        retroarchbtns['r2'] = 'r'

    retroarchGunbtns = {'a': 'aux_a', 'b': 'aux_b', 'y': 'aux_c', \
                        'pageup': 'offscreen_shot', 'pagedown': 'trigger', \
                        'start': 'start', 'select': 'select'}

    # Some input adaptations for some cores...
    # Z is important, in case l2 (z) is not available for this pad, use l1
    if system.name == "n64" and 'r2' not in controller.inputs:
        retroarchbtns["pageup"] = "l2"
        retroarchbtns["l2"] = "l"

    if system.name == "dreamcast" and system.config.core == "flycast" and 'r2' not in controller.inputs:
        retroarchbtns["pageup"] = "l2"
        retroarchbtns["l2"] = "l"
        retroarchbtns["pagedown"] = "r2"
        retroarchbtns["r2"] = "r"

    # Fix for reversed inputs in Yabasanshiro core which is unmaintained by retroarch
    if system.config.core == 'yabasanshiro':
        retroarchbtns["pageup"] = "r"
        retroarchbtns["pagedown"] = "l"

    # config['input_device'] = '"%s"' % controller.real_name
    for btnkey in retroarchbtns:
        btnvalue = retroarchbtns[btnkey]
        if btnkey in controller.inputs:
            input_btn = controller.inputs[btnkey]
            config[f'input_player{controller.player_number}_{btnvalue}_{typetoname[input_btn.type]}'] = getConfigValue(
                input_btn)
    if lightgun:
        for btnkey in retroarchGunbtns: # Gun Mapping
            btnvalue = retroarchGunbtns[btnkey]
            if btnkey in controller.inputs:
                input_btn = controller.inputs[btnkey]
                config[f'input_player{controller.player_number}_gun_{btnvalue}_{typetoname[input_btn.type]}'] = getConfigValue(
                    input_btn)
    for dirkey in retroarchdirs:
        dirvalue = retroarchdirs[dirkey]
        if dirkey in controller.inputs:
            input_btn = controller.inputs[dirkey]
            config[f'input_player{controller.player_number}_{dirvalue}_{typetoname[input_btn.type]}'] = getConfigValue(
                input_btn)
            if lightgun:
                # Gun Mapping
                config[f'input_player{controller.player_number}_gun_dpad_{dirvalue}_{typetoname[input_btn.type]}'] = getConfigValue(
                    input_btn)
    for jskey in retroarchjoysticks:
        jsvalue = retroarchjoysticks[jskey]
        if jskey in controller.inputs:
            input_btn = controller.inputs[jskey]
            if input_btn.value == '-1':
                config[f'input_player{controller.player_number}_{jsvalue}_minus_axis'] = f'-{input_btn.id}'
                config[f'input_player{controller.player_number}_{jsvalue}_plus_axis'] = f'+{input_btn.id}'
            else:
                config[f'input_player{controller.player_number}_{jsvalue}_minus_axis'] = f'+{input_btn.id}'
                config[f'input_player{controller.player_number}_{jsvalue}_plus_axis'] = f'-{input_btn.id}'

    if not lightgun:
        config[f'input_player{controller.player_number}_mouse_index'] = mouseIndex
    
    # Si entra por aquí (Plan A), mete las hotkeys de EmulationStation
    if controller.player_number == 1:
        config.update(writeHotKeyConfig(controller, False))
        
    return config

# Returns the value to write in retroarch config file, depending on the type
def getConfigValue(input_btn: Input, /) -> str | None:
    if input_btn.type == 'button':
        return f'"{input_btn.id}"'
    if input_btn.type == 'axis':
        if input_btn.value == '-1':
            return f'"-{input_btn.id}"'
        return f'"+{input_btn.id}"'
    if input_btn.type == 'hat':
        return f'"h{input_btn.id}{hatstoname[input_btn.value]}"'
    if input_btn.type == 'key':
        return f'"{input_btn.id}"'
    return None

# Return the retroarch analog_dpad_mode
def getAnalogMode(controller: Controller, system: Emulator, /) -> Literal['0', '1']:
    # don't enable analog as hat mode for some systems
    if system.name == 'n64' or system.name == 'dreamcast' or system.name == '3ds':
        return '0'

    for dirkey in retroarchdirs:
        if dirkey in controller.inputs and (controller.inputs[dirkey].type == 'button' or controller.inputs[dirkey].type == 'hat'):
            return '1'
    return '0'


def clearGunInputsForPlayer(n: int, retroarchConfig: dict[str, object], /) -> None:
    keys = ["gun_trigger", "gun_offscreen_shot", "gun_aux_a", "gun_aux_b", "gun_aux_c", "gun_start", "gun_select", "gun_dpad_up", "gun_dpad_down", "gun_dpad_left", "gun_dpad_right"]
    for key in keys:
        for type_ in ("btn", "mbtn"):
            retroarchConfig[f'input_player{n}_{key}_{type_}'] = ''


def configureGunInputsForPlayer(n: int, gun: Gun, controllers: Controllers, retroarchConfig: dict[str, object], core: str, metadata: Mapping[str, str], system: Emulator, /) -> None:
    pedalsKeys = {1: "c", 2: "v", 3: "b", 4: "n"}
    pedalkey = system.config.get(f"controllers.pedals{n}", pedalsKeys.get(n))
    pedalconfig = None

    retroarchConfig[f'input_player{n}_mouse_index'] = gun.mouse_index
    retroarchConfig[f'input_player{n}_gun_trigger_mbtn'] = 1
    retroarchConfig[f'input_player{n}_gun_offscreen_shot_mbtn'] = 2
    pedalconfig = f'input_player{n}_gun_offscreen_shot'
    retroarchConfig[f'input_player{n}_gun_start_mbtn'] = 3
    retroarchConfig[f'input_player{n}_gun_select_mbtn'] = 4
    retroarchConfig[f'input_player{n}_gun_aux_a_mbtn'] = 5
    retroarchConfig[f'input_player{n}_gun_aux_b_mbtn'] = 6
    retroarchConfig[f'input_player{n}_gun_aux_c_mbtn'] = 7
    retroarchConfig[f'input_player{n}_gun_dpad_up_mbtn'] = 8
    retroarchConfig[f'input_player{n}_gun_dpad_down_mbtn'] = 9
    retroarchConfig[f'input_player{n}_gun_dpad_left_mbtn'] = 10
    retroarchConfig[f'input_player{n}_gun_dpad_right_mbtn'] = 11

    if core in ("pcsx_rearmed", "fbneo", "snes9x", "genesis_plus_gx", "genesis_plus_gx-expanded", "flycast", "mame", "swanstation"):
        retroarchConfig[f'input_player{n}_gun_offscreen_shot_mbtn'] = ''
        retroarchConfig[f'input_player{n}_gun_aux_a_mbtn'] = 2
        pedalconfig = f'input_player{n}_gun_aux_a'
        if core == "swanstation":
            retroarchConfig[f'input_player{n}_gun_aux_b_mbtn'] = 3

    if core == "dolphin":
        for key in ["gun_trigger", "gun_offscreen_shot", "gun_aux_a", "gun_aux_b", "gun_aux_c", "gun_start", "gun_select", "gun_dpad_up", "gun_dpad_down", "gun_dpad_left", "gun_dpad_right"]:
            retroarchConfig[f'input_player{n}_{key}_mbtn'] = ''
        wiimote_to_ra = {"b": "b", "a": "a", "1": "start", "2": "select", "+": "r", "-": "l", "up": "up", "down": "down", "left": "left", "right": "right", "c": "x", "z": "y", "shake": "r2", "tiltforward": "l3"}
        action_to_wiimote = {"trigger": "b", "action": "a", "start": "+", "select": "-", "sub1": "1", "sub2": "2", "up": "up", "down": "down", "left": "left", "right": "right"}
        action_to_gun = {"trigger": 1, "action": 2, "start": 3, "select": 4, "sub1": 5, "sub2": 6, "up": 8, "down": 9, "left": 10, "right": 11}
        for action in action_to_wiimote:
            if (gun_action := metadata.get(f"gun_{action}")):
                action_to_wiimote[action] = gun_action
        for action, wiimote in action_to_wiimote.items():
            if wiimote in wiimote_to_ra and action in action_to_gun:
                retroarchConfig[f'input_player{n}_{wiimote_to_ra[wiimote]}_mbtn'] = action_to_gun[action]

    if pedalconfig and pedalkey:
        retroarchConfig[pedalconfig] = pedalkey

    mapping = {"gun_trigger": "b", "gun_offscreen_shot": "a", "gun_aux_a": "x", "gun_aux_b": "y", "gun_aux_c": "pageup", "gun_start": "start", "gun_select": "select", "gun_dpad_up": "up", "gun_dpad_down": "down", "gun_dpad_left": "left", "gun_dpad_right": "right"}
    hatstoname = {'1': 'up', '2': 'right', '4': 'down', '8': 'left'}

    if pad := Controller.find_player_number(controllers, n):
        for m, input_name in mapping.items():
            if input_name in pad.inputs:
                inp = pad.inputs[input_name]
                if inp.type == "button":
                    retroarchConfig[f'input_player{n}_{m}_btn'] = inp.id
                elif inp.type == "hat":
                    retroarchConfig[f'input_player{n}_{m}_btn'] = f"h0{hatstoname[inp.value]}"
                elif inp.type == "axis":
                    aval = "-" if int(inp.value) < 0 else "+"
                    retroarchConfig[f'input_player{n}_{m}_axis'] = f"{aval}{inp.id}"
