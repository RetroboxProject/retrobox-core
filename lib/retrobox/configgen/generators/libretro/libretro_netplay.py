"""RetroArch netplay: the settings and the command line of a hosted or joined room.

EmulationStation asks for netplay through the ``-netplay*`` arguments of the
launcher (see ``FileData::launchGame`` there). ``Emulator`` stores them in the
system configuration as:

=========================== ==================================================
``netplay.mode``            ``host``, ``client`` or ``spectator``
``netplay.server.ip``       address to connect to (a relay, if there is a session)
``netplay.server.port``     port to connect to
``netplay.server.session``  relay (MITM) session of the room
``netplay.password``        password of the room
=========================== ==================================================

The rest comes from the "NETPLAY SETTINGS" menu of EmulationStation
(``global.netplay.*`` in its settings): ``netplay.nickname``, ``netplay.port``
(port to host on), ``netplay.relay`` (``nyc``, ``madrid``, ``montreal``,
``saopaulo``, a community server or ``custom``) and ``netplay.customserver``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from retrobox.configgen.config import Config

_logger = logging.getLogger(__name__)

DEFAULT_PORT: Final = "55435"
DEFAULT_NICKNAME: Final = "Retrobox Player"

_HOST: Final = "host"
_SPECTATOR: Final = "spectator"
_MODES: Final = (_HOST, "client", _SPECTATOR)
# value of netplay_mitm_server for a relay that is not one of RetroArch's own
_CUSTOM_RELAY: Final = "custom"

# The netplay settings of retroarch.cfg. They are all written on every launch,
# so a room joined as a spectator does not leak into the next hosted one.
_NETPLAY_DEFAULTS: Final = {
    "netplay_start_as_spectator": "false",
    "netplay_use_mitm_server": "false",
    "netplay_public_announce": "false",
    "netplay_mitm_server": "",
    "netplay_custom_mitm_server": "",
    "netplay_ip_address": "",
    "netplay_password": "",
    "netplay_spectate_password": "",
}


@dataclass(frozen=True)
class NetplayRequest:  # pylint: disable=too-many-instance-attributes
    """What EmulationStation asked for, with the defaults applied."""

    mode: str
    nickname: str
    port: str
    address: str = ""
    session: str = ""
    password: str = ""
    relay: str = ""
    custom_relay: str = ""

    @property
    def is_host(self) -> bool:
        """Whether this game hosts the room (otherwise it joins one)."""
        return self.mode == _HOST

    @property
    def is_spectator(self) -> bool:
        """Whether this game only watches the room."""
        return self.mode == _SPECTATOR


def from_config(config: Config) -> NetplayRequest | None:
    """Read the netplay request of a game.

    Args:
        config: The configuration of the game.

    Returns:
        The request, or None if the game does not use netplay (or the request
        is invalid, which is logged).
    """
    mode = config.get_str("netplay.mode", "").strip().lower()
    if not mode:
        return None
    if mode not in _MODES:
        _logger.warning("unknown netplay mode '%s', netplay is disabled", mode)
        return None

    nickname = config.get_str("netplay.nickname", "").strip() or DEFAULT_NICKNAME
    if mode == _HOST:
        port = config.get_str("netplay.port", "").strip() or DEFAULT_PORT
        return NetplayRequest(
            mode=mode,
            nickname=nickname,
            port=port,
            password=config.get_str("netplay.password", ""),
            relay=config.get_str("netplay.relay", "").strip(),
            custom_relay=config.get_str("netplay.customserver", "").strip(),
        )

    address = config.get_str("netplay.server.ip", "").strip()
    if not address:
        _logger.warning("netplay mode '%s' without a server address, netplay is disabled", mode)
        return None
    return NetplayRequest(
        mode=mode,
        nickname=nickname,
        port=config.get_str("netplay.server.port", "").strip() or DEFAULT_PORT,
        address=address,
        session=config.get_str("netplay.server.session", "").strip(),
        password=config.get_str("netplay.password", ""),
    )


def settings(request: NetplayRequest) -> dict[str, str]:
    """The retroarch.cfg settings that the request needs.

    Args:
        request: The netplay request of the game.

    Returns:
        The settings. They are always the same keys, see ``_NETPLAY_DEFAULTS``.
    """
    config = {
        **_NETPLAY_DEFAULTS,
        # hardcore mode disables the savestates, which netplay is built on
        "cheevos_hardcore_mode_enable": "false",
        "netplay_nickname": request.nickname,
        "netplay_ip_port": request.port,
    }

    if request.is_host:
        config["netplay_password"] = request.password
        # announce the room in the public lobby (the one EmulationStation lists)
        config["netplay_public_announce"] = "true"
        if request.relay:
            config["netplay_use_mitm_server"] = "true"
            if request.relay == _CUSTOM_RELAY:
                config["netplay_mitm_server"] = _CUSTOM_RELAY
                config["netplay_custom_mitm_server"] = request.custom_relay
            else:
                config["netplay_mitm_server"] = request.relay
        return config

    config["netplay_ip_address"] = request.address
    # the client sends one of the two, the room checks it against its own
    config["netplay_password"] = request.password
    if request.is_spectator:
        config["netplay_start_as_spectator"] = "true"
        config["netplay_spectate_password"] = request.password
    return config


def command_arguments(request: NetplayRequest) -> list[str]:
    """The RetroArch arguments that host or join the room.

    Args:
        request: The netplay request of the game.

    Returns:
        The arguments, to be placed before the content to load.
    """
    if request.is_host:
        return ["--host", "--port", request.port, "--nick", request.nickname]

    arguments = ["--connect", request.address, "--port", request.port, "--nick", request.nickname]
    if request.session:
        arguments.extend(["--mitm-session", request.session])
    return arguments
