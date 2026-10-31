"""Find the fonts of the current EmulationStation theme.

The setup screen borrows two fonts from the theme EmulationStation is using:
the one of the menu entries (``<view name="menu"><menuText name="menutext">``)
and the one of the help bar (``<helpsystem name="help">`` of the system
view). When the theme doesn't set them, EmulationStation's own default font
(``resources/ubuntu_condensed.ttf``) is used, as EmulationStation does.

This is a small subset of EmulationStation's theme engine, enough for fonts:
``<include>`` (recursive, relative to the including file), ``<variables>``
and ``${...}``, and the ``ifSubset`` condition (with the subsets chosen in
es_settings.cfg, or the first one the theme declares). Anything else that
makes an element conditional is taken as "applies". Nothing here raises: an
unreadable theme just yields no fonts.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping

DEFAULT_FONT: Final = "ubuntu_condensed.ttf"  # FONT_PATH_REGULAR of EmulationStation

_THEME_FILE: Final = "theme.xml"
_VARIABLE: Final = re.compile(r"\$\{([^}]+)\}")
_MAX_INCLUDE_DEPTH: Final = 16


@dataclass(frozen=True, slots=True)
class ThemeFonts:
    """Font files for the screen (None: use the screen's own fallback)."""

    menu: Path | None = None
    help: Path | None = None


# ----------------------------------------------------------------- es_settings
def read_es_settings(path: Path) -> dict[str, str]:
    """Every ``<type name="..." value="..."/>`` of es_settings.cfg.

    The file may have no single root element (older EmulationStation), so its
    content is wrapped in one before parsing.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    text = re.sub(r"<\?xml[^>]*\?>", "", text, count=1)
    try:
        root = ET.fromstring(f"<settings>{text}</settings>")
    except ET.ParseError:
        return {}
    return {
        element.get("name", ""): element.get("value", "")
        for element in root.iter()
        if element.get("name") is not None and element.get("value") is not None
    }


def find_theme(theme_dirs: Iterable[Path], theme_set: str) -> Path | None:
    """The directory of the theme EmulationStation uses.

    Args:
        theme_dirs: Directories holding themes, lowest priority first (a
            theme of a later directory replaces one of the same name).
        theme_set: ``ThemeSet`` of es_settings.cfg (may be empty).

    Returns:
        That theme, or (like EmulationStation) the first one by name when it
        is not set or not installed; None if there is no theme at all.
    """
    themes: dict[str, Path] = {}
    for directory in theme_dirs:
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if (entry / _THEME_FILE).is_file():
                themes[entry.name] = entry
    if not themes:
        return None
    return themes.get(theme_set) or themes[min(themes)]


# ---------------------------------------------------------------- theme walk
class _ThemeReader:
    """Walks a theme's XML files in EmulationStation's order."""

    def __init__(self, root: Path, settings: Mapping[str, str], language: str) -> None:
        self._root = root
        self._settings = settings
        self._language = language
        self._variables: dict[str, str] = {}
        self._subset_defaults: dict[str, str] = {}

    def _resolve(self, text: str) -> str:
        return _VARIABLE.sub(lambda m: self._variables.get(m.group(1), m.group(0)), text)

    def _path(self, raw: str, base: Path) -> Path | None:
        """An existing file of the theme, or None.

        Like EmulationStation: relative to the file being read, and, if
        nothing is there, relative to the theme's root.
        """
        value = self._resolve(raw.strip())
        if not value or "${" in value or value.startswith(":/"):
            return None
        path = Path(value).expanduser()
        if path.is_absolute():
            return path if path.is_file() else None
        for directory in dict.fromkeys((base, self._root)):
            candidate = (directory / path).resolve()
            if candidate.is_file():
                return candidate
        return None

    def _selected_subset(self, name: str) -> str:
        theme = self._root.name
        return (
            self._settings.get(f"subset.{theme}.{name}")
            or self._settings.get(f"subset.{name}")
            or self._subset_defaults.get(name, "")
        )

    def _applies(self, element: ET.Element) -> bool:
        """Whether the conditions of ``element`` hold (see the module docstring)."""
        if element.get("tinyScreen") == "true" or element.get("verticalScreen") == "true":
            return False
        lang = element.get("lang")
        if lang and self._language and not any(
            self._language.startswith(code.strip().split("_")[0]) for code in lang.split(",")
        ):
            return False
        for condition in (element.get("ifSubset") or "").split(","):
            name, _, values = condition.partition(":")
            if name.strip() and self._selected_subset(name.strip()) not in {
                value.strip() for value in values.split("|")
            }:
                return False
        return True

    def _load(self, path: Path) -> ET.Element | None:
        try:
            return ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            return None

    def collect_subsets(self, path: Path, depth: int = 0) -> None:
        """First pass: the first option of every subset is its default."""
        root = self._load(path) if depth <= _MAX_INCLUDE_DEPTH else None
        if root is None:
            return
        for element in root:
            if element.tag == "subset" and element.get("name"):
                first = next((inc.get("name") for inc in element if inc.get("name")), None)
                if first:
                    self._subset_defaults.setdefault(element.get("name", ""), first)
            elif element.tag == "include" and element.text:
                included = self._path(element.text, path.parent)
                if included is not None:
                    self.collect_subsets(included, depth + 1)

    def walk(self, path: Path, depth: int = 0) -> Iterator[tuple[str, ET.Element, Path]]:
        """Yield (view names, element, its file) for every element that applies."""
        root = self._load(path) if depth <= _MAX_INCLUDE_DEPTH else None
        if root is None:
            return
        for element in root:
            if not self._applies(element):
                continue
            if element.tag == "variables":
                for variable in element:
                    if self._applies(variable):
                        self._variables[variable.tag] = self._resolve(variable.text or "")
            elif element.tag == "include" and element.text:
                included = self._path(element.text, path.parent)
                if included is not None:
                    yield from self.walk(included, depth + 1)
            elif element.tag == "view":
                for child in element:
                    if self._applies(child):
                        yield element.get("name", ""), child, path

    def font_of(self, element: ET.Element, base: Path) -> Path | None:
        """The ``fontPath`` of an element, if it names an existing file."""
        for prop in element.iter("fontPath"):
            if self._applies(prop) and prop.text:
                font = self._path(prop.text, base.parent)
                if font is not None:
                    return font
        return None


def _names(attribute: str) -> set[str]:
    return {name.strip() for name in attribute.split(",") if name.strip()}


def theme_fonts(
    theme: Path | None,
    settings: Mapping[str, str],
    resource_dirs: Iterable[Path] = (),
    language: str = "",
) -> ThemeFonts:
    """The menu and help fonts of ``theme``.

    Args:
        theme: The theme directory (see find_theme), or None.
        settings: es_settings.cfg (see read_es_settings), for the subsets.
        resource_dirs: EmulationStation's resource directories, where its
            default font lives (used for whatever the theme doesn't set).
        language: Language code, for elements restricted with ``lang``.
    """
    default = next(
        (d / DEFAULT_FONT for d in resource_dirs if (d / DEFAULT_FONT).is_file()), None
    )
    menu = help_font = None
    if theme is not None and (theme / _THEME_FILE).is_file():
        reader = _ThemeReader(theme, settings, language)
        reader.collect_subsets(theme / _THEME_FILE)
        # later definitions override earlier ones, as in EmulationStation
        for views, element, source in reader.walk(theme / _THEME_FILE):
            names = _names(element.get("name", ""))
            if element.tag == "menuText" and "menutext" in names and "menu" in _names(views):
                menu = reader.font_of(element, source) or menu
            elif element.tag == "helpsystem" and "help" in names and "system" in _names(views):
                help_font = reader.font_of(element, source) or help_font
    return ThemeFonts(menu=menu or default, help=help_font or default)
