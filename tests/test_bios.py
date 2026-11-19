"""The BIOS declarations of the systems, and how the BIOS folder is checked."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from conftest import run_python, run_retrobox_module
from retrobox import bios
from retrobox.startup.frontend_conf.system_list_generator import load_systems


def _md5(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def test_shipped_declarations_are_valid() -> None:
    """Every bios block parses, and its required_for names emulators the system offers."""
    declared = 0
    for name, content in load_systems():
        requirements = bios.parse(name, content)  # raises on a malformed block
        declared += bool(requirements)
        refs = set(bios.emulator_refs(content))
        for requirement in requirements:
            unknown = set(requirement.required_for or ()) - refs
            assert not unknown, f"{name}: {requirement.name} is required for {unknown}"
            assert not (requirement.optional and requirement.required_for), requirement
    assert declared >= 5


@pytest.mark.parametrize("block, message", [
    ("nope", "must be a list"),
    ([{"file": "/etc/passwd"}], "inside the BIOS"),
    ([{"file": "../x.bin"}], "inside the BIOS"),
    ([{"file": "x.bin", "md5": "zz"}], "invalid md5"),
    ([{"file": "x.bin", "sha1": "00"}], "unknown keys"),
    ([{"file": "x.bin", "one_of": [{"file": "y.bin"}]}], "not both"),
    ([{"one_of": []}], "list of files"),
    ([{"one_of": [{"file": "y.bin", "optional": True}]}], "only take"),
    ([{"md5": _md5(b"x")}], "needs a 'file'"),
])
def test_malformed_blocks_are_refused(block: object, message: str) -> None:
    """A block that does not follow the format says what is wrong."""
    with pytest.raises(bios.BiosError, match=message):
        bios.parse("demo", {"bios": block})


def test_a_malformed_system_is_left_out(caplog: pytest.LogCaptureFixture) -> None:
    """load_requirements skips (and logs) a broken block instead of failing."""
    loaded = bios.load_requirements([
        ("good", {"bios": [{"file": "a.bin"}]}),
        ("bad", {"bios": [{"file": "/a.bin"}]}),
    ])
    assert list(loaded) == ["good"]
    assert "Ignoring the BIOS of bad" in caplog.text


def test_required_by() -> None:
    """No list: every emulator; a list: its emulators and cores; optional: none."""
    everyone, some = bios.parse("demo", {"bios": [
        {"file": "a.bin"},
        {"file": "b.bin", "required_for": ["ares", "libretro/swanstation"]},
    ]})
    assert everyone.required_by("libretro", "pcsx_rearmed")
    assert some.required_by("ares", "psx")
    assert some.required_by("libretro", "swanstation")
    assert not some.required_by("libretro", "pcsx_rearmed")
    optional = bios.parse("demo", {"bios": [{"file": "c.bin", "optional": True}]})[0]
    assert not optional.required_by("libretro", "any")


def test_default_emulator() -> None:
    """The core marked default wins; else the first one."""
    content = {"emulators": {"ares": {"cores": {"psx": {}}},
                             "libretro": {"cores": {"a": {}, "b": {"default": True}}}}}
    assert bios.default_emulator(content) == ("libretro", "b")
    assert bios.default_emulator({"emulators": {"ares": {"cores": {"psx": {}}}}}) == ("ares", "psx")
    assert bios.default_emulator({}) == ("", "")


def test_check_states(tmp_path: Path) -> None:
    """Found with a known MD5 (or any file when none is known), wrong, missing; globs."""
    good, bad = b"good dump", b"bad dump"
    (tmp_path / "region1.bin").write_bytes(bad)
    (tmp_path / "region2.bin").write_bytes(good)
    (tmp_path / "ps2").mkdir()
    (tmp_path / "ps2" / "any.bin").write_bytes(bad)
    (tmp_path / "unchecked.bin").write_bytes(bad)
    requirements = bios.parse("demo", {"bios": [
        {"one_of": [{"file": "region1.bin", "md5": _md5(good)},
                    {"file": "region2.bin", "md5": [_md5(b"other"), _md5(good)]}]},
        {"file": "region1.bin", "md5": _md5(good)},
        {"file": "missing.bin", "md5": _md5(good)},
        {"file": "ps2/*.bin"},
        {"file": "unchecked.bin"},
    ]})
    results = bios.check(requirements, tmp_path)
    assert [result.state for result in results] == [
        bios.State.FOUND, bios.State.WRONG, bios.State.MISSING, bios.State.FOUND,
        bios.State.FOUND,
    ]
    assert results[0].files == (tmp_path / "region2.bin",)
    assert results[1].files == (tmp_path / "region1.bin",)


def test_md5_cache_follows_changes(tmp_path: Path) -> None:
    """A changed file is hashed again; the cache is written next to the others."""
    cache_file = tmp_path / "cache.json"
    dump = tmp_path / "a.bin"
    dump.write_bytes(b"one")
    cache = bios._Md5Cache(cache_file)  # pylint: disable=protected-access
    assert cache.md5(dump) == _md5(b"one")
    cache.save()
    assert str(dump) in json.loads(cache_file.read_text(encoding="utf-8"))
    dump.write_bytes(b"two!")
    assert bios._Md5Cache(cache_file).md5(dump) == _md5(b"two!")  # pylint: disable=protected-access


def _write_es_settings(root: Path, **values: str) -> None:
    folder = root / "home" / ".config" / "retrobox" / "frontend" / ".emulationstation"
    folder.mkdir(parents=True, exist_ok=True)
    entries = "\n".join(f'<string name="{key.replace("__", ".")}" value="{value}" />'
                        for key, value in values.items())
    (folder / "es_settings.cfg").write_text(f"<config>\n{entries}\n</config>\n", encoding="utf-8")


def _bios_lines(root: Path) -> dict[str, list[dict]]:
    result = run_retrobox_module(root, "retrobox.doctor", "--json", check=False)
    lines: dict[str, list[dict]] = {}
    for line in json.loads(result.stdout)["checks"]:
        if line["section"] == "BIOS":
            lines.setdefault(line["name"], []).append(line)
    return lines


def test_doctor_reports_for_the_chosen_emulator(tmp_path: Path) -> None:
    """Only systems with ROMs; an error when the emulator chosen can't run without it."""
    data = tmp_path / "home" / ".local" / "share" / "retrobox"
    for system in ("saturn", "ps2", "psx"):
        (data / "roms" / system).mkdir(parents=True)
        (data / "roms" / system / "game.chd").write_bytes(b"")
    (data / "bios" / "pcsx2" / "bios").mkdir(parents=True)
    (data / "bios" / "pcsx2" / "bios" / "ps2-0160h-20030602.bin").write_bytes(b"\0" * (4 << 20))

    lines = _bios_lines(tmp_path)
    assert set(lines) == {"saturn", "ps2", "psx"}
    assert [line["status"] for line in lines["saturn"]] == ["ERR"]
    assert "mpr-17933.bin" in lines["saturn"][0]["hint"]
    assert lines["ps2"][0]["status"] == "OK"
    # pcsx_rearmed (the default) runs without one: only a note
    assert {line["status"] for line in lines["psx"]} == {"INFO"}

    _write_es_settings(tmp_path, saturn__emulator="libretro", saturn__core="kronos",
                       psx__emulator="libretro", psx__core="swanstation")
    lines = _bios_lines(tmp_path)
    # Kronos has a BIOS of its own: a note on who needs the real one
    assert [line["status"] for line in lines["saturn"]] == ["INFO"]
    assert "ERR" in {line["status"] for line in lines["psx"]}


