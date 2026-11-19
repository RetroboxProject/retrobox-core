"""Every setting a user can change, described as data: retrobox.ini's,
and retrobox-overlay's overlay.ini (its page shows only where the overlay
is installed, see Page.requires).

The UI builds itself from PAGES (one page per entry, groups of settings
inside, each page's settings in one file), and the model reads and writes
the values this describes; nothing here knows about Qt or files. Labels and
help texts are not here either: the UI looks them up by the ids below
(``<section>.<key>``, ``page.<id>``, ``group.<id>``, ``choice.<value>``).

Values are always the strings written in the ini: ``true``/``false`` for
booleans, a comma-separated list for SYSTEMS, ``:``-separated paths for
DIRECTORY_LIST, a number for INTEGER and DECIMAL, ``RRGGBBAA`` for COLOR.
An empty value means "not set": the setting then takes the value of the
system-wide configuration, or its built-in default.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Final


class Kind(enum.Enum):
    """How a setting is edited."""

    BOOL = enum.auto()  # on / off
    CHOICE = enum.auto()  # one of Setting.choices
    DIRECTORY = enum.auto()  # one folder
    DIRECTORY_LIST = enum.auto()  # several folders, ":"-separated
    SYSTEMS = enum.auto()  # a subset of the systems, comma-separated
    INTEGER = enum.auto()  # a whole number, in Setting.limits
    DECIMAL = enum.auto()  # a number with decimals, in Setting.limits
    TEXT = enum.auto()  # free text (a format, a name)
    COLOR = enum.auto()  # RRGGBBAA


class Missing(enum.Enum):
    """What Retrobox does with a configured folder that doesn't exist."""

    CREATED = enum.auto()  # it creates it
    DEFAULT = enum.auto()  # it uses the default folder instead
    AUTOCORRECT = enum.auto()  # DEFAULT or used as written ([core] autocorrect_paths)


@dataclass(frozen=True, slots=True)
class Limits:
    """The range of a number: its ends, the step of its arrows, and the unit
    shown after it (``ms``, ``%``)."""

    minimum: float
    maximum: float
    step: float = 1.0
    unit: str = ""

    @property
    def decimals(self) -> int:
        """How many decimals the step has (0.05: 2)."""
        text = f"{self.step:g}"
        return len(text.split(".")[1]) if "." in text else 0


@dataclass(frozen=True, slots=True)
class Setting:
    """One key of retrobox.ini."""

    section: str
    key: str
    kind: Kind
    default: str = ""  # built-in default, as written in the ini ("": see store)
    choices: tuple[str, ...] = ()
    missing: Missing | None = None  # DIRECTORY only
    limits: Limits | None = None  # INTEGER and DECIMAL only

    @property
    def id(self) -> str:  # pylint: disable=invalid-name
        """``<section>.<key>``, also the id of its texts."""
        return f"{self.section}.{self.key}"


@dataclass(frozen=True, slots=True)
class Group:
    """Settings shown together, under a title."""

    id: str  # pylint: disable=invalid-name
    settings: tuple[Setting, ...] = ()
    custom_environ: bool = False  # the free [environ] variables table


@dataclass(frozen=True, slots=True)
class Page:
    """One entry of the navigation."""

    id: str  # pylint: disable=invalid-name
    icon: str  # freedesktop icon name
    groups: tuple[Group, ...]
    ini: str = "retrobox.ini"  # the file of its settings, in the configuration directories
    requires: str = ""  # a program without which the page is not shown


SYNC_MODES: Final = ("none", "on-base-dir", "follow-roms-dir")
SIDES: Final = ("right", "left")
TRUE: Final = "true"
FALSE: Final = "false"
OVERLAY_INI: Final = "overlay.ini"


def _sync(key: str) -> Setting:
    return Setting("core", key, Kind.CHOICE, default="none", choices=SYNC_MODES)


def _content_dir(key: str) -> Setting:
    """A [paths] folder that may be moved on its own (roms, saves, bios)."""
    return Setting("paths", key, Kind.DIRECTORY, missing=Missing.AUTOCORRECT)


def _integer(section: str, key: str, default: str, limits: Limits) -> Setting:
    return Setting(section, key, Kind.INTEGER, default=default, limits=limits)


def _decimal(section: str, key: str, default: str, limits: Limits) -> Setting:
    return Setting(section, key, Kind.DECIMAL, default=default, limits=limits)


def _environ_dir(key: str) -> Setting:
    """A folder moved through an [environ] variable."""
    return Setting("environ", key, Kind.DIRECTORY, missing=Missing.DEFAULT)


