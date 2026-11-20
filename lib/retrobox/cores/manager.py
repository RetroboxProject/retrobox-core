"""Install, update and remove RetroArch's cores one by one, from the libretro buildbot.

The cores go to ``<emulators>/retroarch/cores`` and their .info files to
``<emulators>/retroarch/info``, next to RetroArch's ``app/`` and not in it, so
installing RetroArch again keeps them. What was installed from where is kept in
``cores/.retrobox-cores.json`` (the build of each core), so an update only
downloads the cores the buildbot has rebuilt; a core that is not in it (built
from source, or downloaded from RetroArch's own menu) is never replaced by
``update``.

Every failure to reach the buildbot is a ``CoreError`` whose message says so
plainly, as EmulationStation shows it; the last one is also kept until the next
time the buildbot answers, so the list of cores can say that it may be old.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import urllib.parse
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Final

from retrobox.configgen.generators.libretro.libretroPaths import (
    RETROARCH_CORES,
    RETROARCH_INFO,
    RETROARCH_LEGACY_CORES,
)
from retrobox.paths import CACHE
from retrobox.store.transport import DownloadError, download

from .buildbot import (
    BASE_CORES,
    CORE_NAME,
    Build,
    buildbot,
    buildbot_arch,
    core_url,
    index_url,
    info_url,
    machine,
    offered,
    parse_index,
    parse_info,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

CORES_CACHE_DIR: Final = CACHE / "cores"
_VERSIONS: Final = ".retrobox-cores.json"
_LAST_ERROR: Final = "last-error.txt"
_SUFFIX: Final = "_libretro.so"


class CoreError(Exception):
    """A core operation failed; the message says why, for a person."""


def _no_report(_text: str, _percent: int) -> None:
    """A progress report that goes nowhere."""


def _unreachable(error: DownloadError) -> CoreError:
    host = urllib.parse.urlsplit(buildbot()).netloc or buildbot()
    return CoreError(f"can't reach the libretro buildbot ({host}), try again later: {error}")


def migrate_legacy_cores(legacy: Path = RETROARCH_LEGACY_CORES,
                         cores: Path = RETROARCH_CORES) -> int:
    """Move the cores of older installs (inside RetroArch's ``app/``) to the cores folder.

    Every one, whenever there are any left: a core already in the cores folder
    (downloaded since) wins, and the old copy is deleted. Cheap when there is
    nothing to move, so the store and the launcher call it each time, and the
    cores RetroArch's installer put there are listed and found without waiting
    for Retrobox to start again.

    Returns:
        How many were moved.
    """
    if not legacy.is_dir():
        return 0
    moved = 0
    for path in sorted(legacy.glob(f"*{_SUFFIX}")):
        target = cores / path.name
        try:
            if target.exists():
                path.unlink()
                continue
            cores.mkdir(parents=True, exist_ok=True)
            shutil.move(path, target)
            moved += 1
        except OSError as error:
            _logger.warning("Cannot move %s to %s: %s", path, cores, error)
    if moved:
        _logger.info("Moved %d RetroArch cores to %s", moved, cores)
    return moved


class Cores:  # pylint: disable=too-many-instance-attributes
    """The cores of the buildbot for this machine, and the ones installed."""

    def __init__(
        self,
        *,
        cores: Path = RETROARCH_CORES,
        info: Path = RETROARCH_INFO,
        cache: Path = CORES_CACHE_DIR,
        arch: str | None = None,
        report: Callable[[str, int], None] | None = None,
    ) -> None:
        self.cores = cores
        self.info = info
        self.cache = cache
        self.machine = arch or machine()
        self.arch = buildbot_arch(self.machine)
        self._report = report or _no_report
        self._catalog: dict[str, Build] | None = None

    ## The buildbot ----------------------------------------------------------

    @property
    def index_path(self) -> Path:
        """Where the downloaded list of cores is kept."""
        return self.cache / f"index-{self.arch}.txt"

    def _require_arch(self) -> str:
        if self.arch is None:
            raise CoreError(f"the libretro buildbot has no cores for this machine ({self.machine})")
        return self.arch

    def last_error(self) -> str:
        """Why the buildbot could not be reached the last time, if it couldn't."""
        try:
            return (self.cache / _LAST_ERROR).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _remember(self, error: CoreError | None) -> None:
        path = self.cache / _LAST_ERROR
        try:
            if error is None:
                path.unlink(missing_ok=True)
            else:
                self.cache.mkdir(parents=True, exist_ok=True)
                path.write_text(f"{error}\n", encoding="utf-8")
        except OSError as failure:
            _logger.debug("Cannot keep the last error in %s: %s", path, failure)

    def _download(self, url: str, destination: Path, label: str) -> None:
        def progress(done: int, total: int) -> None:
            self._report(label, min(99, done * 100 // total) if total else -1)

        try:
            download(url, destination, progress=progress)
        except DownloadError as error:
            failure = _unreachable(error)
            self._remember(failure)
            raise failure from error
        self._remember(None)

    def refresh(self) -> None:
        """Download the list of cores and the .info files again.

        Raises:
            CoreError: The buildbot can't be reached, or has nothing for this machine.
        """
        arch = self._require_arch()
        self._report("Updating the list of cores", -1)
        self._download(index_url(arch), self.index_path, "Updating the list of cores")
        self._catalog = None
        self.refresh_info()

    def refresh_info(self) -> None:
        """Download the .info file of every core into the info folder."""
        archive = self.cache / "info.zip"
        self._download(info_url(), archive, "Updating the information of the cores")
        try:
            with zipfile.ZipFile(archive) as bundle:
                self.info.mkdir(parents=True, exist_ok=True)
                for member in bundle.infolist():
                    name = Path(member.filename).name
                    if member.is_dir() or not name.endswith("_libretro.info"):
                        continue
                    if not CORE_NAME.match(name.removesuffix("_libretro.info")):
                        continue
                    _write_atomically(self.info / name, bundle.read(member), 0o644)
        except (OSError, zipfile.BadZipFile) as error:
            raise CoreError(f"the information of the cores is unreadable: {error}") from error
        finally:
            archive.unlink(missing_ok=True)

    def catalog(self) -> dict[str, Build]:
        """The cores the buildbot offers for this machine (downloading the list if there is none).

        Raises:
            CoreError: There is no list and the buildbot can't be reached.
        """
        if self._catalog is None:
            arch = self._require_arch()
            if not self.index_path.is_file():
                self.refresh()
            try:
                text = self.index_path.read_text(encoding="utf-8", errors="replace")
            except OSError as error:
                raise CoreError(f"cannot read the list of cores: {error}") from error
            self._catalog = {name: build for name, build in parse_index(text).items()
                             if offered(name, arch)}
        return self._catalog

    def describe(self, core: str) -> dict[str, str]:
        """The .info of a core (empty if it has none)."""
        try:
            text = (self.info / f"{core}_libretro.info").read_text(encoding="utf-8",
                                                                   errors="replace")
        except OSError:
            return {}
        return parse_info(text)

    ## What is installed -------------------------------------------------------

    def _versions(self) -> dict[str, str]:
        try:
            data = json.loads((self.cores / _VERSIONS).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def _save_versions(self, versions: dict[str, str]) -> None:
        content = json.dumps(dict(sorted(versions.items())), indent=1) + "\n"
        _write_atomically(self.cores / _VERSIONS, content.encode(), 0o644)

    def installed(self) -> dict[str, str]:
        """The installed cores and their build (``""`` when it is not known)."""
        versions = self._versions()
        return {path.name.removesuffix(_SUFFIX): versions.get(path.name.removesuffix(_SUFFIX), "")
                for path in sorted(self.cores.glob(f"*{_SUFFIX}"))}

    def outdated(self) -> list[str]:
        """The installed cores the buildbot has a newer build of (only the ones it installed)."""
        catalog = self.catalog()
        return [core for core, version in self.installed().items()
                if version and core in catalog and catalog[core].version != version]

    ## Installing and removing -------------------------------------------------

    def install(self, core: str) -> None:
        """Install a core, or update it to the buildbot's build.

        Raises:
            CoreError: It is not offered for this machine, or can't be downloaded.
        """
        build = self.catalog().get(core) if CORE_NAME.match(core) else None
        if build is None:
            raise CoreError(f"the core '{core}' is not available for {self.machine}")
        archive = self.cache / f"{core}_libretro.so.zip"
        self._download(core_url(self._require_arch(), core), archive, f"Downloading {core}")
        target = f"{core}{_SUFFIX}"
        try:
            with zipfile.ZipFile(archive) as bundle:
                members = [m for m in bundle.infolist() if Path(m.filename).name == target]
                if not members:
                    raise CoreError(f"the download of '{core}' has no {target}")
                self.cores.mkdir(parents=True, exist_ok=True)
                _write_atomically(self.cores / target, bundle.read(members[0]), 0o755)
        except (OSError, zipfile.BadZipFile) as error:
            raise CoreError(f"cannot install '{core}': {error}") from error
        finally:
            archive.unlink(missing_ok=True)
        versions = self._versions()
        versions[core] = build.version
        self._save_versions(versions)
        if not (self.info / f"{core}_libretro.info").is_file():
            try:
                self.refresh_info()
            except CoreError as error:  # the core works without it
                _logger.warning("No information for %s: %s", core, error)
        self._report(f"{core} installed", 100)

    def remove(self, core: str) -> None:
        """Remove an installed core (its .info stays: it is not big, and lists it).

        Raises:
            CoreError: It is not installed.
        """
        path = self.cores / f"{core}{_SUFFIX}"
        if not CORE_NAME.match(core) or not path.is_file():
            raise CoreError(f"the core '{core}' is not installed")
        try:
            path.unlink()
        except OSError as error:
            raise CoreError(f"cannot remove '{core}': {error}") from error
        versions = self._versions()
        if versions.pop(core, None) is not None:
            self._save_versions(versions)
        self._report(f"{core} removed", 100)

    def install_base(self) -> list[str]:
        """Install the base cores (BASE_CORES) if no core is installed yet.

        Cores this machine builds from source (BUILT_ON_ARM: flycast on ARM)
        don't count: RetroArch's installer builds them before it asks for the
        base set, so with them counted it never came on ARM.

        Returns:
            The cores that could not be installed.

        Raises:
            CoreError: The buildbot can't be reached.
        """
        arch = self.arch or ""
        if any(offered(core, arch) for core in self.installed()):
            return []
        catalog = self.catalog()
        failed = []
        for core in BASE_CORES:
            if core not in catalog:
                continue  # not built for this machine, or built from source (BUILT_ON_ARM)
            try:
                self.install(core)
            except CoreError as error:
                _logger.warning("%s", error)
                failed.append(core)
        return failed


def _write_atomically(path: Path, data: bytes, mode: int) -> None:
    """Write a file through a temporary one, so it is never half written."""
    partial = path.with_name(path.name + ".part")
    try:
        partial.write_bytes(data)
        os.chmod(partial, mode)
        partial.replace(path)
    except OSError:
        partial.unlink(missing_ok=True)
        raise
