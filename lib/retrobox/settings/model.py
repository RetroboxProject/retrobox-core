"""The values of the settings, as the user sees and edits them.

retrobox.ini is layered (see retrobox.paths): the system-wide files
(/etc/retrobox/retrobox.ini and its retrobox.ini.d/*.ini), then the user's
~/.config/retrobox/retrobox.ini, then the user's own retrobox.ini.d/*.ini.
overlay.ini (retrobox-overlay's) is layered the same way, without drop-ins.
A model edits one file, the user's main one, so for each setting it knows:

* its *inherited* value: the system-wide one, or else its built-in default;
* its *user* value, if the user's file sets it;
* whether a user drop-in sets it too: then the drop-in wins and the setting
  is *locked* here (it must be changed in that file).

Changes are kept apart until apply() writes them all at once. Setting a value
equal to the inherited one removes it from the file instead: the file only
holds what differs from the defaults, as the rest of Retrobox expects.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Final

from retrobox.paths import CONFIG_DIR, DATA_DIR, SYSCONF_DIR
from retrobox.paths._base import (
    CaseSensitiveConfigParser,
    _ini_files,
    _load_layered_ini,
)

from .inifile import IniDocument
from .schema import OVERLAY_INI, Kind, Setting, known_environ

if TYPE_CHECKING:
    from collections.abc import Mapping

INI_NAME: Final = "retrobox.ini"
_ENV_NAME_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ENVIRON: Final = "environ"

# Built-in defaults that depend on the environment (the others are in the
# schema). Kept apart so the schema stays plain data.
_DEFAULT_SUBDIRS: Final[dict[str, str]] = {
    "paths.roms_dir": "roms",
    "paths.saves_dir": "saves",
    "paths.bios_dir": "bios",
    "environ.SCREENSHOTS_DIR": "screenshots",
    "environ.RECORDINGS_DIR": "recordings",
    "environ.BEZELS_DIR": "decorations",
    "environ.BEZELS_DEFAULT_DIR": "decorations-default",
    "environ.SHADERS_DIR": "shaders",
    "environ.CHEATS_DIR": "cheats",
    "environ.OVERLAYS_DIR": "overlay",
}


def _xdg(variable: str, fallback: str) -> Path:
    value = os.environ.get(variable, "").strip()
    return Path(value) if value and os.path.isabs(value) else Path.home() / fallback


def _clean(setting: Setting, value: str) -> str:
    """A value as Retrobox reads it: folders may be quoted and end in a
    " # comment" (see retrobox.paths._base._clean_path_value)."""
    value = value.strip()
    if setting.kind not in (Kind.DIRECTORY, Kind.DIRECTORY_LIST):
        return value
    if value[:1] in ("'", '"'):
        end = value.find(value[0], 1)
        return value[1:end].strip() if end != -1 else value
    for marker in (" #", "\t#", " ;", "\t;"):
        cut = value.find(marker)
        if cut != -1:
            value = value[:cut].rstrip()
    return value


def _same(setting: Setting, value: str, other: str) -> bool:
    """Whether two values of ``setting`` mean the same (``1`` and ``1.0``;
    ``ffffffff`` and ``FFFFFFFF``)."""
    if setting.kind in (Kind.INTEGER, Kind.DECIMAL):
        try:
            return float(value) == float(other)
        except ValueError:
            return value == other
    if setting.kind is Kind.COLOR:
        return value.upper() == other.upper()
    return value == other


def is_valid_environ_name(name: str) -> bool:
    """Whether ``name`` can be an environment variable."""
    return bool(_ENV_NAME_RE.match(name))


class SettingsModel:
    """Read, edit and save the user's settings (see the module docstring)."""

    def __init__(
        self,
        sysconf_dir: Path = SYSCONF_DIR,
        config_dir: Path = CONFIG_DIR,
        ini: str = INI_NAME,
    ) -> None:
        self.user_file = config_dir / ini
        dropins = ini != OVERLAY_INI
        self._system = _load_layered_ini(_ini_files(sysconf_dir, name=ini, dropins=dropins))
        self._document = IniDocument.read(self.user_file)
        self._dropins: list[tuple[Path, CaseSensitiveConfigParser]] = [
            (path, _load_layered_ini([path]))
            for path in _ini_files(config_dir, name=ini, dropins=dropins)
            if path != self.user_file
        ]
        self._changes: dict[tuple[str, str], str | None] = {}
        self._environ_changes: dict[str, str] | None = None

    # ------------------------------------------------------------- reading
    @staticmethod
    def _get(config: CaseSensitiveConfigParser, setting: Setting) -> str | None:
        key = setting.key.lower() if setting.section in ("core", "paths") else setting.key
        if not config.has_option(setting.section, key):
            return None
        return _clean(setting, config.get(setting.section, key))

    def builtin_default(self, setting: Setting) -> str:
        """The value Retrobox uses when no file sets ``setting``."""
        if setting.default:
            return setting.default
        if setting.id == "paths.data_dir":
            return str(_xdg("XDG_DATA_HOME", ".local/share") / "retrobox")
        if setting.id == "paths.state_dir":
            return str(_xdg("XDG_STATE_HOME", ".local/state") / "retrobox")
        if setting.id in _DEFAULT_SUBDIRS:
            return str(DATA_DIR / _DEFAULT_SUBDIRS[setting.id])
        return ""

    def inherited(self, setting: Setting) -> str:
        """The value when the user's file doesn't set ``setting``."""
        system = self._get(self._system, setting)
        return system if system else self.builtin_default(setting)


    def _dropin(self, setting: Setting) -> tuple[Path, str] | None:
        """The last user drop-in that sets ``setting``, with its value."""
        found = None
        for path, config in self._dropins:
            value = self._get(config, setting)
            if value is not None:
                found = (path, value)
        return found

    def locked_by(self, setting: Setting) -> Path | None:
        """The user drop-in that sets ``setting`` (so it can't be edited here)."""
        dropin = self._dropin(setting)
        return dropin[0] if dropin else None

    def user_value(self, setting: Setting) -> str | None:
        """What the user's file sets (with the pending changes), or None."""
        pending = (setting.section, setting.key)
        if pending in self._changes:
            return self._changes[pending]
        value = self._document.get(setting.section, setting.key)
        return _clean(setting, value) if value else None

    def value(self, setting: Setting) -> str:
        """The value in effect: a user drop-in's, the user's, or else inherited."""
        dropin = self._dropin(setting)
        if dropin is not None and dropin[1]:
            return dropin[1]
        user = self.user_value(setting)
        return user if user is not None else self.inherited(setting)

    def is_custom(self, setting: Setting) -> bool:
        """Whether the user's file sets ``setting`` (with the pending changes)."""
        return self.user_value(setting) is not None

    # ------------------------------------------------------------- editing
    def set(self, setting: Setting, value: str | None) -> None:
        """Change ``setting``; None, empty or the inherited value resets it."""
        value = value.strip() if value is not None else None
        if not value or _same(setting, value, self.inherited(setting)):
            value = None
        saved = self._document.get(setting.section, setting.key)
        saved = _clean(setting, saved) if saved else None
        key = (setting.section, setting.key)
        if value == saved:
            self._changes.pop(key, None)
        else:
            self._changes[key] = value

    def custom_environ(self) -> dict[str, str]:
        """The user's [environ] variables that have no setting of their own."""
        if self._environ_changes is not None:
            return dict(self._environ_changes)
        known = known_environ()
        return {
            key: value for key, value in self._document.items(_ENVIRON).items()
            if key not in known
        }

    def set_custom_environ(self, variables: Mapping[str, str]) -> None:
        """Replace those variables (invalid names are dropped, see
        is_valid_environ_name)."""
        known = known_environ()
        cleaned = {
            name.strip(): value.strip() for name, value in variables.items()
            if is_valid_environ_name(name.strip()) and name.strip() not in known
        }
        saved = {
            key: value for key, value in self._document.items(_ENVIRON).items()
            if key not in known
        }
        self._environ_changes = None if cleaned == saved else cleaned

    @property
    def dirty(self) -> bool:
        """Whether there are changes to save."""
        return bool(self._changes) or self._environ_changes is not None

    # -------------------------------------------------------------- saving
    def apply(self) -> None:
        """Write the pending changes to the user's file.

        Raises:
            OSError: If the file can't be written (the changes are kept).
        """
        if not self.dirty:
            return
        document = IniDocument(list(self._document.lines))
        for (section, key), value in self._changes.items():
            if value is None:
                document.remove(section, key)
            else:
                document.set(section, key, value)
        if self._environ_changes is not None:
            known = known_environ()
            for key in [k for k in document.items(_ENVIRON) if k not in known]:
                if key not in self._environ_changes:
                    document.remove(_ENVIRON, key)
            for key, value in self._environ_changes.items():
                document.set(_ENVIRON, key, value)
        document.write(self.user_file)
        self._document = document
        self._changes.clear()
        self._environ_changes = None
