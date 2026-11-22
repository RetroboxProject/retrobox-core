"""``retrobox --doctor``: what Retrobox needs, and whether this computer has it.

Every check reports one line, ``[ OK ]``, ``[WARN]``, ``[ERR ]`` or ``[INFO]``,
with what it found and, when something is wrong, how to fix it. Nothing is
changed. ``[ERR ]`` is for what keeps games from starting at all; ``[WARN]``,
for what works worse or not at all in some games.

``--json`` prints the same results as JSON, for a bug report. Secrets (the
RetroAchievements token or password) are never printed: only whether they
are set.

The exit status is 1 when a check reports an error, else 0.
"""

from __future__ import annotations

import argparse
import grp
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Final

from retrobox import paths

if TYPE_CHECKING:
    from types import ModuleType

    from retrobox.bios import Requirement

_COMMAND_TIMEOUT: Final = 10.0
_LOW_SPACE_BYTES: Final = 2 * 1024**3
_OVERLAY_MIN_VERSION: Final = (0, 5, 5)
_BIOS_SECTION: Final = "BIOS"

# import name -> what needs it
_REQUIRED_MODULES: Final = {
    "yaml": "the systems and options (PyYAML)",
    "ruamel.yaml": "the systems and options (ruamel.yaml)",
    "evdev": "controllers (python-evdev)",
    "pyudev": "controllers (pyudev)",
    "sdl2": "controllers (PySDL2, bundled; needs the SDL2 library)",
    "PIL": "bezels and tattoos (Pillow)",
    "qrcode": "RetroAchievements QR codes on bezels (qrcode)",
}
_OPTIONAL_MODULES: Final = {
    "jeepney": "keeping the screen on during games (jeepney)",
    "zstandard": "Content Downloader .zst packages (zstandard, or the zstd tool)",
}


class Status(StrEnum):
    """How a check went."""

    OK = "OK"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERR"


@dataclass(frozen=True)
class Check:
    """The result of one check."""

    section: str
    name: str
    status: Status
    detail: str
    hint: str = ""


# --- helpers -------------------------------------------------------------------


def _run(*command: str) -> str | None:
    """A command's standard output, or None if it is missing or fails."""
    if shutil.which(command[0]) is None:
        return None
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=_COMMAND_TIMEOUT, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _version_tuple(text: str) -> tuple[int, ...]:
    """The numbers of a version such as ``v0.6.1`` (a suffix like ``-rc1`` ends it)."""
    numbers = []
    for part in text.strip().removeprefix("v").split("."):
        match = re.match(r"\d+", part)
        if match is None:
            break
        numbers.append(int(match.group()))
        if match.end() < len(part):
            break
    return tuple(numbers)


def retrobox_version() -> str:
    """The installed version (VERSION), or the checkout's ``git describe``."""
    version_file = paths.RETROBOX_ROOTDIR / "VERSION"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip() or "unknown"
    described = _run("git", "-C", str(paths.RETROBOX_ROOTDIR), "describe", "--tags", "--always")
    return f"{described.strip()} (checkout)" if described else "unknown"


def startup_warnings() -> list[str]:
    """What a start of Retrobox should warn about: the essentials that are missing."""
    warnings = []
    missing = [name for name in _REQUIRED_MODULES if not _has_module(name)]
    if missing:
        warnings.append(f"Missing Python modules: {', '.join(missing)}. "
                        "Run 'retrobox --doctor' to see what to install.")
    if not os.access(paths.ES_EXECUTABLE, os.X_OK):
        warnings.append(f"EmulationStation not found at {paths.ES_EXECUTABLE}: "
                        "install the retrobox-emulationstation package.")
    if shutil.which("retrobox-inputd") is None:
        warnings.append("retrobox-inputd not found: no overlay and no gamepad hotkeys. Install "
                        "retrobox-overlay (https://github.com/RetroboxProject/retrobox-overlay).")
    return warnings


# --- the checks ------------------------------------------------------------------


