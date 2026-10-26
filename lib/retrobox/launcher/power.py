"""Power profile handling (powerprofilesctl) and nvidia-powerd management."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

from retrobox.paths import NVIDIA_POWERD_SCRIPT

_logger = logging.getLogger(__name__)

_POWER_PROFILES_BIN = "powerprofilesctl"
_VALID_POWER_PROFILES = {"power-saver", "balanced", "performance"}
_NVIDIA_POWERD_TIMEOUT = 15


def _set_nvidia_powerd(enable: bool) -> None:
    """Start or stop nvidia-powerd.service via the nvidia-powerd-service script.

    Never raises: only logs warnings if something fails.

    Makes sure the 'nvidia-powerd' binary actually exists on the system
    before attempting anything, guaranteeing full compatibility with
    AMD, Intel, Apple, Qualcomm, older Nvidia systems, or devices like
    the Switch.
    """
    # 1. Check that our helper script exists and is executable
    if not NVIDIA_POWERD_SCRIPT.is_file() or not os.access(NVIDIA_POWERD_SCRIPT, os.X_OK):
        _logger.debug(
            "%s not found or not executable, skipping nvidia-powerd management",
            NVIDIA_POWERD_SCRIPT,
        )
        return

    # 2. Check that the real system binary exists in PATH.
    # If it doesn't, abort silently. This protects systems without nvidia-powerd.
    if shutil.which("nvidia-powerd") is None:
        _logger.debug(
            "nvidia-powerd binary not found in system PATH, skipping nvidia-powerd management"
        )
        return

    action = "start" if enable else "stop"
    try:
        subprocess.run(
            [NVIDIA_POWERD_SCRIPT, action],
            check=True,
            capture_output=True,
            text=True,
            timeout=_NVIDIA_POWERD_TIMEOUT,
        )
        _logger.info("nvidia-powerd %s", "started" if enable else "stopped")
    except subprocess.CalledProcessError as err:
        _logger.warning(
            "failed to %s nvidia-powerd: %s", action, err.stderr.strip() if err.stderr else err
        )
    except (OSError, subprocess.SubprocessError) as err:
        _logger.warning("failed to %s nvidia-powerd: %s", action, err)


def _powerprofilesctl(*args: str) -> subprocess.CompletedProcess[str]:
    """Run powerprofilesctl with the given arguments, raising on failure."""
    return subprocess.run(
        [_POWER_PROFILES_BIN, *args],
        check=True,
        capture_output=True,
        text=True,
    )


def apply_power_profile(desired_profile: str) -> str | None:
    """Apply the requested power profile.

    Also starts nvidia-powerd if the profile is 'performance', and stops it in
    any other case.

    Returns:
        The profile that was active before, or None if it couldn't be read or
        powerprofilesctl isn't available.
    """
    desired_profile = (desired_profile or "balanced").strip().lower()
    if desired_profile not in _VALID_POWER_PROFILES:
        _logger.warning("unknown power_profile '%s', falling back to 'balanced'", desired_profile)
        desired_profile = "balanced"

    # nvidia-powerd management: independent of powerprofilesctl.
    _set_nvidia_powerd(desired_profile == "performance")

    if shutil.which(_POWER_PROFILES_BIN) is None:
        _logger.debug("%s not found, skipping power profile management", _POWER_PROFILES_BIN)
        return None

    previous_profile = None
    try:
        previous_profile = _powerprofilesctl("get").stdout.strip()
        _logger.debug("current power profile before launch: %s", previous_profile)
    except (OSError, subprocess.SubprocessError) as err:
        _logger.warning("could not read current power profile: %s", err)

    if previous_profile == desired_profile:
        _logger.debug("power profile already '%s', nothing to do", desired_profile)
        return previous_profile

    try:
        _powerprofilesctl("set", desired_profile)
        _logger.info("power profile set to '%s'", desired_profile)
    except (OSError, subprocess.SubprocessError) as err:
        _logger.warning("failed to set power profile to '%s': %s", desired_profile, err)

    return previous_profile


def restore_power_profile(previous_profile: str | None) -> None:
    """Restore the power profile that was active before the game started."""
    # nvidia-powerd should only stay active if we're going back to
    # 'performance'; for 'balanced', 'power-saver', or no valid previous
    # profile, it gets stopped.
    _set_nvidia_powerd(previous_profile == "performance")

    if not previous_profile or previous_profile not in _VALID_POWER_PROFILES:
        return
    try:
        _powerprofilesctl("set", previous_profile)
        _logger.info("power profile restored to '%s'", previous_profile)
    except (OSError, subprocess.SubprocessError) as err:
        _logger.warning("failed to restore power profile to '%s': %s", previous_profile, err)
