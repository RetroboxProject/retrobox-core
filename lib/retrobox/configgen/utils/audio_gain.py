"""Conversion of the audio gain of the menu (dB) to the volume scale of an emulator."""

from __future__ import annotations

_DB_PER_DECADE = 20  # amplitude: 20 dB is a factor of 10


def gain_to_percent(gain_db: object, max_percent: int = 100) -> int:
    """Convert an audio gain in dB to a volume in percent.

    0 dB is 100 %, -6 dB is about 50 %, and +6 dB is about 200 %.

    Args:
        gain_db: The gain in dB. An invalid or missing gain is taken as 0 dB.
        max_percent: The loudest volume the emulator accepts. A gain above it
            gets this volume, because the emulator cannot amplify any more.

    Returns:
        The volume, between 0 and ``max_percent``.
    """
    try:
        gain = float(gain_db)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        gain = 0.0
    return max(0, min(max_percent, round(100 * 10 ** (gain / _DB_PER_DECADE))))
