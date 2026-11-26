"""vulkaninfo's devices: Mesa's software renderer (llvmpipe) is not a GPU."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from retrobox.configgen.utils import vulkan

_LLVMPIPE = """\
Devices:
========
GPU0:
\tapiVersion         = 1.3.274
\tdeviceType         = PHYSICAL_DEVICE_TYPE_CPU
\tdeviceName         = llvmpipe (LLVM 17.0.6, 256 bits)
\tdeviceUUID         = 6d657361-3234-2e32-2e31-000000000000
"""

_NVIDIA_AND_LLVMPIPE = """\
Devices:
========
GPU0:
\tapiVersion         = 1.3.280
\tdeviceType         = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
\tdeviceName         = NVIDIA GeForce RTX 4060 Laptop GPU
\tdeviceUUID         = 11111111-2222-3333-4444-555555555555
GPU1:
\tapiVersion         = 1.3.274
\tdeviceType         = PHYSICAL_DEVICE_TYPE_CPU
\tdeviceName         = llvmpipe (LLVM 17.0.6, 256 bits)
\tdeviceUUID         = 6d657361-3234-2e32-2e31-000000000000
"""


@pytest.fixture(name="summary")
def _summary(monkeypatch: pytest.MonkeyPatch):
    """Make vulkaninfo print the text a test sets in ``summary.text``."""

    output = SimpleNamespace(text="")
    monkeypatch.setattr(vulkan.subprocess, "check_output", lambda *_, **__: output.text)
    vulkan._devices.cache_clear()  # pylint: disable=protected-access
    yield output
    vulkan._devices.cache_clear()  # pylint: disable=protected-access


def test_only_llvmpipe_is_no_vulkan(summary) -> None:
    """A machine whose only device is llvmpipe has no Vulkan: the emulators use OpenGL."""
    summary.text = _LLVMPIPE
    assert not vulkan.is_available()
    assert not vulkan.has_discrete_gpu()
    assert vulkan.get_version() == ""


def test_llvmpipe_next_to_a_gpu_is_ignored(summary) -> None:
    """With a real GPU, llvmpipe does not count: the index and the name are the GPU's."""
    summary.text = _NVIDIA_AND_LLVMPIPE
    assert vulkan.is_available()
    assert vulkan.get_discrete_gpu_index() == "0"
    assert vulkan.get_discrete_gpu_name() == "NVIDIA GeForce RTX 4060 Laptop GPU"
    assert vulkan.get_version() == "1.3.280"
