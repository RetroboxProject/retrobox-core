"""Linux apps: executable .sh/.run files, run as they are, without overlay or hotkeys."""

from __future__ import annotations

from pathlib import Path

import pytest

from retrobox.configgen.exceptions import RetroboxException
from retrobox.configgen.generators import get_generator
from retrobox.configgen.generators.linuxapp.linuxappGenerator import LinuxappGenerator
from retrobox.configgen.generators.Generator import Generator


def _generate(rom: Path) -> list[str]:
    generator = get_generator("linuxapp", "linuxapp")
    command = generator.generate(None, rom, {}, {}, None, {}, None)  # type: ignore[arg-type]
    return [str(part) for part in command.array]


def _script(folder: Path, name: str, text: str, mode: int) -> Path:
    path = folder / name
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)
    return path


def test_the_generator_is_found() -> None:
    """The emulator name resolves to the generator."""
    assert isinstance(get_generator("linuxapp", "linuxapp"), LinuxappGenerator)


def test_an_executable_script_runs_as_it_is(tmp_path: Path) -> None:
    """With a shebang, the file itself is the command."""
    rom = _script(tmp_path, "app.sh", "#!/bin/sh\necho hi\n", 0o755)
    assert _generate(rom) == [str(rom)]


def test_a_script_without_shebang_goes_to_bash(tmp_path: Path) -> None:
    """The kernel cannot run it, so bash does."""
    rom = _script(tmp_path, "app.sh", "echo hi\n", 0o755)
    assert _generate(rom) == ["/bin/bash", str(rom)]


def test_a_run_file_is_never_wrapped(tmp_path: Path) -> None:
    """A .run installer is binary or makeself: run directly."""
    rom = _script(tmp_path, "app.run", "no shebang", 0o755)
    assert _generate(rom) == [str(rom)]


def test_a_file_without_exec_bit_is_refused(tmp_path: Path) -> None:
    """The error says how to fix it."""
    rom = _script(tmp_path, "app.sh", "#!/bin/sh\n", 0o644)
    with pytest.raises(RetroboxException, match="chmod"):
        _generate(rom)


def test_it_runs_from_its_own_folder(tmp_path: Path) -> None:
    """Like a file manager would."""
    rom = _script(tmp_path, "app.sh", "#!/bin/sh\n", 0o755)
    assert LinuxappGenerator().executionDirectory(None, rom) == tmp_path  # type: ignore[arg-type]


def test_hotkeys_are_opt_in_only_for_linux_apps() -> None:
    """Every other generator keeps its hotkeys."""
    assert LinuxappGenerator().hotkeys_opt_in()
    assert not get_generator("sh", "sh").hotkeys_opt_in()
    assert not Generator.hotkeys_opt_in(get_generator("chrome", "chrome"))
