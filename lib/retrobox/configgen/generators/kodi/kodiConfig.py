"""Kodi's controller configuration and the lookup of the Kodi to start.

Kodi reads the controllers through its ``peripheral.joystick`` add-on, which
keeps one button map (XML) per device in the userdata folder. The button maps
written here follow EmulationStation's layout, so the pads behave in Kodi's
menus as they do in EmulationStation.

Kodi matches a button map to a pad by provider, kernel device name and counts.
Its udev driver files the maps under the "linux" provider (the folder Kodi
itself writes to and ships its own maps in), and names the pad as the kernel
does, which is not always SDL's name: a PDP pad driven by xone is
"Microsoft Xbox Controller" for Kodi but "PDP Xbox One Arctic White" for SDL.
"""

# The module name is the one the generator importer uses.
# pylint: disable=invalid-name

from __future__ import annotations

import hashlib
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING, Final

from retrobox.configgen.exceptions import RetroboxException
from retrobox.paths import (
    _USER_HOME,
    ES_SETTINGS_CFG,
    RETROBOX_ROOTDIR,
    ensure_parents_and_open,
    mkdir_if_not_exists,
)
from retrobox.utils.es_settings import confirm_is_east, read_es_settings

if TYPE_CHECKING:
    from ...controller import Controller, Controllers

# What ``retrobox-kodi --which`` prints, and where each Kodi keeps its userdata.
_KODI_USERDATA: Final = {
    "native": _USER_HOME / ".kodi" / "userdata",
    "flatpak": _USER_HOME / ".var" / "app" / "tv.kodi.Kodi" / "data" / "userdata",
}

KODI_LAUNCHER: Final = RETROBOX_ROOTDIR / "bin" / "retrobox-kodi"

# The provider Kodi's udev driver files its button maps under, and the one
# older versions of this module wrote to (Kodi ignores it).
_PROVIDER: Final = "linux"
_STALE_PROVIDER: Final = "udev"

# EmulationStation's analog triggers: Kodi needs to know they rest at -1.
_TRIGGERS: Final = ("l2", "r2")

_SYSFS_INPUT: Final = Path("/sys/class/input")

# The hat values of es_input.cfg (SDL's) and the direction they mean.
_HAT_DIRECTIONS: Final = {1: "up", 2: "right", 4: "down", 8: "left"}

# EmulationStation's names (SNES layout) -> the features of Kodi's default
# controller (Xbox layout), by position: ES "b" is the south button, Kodi's "a".
# "hotkey" is left out on purpose: in Retrobox it is a modifier (gamepadly reads
# it), and Kodi's "guide" would jump to its home screen.
_FEATURES: Final = {
    "a": "b", "b": "a", "x": "y", "y": "x",
    "select": "back", "start": "start",
    "pageup": "leftbumper", "pagedown": "rightbumper",
    "l2": "lefttrigger", "r2": "righttrigger",
    "l3": "leftthumb", "r3": "rightthumb",
    "up": "up", "down": "down", "left": "left", "right": "right",
}

# EmulationStation's stick axes -> (Kodi's stick, direction). EmulationStation
# only names the "up" and "left" ones; the opposite direction is derived.
_STICKS: Final = {
    "joystick1up": ("leftstick", "up"),
    "joystick1left": ("leftstick", "left"),
    "joystick2up": ("rightstick", "up"),
    "joystick2left": ("rightstick", "left"),
}
_OPPOSITE_DIRECTIONS: Final = {"up": "down", "down": "up", "left": "right", "right": "left"}


def kodi_install() -> str:
    """Tell which Kodi retrobox-kodi starts.

    Returns:
        "flatpak" or "native".

    Raises:
        RetroboxException: if there is no Kodi, or retrobox-kodi cannot run.
    """
    try:
        result = subprocess.run(
            [str(KODI_LAUNCHER), "--which"], capture_output=True, text=True, check=False
        )
    except OSError as err:
        raise RetroboxException(f"Cannot run {KODI_LAUNCHER}: {err}") from err
    kind = result.stdout.strip()
    if result.returncode != 0 or kind not in _KODI_USERDATA:
        raise RetroboxException(
            "Kodi not found (neither the tv.kodi.Kodi Flatpak nor a native kodi)"
        )
    return kind


