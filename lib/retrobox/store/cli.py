"""Command line of the store, compatible with ``batocera-store``.

EmulationStation runs these, reading the output: ``list`` prints XML (a table on
a terminal), and the operations print progress lines ``<text> >>><percent>``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import TYPE_CHECKING

from retrobox.configgen.utils.logger import setup_logging
from retrobox.paths import LOGS

from .store import REPOSITORY_NAME, Store, StoreError
from .xmlout import render_packages, render_repositories

if TYPE_CHECKING:
    from collections.abc import Callable

    from .catalog import Package
    from .state import Installed

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
    for name, text in (("install", "install a package"), ("remove", "remove a package")):
        command = commands.add_parser(name, help=text)
        command.add_argument("package")
    return parser


def _print_table(catalog: dict[str, Package], installed: dict[str, Installed]) -> None:
    """The packages as plain text, for a person."""
    for name in sorted(catalog):
        package = catalog[name]
        mark = "*" if name in installed else " "
        print(f"{mark} {name} {package.version}\n      {package.description}")


def _update(store: Store) -> int:
    """Update every installed package that has a newer version."""
    failures = 0
    for name in store.outdated():
        try:
            store.install(name)
        except StoreError as error:
            _logger.error("%s: %s", name, error)
            failures += 1
    return 1 if failures else 0


def _run(args: argparse.Namespace, store: Store) -> int:
    """Run the command; StoreError is for the caller to report."""
    match args.command:
        case "list":
            catalog = store.catalog()
            installed = store.installed.all()
            if sys.stdout.isatty():
                _print_table(catalog, installed)
            else:
                print(render_packages(catalog, installed, REPOSITORY_NAME, store.repository))
        case "list-repositories":
            print(render_repositories(REPOSITORY_NAME, store.repository))
        case "refresh":
            store.refresh()
        case "update":
            store.refresh()
            return _update(store)
        case "install":
            store.install(args.package)
        case "remove":
            store.remove(args.package)
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
        store = Store(args.repository, report=None if quiet else _make_reporter())
        try:
            return _run(args, store)
        except StoreError as error:
            _logger.error("%s", error)
            return 1
