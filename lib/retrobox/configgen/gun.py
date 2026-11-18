"""Light gun compatibility shim.

Retrobox does not ship light gun support: the pre-calibration data, the help
overlays and the device detection were removed. The ``Gun`` / ``Guns`` types
and :func:`guns_need_crosses` stay only so the generator signatures keep
working; no gun is ever detected, so ``Guns`` is always empty.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass(slots=True, kw_only=True)
class Gun:
    """A light gun. Kept for typing only: instances are never created."""

    node: str
    mouse_index: int
    needs_cross: bool
    needs_borders: bool
    name: str
    buttons: list[str]
    button_map: Mapping[str, int] = field(default_factory=dict)


GunList = list[Gun]
Guns = Sequence[Gun]


def guns_need_crosses(guns: Guns) -> bool:
    """Whether a crosshair must be drawn (always, as there is no gun)."""
    # no gun, enable the cross for joysticks, mouses...
    if not guns:
        return True

    return any(gun.needs_cross for gun in guns)
