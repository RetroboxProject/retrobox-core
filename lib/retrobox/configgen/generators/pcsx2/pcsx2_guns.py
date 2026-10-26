"""Lightguns (GunCon 2) and the fog hack of Time Crisis - Crisis Zone."""

from __future__ import annotations

import logging
import shutil
from typing import TYPE_CHECKING

from .pcsx2_paths import _PCSX2_CFGDIR, _PCSX2_TEXTURES

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ...config import SystemConfig
    from ...controller import Controller, Controllers
    from ...gun import Guns
    from ...utils.configparser import CaseSensitiveConfigParser

_logger = logging.getLogger(__name__)

_USB_PORTS = ("USB1", "USB2")
_GUN_OPTIONS = ("guncon2_Start", "guncon2_C", "guncon2_numdevice")
_PEDAL_KEYS = {1: "c", 2: "v"}
# the crosshair color of each port: blue for the first gun, red for the second
_CROSSHAIR_COLORS = {"USB1": "#0000ff", "USB2": "#ff0000"}
_FOG_TEXTURE = "c321d53987f3986d-eadd4df7c9d76527-00005dd4.png"
_FOG_GAMES = ("SCES-52530", "SLUS-20927")


def _remove_guns_and_wheels(settings: CaseSensitiveConfigParser) -> None:
    """Remove what a previous game left in the USB ports: guns and wheels."""
    for port in _USB_PORTS:
        if not settings.has_section(port):
            continue
        port_type = settings.get(port, "Type", fallback=None)
        is_wheel = port_type == "Pad" and settings.get(port, "Pad_subtype", fallback=None) == "1"
        if port_type == "guncon2" or is_wheel:
            settings.remove_option(port, "Type")
        for option in _GUN_OPTIONS:
            settings.remove_option(port, option)


def _players_of_gun(
    controllers: Controllers, gun_number: int, *, only_gun_is_on_port2: bool
) -> list[Controller]:
    """Return the pads of the players that use a gun: the Start button of those is mapped."""
    if gun_number == 2 and only_gun_is_on_port2:
        return list(controllers)  # the only gun is player 1's, plugged into the second port
    return [pad for number, pad in enumerate(controllers, start=1) if number == gun_number]


def _plug_gun(
    settings: CaseSensitiveConfigParser,
    config: SystemConfig,
    port: str,
    gun_number: int,
    pads: list[Controller],
) -> None:
    """Plug a GunCon 2 into a USB port and map its Start button and its pedal."""
    if not settings.has_section(port):
        settings.add_section(port)
    settings.set(port, "Type", "guncon2")

    for pad in pads:
        if "start" in pad.inputs:
            settings.set(port, "guncon2_Start", f"SDL-{pad.index}/Start")

    # a keyboard key simulates the pedal of the player (always like button 2)
    pedal_key = config.get(f"controllers.pedals{gun_number}", _PEDAL_KEYS[gun_number])
    settings.set(port, "guncon2_C", f"Keyboard/{pedal_key.upper()}")


def configure_guns(
    settings: CaseSensitiveConfigParser,
    config: SystemConfig,
    controllers: Controllers,
    guns: Guns,
    metadata: Mapping[str, str],
) -> None:
    """Configure the GunCon 2 of the players and their crosshairs."""
    _remove_guns_and_wheels(settings)

    if config.use_guns and guns:
        only_gun_is_on_port2 = len(guns) == 1 and metadata.get("gun_gun1port") == "2"

        if not only_gun_is_on_port2:
            pads = _players_of_gun(controllers, 1, only_gun_is_on_port2=False)
            _plug_gun(settings, config, "USB1", 1, pads)

        if len(guns) >= 2 or only_gun_is_on_port2:
            pads = _players_of_gun(controllers, 2, only_gun_is_on_port2=only_gun_is_on_port2)
            _plug_gun(settings, config, "USB2", 2, pads)
            if only_gun_is_on_port2:
                settings.set("USB2", "guncon2_numdevice", "0")

    for port in _USB_PORTS:
        if not settings.has_section(port):
            continue
        if config.get("pcsx2_crosshairs") == "1":
            crosshair = _PCSX2_CFGDIR / "crosshairs" / "default.png"
            settings.set(port, "guncon2_cursor_path", str(crosshair))
            settings.set(port, "guncon2_cursor_color", _CROSSHAIR_COLORS[port])
        else:
            settings.set(port, "guncon2_cursor_path", "")


def configure_fog_hack(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Replace the fog textures of Time Crisis - Crisis Zone, for the guns, or remove them.

    The replacement texture is looked for in the textures folder of PCSX2 and,
    if it is somewhere else than where PCSX2 reads it, copied there. A game
    without the texture is skipped with a warning.
    """
    enabled = config.get_bool("pcsx2_crisis_fog")
    replaced = False
    for game in _FOG_GAMES:
        source = _PCSX2_CFGDIR / "textures" / game / "replacements" / _FOG_TEXTURE
        target = _PCSX2_TEXTURES / game / "replacements" / _FOG_TEXTURE
        if not enabled:
            if target.is_file():
                target.unlink()
            continue

        if not source.is_file():
            _logger.warning("Fog replacement texture not found: %s", source)
            continue
        if source != target:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        replaced = True

    if replaced:
        # texture replacements must be enabled for the fog fix to take effect
        settings.set("EmuCore/GS", "LoadTextureReplacements", "true")
