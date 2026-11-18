"""Typed dictionaries shared by the generators and the launcher."""

# the keys follow Batocera's configgen
# pylint: disable=invalid-name

from __future__ import annotations

from collections.abc import Mapping
from typing import NotRequired, TypedDict


class Resolution(TypedDict):
    """A screen or game resolution, in pixels."""

    width: int
    height: int


class ScreenInfo(TypedDict):
    """Size and position of a screen."""

    width: int
    height: int
    x: int
    y: int


class DeviceInfo(TypedDict):
    """An input device as found by controllersConfig."""

    eventId: int
    sysfs_path: str
    isJoystick: bool
    isWheel: bool
    isMouse: bool
    associatedDevices: list[str] | None
    joystick_index: int | None
    mouse_index: int | None
    wheel_rotation: NotRequired[int]


type DeviceInfoMapping = Mapping[str, DeviceInfo]
type DeviceInfoDict = dict[str, DeviceInfo]
