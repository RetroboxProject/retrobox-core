"""The listings of the store, in the XML EmulationStation reads.

Besides batocera's packages, ``<packages>`` lists RetroArch's cores (their own
``libretro`` repository, a tab of the Content Downloader) and an ``<error>``
for each repository that could not be read, which retrobox-emulationstation
shows (patch 0016).
"""

from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from .catalog import compare_versions

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from retrobox.cores.buildbot import Build

    from .catalog import Package
    from .state import Installed

CORES_REPOSITORY = "libretro"
"""The repository (Content Downloader tab) of RetroArch's cores."""
CORE_PACKAGE_SUFFIX = "_libretro"
"""A core's package name is its file's: ``snes9x_libretro``."""


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


def new_listing() -> ET.Element:
    """An empty ``<packages>``."""
    return ET.Element("packages")


def add_packages(
    root: ET.Element,
    catalog: Mapping[str, Package],
    installed: Mapping[str, Installed],
    repository_name: str,
    repository_url: str,
) -> None:
    """Add the packages of a repository to ``<packages>``.

    Args:
        root: The ``<packages>`` element.
        catalog: The packages of the repository.
        installed: The installed packages, to tell which are.
        repository_name: The name of the repository.
        repository_url: Its address, where the preview pictures are.
    """
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


def add_cores(
    root: ET.Element,
    catalog: Mapping[str, Build],
    installed: Mapping[str, str],
    describe: Callable[[str], Mapping[str, str]],
    size_kb: Callable[[str], int],
) -> None:
    """Add RetroArch's cores (the buildbot's and the installed ones) to ``<packages>``.

    Args:
        root: The ``<packages>`` element.
        catalog: The cores the buildbot offers, by name.
        installed: The installed cores and their build (``""``: not known).
        describe: The .info of a core.
        size_kb: The size of an installed core, in KiB.
    """
    for core in sorted(set(catalog) | set(installed)):
        info = describe(core)
        build = catalog.get(core)
        element = ET.SubElement(root, "package")
        _text(element, "name", core + CORE_PACKAGE_SUFFIX)
        _text(element, "repository", CORES_REPOSITORY)
        _text(element, "available_version", build.date if build else "")
        _text(element, "description", info.get("display_name") or core)
        _text(element, "url", "https://docs.libretro.com/")
        _text(element, "packager", "libretro buildbot" if build else "local")
        _text(element, "download_size", 0)
        _text(element, "installed_size", size_kb(core) if core in installed else 0)
        _text(element, "arch", "any")
        status = ET.SubElement(element, "status")
        if core in installed:
            version = installed[core]
            status.text = "installed"
            status.set("version", version.split(" ")[0] if version else "unknown")
            newer = bool(build and version and build.version != version)
            status.set("need_update", "true" if newer else "false")
        else:
            status.text = "none"
        _text(element, "group", info.get("manufacturer") or "other")
        if info.get("license"):
            _text(element, "license", info["license"])


def add_error(root: ET.Element, repository: str, message: str) -> None:
    """Say that a repository could not be read (or only from an old list)."""
    ET.SubElement(root, "error", repository=repository).text = message


def to_text(root: ET.Element) -> str:
    """The listing as a document."""
    ET.indent(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def render_packages(
    catalog: Mapping[str, Package],
    installed: Mapping[str, Installed],
    repository_name: str,
    repository_url: str,
) -> str:
    """The catalog of one repository as ``<packages>`` (see add_packages)."""
    root = new_listing()
    add_packages(root, catalog, installed, repository_name, repository_url)
    return to_text(root)


def render_repositories(name: str, url: str) -> str:
    """The repositories as ``<repositories>``."""
    root = ET.Element("repositories")
    ET.SubElement(root, "repository", name=name, server=url)
    ET.indent(root)
    return ET.tostring(root, encoding="unicode")
