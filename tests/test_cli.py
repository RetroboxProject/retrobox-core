"""The ``retrobox`` command line (bin/retrobox) and the installers' shared library."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import REPO_ROOT, sandbox_environment

_RETROBOX = REPO_ROOT / "bin" / "retrobox"


def _retrobox(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_RETROBOX), *args], env=sandbox_environment(root),
        capture_output=True, text=True, timeout=60, check=False,
    )


def test_help_and_version(tmp_path: Path) -> None:
    """--help and --version answer and exit."""
    result = _retrobox(tmp_path, "--help")
    assert result.returncode == 0
    assert "--install-emulator" in result.stdout
    assert _retrobox(tmp_path, "--version").stdout.strip()


@pytest.mark.parametrize("args", [
    ("--foo",),
    ("--install-emulator", "cemu", "--doctor"),
    ("--download", "theme", "--settings"),
    ("--version", "--help"),
    ("--setup-emulator",),
    ("--update-default-theme",),
])
def test_bad_command_lines_change_nothing(tmp_path: Path, args: tuple[str, ...]) -> None:
    """Unknown or combined options are an error before anything runs."""
    result = _retrobox(tmp_path, *args)
    assert result.returncode == 2, result.stderr
    assert "retrobox --help" in result.stderr


def test_lists(tmp_path: Path) -> None:
    """An action without names lists what it can act on."""
    emulators = _retrobox(tmp_path, "--install-emulator")
    assert emulators.returncode == 0, emulators.stderr
    assert "retroarch" in emulators.stdout
    assert "dolphin-emu    appimage,source" in emulators.stdout
    assert "switch-online" in _retrobox(tmp_path, "--install-bezels").stdout
    assert "theme" in _retrobox(tmp_path, "--download").stdout


def test_unknown_installer(tmp_path: Path) -> None:
    """A name without an installer is an error."""
    result = _retrobox(tmp_path, "--remove-emulator", "nope")
    assert result.returncode == 1
    assert "no installer for 'nope'" in result.stderr


# --- tools/lib/installer.sh, with a fake emulator ------------------------------

_FAKE_INSTALLER = """#!/usr/bin/env bash
EMULATOR="fake"
LABEL="Fake"
PORTABLE="${FAKE_PORTABLE:-0}"
KEEP=(user.cfg)
LEGACY=(fake.AppImage)
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"
function install_appimage() { unavailable "no AppImage for this test"; }
function install_archive() {
    mkdir -p "${STAGE}/bin"
    printf '#!/bin/sh\\necho %s\\n' "${FAKE_VERSION:-1}" >"${STAGE}/bin/fake"
    chmod +x "${STAGE}/bin/fake"
    echo shipped >"${STAGE}/user.cfg"
    [[ -z "${FAKE_FAIL:-}" ]] || die "the download failed"
}
installer_main "$@"
"""


@pytest.fixture(name="fake")
def _fake(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    """A copy of tools/ with a fake installer, its environment and its folder."""
    tools = tmp_path / "tools"
    shutil.copytree(REPO_ROOT / "tools" / "lib", tools / "lib")
    script = tools / "emulators" / "fake.sh"
    script.parent.mkdir()
    script.write_text(_FAKE_INSTALLER, encoding="utf-8")
    emulators = tmp_path / "emulators"
    environment = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "NO_COLOR": "1",
        # set: tools/lib/paths.sh has nothing to resolve
        "RETROBOX_DATADIR": str(tmp_path),
        "RETROBOX_BIOS_DIR": str(tmp_path / "bios"),
        "RETROBOX_INI": str(tmp_path / "retrobox.ini"),
        "RETROBOX_EMULATORS_DIR": str(emulators),
    }
    return script, environment, emulators / "fake"


def _install(fake: tuple[Path, dict[str, str], Path], flag: str,
             **extra: str) -> subprocess.CompletedProcess[str]:
    script, environment, _ = fake
    return subprocess.run(["bash", str(script), flag], env={**environment, **extra},
                          capture_output=True, text=True, timeout=60, check=False)


def _version(folder: Path) -> str:
    binary = next(path for path in (folder / "app" / "bin" / "fake", folder / "bin" / "fake")
                  if path.exists())
    return subprocess.run([str(binary)], capture_output=True, text=True,
                          check=True).stdout.strip()


def test_install_falls_back_and_keeps_user_data(fake: tuple[Path, dict[str, str], Path]) -> None:
    """-i falls back, swaps app/ atomically and -u keeps the saves."""
    _, _, folder = fake
    (folder / "saves").mkdir(parents=True)
    (folder / "fake.AppImage").write_text("", encoding="utf-8")
    assert _install(fake, "-l").stdout.split() == ["appimage", "archive"]

    result = _install(fake, "-i")
    assert result.returncode == 0, result.stderr
    assert _version(folder) == "1"
    assert not (folder / "fake.AppImage").exists()  # an older layout
    assert (folder / "saves").is_dir()

    # only the AppImage asked for, and there is none: nothing changes
    assert _install(fake, "-a").returncode == 2

    # a failed update leaves the installed version and no staging folder
    assert _install(fake, "-i", FAKE_FAIL="1", FAKE_VERSION="2").returncode == 1
    assert _version(folder) == "1"
    assert sorted(path.name for path in folder.iterdir()) == ["app", "saves"]

    (folder / "saves" / "slot1").write_text("", encoding="utf-8")
    assert _install(fake, "-u").returncode == 0
    assert sorted(path.name for path in folder.iterdir()) == ["saves"]


_FAKE_FLATPAK = """#!/bin/sh
echo "flatpak $*" >>"${FAKE_FLATPAK_LOG}"
case "$1" in
    info) [ -e "${FAKE_FLATPAK_LOG}.installed" ] ;;
    install) : >"${FAKE_FLATPAK_LOG}.installed" ;;
    uninstall) rm -f "${FAKE_FLATPAK_LOG}.installed" ;;
