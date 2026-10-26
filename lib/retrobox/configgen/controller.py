from __future__ import annotations

import glob
import logging
import os
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import InitVar, dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, Self, TypedDict, Unpack, cast

import evdev

from retrobox.paths import FRONTEND_DIR, _USER_HOME, ES_INPUT_CFG, RUNTIME_DIR

_logger: Final = logging.getLogger(__name__)

from .exceptions import RetroboxException
from .input import Input, InputDict, InputMapping

if TYPE_CHECKING:
    from argparse import Namespace

"""Default mapping of Batocera keys to SDL_GAMECONTROLLERCONFIG keys."""
_DEFAULT_SDL_MAPPING: Final = {
    'b': 'a',
    'a': 'b',
    'x': 'y',
    'y': 'x',
    'l2': 'lefttrigger',
    'r2': 'righttrigger',
    'l3': 'leftstick',
    'r3': 'rightstick',
    'pageup': 'leftshoulder',
    'pagedown': 'rightshoulder',
    'start': 'start',
    'select': 'back',
    'up': 'dpup',
    'down': 'dpdown',
    'left': 'dpleft',
    'right': 'dpright',
    'joystick1up': 'lefty',
    'joystick1left': 'leftx',
    'joystick2up': 'righty',
    'joystick2left': 'rightx',
    'hotkey': 'guide'
}

def _key_to_sdl_game_controller_config(keyname: str, input: Input, /) -> str | None:
    """
    Converts a key mapping to the SDL_GAMECONTROLLER format.

    Arguments:
      keyname: (str) SDL_GAMECONTROLLERCONFIG input name.
      input: (Input) input object.
    Returns:
      (str) SDL_GAMECONTROLLERCONFIG-formatted key mapping string.
    """
    if input.type == 'button':
        return f'{keyname}:b{input.id}'

    if input.type == 'hat':
        return f'{keyname}:h{input.id}.{input.value}'

    if input.type == 'axis':
        if 'joystick' in input.name:
            return f"{keyname}:a{input.id}{'~' if int(input.value) > 0 else ''}"

        if keyname in ('dpup', 'dpdown', 'dpleft', 'dpright'):
            return f"{keyname}:{'-' if int(input.value) < 0 else '+'}a{input.id}"

        if 'trigger' in keyname:
            return f"{keyname}:a{input.id}{'~' if int(input.value) < 0 else ''}"

        return f'{keyname}:a{input.id}'

    if input.type == 'key':
        return None

    raise RetroboxException(f'Unknown controller input type: {input.type!r}')

def _find_input_config(roots: Iterable[ET.Element], name: str, guid: str, /) -> ET.Element:
    path = './inputConfig'

    for root in roots:
        element = root.find(f'{path}[@deviceGUID="{guid}"][@deviceName="{name}"]')
        if element is not None:
            return element

    for root in roots:
        element = root.find(f'{path}[@deviceGUID="{guid}"]')
        if element is not None:
            return element

    for root in roots:
        element = root.find(f'{path}[@deviceName="{name}"]')
        if element is not None:
            return element

    raise RetroboxException(f'Could not find controller data for "{name}" with GUID "{guid}"')


_HIDAPI_BUS = "0300"  # lo que SDL+HIDAPI reporta siempre vía kernel HID

def normalize_sdl_guid_for_emulator(raw_guid: str) -> str:
    """
    SDL con backend HIDAPI/hidraw presenta todos los mandos como USB HID (0300)
    independientemente del transporte físico (BT=0500, virtual=0600, etc.).
    Normaliza el GUID de Batocera para que coincida con lo que ve el emulador.
    """
    g = raw_guid.lower()
    bus = g[:4]

    if bus == _HIDAPI_BUS:
        return g  # ya correcto, no tocar

    # cualquier otro bus → USB HID, igual que lo ve SDL+HIDAPI
    return _HIDAPI_BUS + g[4:]

def evdev_to_hidraw():

    result = {}

    for hid_path in glob.glob('/sys/class/hidraw/hidraw*'):
        hid_dev = os.path.realpath(os.path.join(hid_path, "device"))

        events = []
        for root, dirs, files in os.walk(hid_dev):
            for dir in dirs:
                if dir.startswith("event"):
                    event_path = os.path.join(root, dir)
                    if "/input" in event_path and "/event" in event_path:
                        events.append(event_path)

        if events:
            for ev in events:
                ev_name = os.path.basename(ev)
                hid_name = os.path.basename(hid_path)
                result[f"/dev/input/{ev_name}"] = f"/dev/{hid_name}"
    return result