def check_retrobox() -> Iterator[Check]:
    """Version, Python and its modules."""
    section = "Retrobox"
    yield Check(section, "Version", Status.INFO,
                f"{retrobox_version()} in {paths.RETROBOX_ROOTDIR}")

    python = platform.python_version()
    if sys.version_info >= (3, 12):
        yield Check(section, "Python", Status.OK, f"{python} ({sys.executable})")
    else:
        yield Check(section, "Python", Status.ERROR, f"{python} is too old",
                    "Retrobox needs Python 3.12 or later")

    missing = [f"{name}: {use}" for name, use in _REQUIRED_MODULES.items() if not _has_module(name)]
    if missing:
        yield Check(section, "Python modules", Status.ERROR, "missing " + "; ".join(missing),
                    "install the packages of tools/deps/*.list (or reinstall Retrobox)")
    else:
        yield Check(section, "Python modules", Status.OK, "all the required ones")

    for name, use in _OPTIONAL_MODULES.items():
        if name == "zstandard" and (sys.version_info >= (3, 14) or shutil.which("zstd")):
            continue
        if not _has_module(name):
            yield Check(section, f"Module {name}", Status.WARN, f"missing: {use}",
                        f"install python3-{name}")

    if not (_has_module("PySide6") or _has_module("PyQt6")):
        yield Check(section, "Settings window", Status.INFO,
                    "no PySide6 or PyQt6: retrobox --settings won't open",
                    "install PySide6 (python3-pyside6) to use it")


def _overlay_check(section: str) -> Check:
    binary = shutil.which("retrobox-overlay")
    if binary is None:
        return Check(section, "Overlay", Status.WARN,
                     "not installed: no overlay, no gamepad hotkeys, no setup screen",
                     "install retrobox-overlay")
    output = _run(binary, "--version") or ""
    version = output.split()[-1] if output.split() else "unknown"
    if _version_tuple(version) and _version_tuple(version) < _OVERLAY_MIN_VERSION:
        minimum = ".".join(map(str, _OVERLAY_MIN_VERSION))
        return Check(section, "Overlay", Status.WARN, f"{version} is too old",
                     f"update retrobox-overlay to {minimum} or later")
    if shutil.which("retrobox-inputd") is None:
        return Check(section, "Overlay", Status.WARN,
                     f"{version}, but retrobox-inputd is missing: no gamepad hotkeys",
                     "reinstall retrobox-overlay")
    return Check(section, "Overlay", Status.OK, f"{version} ({binary})")


def _themes() -> list[str]:
    found = []
    for folder in (paths.FRONTEND_DIR / "themes", paths.THEMES_DIR):
        if folder.is_dir():
            found += [entry.name for entry in folder.iterdir() if entry.is_dir()]
    return sorted(set(found))


def check_components() -> Iterator[Check]:
    """EmulationStation, the overlay, MangoHud and a theme."""
    section = "Components"
    executable = paths.ES_EXECUTABLE
    if os.access(executable, os.X_OK):
        yield Check(section, "EmulationStation", Status.OK, str(executable))
    else:
        yield Check(section, "EmulationStation", Status.ERROR, f"not found at {executable}",
                    "install retrobox-emulationstation")

    yield _overlay_check(section)

    if os.access(paths.MANGOHUD_BIN, os.X_OK):
        yield Check(section, "MangoHud", Status.OK, f"Retrobox's build ({paths.MANGOHUD_BIN})")
    elif mangohud := shutil.which("mangohud"):
        yield Check(section, "MangoHud", Status.WARN,
                    f"only the system's ({mangohud}): no bezels outside RetroArch",
                    "install retrobox-mangohud")
    else:
        yield Check(section, "MangoHud", Status.WARN,
                    "not installed: no bezels, HUD or tattoos outside RetroArch",
                    "install retrobox-mangohud")

    themes = _themes()
    if themes:
        yield Check(section, "Themes", Status.OK, ", ".join(themes))
    else:
        yield Check(section, "Themes", Status.WARN, "none yet",
                    "retrobox --download theme (or it comes on the next start)")


def _resolution_tool(session: str, desktop: str) -> str:
    if session == "wayland":
        return "kscreen-doctor" if "KDE" in desktop.upper() else "wlr-randr"
    return "xrandr"


def check_display() -> Iterator[Check]:
    """The graphical session, the screen tool and the GPU."""
    section = "Display"
    session = os.environ.get("XDG_SESSION_TYPE", "")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    display = os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")
    if not display:
        yield Check(section, "Session", Status.WARN,
                    "no WAYLAND_DISPLAY or DISPLAY: not in a graphical session",
                    "run the doctor from a terminal of the desktop Retrobox runs on")
    else:
        kind = session or ("wayland" if os.environ.get("WAYLAND_DISPLAY") else "x11")
        yield Check(section, "Session", Status.OK, f"{kind}, {desktop or 'unknown desktop'}")
        tool = _resolution_tool(kind, desktop)
        if shutil.which(tool):
            yield Check(section, "Screen modes", Status.OK, tool)
        else:
            yield Check(section, "Screen modes", Status.WARN,
                        f"{tool} missing: resolution changes and screen size detection fail",
                        f"install {tool}")

    summary = _run("vulkaninfo", "--summary")
    if summary is None:
        yield Check(section, "Vulkan", Status.WARN,
                    "vulkaninfo missing or failing: emulators fall back to OpenGL",
                    "install vulkan-tools and your GPU's Vulkan driver")
    else:
        names = [line.split("=", 1)[1].strip() for line in summary.splitlines()
                 if line.strip().startswith("deviceName")]
        real = [name for name in names if "llvmpipe" not in name.lower()]
        if real:
            yield Check(section, "Vulkan", Status.OK, ", ".join(dict.fromkeys(real)))
        else:
            yield Check(section, "Vulkan", Status.WARN,
                        "only a software device (llvmpipe): games will be slow",
                        "install your GPU's Vulkan driver")


