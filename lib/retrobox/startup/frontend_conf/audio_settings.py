"""Point EmulationStation's volume control at the sound server.

EmulationStation plays its sounds through SDL, which talks to PipeWire (or
PulseAudio) directly, but it changes the *system* volume through an ALSA
mixer: the ``AudioCard`` and ``AudioDevice`` keys of es_settings.cfg, which
default to ``default`` and ``Master``. On a desktop that runs PipeWire the ALSA
``default`` card is usually the physical sound card, whose ``Master`` control
does nothing for an HDMI output, so the volume keys and sticks seem to work
(no error) while the volume the user hears never changes.

The ALSA ``pulse`` plugin (libasound2-plugins, alsa-plugins-pulseaudio) exposes
a ``Master`` control that sets the volume of the sink the sound server uses by
default. It works through ``pipewire-pulse`` as well, so one setting covers
PipeWire and PulseAudio.

This module writes that choice into es_settings.cfg before EmulationStation
starts, only when both the sound server and the plugin are there and only when
the user has not chosen a mixer of their own.
"""

from __future__ import annotations

import glob
import logging
import os
from pathlib import Path

from retrobox.configgen.utils.audio import pulse_is_available
from retrobox.paths import ES_SETTINGS_CFG
from retrobox.utils.es_settings import read_es_settings

_logger = logging.getLogger(__name__)

MIXER_CARD = "pulse"
"""ALSA card (``AudioCard``) whose mixer controls the sound server's volume."""
MIXER_NAME = "Master"
"""Mixer control (``AudioDevice``) of that card."""

_PULSE_PLUGIN_GLOBS = (
    "/usr/lib/*/alsa-lib/libasound_module_ctl_pulse.so",  # Debian and Ubuntu
    "/usr/lib*/alsa-lib/libasound_module_ctl_pulse.so",  # Fedora (lib64), Arch
)
"""Where the distros install the ALSA ``pulse`` mixer plugin."""

_NEW_FILE = '<?xml version="1.0"?>\n<config>\n{lines}</config>\n'


def pulse_mixer_is_available() -> bool:
    """Whether ALSA can open the ``pulse`` mixer, so ``AudioCard=pulse`` would work."""
    return any(glob.glob(pattern) for pattern in _PULSE_PLUGIN_GLOBS)


def _setting_lines() -> str:
    return (
        f'\t<string name="AudioCard" value="{MIXER_CARD}" />\n'
        f'\t<string name="AudioDevice" value="{MIXER_NAME}" />\n'
    )


def _with_audio_settings(text: str) -> str:
    """The content of an existing es_settings.cfg with the mixer settings added."""
    lines = _setting_lines()
    if "</config>" in text:
        head, _, tail = text.rpartition("</config>")
        return head.rstrip("\n") + "\n" + lines + "</config>" + tail
    # Older EmulationStation: no single root element, just the settings.
    body = text.rstrip("\n")
    return (body + "\n" if body else "") + lines


def ensure_audio_mixer(settings_path: Path = ES_SETTINGS_CFG) -> bool:
    """Make EmulationStation's volume control change the sound server's volume.

    Does nothing (and returns False) when there is no sound server or no ALSA
    ``pulse`` plugin, or when es_settings.cfg already has an ``AudioCard`` or
    ``AudioDevice``, which is then the user's own choice. EmulationStation must
    not be running: it rewrites the file when it exits.

    Args:
        settings_path: The es_settings.cfg to update.

    Returns:
        True if the file was written.
    """
    if not pulse_is_available():
        _logger.debug("No PipeWire/PulseAudio server: leaving the volume control alone")
        return False
    if not pulse_mixer_is_available():
        _logger.warning(
            "The ALSA 'pulse' plugin is missing (libasound2-plugins on Debian, "
            "alsa-plugins-pulseaudio on Fedora): the volume set from EmulationStation "
            "may not reach the sound server"
        )
        return False

    settings = read_es_settings(settings_path)
    if "AudioCard" in settings or "AudioDevice" in settings:
        return False

    try:
        text = settings_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        content = _NEW_FILE.format(lines=_setting_lines())
    except OSError as err:
        _logger.warning("Cannot read %s: %s", settings_path, err)
        return False
    else:
        content = _with_audio_settings(text)

    temporary = settings_path.with_name(f"{settings_path.name}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, settings_path)
    except OSError as err:
        _logger.warning("Cannot write %s: %s", settings_path, err)
        temporary.unlink(missing_ok=True)
        return False

    _logger.info("Volume control set to the ALSA '%s' mixer (%s)", MIXER_CARD, MIXER_NAME)
    return True
