"""Every setting of retrobox.ini a user can change, described as data.

The UI builds itself from PAGES (one page per entry, groups of settings
inside), and the model reads and writes the values this describes; nothing
here knows about Qt or files. Labels and help texts are not here either: the
UI looks them up by the ids below (``<section>.<key>``, ``page.<id>``,
``group.<id>``, ``choice.<value>``).

Values are always the strings written in the ini: ``true``/``false`` for
booleans, a comma-separated list for SYSTEMS, ``:``-separated paths for
DIRECTORY_LIST. An empty value means "not set": the setting then takes the
value of the system-wide configuration, or its built-in default.
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


class Missing(enum.Enum):
    """What Retrobox does with a configured folder that doesn't exist."""

    CREATED = enum.auto()  # it creates it
    DEFAULT = enum.auto()  # it uses the default folder instead
    AUTOCORRECT = enum.auto()  # DEFAULT or used as written ([core] autocorrect_paths)


@dataclass(frozen=True, slots=True)
class Setting:
    """One key of retrobox.ini."""

    section: str
    key: str
    kind: Kind
    default: str = ""  # built-in default, as written in the ini ("": see store)
    choices: tuple[str, ...] = ()
    missing: Missing | None = None  # DIRECTORY only

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


SYNC_MODES: Final = ("none", "on-base-dir", "follow-roms-dir")
TRUE: Final = "true"
FALSE: Final = "false"


def _sync(key: str) -> Setting:
    return Setting("core", key, Kind.CHOICE, default="none", choices=SYNC_MODES)


def _content_dir(key: str) -> Setting:
    """A [paths] folder that may be moved on its own (roms, saves, bios)."""
    return Setting("paths", key, Kind.DIRECTORY, missing=Missing.AUTOCORRECT)


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
                (Setting("core", "ignore_systems", Kind.SYSTEMS),),
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
    return frozenset(s.key for s in all_settings() if s.section == "environ")


def setting_by_id(setting_id: str) -> Setting:
    """The setting ``<section>.<key>``.

    Raises:
        KeyError: If there is none.
    """
    for setting in all_settings():
        if setting.id == setting_id:
            return setting
    raise KeyError(setting_id)
