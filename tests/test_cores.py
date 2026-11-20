"""RetroArch's cores, downloaded one by one from a buildbot (a fake one, in a folder)."""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from conftest import run_retrobox_module
from retrobox.cores import BASE_CORES, CoreError, Cores, migrate_legacy_cores
from retrobox.cores.buildbot import buildbot_arch, parse_index, parse_info

_INFO = 'display_name = "{name}"\nmanufacturer = "{maker}"\nlicense = "GPLv2"\n'


def _zip(path: Path, files: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
    path.write_bytes(buffer.getvalue())


def _buildbot(root: Path, cores: dict[str, str], arch: str = "x86_64") -> Path:
    """A buildbot with ``cores`` (name: crc) built for ``arch``, and their .info."""
    latest = root / "nightly" / "linux" / arch / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    lines = []
    for core, crc in cores.items():
        lines.append(f"2026-11-18 {crc} {core}_libretro.so.zip")
        content = f"ELF {core} {crc}".encode()
        _zip(latest / f"{core}_libretro.so.zip", {f"{core}_libretro.so": content})
    (latest / ".index-extended").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _zip(root / "assets" / "frontend" / "info.zip", {
        f"{core}_libretro.info": _INFO.format(name=f"Nintendo - {core}", maker="Nintendo").encode()
        for core in cores
    })
    return root


@pytest.fixture(name="bot")
def _bot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _buildbot(tmp_path / "bot", {"snes9x": "aaaa0001", "flycast": "bbbb0001",
                                        "mgba": "cccc0001"})
    monkeypatch.setenv("RETROBOX_BUILDBOT", root.as_uri())
    return root


def _cores(tmp_path: Path, arch: str = "x86_64") -> Cores:
    return Cores(cores=tmp_path / "ra" / "cores", info=tmp_path / "ra" / "info",
                 cache=tmp_path / "cache", arch=arch)


def test_parsing() -> None:
    """The index's lines, the .info's keys, and the buildbot's folder of each machine."""
    builds = parse_index("2026-11-18 0a1b2c3d snes9x_libretro.so.zip\nnot a line\n"
                         "2026-11-17 ffff mame2003_plus_libretro.so.zip\n")
    assert builds["snes9x"].version == "2026-11-18 0a1b2c3d"
    assert builds["mame2003_plus"].crc == "ffff"
    assert len(builds) == 2
    info = '# x\ndisplay_name = "Sega - Saturn (Beetle)"\nsupports_no_game = "false"\n'
    assert parse_info(info) == {"display_name": "Sega - Saturn (Beetle)",
                                "supports_no_game": "false"}
    assert buildbot_arch("x86_64") == "x86_64"
    assert buildbot_arch("arm64") == "aarch64"
    assert buildbot_arch("riscv64") is None


def test_install_update_remove(bot: Path, tmp_path: Path) -> None:
    """A core goes to cores/ with its build remembered; update only what was rebuilt."""
    cores = _cores(tmp_path)
    cores.install("snes9x")
    so = tmp_path / "ra" / "cores" / "snes9x_libretro.so"
    assert so.read_bytes() == b"ELF snes9x aaaa0001"
    assert (tmp_path / "ra" / "info" / "snes9x_libretro.info").is_file()
    assert cores.installed() == {"snes9x": "2026-11-18 aaaa0001"}
    # a core RetroArch downloaded itself: installed, build unknown, never updated in bulk
    (tmp_path / "ra" / "cores" / "mgba_libretro.so").write_bytes(b"own")
    assert cores.installed()["mgba"] == ""

    _buildbot(bot, {"snes9x": "aaaa0002", "flycast": "bbbb0001", "mgba": "cccc0002"})
    cores.refresh()
    assert cores.outdated() == ["snes9x"]
    cores.install("snes9x")
    assert so.read_bytes() == b"ELF snes9x aaaa0002"
    assert cores.outdated() == []

    cores.remove("snes9x")
    assert not so.exists() and "snes9x" not in cores.installed()
    with pytest.raises(CoreError, match="not installed"):
        cores.remove("snes9x")
    with pytest.raises(CoreError, match="not available"):
        cores.install("nothere")
    with pytest.raises(CoreError, match="not available"):
        cores.install("../evil")


def test_arm_keeps_its_own_builds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """On ARM, flycast (built from source) is not offered; mupen64plus_next is."""
    root = _buildbot(tmp_path / "bot", {"snes9x": "1", "flycast": "2", "mupen64plus_next": "3"},
                     arch="aarch64")
    monkeypatch.setenv("RETROBOX_BUILDBOT", root.as_uri())
    assert set(_cores(tmp_path, "aarch64").catalog()) == {"snes9x", "mupen64plus_next"}
    with pytest.raises(CoreError, match="no cores for this machine"):
        _cores(tmp_path, "riscv64").catalog()


def test_base_cores_only_the_first_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The base set when no core is installed (skipping what isn't built); nothing after."""
    root = _buildbot(tmp_path / "bot", {core: "1" for core in (*BASE_CORES[:3], "dosbox_pure")})
    monkeypatch.setenv("RETROBOX_BUILDBOT", root.as_uri())
    cores = _cores(tmp_path)
    assert not cores.install_base()
    assert set(cores.installed()) == set(BASE_CORES[:3])
    cores.remove(BASE_CORES[0])
    assert not cores.install_base()  # cores are installed: left as they are
    assert BASE_CORES[0] not in cores.installed()


def test_unreachable_buildbot(bot: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No buildbot: a plain error, remembered until it answers again; the old list stays."""
    cores = _cores(tmp_path)
    cores.catalog()
    monkeypatch.setenv("RETROBOX_BUILDBOT", (tmp_path / "gone").as_uri())
    with pytest.raises(CoreError, match="can't reach the libretro buildbot"):
        cores.refresh()
    assert "can't reach" in cores.last_error()
    assert "snes9x" in _cores(tmp_path).catalog()  # the list downloaded before
    with pytest.raises(CoreError, match="can't reach"):
        cores.install("snes9x")
    monkeypatch.setenv("RETROBOX_BUILDBOT", bot.as_uri())
    cores.refresh()
    assert not cores.last_error()


def test_legacy_cores_are_moved(tmp_path: Path) -> None:
    """Every core inside app/ moves to cores/, even when cores/ has some; cores/ wins."""
    legacy = tmp_path / "app" / "share" / "retroarch" / "cores"
    legacy.mkdir(parents=True)
    (legacy / "snes9x_libretro.so").write_bytes(b"old")
    (legacy / "snes9x_libretro.info").write_text("", encoding="utf-8")
    assert migrate_legacy_cores(legacy, tmp_path / "cores") == 1
    assert (tmp_path / "cores" / "snes9x_libretro.so").read_bytes() == b"old"
    (legacy / "mgba_libretro.so").write_bytes(b"x")
    (legacy / "snes9x_libretro.so").write_bytes(b"older")
    assert migrate_legacy_cores(legacy, tmp_path / "cores") == 1
    assert (tmp_path / "cores" / "mgba_libretro.so").is_file()
    assert (tmp_path / "cores" / "snes9x_libretro.so").read_bytes() == b"old"
    assert not list(legacy.glob("*.so"))
    assert migrate_legacy_cores(legacy, tmp_path / "cores") == 0


def _store(root: Path, bot: Path, *args: str) -> tuple[int, str]:
    env = {"RETROBOX_BUILDBOT": bot.as_uri(), "RETROBOX_CORES_ARCH": "x86_64",
           "RETROBOX_STORE_REPO": (root / "no-store").as_uri()}
    result = run_retrobox_module(root, "retrobox.store", *args, env=env, check=False)
    return result.returncode, result.stdout


def test_content_downloader(bot: Path, tmp_path: Path) -> None:
    """retrobox-store lists the cores in their tab, with an <error> for the store it can't reach."""
    status, out = _store(tmp_path, bot, "list")
    assert status == 0
    root = ET.fromstring(out)
    errors = {e.get("repository"): e.text for e in root.iter("error")}
    assert set(errors) == {"batocera"}
    cores = {p.findtext("name"): p for p in root.iter("package")
             if p.findtext("repository") == "libretro"}
    assert set(cores) == {"snes9x_libretro", "flycast_libretro", "mgba_libretro"}
    snes = cores["snes9x_libretro"]
    assert snes.findtext("description") == "Nintendo - snes9x"
    assert snes.findtext("group") == "Nintendo" and snes.findtext("status") == "none"

    # a core RetroArch's installer left inside app/ (older installs) is listed as installed
    legacy = (tmp_path / "home" / ".local" / "share" / "retrobox" / "emulators" / "retroarch"
              / "app" / "share" / "retroarch" / "cores")
    legacy.mkdir(parents=True)
    (legacy / "mgba_libretro.so").write_bytes(b"from the installer")
    mgba = next(p for p in ET.fromstring(_store(tmp_path, bot, "list")[1]).iter("package")
                if p.findtext("name") == "mgba_libretro")
    assert mgba.findtext("status") == "installed"
    assert mgba.find("status").get("version") == "unknown"

    assert _store(tmp_path, bot, "install", "snes9x_libretro")[0] == 0
    out = _store(tmp_path, bot, "list")[1]
    snes = next(p for p in ET.fromstring(out).iter("package")
                if p.findtext("name") == "snes9x_libretro")
    assert snes.findtext("status") == "installed"
    assert snes.find("status").get("version") == "2026-11-18"

    # a failure says why in its last line, which EmulationStation shows
    status, out = _store(tmp_path, tmp_path / "gone", "install", "flycast_libretro")
    assert status == 1
    assert out.strip().splitlines()[-1].startswith("Error: can't reach the libretro buildbot")
    root = ET.fromstring(_store(tmp_path, tmp_path / "gone", "list")[1])
    assert "may be old" in next(e.text for e in root.iter("error")
                                if e.get("repository") == "libretro")
    assert _store(tmp_path, bot, "remove", "snes9x_libretro")[0] == 0
