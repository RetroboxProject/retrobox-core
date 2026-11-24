"""Which video driver RetroArch gets: vulkan, glcore or gl.

One rule, whichever driver the game starts with: the drivers form the chain
``vulkan > glcore > gl`` and the cascade only ever goes *down* it, from the
starting point to the end.

* start ``vulkan``: vulkan is checked, then glcore, and gl is the last resort;
* start ``glcore``: vulkan is never looked at; glcore is checked, then gl;
* start ``gl``: nothing is checked at all.

``gl`` is the end of the chain, so it is never probed: it is what is left.
The starting point is the driver chosen for the game (``gfxbackend``) or,
when it is "Default", the best one for its core.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Final, Protocol

from retrobox.configgen.utils import opengl, vulkan

_logger: Final = logging.getLogger(__name__)

VULKAN: Final = "vulkan"
GLCORE: Final = "glcore"
GL: Final = "gl"

# best first
BACKEND_ORDER: Final = (VULKAN, GLCORE, GL)
GL_BACKENDS: Final = (GLCORE, GL)
AUTO: Final = "auto"

_ALIASES: Final[Mapping[str, str]] = {
    "opengl": GL,
    "opengl_legacy": GL,
    "opengl legacy": GL,
    "opengl core": GLCORE,
    "opengl_core": GLCORE,
    "gl_core": GLCORE,
    "gl core": GLCORE,
    "vk": VULKAN,
}

# RetroArch's glcore needs a 3.2 core profile
MIN_GLCORE_VERSION: Final = (3, 2)

# cores whose hardware renderer needs an OpenGL context: with "Default" they
# start the cascade at glcore / gl instead of vulkan
FORCE_GLCORE_CORES: Final = ("kronos", "mupen64plus_next", "melonds", "beetle-psx-hw")
FORCE_GL_CORES: Final = ("parallel_n64", "yabasanshiro")


class _Config(Protocol):  # pylint: disable=too-few-public-methods
    """The part of a game's configuration the driver choice reads."""

    def get_str(self, key: str, default: str, /) -> str:
        """The string stored under ``key``, ``default`` when it is not set."""


def normalize(value: object) -> str | None:
    """The driver a ``gfxbackend`` value stands for, None for "Default" or garbage."""
    text = str(value or "").strip().lower()
    text = _ALIASES.get(text, text)
    if not text or text == AUTO:
        return None
    if text not in BACKEND_ORDER:
        _logger.warning("unknown video driver %r, choosing one automatically", value)
        return None
    return text


def start_backend(config: _Config) -> str:
    """Where the cascade starts: the driver chosen, else the best one of the core.

    retroarch.cfg is not looked at: its video_driver is written by the
    generator on every launch, so it would only echo the previous choice.
    """
    chosen = normalize(config.get_str("gfxbackend", ""))
    if chosen is not None:
        return chosen
    core = config.get_str("core", "")
    if core in FORCE_GL_CORES:
        return GL
    if core in FORCE_GLCORE_CORES:
        return GLCORE
    return BACKEND_ORDER[0]


def cascade(start: str) -> tuple[str, ...]:
    """``start`` and every driver below it, in order."""
    return BACKEND_ORDER[BACKEND_ORDER.index(start):]


def _vulkan_usable() -> tuple[bool, str]:
    if vulkan.is_available():
        return True, "vulkaninfo lists a device"
    return False, "vulkaninfo lists no device"


def _glcore_usable() -> tuple[bool, str]:
    status, reason = opengl.core_profile_status(MIN_GLCORE_VERSION)
    if status is None:
        # No glxinfo/eglinfo, or no display for them: nothing says glcore does
        # not work, and every GPU of the last decade does it. Assuming gl here
        # is what used to give the legacy driver on setups without glxinfo.
        return True, f"{reason}; assuming it is available"
    return status, reason


_CHECKS: Final[Mapping[str, Callable[[], tuple[bool, str]]]] = {
    VULKAN: _vulkan_usable,
    GLCORE: _glcore_usable,
}


def resolve(
    start: str,
    checks: Mapping[str, Callable[[], tuple[bool, str]]] | None = None,
) -> str:
    """Walk the cascade from ``start`` and return the first usable driver.

    The last driver of the chain (gl) is not checked: it is the fallback.
    """
    checks = _CHECKS if checks is None else checks
    chain = cascade(start)
    for backend in chain[:-1]:
        usable, reason = checks[backend]()
        if usable:
            if backend != start:
                _logger.info("video driver %s not available, using %s", start, backend)
            return backend
        _logger.info("video driver %s not usable: %s", backend, reason)
    return chain[-1]


def get_backend(config: _Config) -> str:
    """The video driver for the game described by ``config``."""
    start = start_backend(config)
    backend = resolve(start)
    _logger.debug("video driver: %s (started at %s)", backend, start)
    return backend


def uses_opengl(config: _Config) -> bool:
    """Whether the driver that will really be used is an OpenGL one."""
    return get_backend(config) in GL_BACKENDS