esac
"""


def test_flatpak_install(fake: tuple[Path, dict[str, str], Path], tmp_path: Path) -> None:
    """A Flatpak install leaves its marker in app/, and -u removes the Flatpak."""
    script, environment, folder = fake
    script.write_text(script.read_text(encoding="utf-8").replace(
        "function install_appimage()",
        'function install_flatpak() { flatpak_install org.example.Fake; }\n'
        "function install_appimage()",
    ), encoding="utf-8")
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    (bin_dir / "flatpak").write_text(_FAKE_FLATPAK, encoding="utf-8")
    (bin_dir / "flatpak").chmod(0o755)
    log = tmp_path / "flatpak.log"
    extra = {"PATH": f"{bin_dir}:{environment['PATH']}", "FAKE_FLATPAK_LOG": str(log)}
    assert _install(fake, "-l").stdout.split() == ["flatpak", "appimage", "archive"]

    result = _install(fake, "-i", **extra)
    assert result.returncode == 0, result.stderr
    marker = folder / "app" / ".retrobox-flatpak"
    assert marker.read_text(encoding="utf-8") == "org.example.Fake\n"
    assert "install --user --or-update --noninteractive -y flathub org.example.Fake" in (
        log.read_text(encoding="utf-8"))

    assert _install(fake, "-u", **extra).returncode == 0
    assert not (folder / "app").exists()
    uninstalled = "uninstall --user --noninteractive -y org.example.Fake"
    assert uninstalled in log.read_text(encoding="utf-8")

    # no flatpak command: -i goes on with the next method
    if shutil.which("flatpak"):
        return  # this machine has one: it would really be used
    result = _install(fake, "-i", PATH=f"{tmp_path / 'nothing'}:{environment['PATH']}")
    assert result.returncode == 0, result.stderr
    assert (folder / "app" / "bin" / "fake").is_file()


def test_portable_install(fake: tuple[Path, dict[str, str], Path]) -> None:
    """A portable emulator is installed at the top of its folder, keeping KEEP files."""
    _, _, folder = fake
    assert _install(fake, "-t", FAKE_PORTABLE="1").returncode == 0
    (folder / "user.cfg").write_text("mine", encoding="utf-8")
    assert _install(fake, "-t", FAKE_PORTABLE="1", FAKE_VERSION="2").returncode == 0
    assert _version(folder) == "2"
    assert (folder / "user.cfg").read_text(encoding="utf-8") == "mine"

    assert _install(fake, "-u", FAKE_PORTABLE="1").returncode == 0
    assert sorted(path.name for path in folder.iterdir()) == ["user.cfg"]
