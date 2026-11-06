"""The store: install, remove and update the packages of a repository."""

from __future__ import annotations

import logging
import os
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING, Final

from . import gamelist
from .catalog import Package, compare_versions, load_catalog
from .extract import Extraction, Layout, extract_package, free_space_ok
from .state import STORE_CACHE_DIR, Installed, InstalledDatabase, is_valid_name
from .transport import DownloadError, download

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

DEFAULT_REPOSITORY: Final = "https://store.batocera.org/"
REPOSITORY_NAME: Final = "batocera"
REPOSITORY_ENV: Final = "RETROBOX_STORE_REPO"

class StoreError(Exception):
    """An operation of the store failed; the message says why."""


def _no_report(_text: str, _percent: int) -> None:
    """A progress report that goes nowhere."""


class Store:
    """A package repository and what is installed from it."""

    def __init__(
        self,
        repository: str | None = None,
        *,
        installed: InstalledDatabase | None = None,
        layout: Layout | None = None,
        cache: Path = STORE_CACHE_DIR,
        report: Callable[[str, int], None] | None = None,
    ) -> None:
        base = repository or os.environ.get(REPOSITORY_ENV) or DEFAULT_REPOSITORY
        self.repository = base if base.endswith("/") else base + "/"
        self.installed = installed or InstalledDatabase()
        self.layout = layout or Layout.default()
        self.cache = cache
        self._report = report or _no_report

    @property
    def database_path(self) -> Path:
        """Where the downloaded catalog is kept."""
        return self.cache / f"{REPOSITORY_NAME}.db"

    def _url(self, filename: str) -> str:
        return urllib.parse.urljoin(self.repository, urllib.parse.quote(filename))

    def refresh(self) -> None:
        """Download the catalog again.

        Raises:
            StoreError: The repository cannot be reached.
        """
        self._report("Updating the list of content", -1)
        try:
            download(self._url(f"{REPOSITORY_NAME}.db"), self.database_path)
        except DownloadError as error:
            raise StoreError(str(error)) from error

    def catalog(self) -> dict[str, Package]:
        """The packages of the repository (downloading the catalog if there is none).

        Raises:
            StoreError: There is no catalog and it cannot be downloaded, or it is unreadable.
        """
        if not self.database_path.is_file():
            self.refresh()
        try:
            return load_catalog(self.database_path)
        except (OSError, ValueError) as error:
            raise StoreError(f"cannot read the catalog: {error}") from error

    def _fetch(self, package: Package) -> Path:
        """Download the file of a package into the cache."""
        if Path(package.filename).name != package.filename or package.filename.startswith("."):
            raise StoreError(f"{package.name}: unsafe file name {package.filename!r}")
        if not free_space_ok(self.cache, package.download_size):
            raise StoreError(f"not enough disk space to download {package.name}")
        destination = self.cache / package.filename

        def progress(done: int, total: int) -> None:
            percent = min(99, done * 100 // total) if total else -1
            self._report(f"Downloading {package.name}", percent)

        try:
            download(
                self._url(package.filename),
                destination,
                expected_size=package.download_size,
                expected_sha256=package.sha256,
                progress=progress,
            )
        except DownloadError as error:
            raise StoreError(str(error)) from error
        return destination

    def install(self, name: str) -> Installed:
        """Install a package, or upgrade it to the version of the catalog.

        Args:
            name: The package name.

        Returns:
            The manifest of the installed package.

        Raises:
            StoreError: The package does not exist or cannot be installed.
        """
        package = self.catalog().get(name) if is_valid_name(name) else None
        if package is None:
            raise StoreError(f"package '{name}' not found")
        previous = self.installed.get(name)
        archive = self._fetch(package)
        extraction = Extraction()
        try:
            extract_package(
                archive, self.layout, package.installed_size, extraction, self._report
            )
        except Exception as error:  # pylint: disable=broad-exception-caught
            # a damaged archive or a decompressor failing raise many kinds of errors
            _logger.debug("extraction failed", exc_info=True)
            self._undo(extraction, previous)
            raise StoreError(f"cannot install {name}: {error}") from error
        finally:
            archive.unlink(missing_ok=True)

        if previous is not None:
            # files that the old version had and the new one does not
            stale = set(previous.files) - set(extraction.files)
            self._delete_files(stale, keep=self._owned_by_others(name))

        manifest = Installed(
            name=name,
            version=package.version,
            files=sorted(set(extraction.files)),
            batoexec=extraction.batoexec,
        )
        self.installed.save(manifest)
        for text in manifest.batoexec:
            gamelist.apply(text, "install")
        self._report(f"{name} installed", 100)
        return manifest

    def remove(self, name: str) -> None:
        """Remove an installed package.

        Args:
            name: The package name.

        Raises:
            StoreError: The package is not installed.
        """
        manifest = self.installed.get(name)
        if manifest is None:
            raise StoreError(f"package '{name}' is not installed")
        for text in manifest.batoexec:
            gamelist.apply(text, "uninstall")
        self._delete_files(set(manifest.files), keep=self._owned_by_others(name))
        self.installed.delete(name)
        self._report(f"{name} removed", 100)

    def outdated(self) -> list[str]:
        """The installed packages that have a newer version in the catalog."""
        catalog = self.catalog()
        return [
            name
            for name, manifest in self.installed.all().items()
            if name in catalog and compare_versions(catalog[name].version, manifest.version) > 0
        ]

    def clean(self, everything: bool = False) -> None:
        """Delete the downloaded files that are left over (all the cache if asked)."""
        if not self.cache.is_dir():
            return
        for path in self.cache.iterdir():
            keep_catalog = path == self.database_path and not everything
            if path.is_file() and not keep_catalog:
                path.unlink(missing_ok=True)

    def _owned_by_others(self, name: str) -> set[str]:
        """The files that other installed packages also list."""
        owned: set[str] = set()
        for other, manifest in self.installed.all().items():
            if other != name:
                owned.update(manifest.files)
        return owned

    def _undo(self, extraction: Extraction, previous: Installed | None) -> None:
        """Remove what a failed installation wrote (but not what was already there)."""
        old = set(previous.files) if previous else set()
        self._delete_files(set(extraction.files) - old, keep=set())

    def _delete_files(self, files: set[str], keep: set[str]) -> None:
        """Delete files, and the folders that are left empty (but not the roots)."""
        roots = {root.resolve() for root in self.layout.roots.values()}
        for name in sorted(files - keep):
            path = Path(name)
            path.unlink(missing_ok=True)
            parent = path.parent
            while parent.resolve() not in roots and parent != parent.parent:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