def _in_group(name: str) -> bool:
    try:
        group = grp.getgrnam(name)
    except KeyError:
        return False
    return group.gr_gid in os.getgroups()


def _gamepads() -> list[str]:
    by_id = Path("/dev/input/by-id")
    if not by_id.is_dir():
        return []
    return sorted(entry.name for entry in by_id.iterdir() if entry.name.endswith("-event-joystick"))


def check_input() -> Iterator[Check]:
    """Controllers, the input group, uinput and the udev rules."""
    section = "Input"
    pads = _gamepads()
    if pads:
        yield Check(section, "Controllers", Status.OK, f"{len(pads)} connected")
    else:
        yield Check(section, "Controllers", Status.INFO, "none connected right now")

    if _in_group("input"):
        yield Check(section, "input group", Status.OK, "you are in it")
    else:
        yield Check(section, "input group", Status.WARN,
                    "you are not in it: the overlay and the hotkeys can't read every device",
                    "sudo usermod -aG input $USER, then log in again")

    uinput = Path("/dev/uinput")
    if os.access(uinput, os.W_OK):
        yield Check(section, "uinput", Status.OK, "writable")
    else:
        yield Check(section, "uinput", Status.WARN,
                    "not writable: the pad-to-keyboard mappings and hotkeys can't type",
                    "the input group needs it: sudo usermod -aG input $USER, then log in again")

    rule_dirs = (Path("/usr/lib/udev/rules.d"), Path("/lib/udev/rules.d"),
                 Path("/etc/udev/rules.d"))
    rules = [str(path) for folder in rule_dirs if folder.is_dir()
             for path in folder.glob("*retrobox*.rules")]
    if rules:
        yield Check(section, "udev rules", Status.OK, ", ".join(rules))
    else:
        yield Check(section, "udev rules", Status.WARN,
                    "Retrobox's are not installed (Switch Pro Controller, panel brightness)",
                    "install them with the package or install.sh")


def check_power() -> Iterator[Check]:
    """What keeps the computer awake during a game."""
    section = "Power"
    tool = shutil.which("systemd-inhibit") or shutil.which("elogind-inhibit")
    if tool:
        yield Check(section, "Sleep during games", Status.OK, f"blocked with {Path(tool).name}")
    else:
        yield Check(section, "Sleep during games", Status.WARN,
                    "no systemd-inhibit or elogind-inhibit: the computer may sleep mid-game")
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        yield Check(section, "Session bus", Status.WARN,
                    "no DBUS_SESSION_BUS_ADDRESS: the screen may blank during games")


def _free_space(folder: Path) -> int | None:
    probe = folder
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return None


def check_folders() -> Iterator[Check]:
    """The ROMs, BIOS and data folders."""
    section = "Folders"
    roms = paths.ROMS
    if not roms.is_dir():
        yield Check(section, "ROMs", Status.ERROR, f"{roms} does not exist",
                    "plug in its drive, or set roms_dir in retrobox.ini")
    elif not os.access(roms, os.W_OK):
        yield Check(section, "ROMs", Status.WARN, f"{roms} is read-only",
                    "scraping and new ROM folders need it writable")
    else:
        systems = sum(1 for entry in roms.iterdir() if entry.is_dir())
        yield Check(section, "ROMs", Status.OK, f"{roms} ({systems} folders)")

    bios = paths.BIOS
    files = sum(1 for path in bios.rglob("*") if path.is_file()) if bios.is_dir() else 0
    status = Status.OK if files else Status.INFO
    yield Check(section, "BIOS", status, f"{bios} ({files} files)")

    free = _free_space(paths.DATA_DIR)
    if free is not None:
        gigabytes = f"{free / 1024**3:.1f} GB free"
        if free < _LOW_SPACE_BYTES:
            yield Check(section, "Data", Status.WARN, f"{paths.DATA_DIR}: only {gigabytes}")
        else:
            yield Check(section, "Data", Status.OK, f"{paths.DATA_DIR} ({gigabytes})")
    yield Check(section, "Logs", Status.INFO, str(paths.LOGS))


