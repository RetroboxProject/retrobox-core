"""Pick the discrete GPU for the emulators that run on Vulkan."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import vulkan

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)


def discrete_gpu_property(
    emulator: str, label: str, get_property: Callable[[], str | None]
) -> str | None:
    """Return a property of the discrete GPU (its name, UUID or index), if there is one.

    Args:
        emulator: The emulator the property is for, for the log.
        label: What the property is ("Name", "UUID", "Index"), for the log.
        get_property: Reads the property from the system.

    Returns:
        The property, or None when the system has no discrete GPU or it cannot be read.
    """
    if not vulkan.has_discrete_gpu():
        _logger.debug("Discrete GPU is not available on the system. Using default.")
        return None

    _logger.debug("A discrete GPU is available on the system. We will use that for performance")
    if value := get_property():
        _logger.debug("Using Discrete GPU %s: %s for %s", label, value, emulator)
        return value

    _logger.debug("Couldn't get discrete GPU %s", label)
    return None
