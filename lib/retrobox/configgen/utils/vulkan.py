from __future__ import annotations

import functools
import logging
import re
import subprocess
from typing import Final

_logger: Final = logging.getLogger(__name__)

_GPU_HEADER_RE = re.compile(r'^GPU(\d+):?\s*$')
_KV_RE = re.compile(r'^(\w+)\s*=\s*(.+)$')
_VERSION_RE = re.compile(r'\d+\.\d+\.\d+')
_DISCRETE_TYPE = 'PHYSICAL_DEVICE_TYPE_DISCRETE_GPU'


@functools.lru_cache(maxsize=1)
def _devices() -> list[dict]:
    """Launches vulkaninfo --summary once and parses all GPU blocks."""
    try:
        output = subprocess.check_output(
            ['vulkaninfo', '--summary'], text=True, stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        _logger.exception('Error running vulkaninfo.')
        return []

    devices: list[dict] = []
    current: dict | None = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        header = _GPU_HEADER_RE.match(line)
        if header:
            current = {'index': int(header.group(1))}
            devices.append(current)
            continue
        if current is None:
            continue
        kv = _KV_RE.match(line)
        if kv:
            current[kv.group(1)] = kv.group(2).strip()

    devices.sort(key=lambda d: d['index'])
    return devices


def _discrete_device() -> dict | None:
    return next((d for d in _devices() if d.get('deviceType') == _DISCRETE_TYPE), None)


def is_available() -> bool:
    """True si vulkaninfo enumera al menos un device real (loader + ICD funcionales)."""
    return bool(_devices())


def has_discrete_gpu() -> bool:
    return _discrete_device() is not None


def get_discrete_gpu_index() -> str | None:
    d = _discrete_device()
    return str(d['index']) if d else None


def get_discrete_gpu_name() -> str | None:
    d = _discrete_device()
    return d.get('deviceName') if d else None


def get_discrete_gpu_uuid() -> str | None:
    d = _discrete_device()
    return d.get('deviceUUID') if d else None


def get_default_gpu_name() -> str | None:
    devices = _devices()
    return devices[0].get('deviceName') if devices else None


def get_version() -> str:
    device = _discrete_device() or (_devices()[0] if _devices() else None)
    if not device:
        return ''
    m = _VERSION_RE.search(device.get('apiVersion', ''))
    return m.group(0) if m else ''