def check_emulators() -> Iterator[Check]:
    """The emulators Retrobox can install, and where each one was found."""
    section = "Emulators"
    # pylint: disable-next=import-outside-toplevel  # reads every generator's paths module
    from retrobox.launcher.emulator_setup import detector_of, installables

    missing = []
    for entry in installables():
        detector = detector_of(entry)
        found = detector.find() if detector is not None else None
        if found is None:
            missing.append(entry.installer)
        elif detector is not None and detector.installed_by_retrobox():
            yield Check(section, entry.label, Status.OK, str(found))
        else:
            yield Check(section, entry.label, Status.OK, f"{found} (not Retrobox's own)")
    if missing:
        yield Check(section, "Not installed", Status.INFO, ", ".join(missing),
                    "retrobox --install-emulator NAME (or a game offers it)")


def _has_roms(system: str) -> bool:
    """Whether the ROM folder of ``system`` holds anything but its _info.txt."""
    try:
        return any(
            not entry.name.startswith(".") and entry.name != "_info.txt"
            for entry in (paths.ROMS / system).iterdir()
        )
    except OSError:
        return False


def _bios_hint(requirement: Requirement) -> str:
    """Where to put the files that meet a requirement."""
    # pylint: disable-next=import-outside-toplevel  # loaded with check_bios
    from retrobox.bios import describe

    return f"put {describe(requirement)}"


def _found_label(requirement: Requirement, files: tuple[Path, ...]) -> str:
    """The file that meets a requirement; for a folder of dumps, how many there are."""
    if len(requirement.files) == 1 and requirement.files[0].is_glob:
        folder = Path(requirement.files[0].path).parent
        return f"{len(files)} in {folder}" if len(files) > 1 else f"{folder / files[0].name}"
    return files[0].name


def check_bios() -> Iterator[Check]:
    """The BIOS of the systems that have ROMs, for the emulator each one runs with."""
    section = _BIOS_SECTION
    try:
        # pylint: disable-next=import-outside-toplevel  # needs PyYAML
        from retrobox import bios
        # pylint: disable-next=import-outside-toplevel
        from retrobox.startup.frontend_conf.system_list_generator import load_systems
        # pylint: disable-next=import-outside-toplevel
        from retrobox.utils.es_settings import read_es_settings

        systems = [(name, content) for name, content in load_systems() if _has_roms(name)]
    except (ImportError, OSError) as error:
        yield Check(section, "Systems", Status.INFO, f"not checked ({error})")
        return

    settings = read_es_settings(paths.ES_SETTINGS_CFG)
    requirements = bios.load_requirements(systems)
    if not requirements:
        yield Check(section, "Systems", Status.OK, "no system with ROMs needs a BIOS")
        return
    for name, content in sorted(systems):
        if name not in requirements:
            continue
        emulator, core = bios.chosen_emulator(name, content, settings)
        yield from _check_system_bios(bios, name, emulator, core, requirements[name])


def _check_system_bios(bios: ModuleType, name: str, emulator: str, core: str,
                       requirements: list[Requirement]) -> Iterator[Check]:
    """The BIOS lines of one system run with ``emulator``: its problems, or one OK line."""
    section = _BIOS_SECTION
    chosen = emulator if core in ("", emulator) else f"{emulator}/{core}"
    found: list[str] = []
    reported: set[Path] = set()
    problems = False
    for result in bios.check(requirements):
        requirement = result.requirement
        needed = requirement.required_by(emulator, core)
        if result.state is bios.State.FOUND:
            found.append(_found_label(requirement, result.files))
        elif result.state is bios.State.WRONG:
            problems = True
            wrong = [path for path in result.files if path not in reported]
            reported.update(wrong)
            if wrong:
                yield Check(section, name, Status.WARN if needed else Status.INFO,
                            f"{', '.join(path.name for path in wrong)}: not a known dump "
                            f"of the {requirement.name}",
                            "games may not start with it: use a good dump (its MD5 is checked)")
        elif needed:
            problems = True
            yield Check(section, name, Status.ERROR,
                        f"{requirement.name} missing, {chosen} needs it", _bios_hint(requirement))
        elif requirement.optional:
            problems = True
            yield Check(section, name, Status.WARN,
                        f"{requirement.name} missing: {chosen} runs without it, "
                        f"but it works better with it", _bios_hint(requirement))
        elif requirement.required_for:
            problems = True
            yield Check(section, name, Status.INFO,
                        f"{requirement.name} missing: {chosen} runs without it, "
                        f"{', '.join(requirement.required_for)} need it",
                        _bios_hint(requirement))
    if not problems:
        # dict.fromkeys: one file can meet two requirements
        yield Check(section, name, Status.OK,
                    f"{', '.join(dict.fromkeys(found))} ({chosen})" if found
                    else f"nothing needed by {chosen}")