PAGES: Final[tuple[Page, ...]] = (
    Page(
        "general",
        "preferences-system",
        (
            Group(
                "frontend",
                (
                    Setting("core", "ignore_systems", Kind.SYSTEMS),
                    Setting("core", "full_quit_menu", Kind.BOOL, default=FALSE),
                ),
            ),
            Group(
                "behaviour",
                (Setting("core", "autocorrect_paths", Kind.BOOL, default=TRUE),),
            ),
        ),
    ),
    Page(
        "folders",
        "folder",
        (
            Group(
                "main_folders",
                (
                    Setting("paths", "data_dir", Kind.DIRECTORY, missing=Missing.CREATED),
                    Setting("paths", "state_dir", Kind.DIRECTORY, missing=Missing.CREATED),
                ),
            ),
            Group(
                "content_folders",
                (_content_dir("roms_dir"), _content_dir("saves_dir"), _content_dir("bios_dir")),
            ),
            Group(
                "media_folders",
                (
                    _environ_dir("SCREENSHOTS_DIR"),
                    _environ_dir("RECORDINGS_DIR"),
                    _environ_dir("BEZELS_DIR"),
                    _environ_dir("BEZELS_DEFAULT_DIR"),
                    _environ_dir("SHADERS_DIR"),
                    _environ_dir("CHEATS_DIR"),
                    _environ_dir("OVERLAYS_DIR"),
                ),
            ),
        ),
    ),
    Page(
        "pcgames",
        "applications-games",
        (
            Group(
                "pcgames_sync",
                (_sync("steam_sync"), _sync("heroic_sync"), _sync("lutris_sync")),
            ),
            Group(
                "steam",
                (Setting("environ", "STEAM_LIBRARY_DIR", Kind.DIRECTORY_LIST),),
            ),
        ),
    ),
    Page(
        "overlay",
        "input-gaming",
        (
            Group(
                "overlay_menu",
                (
                    Setting("overlay", "side", Kind.CHOICE, default="right", choices=SIDES),
                    _decimal("overlay", "dim", "0.75", Limits(0, 1, 0.05)),
                    _integer("overlay", "animation_ms", "150", Limits(0, 1000, 10, "ms")),
                    Setting("overlay", "icons", Kind.BOOL, default=TRUE),
                    Setting(
                        "overlay", "take_keyboard", Kind.CHOICE, default="auto",
                        choices=("auto", "yes", "no"),
                    ),
                    _decimal("touch", "row_scale", "1", Limits(1, 2, 0.05)),
                ),
            ),
            Group(
                "overlay_clock",
                (
                    Setting("clock", "enabled", Kind.BOOL, default=TRUE),
                    Setting("clock", "size", Kind.CHOICE, default="big", choices=("big", "small")),
                    Setting(
                        "clock", "position", Kind.CHOICE, default="top",
                        choices=("top", "center", "bottom"),
                    ),
                    Setting("clock", "color", Kind.COLOR, default="FFFFFFFF"),
                    Setting("clock", "time_format", Kind.TEXT),
                    Setting("clock", "date_format", Kind.TEXT),
                    Setting("clock", "small_format", Kind.TEXT),
                ),
            ),
            Group(
                "overlay_status",
                (
                    Setting("status", "battery_percent", Kind.BOOL, default=TRUE),
                    Setting("system", "standby", Kind.BOOL, default=TRUE),
                    Setting("system", "performance", Kind.BOOL, default=TRUE),
                ),
            ),
            Group(
                "overlay_sounds",
                (_integer("sounds", "volume", "50", Limits(0, 100, 5, "%")),),
            ),
            Group(
                "overlay_break",
                (
                    _integer("break", "after_min", "120", Limits(0, 720, 15, "min")),
                    _integer("break", "every_min", "30", Limits(0, 240, 5, "min")),
                ),
            ),
            Group(
                "overlay_osk",
                tuple(
                    Setting("osk", key, Kind.TEXT)
                    for key in ("layout", "variant", "model", "options")
                ),
            ),
            Group(
                "overlay_manual",
                (
                    Setting(
                        "manual", "scaling", Kind.CHOICE, default="compositor",
                        choices=("compositor", "overlay"),
                    ),
                ),
            ),
        ),
        ini=OVERLAY_INI,
        requires="retrobox-overlay",
    ),
    Page(
        "advanced",
        "preferences-other",
        (
            Group("environ", custom_environ=True),
        ),
    ),
)


def all_settings() -> tuple[Setting, ...]:
    """Every setting of PAGES, in display order."""
    return tuple(setting for page in PAGES for group in page.groups for setting in group.settings)


def known_environ() -> frozenset[str]:
    """The [environ] variables that have their own setting (not in the free table)."""
    return frozenset(
        setting.key
        for page in PAGES
        if page.ini == "retrobox.ini"
        for group in page.groups
        for setting in group.settings
        if setting.section == "environ"
    )


def ini_files() -> tuple[str, ...]:
    """The files the pages edit, retrobox.ini first."""
    return tuple(dict.fromkeys(page.ini for page in PAGES))


def setting_by_id(setting_id: str) -> Setting:
    """The setting ``<section>.<key>``.

    Raises:
        KeyError: If there is none.
    """
    for setting in all_settings():
        if setting.id == setting_id:
            return setting
    raise KeyError(setting_id)