def _bios_root(root: Path) -> Path:
    folder = root / "home" / ".local" / "share" / "retrobox" / "bios"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


_REQUIRE = """
from retrobox.bios import require
from retrobox.configgen.exceptions import RetroboxException
try:
    require({system!r}, {emulator!r}, {core!r})
    print("OK")
except RetroboxException as error:
    print("STOP", error.exit_code, error.args[0])
"""


def _require(root: Path, system: str, emulator: str, core: str = "") -> str:
    code = _REQUIRE.format(system=system, emulator=emulator, core=core)
    return run_python(root, code).stdout


def test_require_stops_a_game_without_its_bios(tmp_path: Path) -> None:
    """The launcher's check: a RetroboxException (EmulationStation's 250) that says what to put."""
    out = _require(tmp_path, "saturn", "libretro", "mednafen_saturn")
    assert out.startswith("STOP 250 libretro/mednafen_saturn can't run without its BIOS")
    assert "mpr-17933.bin" in out
    # Kronos has a BIOS of its own; Dreamcast's is optional
    assert _require(tmp_path, "saturn", "libretro", "kronos").strip() == "OK"
    assert _require(tmp_path, "dreamcast", "libretro", "flycast").strip() == "OK"


def test_require_checks_sizes(tmp_path: Path) -> None:
    """A PS2 dump must look like one (min_size), and Cemu needs a real keys.txt."""
    folder = _bios_root(tmp_path)
    (folder / "pcsx2" / "bios").mkdir(parents=True)
    (folder / "pcsx2" / "bios" / "Mcd001.bin").write_bytes(b"x" * 1024)
    assert _require(tmp_path, "ps2", "pcsx2", "pcsx2").startswith("STOP")
    assert _require(tmp_path, "ps2", "libretro", "play").strip() == "OK"
    (folder / "pcsx2" / "bios" / "ps2-0230e-20080220.bin").write_bytes(b"\0" * (4 << 20))
    assert _require(tmp_path, "ps2", "pcsx2", "pcsx2").strip() == "OK"

    (folder / "Cemu").mkdir()
    (folder / "Cemu" / "keys.txt").write_text("short\n", encoding="utf-8")
    assert _require(tmp_path, "wiiu", "cemu", "cemu").startswith("STOP")
    (folder / "Cemu" / "keys.txt").write_text(("0" * 32 + "\n") * 40, encoding="utf-8")
    assert _require(tmp_path, "wiiu", "cemu", "cemu").strip() == "OK"


