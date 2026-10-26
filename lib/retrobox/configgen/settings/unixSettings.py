from __future__ import annotations

import io
import logging
import re
import typing
import xml.etree.ElementTree as ET
from dataclasses import InitVar, dataclass, field
from pathlib import Path
from ..utils.configparser import CaseSensitiveConfigParser

if typing.TYPE_CHECKING:
    from _typeshed import StrPath
    from collections.abc import Iterator

_logger = logging.getLogger(__name__)


def _protect_string(string: str) -> str:
    return re.sub(r'[^A-Za-z0-9-\.]+', '_', string)


def _is_xml(path: Path) -> bool:
    """Peek at the first non-empty line to detect XML."""
    try:
        with path.open(encoding='utf-8', errors='replace') as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    return stripped.startswith('<')
    except OSError:
        pass
    return False


@dataclass(slots=True)
class UnixSettings:
    filename_or_path: InitVar[StrPath]
    separator: str = field(default='', kw_only=True)

    settings_path: Path = field(init=False)
    config: CaseSensitiveConfigParser = field(init=False)
    _xml_mode: bool = field(init=False, default=False)
    _xml_data: dict[str, str] = field(init=False, default_factory=dict)

    def __post_init__(self, filename_or_path: StrPath) -> None:
        self.settings_path = Path(filename_or_path)
        _logger.debug("Creating parser for %s", self.settings_path)

        if self.settings_path.exists() and _is_xml(self.settings_path):
            self._xml_mode = True
            self.config = CaseSensitiveConfigParser(interpolation=None, strict=False)
            self._load_xml()
        else:
            self._xml_mode = False
            self._xml_data = {}
            self.config = CaseSensitiveConfigParser(interpolation=None, strict=False)
            self._load_ini()

    def _load_xml(self) -> None:
        try:
            tree = ET.parse(self.settings_path)
            root = tree.getroot()
            for elem in root:
                name = elem.get('name')
                value = elem.get('value')
                if name is not None and value is not None:
                    self._xml_data[name] = value
        except OSError as e:
            _logger.error("Cannot open %s: %s", self.settings_path, e)
        except ET.ParseError as e:
            _logger.error("XML parse error in %s: %s", self.settings_path, e)

    def _load_ini(self) -> None:
        try:
            file = io.StringIO()
            file.write('[DEFAULT]\n')
            with self.settings_path.open(encoding='latin1') as f:
                file.write(f.read())
            file.seek(0)
            self.config.read_file(file)
        except OSError as e:
            _logger.error(str(e))

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write(self) -> None:
        if self._xml_mode:
            self._write_xml()
        else:
            self._write_ini()

    def _write_xml(self) -> None:
        root = ET.Element("config")
        for name, value in sorted(self._xml_data.items()):
            ET.SubElement(root, "string", name=name, value=value)
        tree = ET.ElementTree(root)
        ET.indent(tree, space="\t")
        with self.settings_path.open("wb") as fp:
            tree.write(fp, encoding="utf-8", xml_declaration=True)

    def _write_ini(self) -> None:
        with self.settings_path.open('w') as fp:
            try:
                for key, value in self.config.items('DEFAULT'):
                    fp.write(f"{key}{self.separator}={self.separator}{value!s}\n")
            except Exception:
                _logger.error("Wrong value detected (after % char maybe?), ignoring.")

    def save(self, name: str, value: object) -> None:
        if "password" in name.lower():
            _logger.debug("Writing %s = ******** to %s", name, self.settings_path)
        else:
            _logger.debug("Writing %s = %s to %s", name, value, self.settings_path)
        if self._xml_mode:
            self._xml_data[name] = str(value)
        else:
            self.config.set('DEFAULT', name, str(value))

    def disable_all(self, name: str) -> None:
        _logger.debug("Disabling %s from %s", name, self.settings_path)
        if self._xml_mode:
            for key in list(self._xml_data):
                if key[:len(name)] == name:
                    del self._xml_data[key]
        else:
            for key, _ in self.config.items('DEFAULT'):
                if key[:len(name)] == name:
                    self.config.remove_option('DEFAULT', key)

    def remove(self, name: str) -> None:
        if self._xml_mode:
            self._xml_data.pop(name, None)
        else:
            self.config.remove_option('DEFAULT', name)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_all(self, name: str, /, *, keep_name: bool = False, keep_defaults: bool = False) -> dict[str, str]:
        return dict(self.get_all_iter(name, keep_name=keep_name, keep_defaults=keep_defaults))

    def get_all_iter(
        self, name: str, /, *, keep_name: bool = False, keep_defaults: bool = False
    ) -> Iterator[tuple[str, str]]:
        _logger.debug("Looking for %s.* in %s", name, self.settings_path)

        if self._xml_mode:
            protected_name = _protect_string(name)
            for key, value in self._xml_data.items():
                m = re.match(rf"^{re.escape(protected_name)}\.(.+)", _protect_string(key))
                if m:
                    if not keep_defaults and value in ['', 'default', 'auto']:
                        continue
                    yield f'{name}.{m.group(1)}' if keep_name else m.group(1), value
        else:
            for key, value in self.config.items('DEFAULT'):
                m = re.match(rf"^{_protect_string(name)}\.(.+)", _protect_string(key))
                if m:
                    if not keep_defaults and value in ['', 'default', 'auto']:
                        continue
                    yield f'{name}.{m.group(1)}' if keep_name else m.group(1), value