def getJoystickHardwareIds(device_path: str, /) -> tuple[str, str] | None:
    """
    Obtiene Vendor y Product ID en decimal leyendo de forma unívoca el archivo uevent.
    Soporta /dev/hidrawX y /dev/input/eventX sin depender de estructuras dinámicas de subcarpetas.
    """

    if not device_path or not os.path.exists(device_path):
        return None

    base_name = os.path.basename(device_path) # ej: 'hidraw6' o 'event19'

    try:
        # 1. Determinamos la ruta base en sysfs según el tipo de nodo
        if 'hidraw' in base_name:
            uevent_path = Path("/sys/class/hidraw") / base_name / "device" / "uevent"
        elif 'event' in base_name:
            uevent_path = Path("/sys/class/input") / base_name / "device" / "uevent"
        else:
            return None

        if not uevent_path.exists():
            return None

        # 2. Parseamos el archivo uevent buscando el ID de hardware
        vendor_hex, product_hex = None, None
        
        with open(uevent_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Caso hidraw: Típicamente "HID_ID=0005:0000057E:00002009"
                if line.startswith("HID_ID="):
                    parts = line.split("=")[1].split(":")
                    vendor_hex = parts[1]
                    product_hex = parts[2]
                    break
                
                # Caso event estándar: Típicamente "PRODUCT=3/57e/2009/11b"
                elif line.startswith("PRODUCT="):
                    parts = line.split("=")[1].split("/")
                    vendor_hex = parts[1]
                    product_hex = parts[2]
                    break

        # 3. Si encontramos los hexadecimales, conversión limpia a string decimal
        if vendor_hex and product_hex:
            return str(int(vendor_hex, 16)), str(int(product_hex, 16))

    except Exception as e:
        print(f"[DEBUG_HW] Error unívoco en sysfs para {base_name}: {e}")

    return None



class _RelaxedDict(TypedDict):
    centered: bool
    reversed: bool

class _ControllerChanges(TypedDict, total=False):
    guid: str
    player_number: int
    index: int
    real_name: str
    device_path: str
    button_count: int
    hat_count: int
    axis_count: int
    physical_device_path: str | None
    physical_index: int | None

@dataclass(slots=True, kw_only=True)
class Controller:
    name: str
    type: Literal['keyboard', 'joystick']
    guid: str
    player_number: int  # when this is filled out, it will start at 1
    index: int
    real_name: str
    device_path: str
    button_count: int
    hat_count: int
    axis_count: int
    physical_device_path: str | None = None
    physical_index: int | None = None

    inputs_: InitVar[InputMapping | Iterable[tuple[str, Input]] | None] = None
    inputs: InputDict = field(init=False)

    def __post_init__(self, inputs_: InputMapping | Iterable[tuple[str, Input]] | None, /) -> None:
        self.inputs = dict(inputs_) if inputs_ is not None else {}

    def replace(self, /, **changes: Unpack[_ControllerChanges]) -> Self:
        return replace(self, **changes, inputs_={name: input.replace() for name, input in self.inputs.items()})

    def generate_sdl_game_db_line(self, sdl_mapping: Mapping[str, str] = _DEFAULT_SDL_MAPPING, /, ignore_buttons: list[str] | None = None) -> str:
        """Returns an SDL_GAMECONTROLLERCONFIG-formatted string for the given configuration."""
        config = [self.guid, self.real_name.replace(",", "."), "platform:Linux"]

        def add_mapping(input: Input) -> None:
            key_name = sdl_mapping.get(input.name, None)
            if key_name is None:
                return
            sdl_config = _key_to_sdl_game_controller_config(key_name, input)
            if sdl_config is not None:
                config.append(sdl_config)

        # "hotkey" is often mapped to an existing button but such a duplicate mapping
        # confuses SDL apps. We add "hotkey" mapping only if its target isn't also mapped elsewhere.
        hotkey_input: Input | None = None
        mapped_button_ids: set[str] = set()

        for input in self.inputs.values():
            if input.name is None:  # pragma: no cover
                continue
            if ignore_buttons is not None and input.name in ignore_buttons:
                continue
            if input.name == 'hotkey':
                hotkey_input = input
                continue
            if input.type == 'button':
                mapped_button_ids.add(input.id)

            add_mapping(input)

        if hotkey_input is not None and hotkey_input.id not in mapped_button_ids:
            add_mapping(hotkey_input)

        config.append('')

        return ','.join(config)
    
    @staticmethod
    def find_device_path_sdl(guid: str, index: int) -> str | None:
        try:
            import sdl2
        except ImportError:
            return None

        try:
            if sdl2.SDL_WasInit(sdl2.SDL_INIT_JOYSTICK) == 0:
                sdl2.SDL_Init(sdl2.SDL_INIT_JOYSTICK)

            import ctypes

            matches: list[str] = []
            for i in range(sdl2.SDL_NumJoysticks()):
                joy = sdl2.SDL_JoystickOpen(i)
                if not joy:
                    continue

                sdl_guid = sdl2.SDL_JoystickGetGUID(joy)
                buf = ctypes.create_string_buffer(33)
                sdl2.SDL_JoystickGetGUIDString(sdl_guid, buf, 33)
                guid_str = buf.value.decode().lower()

                if guid_str == guid and hasattr(sdl2, "SDL_JoystickPath"):
                    path = sdl2.SDL_JoystickPath(joy)
                    if path:
                        matches.append(path.decode())

            if not matches:
                return None

            # `index` no es fiable entre procesos: solo desambigua entre mandos
            # con el mismo GUID (modelos duplicados), nunca filtra por posición absoluta.
            return matches[min(index, len(matches) - 1)]

        except Exception:
            pass

        return None
    @staticmethod
    def find_device_path_evdev(
        real_name: str,
        axis_count: int,
        button_count: int,
        hat_count: int,
        index: int,
    ) -> str | None:
        try:
            import evdev
        except ImportError:
            return None

        matches: list[str] = []

        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
            except Exception:
                continue

            if dev.name != real_name:
                continue

            caps = dev.capabilities()

            axes = len(caps.get(evdev.ecodes.EV_ABS, []))
            buttons = len(caps.get(evdev.ecodes.EV_KEY, []))

            if axes >= axis_count and buttons >= button_count:
                matches.append(path)

        if not matches:
            return None

        return matches[min(index, len(matches) - 1)]


    @staticmethod
    def resolve_device_path(
        guid: str,
        index: int,
        real_name: str,
        axis_count: int,
        button_count: int,
        hat_count: int,
    ) -> str | None:
        if (path := Controller.find_device_path_sdl(guid, index)) is not None:
            return path

        return Controller.find_device_path_evdev(
            real_name,
            axis_count,
            button_count,
            hat_count,
            index,
        )

    def get_mapping_axis_relaxed_values(self) -> dict[str, _RelaxedDict]:
        import evdev

        # read the sdl2 cache if possible for axis
        cache_file = Path(_USER_HOME / ".sdl2" / f"{self.guid}_{self.name}.cache")
        if not cache_file.exists():
            return {}

        cache_content = cache_file.read_text(encoding="utf-8").splitlines()
        n = int(cache_content[0]) # number of lines of the cache

        relaxed_values: list[int] = [int(cache_content[i]) for i in range(1, n+1)]

        # get full list of axis (in case one is not used in es)

        caps = evdev.InputDevice(self.device_path).capabilities(absinfo=True)
        abs_caps = cast('list[tuple[int, object]]', caps.get(evdev.ecodes.EV_ABS, []))

        code_values: dict[int, int] = {}
        i = 0
        for code, _absinfo in abs_caps:
            if code < evdev.ecodes.ABS_HAT0X:
                code_values[code] = relaxed_values[i]
                i += 1

        # dict with es input names
        res: dict[str, _RelaxedDict] = {}
        for x, input in self.inputs.items():
            if input.type == "axis":
                # sdl values : from -32000 to 32000 / do not put < 0 cause a wheel/pad could be not correctly centered
                # 3 possible initial positions <1----------------|-------2-------|----------------3>
                if (val := code_values.get(int(cast('str', input.code)))) is not None:
                    res[x] = { "centered":  val > -4000 and val < 4000, "reversed": val > 4000 }
                else:
                    res[x] = { "centered":  True, "reversed": False }
        return res

    # Create a controller array with the player id as a key
    @classmethod
    def load_for_players(cls, max_players: int, args: Namespace, /) -> ControllerList:
        cfg_roots = []
        for conffile in (ES_INPUT_CFG, FRONTEND_DIR / 'es_input.cfg'):
            es_input_exists = conffile.exists()
            print(f"[DEBUG] buscando es_input.cfg en: {conffile} → {es_input_exists}")
            if es_input_exists:
                cfg_roots.append(ET.parse(conffile).getroot())

        return [
            controller
            for player_number in range(1, max_players + 1)
            if (controller := cls._find_best_controller(cfg_roots, args, player_number)) is not None
        ]

    @classmethod
    def _find_best_controller(
        cls, roots: Iterable[ET.Element], args: Namespace, player_number: int, /,
    ) -> Controller | None:
        index: int | None = getattr(args, f'p{player_number}index')
        if index is None:
            return None

        guid: str = getattr(args, f'p{player_number}guid')
        real_name: str = getattr(args, f'p{player_number}name')

        input_config = _find_input_config(roots, real_name, guid)

        print(f"[DEBUG] player{player_number}: buscando guid={guid} name={real_name}")
        print(f"[DEBUG] player{player_number}: encontrado deviceName={input_config.get('deviceName')} guid={input_config.get('deviceGUID')}")


        device_path_calc = getattr(args, f'p{player_number}devicepath', None)
        button_count_calc = getattr(args, f'p{player_number}nbbuttons')
        hat_count_calc = getattr(args, f'p{player_number}nbhats')
        axis_count_calc = getattr(args, f'p{player_number}nbaxes')
        _logger.warning("resolve_device_path player=%s → %s", player_number, device_path_calc)

        if not device_path_calc:
            device_path_calc = cls.resolve_device_path(
                guid,
                index,
                real_name,
                axis_count_calc,
                button_count_calc,
                hat_count_calc,
            )

        if device_path_calc is None:
            raise ValueError(
                f"No se pudo resolver device_path para player{player_number} "
                f"(guid={guid}, name={real_name})"
            )
            
        return cls(
            name=cast('str', input_config.get("deviceName")),
            type=cast('Literal["keyboard", "joystick"]', input_config.get("type")),
            guid=guid,
            inputs_=Input.from_parent_element(input_config),
            player_number=player_number,
            index=index,
            real_name=real_name,
            device_path=device_path_calc,
            button_count=button_count_calc,
            hat_count=hat_count_calc,
            axis_count=axis_count_calc,
        )

    @staticmethod
    def find_player_number(controllers: Controllers, player_number: int, /) -> Controller | None:
        for controller in controllers:
            if controller.player_number == player_number:
                return controller

        return None

    def has_motion_controls(self) -> bool:
        """
        Comprueba si el mando identificado por su GUID SDL tiene soporte de
        controles de movimiento (acelerómetro y/o giroscopio).

        Arguments:
        guid: (str) GUID SDL del mando (formato hexadecimal de 32 caracteres).
        Returns:
        (bool) True si el mando expone acelerómetro o giroscopio, False en
        cualquier otro caso (no encontrado, sin soporte, error de SDL, etc).
        """
        try:
            import sdl2
        except ImportError:
            return False

        guid_normalized = normalize_sdl_guid_for_emulator(self.guid)

        try:
            if sdl2.SDL_WasInit(sdl2.SDL_INIT_GAMECONTROLLER) == 0:
                sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER | sdl2.SDL_INIT_SENSOR)

            import ctypes

            for i in range(sdl2.SDL_NumJoysticks()):
                sdl_guid = sdl2.SDL_JoystickGetDeviceGUID(i)

                buf = ctypes.create_string_buffer(33)  # 32 chars + null
                sdl2.SDL_JoystickGetGUIDString(sdl_guid, buf, 33)

                guid_str = normalize_sdl_guid_for_emulator(buf.value.decode().lower())

                if guid_str != guid_normalized:
                    continue

                if not sdl2.SDL_IsGameController(i):
                    return False

                controller = sdl2.SDL_GameControllerOpen(i)
                if not controller:
                    return False

                try:
                    accel = bool(sdl2.SDL_GameControllerHasSensor(controller, sdl2.SDL_SENSOR_ACCEL))
                    gyro = bool(sdl2.SDL_GameControllerHasSensor(controller, sdl2.SDL_SENSOR_GYRO))
                    return accel or gyro
                finally:
                    sdl2.SDL_GameControllerClose(controller)

        except Exception:
            return False

        return False

def generate_sdl_game_controller_config(controllers: Controllers, /, ignore_buttons: list[str] | None = None) -> str:
    return "\n".join(controller.generate_sdl_game_db_line(ignore_buttons = ignore_buttons) for controller in controllers)

def write_sdl_controller_db(
    controllers: Controllers, outputFile: str | Path = RUNTIME_DIR / "gamecontrollerdb.txt", /,
) -> Path:
    outputFile = Path(outputFile)

    with outputFile.open("w") as text_file:
        text_file.write(generate_sdl_game_controller_config(controllers))

    return outputFile

type Controllers = Sequence[Controller]
type ControllerList = list[Controller]