def check_achievements() -> Iterator[Check]:
    """RetroAchievements, as EmulationStation's menu set it (no secret is shown)."""
    section = "RetroAchievements"
    # pylint: disable-next=import-outside-toplevel  # configgen is heavy for the rest
    from retrobox.configgen.settings.unixSettings import UnixSettings

    if not paths.ES_SETTINGS_CFG.is_file():
        yield Check(section, "Account", Status.INFO, "EmulationStation has not run yet")
        return
    settings = UnixSettings(paths.ES_SETTINGS_CFG).get_all("global")
    if settings.get("retroachievements") not in ("1", "true", "on", "yes"):
        yield Check(section, "Account", Status.INFO, "off")
        return
    user = settings.get("retroachievements.username", "").strip()
    if not user:
        yield Check(section, "Account", Status.WARN, "on, but without a user",
                    "set it in EmulationStation's RetroAchievements settings")
    elif settings.get("retroachievements.token", "").strip():
        yield Check(section, "Account", Status.OK, f"{user}, with a token")
    elif settings.get("retroachievements.password", ""):
        yield Check(section, "Account", Status.WARN,
                    f"{user}, with a password but no token: each PCSX2, Dolphin or Flycast "
                    "game logs in first", "validate the account in EmulationStation")
    else:
        yield Check(section, "Account", Status.WARN, f"{user}, without a token or password",
                    "validate the account in EmulationStation")


CHECKS: Final[tuple[Callable[[], Iterator[Check]], ...]] = (
    check_retrobox,
    check_components,
    check_display,
    check_input,
    check_power,
    check_folders,
    check_emulators,
    check_bios,
    check_achievements,
)


def run_checks() -> list[Check]:
    """Every check; one that crashes reports the error instead of stopping the rest."""
    results: list[Check] = []
    for check in CHECKS:
        try:
            results.extend(check())
        except Exception as err:  # pylint: disable=broad-exception-caught
            name = check.__name__.removeprefix("check_")
            results.append(Check(name.title(), "Check", Status.ERROR,
                                 f"the check failed: {err!r}"))
    return results


# --- output ----------------------------------------------------------------------

_TAGS: Final = {
    Status.OK: ("[ OK ]", "\033[32m"),
    Status.INFO: ("[INFO]", "\033[36m"),
    Status.WARN: ("[WARN]", "\033[33m"),
    Status.ERROR: ("[ERR ]", "\033[31m"),
}
_RESET: Final = "\033[0m"
_BOLD: Final = "\033[1m"


def format_text(results: list[Check], color: bool) -> str:
    """The report for a terminal."""
    width = max((len(result.name) for result in results), default=0)
    lines = [f"Retrobox doctor ({retrobox_version()})"]
    section = None
    for result in results:
        if result.section != section:
            section = result.section
            lines.append("")
            lines.append(f"{_BOLD}{section}{_RESET}" if color else section)
        tag, tint = _TAGS[result.status]
        shown = f"{tint}{tag}{_RESET}" if color else tag
        lines.append(f"  {shown} {result.name.ljust(width)}  {result.detail}")
        if result.hint and result.status in (Status.WARN, Status.ERROR):
            lines.append(f"  {' ' * len(tag)} {' ' * width}  -> {result.hint}")
    errors = sum(result.status is Status.ERROR for result in results)
    warnings = sum(result.status is Status.WARN for result in results)
    lines.append("")
    lines.append(f"{errors} error(s), {warnings} warning(s)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the checks and print the report."""
    parser = argparse.ArgumentParser(
        prog="retrobox --doctor", description=__doc__.split("\n", maxsplit=1)[0]
    )
    parser.add_argument("--json", action="store_true", help="print the results as JSON")
    args = parser.parse_args(argv)

    results = run_checks()
    if args.json:
        print(json.dumps(
            {"version": retrobox_version(), "checks": [asdict(result) for result in results]},
            indent=2,
        ))
    else:
        color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        print(format_text(results, color))
    return 1 if any(result.status is Status.ERROR for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
