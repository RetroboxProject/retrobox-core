"""RetroArch's video driver: the cascade only goes down vulkan > glcore > gl."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from retrobox.configgen.config import SystemConfig
from retrobox.configgen.generators.libretro import libretro_backend as backend
from retrobox.configgen.utils import opengl

CORE_4_6 = """\
OpenGL vendor string: Intel
OpenGL renderer string: Mesa Intel(R) Graphics (ADL GT2)
OpenGL core profile version string: 4.6 (Core Profile) Mesa 24.0.5
OpenGL version string: 4.6 (Compatibility Profile) Mesa 24.0.5
"""

NO_CORE = """\
OpenGL vendor string: Old Vendor
OpenGL renderer string: Old GPU
OpenGL version string: 2.1 Old
"""


def _checks(
    vulkan: bool, glcore: bool, calls: list[str]
) -> dict[str, Callable[[], tuple[bool, str]]]:
    def make(name: str, result: bool) -> Callable[[], tuple[bool, str]]:
        def check() -> tuple[bool, str]:
            calls.append(name)
            return result, "test"

        return check

    return {backend.VULKAN: make("vulkan", vulkan), backend.GLCORE: make("glcore", glcore)}


@pytest.mark.parametrize(
    ("start", "vulkan", "glcore", "expected", "checked"),
    [
        ("vulkan", True, True, "vulkan", ["vulkan"]),
        ("vulkan", False, True, "glcore", ["vulkan", "glcore"]),
        ("vulkan", False, False, "gl", ["vulkan", "glcore"]),
        ("vulkan", True, False, "vulkan", ["vulkan"]),
        # glcore never looks at vulkan, even when it is there
        ("glcore", True, True, "glcore", ["glcore"]),
        ("glcore", True, False, "gl", ["glcore"]),
        # gl is the end of the chain: nothing is checked
        ("gl", True, True, "gl", []),
        ("gl", False, False, "gl", []),
    ],
)
def test_cascade_only_goes_down(
    start: str, vulkan: bool, glcore: bool, expected: str, checked: list[str]
) -> None:
    """The first usable driver wins, and only the drivers below the start are checked."""
    calls: list[str] = []
    assert backend.resolve(start, _checks(vulkan, glcore, calls)) == expected
    assert calls == checked


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({}, "vulkan"),
        ({"gfxbackend": "auto"}, "vulkan"),
        ({"gfxbackend": "glcore"}, "glcore"),
        ({"gfxbackend": "GL"}, "gl"),
        ({"gfxbackend": "opengl"}, "gl"),
        ({"gfxbackend": "nonsense"}, "vulkan"),
        ({"core": "mupen64plus_next"}, "glcore"),
        ({"core": "parallel_n64"}, "gl"),
        # what the player chose wins over the core's preference
        ({"core": "mupen64plus_next", "gfxbackend": "vulkan"}, "vulkan"),
        ({"core": "mupen64plus_next", "gfxbackend": "gl"}, "gl"),
    ],
)
def test_where_the_cascade_starts(data: dict[str, str], expected: str) -> None:
    """The chosen driver, else the core's best one, is where the cascade starts."""
    assert backend.start_backend(SystemConfig(data)) == expected


def test_preload_follows_the_resolved_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    """"Default" that falls to glcore, or a chosen vulkan that falls to gl, is OpenGL."""
    monkeypatch.setattr(backend, "_CHECKS", _checks(False, True, []))
    assert backend.uses_opengl(SystemConfig({}))
    monkeypatch.setattr(backend, "_CHECKS", _checks(True, True, []))
    assert not backend.uses_opengl(SystemConfig({}))
    assert backend.uses_opengl(SystemConfig({"gfxbackend": "gl"}))


def test_core_profile_is_what_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    """A core profile of 3.2 or later is enough for glcore."""
    monkeypatch.setattr(opengl, "probe", lambda: opengl.parse(CORE_4_6))
    assert opengl.core_profile_status((3, 2))[0] is True
    # Intel is not left out any more
    assert backend._glcore_usable()[0] is True  # pylint: disable=protected-access


def test_no_core_profile_means_no_glcore(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a core profile glcore is not usable."""
    monkeypatch.setattr(opengl, "probe", lambda: opengl.parse(NO_CORE))
    assert backend._glcore_usable()[0] is False  # pylint: disable=protected-access


def test_unknown_gl_does_not_drop_glcore(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without glxinfo/eglinfo nothing says glcore fails: it is not replaced by gl."""
    monkeypatch.setattr(opengl, "probe", lambda: None)
    assert backend._glcore_usable()[0] is True  # pylint: disable=protected-access
    assert backend.resolve("glcore") == "glcore"


def test_versions_are_not_floats() -> None:
    """Versions are compared as tuples: 4.10 is later than 4.9."""
    info = opengl.parse(CORE_4_6.replace("4.6 (Core", "4.10 (Core"))
    assert info is not None
    assert info.core_version == (4, 10)
    assert info.core_version > (4, 9)


def test_empty_output_is_unknown() -> None:
    """Output with no OpenGL information gives no result."""
    assert opengl.parse("") is None
    assert opengl.parse("Error: unable to open display") is None
