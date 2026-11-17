"""Where Retrobox puts things: XDG defaults, retrobox.ini layers and overrides."""

from __future__ import annotations

from pathlib import Path

from conftest import parse_assignments, run_python, run_retrobox_module


def _paths(root: Path, env: dict[str, str] | None = None) -> dict[str, str]:
    """The directories ``python3 -m retrobox.paths`` resolves in a sandbox."""
    return parse_assignments(run_retrobox_module(root, "retrobox.paths", env=env).stdout)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _user_ini(root: Path) -> Path:
    return root / "home" / ".config" / "retrobox" / "retrobox.ini"


def _system_ini(root: Path) -> Path:
    return root / "etc" / "retrobox" / "retrobox.ini"


def test_defaults_follow_xdg(tmp_path: Path) -> None:
    """Without retrobox.ini everything lives in the XDG directories of the home."""
    home = tmp_path / "home"
    paths = _paths(tmp_path)
    assert paths["RETROBOX_CONFIGDIR"] == str(home / ".config" / "retrobox")
    assert paths["RETROBOX_DATADIR"] == str(home / ".local" / "share" / "retrobox")
    assert paths["RETROBOX_STATEDIR"] == str(home / ".local" / "state" / "retrobox")
    assert paths["RETROBOX_RUNTIME_DIR"] == str(tmp_path / "run" / "retrobox")
    assert paths["RETROBOX_ROMS_DIR"] == paths["RETROBOX_DATADIR"] + "/roms"
    assert paths["RETROBOX_SAVES_DIR"] == paths["RETROBOX_DATADIR"] + "/saves"
    assert paths["RETROBOX_BIOS_DIR"] == paths["RETROBOX_DATADIR"] + "/bios"


def test_runtime_dir_is_private(tmp_path: Path) -> None:
    """The runtime directory is created with mode 0700."""
    paths = _paths(tmp_path)
    assert Path(paths["RETROBOX_RUNTIME_DIR"]).stat().st_mode & 0o777 == 0o700


def test_ini_moves_data_and_content_dirs(tmp_path: Path) -> None:
    """[paths] data_dir moves the data dir; roms_dir alone moves the ROMs."""
    games = tmp_path / "disk" / "games"
    games.mkdir(parents=True)
    _write(
        _user_ini(tmp_path),
        f"[paths]\ndata_dir = {tmp_path / 'data'}\n"
        f"roms_dir = \"{games}\"  # quoted, with a comment\n",
    )
    paths = _paths(tmp_path)
    assert paths["RETROBOX_DATADIR"] == str(tmp_path / "data")
    assert paths["RETROBOX_ROMS_DIR"] == str(games)
    assert paths["RETROBOX_SAVES_DIR"] == str(tmp_path / "data" / "saves")


def test_environment_beats_ini(tmp_path: Path) -> None:
    """RETROBOX_DATADIR wins over [paths] data_dir."""
    _write(_user_ini(tmp_path), f"[paths]\ndata_dir = {tmp_path / 'from-ini'}\n")
    paths = _paths(tmp_path, env={"RETROBOX_DATADIR": str(tmp_path / "from-env")})
    assert paths["RETROBOX_DATADIR"] == str(tmp_path / "from-env")


def test_layers_and_drop_ins(tmp_path: Path) -> None:
    """User beats /etc; inside a layer the drop-ins beat the main file, in order."""
    _write(_system_ini(tmp_path), "[advanced]\nkey = system\nonly_system = yes\n")
    _write(_user_ini(tmp_path), "[advanced]\nkey = user\n")
    drop_ins = _user_ini(tmp_path).parent / "retrobox.ini.d"
    _write(drop_ins / "10-first.ini", "[advanced]\nkey = first drop-in\n")
    _write(drop_ins / "50-last.ini", "[advanced]\nkey = last drop-in\n")

    def get(key: str) -> str:
        return run_retrobox_module(
            tmp_path, "retrobox.paths", "--get", f"advanced.{key}"
        ).stdout.strip()

    assert get("key") == "last drop-in"
    assert get("only_system") == "yes"


def test_known_sections_ignore_case(tmp_path: Path) -> None:
    """An old [PATHS] / [CORE] section in capitals still counts."""
    games = tmp_path / "games"
    games.mkdir()
    _write(_user_ini(tmp_path), f"[PATHS]\nROMS_DIR = {games}\n[CORE]\nIGNORE_SYSTEMS = GBA\n")
    paths = _paths(tmp_path)
    assert paths["RETROBOX_ROMS_DIR"] == str(games)
    ignored = run_python(
        tmp_path, "from retrobox.paths import IGNORED_SYSTEMS; print(sorted(IGNORED_SYSTEMS))"
    )
    assert ignored.stdout.strip() == "['gba']"


def test_unusable_roms_dir_is_autocorrected(tmp_path: Path) -> None:
    """A roms_dir that doesn't exist falls back to the default, with a warning."""
    missing = tmp_path / "unplugged-drive" / "roms"
    _write(_user_ini(tmp_path), f"[paths]\nroms_dir = {missing}\n")
    result = run_retrobox_module(tmp_path, "retrobox.paths")
    paths = parse_assignments(result.stdout)
    assert paths["RETROBOX_ROMS_DIR"] == paths["RETROBOX_DATADIR"] + "/roms"
    assert str(missing) in result.stderr
    assert not missing.exists()


def test_autocorrect_off_keeps_the_value(tmp_path: Path) -> None:
    """With autocorrect_paths = false the value is used as written, and not created."""
    missing = tmp_path / "unplugged-drive" / "roms"
    _write(
        _user_ini(tmp_path),
        f"[core]\nautocorrect_paths = false\n[paths]\nroms_dir = {missing}\n",
    )
    assert _paths(tmp_path)["RETROBOX_ROMS_DIR"] == str(missing)
    assert not missing.exists()


def test_environ_section_is_exported(tmp_path: Path) -> None:
    """[environ] reaches os.environ, but a variable already set wins."""
    _write(_user_ini(tmp_path), "[environ]\nMy_Var = from-ini\nALREADY = from-ini\n")
    result = run_python(
        tmp_path,
        "import os, retrobox.paths; print(os.environ['My_Var'], os.environ['ALREADY'])",
        env={"ALREADY": "from-env"},
    )
    assert result.stdout.split() == ["from-ini", "from-env"]


def test_layered_file_prefers_the_user(tmp_path: Path) -> None:
    """A file of ~/.config/retrobox replaces the shipped one of the same path."""
    relative = "pad2key/hotkeys.yaml"
    shipped = run_python(
        tmp_path, f"from retrobox.paths import layered_file; print(layered_file({relative!r}))"
    ).stdout.strip()
    assert shipped.endswith("share/" + relative)

    user_copy = _write(tmp_path / "home" / ".config" / "retrobox" / relative, "pad: {}\n")
    found = run_python(
        tmp_path, f"from retrobox.paths import layered_file; print(layered_file({relative!r}))"
    ).stdout.strip()
    assert found == str(user_copy)


def test_retrobox_ini_is_never_written(tmp_path: Path) -> None:
    """Resolving the paths leaves no retrobox.ini behind."""
    _paths(tmp_path)
    assert not _user_ini(tmp_path).exists()