def test_min_size_must_be_bytes() -> None:
    """min_size is a number of bytes."""
    with pytest.raises(bios.BiosError, match="number of bytes"):
        bios.parse("demo", {"bios": [{"file": "a.bin", "min_size": "1M"}]})


def test_a_bios_can_be_next_to_the_games(tmp_path: Path) -> None:
    """{roms}/ paths: neogeo.zip in the BIOS folder or in the Neo Geo ROMs one."""
    out = _require(tmp_path, "neogeo", "libretro", "fbneo")
    assert out.startswith("STOP") and "neogeo.zip" in out and "roms/neogeo" in out
    roms = tmp_path / "home" / ".local" / "share" / "retrobox" / "roms" / "neogeo"
    roms.mkdir(parents=True)
    (roms / "neogeo.zip").write_bytes(b"PK")
    assert _require(tmp_path, "neogeo", "libretro", "fbneo").strip() == "OK"


def test_roms_paths_stay_inside() -> None:
    """{roms}/ only prefixes a path inside the ROMs folder."""
    with pytest.raises(bios.BiosError, match="inside the BIOS"):
        bios.parse("demo", {"bios": [{"file": "{roms}/../x.zip"}]})
    with pytest.raises(bios.BiosError, match="inside the BIOS"):
        bios.parse("demo", {"bios": [{"file": "{data}/x.zip"}]})


def _es_list(root: Path, *args: str) -> list[str]:
    return run_retrobox_module(root, "retrobox.bios", *args).stdout.splitlines()


def test_emulationstation_list(tmp_path: Path) -> None:
    """retrobox-bios prints batocera-systems' format, for the emulator each system runs with."""
    lines = _es_list(tmp_path)
    assert "> saturn" in lines and "> ps2" in lines
    assert "> psx" not in lines  # pcsx_rearmed (the default) has a BIOS of its own
    for line in lines:
        assert line.startswith("> ") or line.split(" ", 2)[0] in ("MISSING", "INVALID"), line

    saturn = _es_list(tmp_path, "--filter", "saturn")
    assert saturn[0] == "> saturn" and len(saturn) == 2
    assert "mpr-17933.bin" in saturn[1]
    assert _es_list(tmp_path, "--filter", "ps2") == [
        "> ps2", "MISSING - PlayStation 2 BIOS: one of 82 files in pcsx2/bios/"]

    _write_es_settings(tmp_path, saturn__emulator="libretro", saturn__core="kronos")
    assert not _es_list(tmp_path, "--filter", "saturn")


def test_emulationstation_list_flags_bad_dumps(tmp_path: Path) -> None:
    """A file that is there but is not a known dump is INVALID; a good one, nothing."""
    folder = _bios_root(tmp_path)
    (folder / "lynxboot.img").write_bytes(b"\0" * 512)
    _write_es_settings(tmp_path, lynx__emulator="libretro", lynx__core="mednafen_lynx")
    md5 = "fcd403db69f54290b51035d82f835e7b"
    assert _es_list(tmp_path, "--filter", "lynx") == ["> lynx", f"INVALID {md5} lynxboot.img"]