def kodi_userdata() -> Path:
    """Return the userdata folder of the Kodi retrobox-kodi starts."""
    return _KODI_USERDATA[kodi_install()]


def _vid_pid(guid: str) -> tuple[str, str]:
    """Vendor and product ids of an SDL GUID, as Kodi's udev provider writes them."""
    return guid[10:12] + guid[8:10], guid[18:20] + guid[16:18]


def _kernel_name(controller: Controller) -> str:
    """The pad's name as the kernel (and so Kodi) gives it; SDL's as a fallback."""
    for device_path in (controller.physical_device_path, controller.device_path):
        if not device_path:
            continue
        name_file = _SYSFS_INPUT / os.path.basename(device_path) / "device" / "name"
        try:
            name = name_file.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if name:
            return name
    return controller.real_name


def _signed(axis_id: str, positive: bool) -> str:
    return f"{'+' if positive else '-'}{axis_id}"


def _stick_element(sticks: dict[str, ET.Element], name: str, direction: str, axis_id: str,
                   positive: bool) -> None:
    """Add to the Kodi stick ``name`` the element of a direction, creating the stick."""
    stick = sticks.get(name)
    if stick is None:
        stick = sticks[name] = ET.Element("feature", {"name": name})
    ET.SubElement(stick, direction, {"axis": _signed(axis_id, positive)})


def _add_stick_axis(sticks: dict[str, ET.Element], input_name: str, axis_id: str,
                    value: int) -> None:
    """Map one stick axis of EmulationStation, and the opposite direction."""
    stick, direction = _STICKS[input_name]
    # the axis moves towards the direction in the sense EmulationStation recorded
    # (its value) and towards the opposite one in the other sense
    _stick_element(sticks, stick, direction, axis_id, value >= 0)
    _stick_element(sticks, stick, _OPPOSITE_DIRECTIONS[direction], axis_id, value < 0)


def _hat_feature(controller: Controller, hat_id: int, hat_value: int) -> ET.Element:
    """A d-pad direction of a hat: Kodi sees each hat as two axes after the real ones."""
    direction = _HAT_DIRECTIONS[hat_value]
    horizontal = direction in ("left", "right")
    axis = controller.axis_count + 2 * hat_id + (0 if horizontal else 1)
    return ET.Element("feature", {
        "name": direction,
        "axis": _signed(str(axis), direction in ("down", "right")),
    })


def _controller_element(controller: Controller, features: dict[str, str]) -> ET.Element:
    """The ``controller`` element (the features) of a device's button map."""
    element = ET.Element("controller", {"id": "game.controller.default"})
    sticks: dict[str, ET.Element] = {}
    buttons_done: set[int] = set()

    for pad_input in controller.inputs.values():
        if pad_input.type == "axis" and pad_input.name in _STICKS:
            _add_stick_axis(sticks, pad_input.name, pad_input.id, int(pad_input.value))
        elif pad_input.name not in features:
            continue
        elif pad_input.type == "button":
            if int(pad_input.id) not in buttons_done:
                buttons_done.add(int(pad_input.id))
                element.append(ET.Element("feature", {
                    "name": features[pad_input.name], "button": str(int(pad_input.id)),
                }))
        elif pad_input.type == "hat" and int(pad_input.value) in _HAT_DIRECTIONS:
            element.append(_hat_feature(controller, int(pad_input.id), int(pad_input.value)))
        elif pad_input.type == "axis":
            element.append(ET.Element("feature", {
                "name": features[pad_input.name],
                "axis": _signed(pad_input.id, int(pad_input.value) >= 0),
            }))

    element.extend(sticks.values())
    return element


