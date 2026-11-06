"""The listings of the store, in the XML EmulationStation reads."""

from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from .catalog import compare_versions

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .catalog import Package
    from .state import Installed


def _text(parent: ET.Element, tag: str, value: object) -> None:
    ET.SubElement(parent, tag).text = str(value)


def _status(parent: ET.Element, package: Package, installed: Installed | None) -> None:
    """The ``<status>`` of a package: ``none``, or ``installed`` with its version."""
    status = ET.SubElement(parent, "status")
    if installed is None:
        status.text = "none"
        return
    status.text = "installed"
    status.set("version", installed.version)
    newer = compare_versions(package.version, installed.version) > 0
    status.set("need_update", "true" if newer else "false")


def render_packages(
    catalog: Mapping[str, Package],
    installed: Mapping[str, Installed],
    repository_name: str,
    repository_url: str,
) -> str:
    """The catalog as ``<packages>``.

    Args:
        catalog: The packages of the repository.
        installed: The installed packages, to tell which are.
        repository_name: The name of the repository.
        repository_url: Its address, where the preview pictures are.

    Returns:
        The XML document.
    """
    root = ET.Element("packages")
    for name in sorted(catalog):
        package = catalog[name]
        element = ET.SubElement(root, "package")
        _text(element, "name", package.name)
        _text(element, "repository", repository_name)
        _text(element, "available_version", package.version)
        _text(element, "description", package.description)
        _text(element, "url", package.url)
        _text(element, "packager", package.packager)
        _text(element, "download_size", package.download_size_kb)
        _text(element, "installed_size", package.installed_size_kb)
        _text(element, "arch", package.arch)
        preview = urllib.parse.urljoin(
            repository_url, f"thumbnails/{urllib.parse.quote(package.name)}.png"
        )
        _text(element, "preview_url", preview)
        _status(element, package, installed.get(name))
        for group in package.groups:
            _text(element, "group", group)
        for licence in package.licenses:
            _text(element, "license", licence)
    ET.indent(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def render_repositories(name: str, url: str) -> str:
    """The repositories as ``<repositories>``."""
    root = ET.Element("repositories")
    ET.SubElement(root, "repository", name=name, server=url)
    ET.indent(root)
    return ET.tostring(root, encoding="unicode")
