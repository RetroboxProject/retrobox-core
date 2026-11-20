"""Command line of the store, compatible with ``batocera-store``.

EmulationStation runs these, reading the output: ``list`` prints XML (a table on
a terminal), and the operations print progress lines ``<text> >>><percent>``;
when one fails, its last line says why (EmulationStation shows the last line).

Two repositories are behind it: batocera's store, and RetroArch's cores from
the libretro buildbot (retrobox.cores), whose packages are named after the
core's file (``snes9x_libretro``). A repository that can't be reached doesn't
hide the other one: ``list`` adds an ``<error>`` for it.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import TYPE_CHECKING

from retrobox.configgen.utils.logger import setup_logging
from retrobox.cores import CoreError, Cores
from retrobox.paths import LOGS

from .store import REPOSITORY_NAME, Store, StoreError
from .xmlout import (
    CORE_PACKAGE_SUFFIX,
    CORES_REPOSITORY,
    add_cores,
    add_error,
    add_packages,
    new_listing,
    render_repositories,
    to_text,
)

if TYPE_CHECKING:
    from collections.abc import Callable


_logger = logging.getLogger(__name__)


def _make_reporter() -> Callable[[str, int], None]:
    """A progress report that prints the way EmulationStation expects it."""
    last: tuple[str, int] | None = None

    def report(text: str, percent: int) -> None:
        nonlocal last
        if (text, percent) == last:
            return
        last = (text, percent)
        print(f"{text} >>>{percent}" if percent >= 0 else text, flush=True)

    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="retrobox-store",
        description="Install and remove content (music, bezels, shaders, homebrew...).",
    )
    parser.add_argument(
        "--repository",
        metavar="URL",
        help="package repository (default: batocera's store, or $RETROBOX_STORE_REPO)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="list the packages (XML unless on a terminal)")
    commands.add_parser("list-repositories", help="list the repositories (XML)")
    commands.add_parser("refresh", help="download the list of packages again")
    commands.add_parser("update", help="update the installed packages")
    commands.add_parser("clean", help="delete the leftover downloads")
    commands.add_parser("clean-all", help="delete every download and the cached list")
    for name, text in (("install", "install packages"), ("remove", "remove packages")):
        command = commands.add_parser(name, help=f"{text} (a core: <core>{CORE_PACKAGE_SUFFIX})")
        command.add_argument("package", nargs="+")
    commands.add_parser(
        "install-base-cores",
        help="install RetroArch's base cores, unless a core is installed (its installer runs this)",
    )
    return parser


class _Repositories:
    """The two repositories: batocera's store and RetroArch's cores."""

    def __init__(self, store: Store, cores: Cores) -> None:
        self.store = store
        self.cores = cores

    def install(self, name: str) -> None:
        """Install (or update) a package or a core."""
        if name.endswith(CORE_PACKAGE_SUFFIX):
            self.cores.install(name.removesuffix(CORE_PACKAGE_SUFFIX))
        else:
            self.store.install(name)

    def remove(self, name: str) -> None:
        """Remove a package or a core."""
        if name.endswith(CORE_PACKAGE_SUFFIX):
            self.cores.remove(name.removesuffix(CORE_PACKAGE_SUFFIX))
        else:
            self.store.remove(name)

    def listing(self) -> str:
        """``<packages>`` with both repositories, and an ``<error>`` for each one that failed."""
        root = new_listing()
        try:
            add_packages(root, self.store.catalog(), self.store.installed.all(),
                         REPOSITORY_NAME, self.store.repository)
        except StoreError as error:
            add_error(root, REPOSITORY_NAME, str(error))
        installed = self.cores.installed()
        try:
            catalog = self.cores.catalog()
        except CoreError as error:
            catalog = {}
            add_error(root, CORES_REPOSITORY, str(error))
        else:
            if last_error := self.cores.last_error():
                add_error(root, CORES_REPOSITORY, f"the list of cores may be old: {last_error}")
        add_cores(root, catalog, installed, self.cores.describe, self._size_kb)
        return to_text(root)

    def _size_kb(self, core: str) -> int:
        try:
            return (self.cores.cores / f"{core}_libretro.so").stat().st_size // 1024
        except OSError:
            return 0

    def table(self) -> None:
        """Both repositories as plain text, for a person."""
        catalog = self.store.catalog()
        installed = self.store.installed.all()
        for name in sorted(catalog):
            mark = "*" if name in installed else " "
            print(f"{mark} {name} {catalog[name].version}\n      {catalog[name].description}")
        cores = self.cores.installed()
        for core, build in sorted(self.cores.catalog().items()):
            mark = "*" if core in cores else " "
            description = self.cores.describe(core).get("display_name", core)
            print(f"{mark} {core}{CORE_PACKAGE_SUFFIX} {build.date}\n      {description}")

    def refresh(self) -> int:
        """Download the lists of both again; 1 if one of them failed."""
        failures = 0
        for refresh in (self.store.refresh, self.cores.refresh):
            try:
                refresh()
            except (StoreError, CoreError) as error:
                _fail(error)
                failures += 1
        return 1 if failures else 0

    def update(self) -> int:
        """Update every installed package and core that has a newer version."""
        status = self.refresh()
        updates: list[tuple[Callable[[str], None], str]] = []
        try:
            updates += [(self.store.install, name) for name in self.store.outdated()]
            updates += [(self.cores.install, core) for core in self.cores.outdated()]
        except (StoreError, CoreError) as error:
            _fail(error)
            status = 1
        for install, name in updates:
            try:
                install(name)
            except (StoreError, CoreError) as error:
                _fail(f"{name}: {error}")
                status = 1
        return status


def _fail(error: Exception | str) -> None:
    """Report a failure: in the log, and on stdout, where EmulationStation reads it."""
    _logger.error("%s", error)
    print(f"Error: {error}", flush=True)


def _install_base_cores(cores: Cores) -> int:
    """The base cores, for RetroArch's installer (nothing if a core is installed)."""
    cores.refresh()
    failed = cores.install_base()
    if failed:
        _fail(f"could not install the cores {', '.join(failed)}")
        return 1
    return 0


def _run(args: argparse.Namespace, repositories: _Repositories) -> int:
    """Run the command; StoreError and CoreError are for the caller to report."""
    store = repositories.store
    match args.command:
        case "list":
            if sys.stdout.isatty():
                repositories.table()
            else:
                print(repositories.listing())
        case "list-repositories":
            print(render_repositories(REPOSITORY_NAME, store.repository))
        case "refresh":
            return repositories.refresh()
        case "update":
            return repositories.update()
        case "install" | "remove":
            change = repositories.install if args.command == "install" else repositories.remove
            for name in args.package:
                change(name)
        case "install-base-cores":
            return _install_base_cores(repositories.cores)
        case "clean":
            store.clean()
        case "clean-all":
            store.clean(everything=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run ``retrobox-store``; returns the exit status."""
    args = _build_parser().parse_args(argv)
    with setup_logging(LOGS / "retrobox-store.log"):
        # a listing is read by a program: nothing but the XML on stdout
        quiet = args.command in ("list", "list-repositories")
        report = None if quiet else _make_reporter()
        repositories = _Repositories(Store(args.repository, report=report), Cores(report=report))
        try:
            return _run(args, repositories)
        except (StoreError, CoreError) as error:
            _fail(error)
            return 1
