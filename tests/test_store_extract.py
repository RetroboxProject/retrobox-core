"""Unpacking a store package: what goes where, and what never gets written."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from retrobox.store.extract import Extraction, Layout, extract_package

if TYPE_CHECKING:
    from collections.abc import Callable


def _layout(root: Path) -> Layout:
    return Layout(
        {
            "roms": root / "roms",
            "music": root / "music",
            "system/configs": root / "config" / "emulators",
        }
    )


def _add_file(
    archive: tarfile.TarFile, name: str, data: bytes = b"data", mode: int = 0o644
) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = mode
    archive.addfile(info, io.BytesIO(data))


def _add_special(archive: tarfile.TarFile, name: str, kind: bytes, target: str = "") -> None:
    info = tarfile.TarInfo(name)
    info.type = kind
    info.linkname = target
    archive.addfile(info)


def _package(path: Path, build: Callable[[tarfile.TarFile], None]) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        build(archive)
    return path


def _extract(package: Path, root: Path) -> Extraction:
    result = Extraction()
    extract_package(package, _layout(root), 1024, result, lambda text, percent: None)
    return result


def _all_files(root: Path) -> set[str]:
    return {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}


def test_files_go_to_their_folders(tmp_path: Path) -> None:
    """userdata/<folder> maps to Retrobox's directories; system/configs to the emulators'."""

    def build(archive: tarfile.TarFile) -> None:
        _add_file(archive, ".PKGINFO", b"pkgname = test")
        _add_file(archive, "userdata/roms/snes/Game.sfc")
        _add_file(archive, "userdata/music/song.ogg")
        _add_file(archive, "userdata/system/configs/retroarch/cores.cfg")
        _add_file(archive, "userdata/roms/ports/run.sh", b"#!/bin/sh\n", mode=0o755)

    root = tmp_path / "out"
    result = _extract(_package(tmp_path / "pkg.tar.gz", build), root)
    assert _all_files(root) == {
        "roms/snes/Game.sfc",
        "music/song.ogg",
        "config/emulators/retroarch/cores.cfg",
        "roms/ports/run.sh",
    }
    assert len(result.files) == 4
    assert (root / "roms/ports/run.sh").stat().st_mode & 0o777 == 0o755
    assert (root / "music/song.ogg").stat().st_mode & 0o777 == 0o644


@pytest.mark.parametrize(
    "name",
    [
        "userdata/roms/../../escape.txt",
        "/userdata/roms/absolute.txt",
        "../userdata/roms/up.txt",
        "userdata/roms",  # a root itself, as a file
        "userdata/system/other/file.txt",  # no place here
        "userdata/unknown/file.txt",
    ],
)
def test_entries_without_a_place_are_skipped(tmp_path: Path, name: str) -> None:
    """Paths that climb out, are absolute or have no folder here write nothing."""
    root = tmp_path / "out"
    _extract(_package(tmp_path / "pkg.tar.gz", lambda archive: _add_file(archive, name)), root)
    assert _all_files(tmp_path) == {"pkg.tar.gz"}
    assert not (tmp_path.parent / "escape.txt").exists()


def test_links_and_devices_are_never_created(tmp_path: Path) -> None:
    """Symbolic and hard links, devices and FIFOs are skipped."""

    def build(archive: tarfile.TarFile) -> None:
        _add_special(archive, "userdata/roms/link", tarfile.SYMTYPE, "/etc/passwd")
        _add_special(archive, "userdata/roms/hard", tarfile.LNKTYPE, "userdata/roms/x")
        _add_special(archive, "userdata/roms/fifo", tarfile.FIFOTYPE)
        _add_special(archive, "userdata/roms/dev", tarfile.CHRTYPE)

    root = tmp_path / "out"
    result = _extract(_package(tmp_path / "pkg.tar.gz", build), root)
    assert result.skipped == 4
    assert not [path for path in tmp_path.rglob("*") if path.is_symlink()]
    assert _all_files(tmp_path) == {"pkg.tar.gz"}


def test_existing_link_cannot_lead_out(tmp_path: Path) -> None:
    """A link already inside a folder that points outside it is not followed."""
    outside = tmp_path / "outside"
    outside.mkdir()
    roms = tmp_path / "out" / "roms"
    roms.mkdir(parents=True)
    (roms / "snes").symlink_to(outside)

    _extract(
        _package(
            tmp_path / "pkg.tar.gz",
            lambda archive: _add_file(archive, "userdata/roms/snes/Game.sfc"),
        ),
        tmp_path / "out",
    )
    assert not (outside / "Game.sfc").exists()


def test_file_replaces_a_link(tmp_path: Path) -> None:
    """Writing over a link replaces the link, not the file it points to."""
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me", encoding="utf-8")
    music = tmp_path / "out" / "music"
    music.mkdir(parents=True)
    (music / "song.ogg").symlink_to(victim)

    _extract(
        _package(
            tmp_path / "pkg.tar.gz",
            lambda archive: _add_file(archive, "userdata/music/song.ogg", b"new"),
        ),
        tmp_path / "out",
    )
    assert victim.read_text(encoding="utf-8") == "keep me"
    assert not (music / "song.ogg").is_symlink()
    assert (music / "song.ogg").read_bytes() == b"new"


def test_batoexec_is_read_but_never_run(tmp_path: Path) -> None:
    """The package's exec instructions are kept as text and not written anywhere."""
    marker = tmp_path / "ran"

    def build(archive: tarfile.TarFile) -> None:
        _add_file(
            archive,
            "userdata/system/pacman/batoexec/test.batoexec",
            f"touch {marker}\n".encode(),
            mode=0o755,
        )

    root = tmp_path / "out"
    result = _extract(_package(tmp_path / "pkg.tar.gz", build), root)
    assert result.batoexec == [f"touch {marker}\n"]
    assert not marker.exists()
    assert _all_files(tmp_path) == {"pkg.tar.gz"}


def test_layout_target_rejects_bad_parts(tmp_path: Path) -> None:
    """Layout.target() refuses empty, dot and NUL components."""
    layout = _layout(tmp_path)
    assert layout.target(("roms", "snes", "Game.sfc")) == tmp_path / "roms" / "snes" / "Game.sfc"
    for parts in (("roms",), ("roms", ".."), ("roms", "a", ".", "b"), ("roms", "a\x00b")):
        assert layout.target(parts) is None
    assert layout.target(("system", "configs", "ra", "x.cfg")) == (
        tmp_path / "config" / "emulators" / "ra" / "x.cfg"
    )