def _configuration_element(controller: Controller) -> ET.Element:
    """The ``configuration`` element: the analog triggers rest at -1, not at 0."""
    element = ET.Element("configuration")
    trigger_axes = sorted({
        int(pad_input.id) for pad_input in controller.inputs.values()
        if pad_input.name in _TRIGGERS and pad_input.type == "axis"
    })
    for axis in trigger_axes:
        ET.SubElement(element, "axis", {"index": str(axis), "center": "-1", "range": "2"})
    return element


def _device_element(controller: Controller, provider: str, features: dict[str, str]) -> ET.Element:
    """The ``device`` element of a controller's button map."""
    attributes = {"name": _kernel_name(controller), "provider": provider}
    if provider == "udev":
        attributes["vid"], attributes["pid"] = _vid_pid(controller.guid)
    attributes["buttoncount"] = str(controller.button_count)
    attributes["axiscount"] = str(2 * controller.hat_count + controller.axis_count)

    device = ET.Element("device", attributes)
    device.append(_configuration_element(controller))
    device.append(_controller_element(controller, features))
    return device


def write_kodi_configs(
    template: Path, controllers: Controllers, provider: str, confirm_east: bool = False
) -> None:
    """Write a button map for each of the controllers.

    Arguments:
        template: path of the files, with a ``{}`` in the name for the controller.
        controllers: the players' controllers.
        provider: the provider Kodi's peripheral.joystick reads them with.
        confirm_east: whether EmulationStation confirms with the east button.
    """
    features = dict(_FEATURES)
    if confirm_east:
        # Kodi's menus confirm with its "a": follow EmulationStation's button
        features["a"], features["b"] = "a", "b"

    done: set[str] = set()
    for controller in controllers:
        # one file per name: a pad is repeated when several are the same model
        name = _kernel_name(controller)
        if name in done:
            continue
        done.add(name)

        # the name hash is because 2 pads with a different name sometimes have the
        # same vid/pid; the "batocera_" prefix is kept so that the files of older
        # versions are overwritten, not duplicated
        digest = hashlib.md5(name.encode("utf-8")).hexdigest()
        path = template.with_name(template.name.format(f"{controller.guid}_{digest}"))

        root = ET.Element("buttonmap")
        root.append(_device_element(controller, provider, features))
        ET.indent(root)
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def write_kodi_config(controllers: Controllers, userdata: Path | None = None) -> None:
    """Write Kodi's controller configuration into its userdata folder.

    Arguments:
        controllers: the players' controllers.
        userdata: Kodi's userdata folder; by default the one of the Kodi that
            retrobox-kodi starts (the Flatpak first).
    """
    # if there is no controller, don't remove the current generated one:
    # it allows people to start kodi at startup when having only bluetooth joysticks
    # or this allows people to plug the last used joystick
    if not controllers:
        return
    if userdata is None:
        userdata = kodi_userdata()

    xml_dir = userdata / "addon_data" / "peripheral.joystick" / "resources" / "buttonmaps" / "xml"
    # the maps of older versions, in a folder Kodi does not read
    for stale in (xml_dir / _STALE_PROVIDER).glob("batocera_*.xml"):
        stale.unlink(missing_ok=True)

    buttonmaps = xml_dir / _PROVIDER / "batocera_{}.xml"
    mkdir_if_not_exists(buttonmaps.parent)
    write_kodi_configs(
        buttonmaps, controllers, _PROVIDER,
        confirm_east=confirm_is_east(read_es_settings(ES_SETTINGS_CFG)),
    )

    # force the udev plugin
    settings = userdata / "addon_data" / "peripheral.joystick" / "settings.xml"
    with ensure_parents_and_open(settings, "w") as file:
        file.write('<settings version="2"><setting id="driver_linux">1</setting></settings>')

    # disable the kodi splash by default (nicer integration)
    advanced = userdata / "advancedsettings.xml"
    if not advanced.exists():
        with ensure_parents_and_open(advanced, "w") as file:
            file.write("<advancedsettings><splash>false</splash></advancedsettings>")
