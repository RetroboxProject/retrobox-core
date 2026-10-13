"""Files and environment DuckStation needs: BIOS, playlists and language."""

from __future__ import annotations

from os import environ
from pathlib import Path
from typing import TYPE_CHECKING

from runtime.paths import BIOS

from ...exceptions import RetroboxException

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

BIOS_LISTS: Mapping[str, Sequence[str]] = {
    "NTSCU": ["scph101.bin", "scph1001.bin", "scph5501.bin", "scph7001.bin", "scph7501.bin"],
    "PAL": [
        "scph1002.bin", "scph5502.bin", "scph5552.bin", "scph7002.bin", "scph7502.bin",
        "scph9002.bin", "scph102a.bin", "scph102b.bin",
    ],
    "NTSCJ": [
        "scph100.bin", "scph1000.bin", "scph3000.bin", "scph3500.bin", "scph5500.bin",
        "scph7000.bin", "scph7003.bin",
    ],
    "Uni": ["psxonpsp660.bin", "ps1_rom.bin"],
}  # fmt: skip

_DEFAULT_LANGUAGE = "en_US"
_LANGUAGES = {
    "en_US": "en",
    "de_DE": "de",
    "fr_FR": "fr",
    "es_ES": "es",
    "he_IL": "he",
    "it_IT": "it",
    "ja_JP": "ja",
    "nl_NL": "nl",
    "pl_PL": "pl",
    "pt_BR": "pt-br",
    "pt_PT": "pt-pt",
    "ru_RU": "ru",
    "zh_CN": "zh-cn",
}


def get_language_from_environment() -> str:
    """Return the DuckStation language code for the ``LANG`` of the session."""
    lang = environ.get("LANG", _DEFAULT_LANGUAGE)[:5]
    return _LANGUAGES.get(lang, _LANGUAGES[_DEFAULT_LANGUAGE])


def rewrite_m3u_full_path(m3u: Path) -> Path:
    """Rewrite a playlist so every disc has a full path, and return the new file.

    DuckStation does not resolve the relative paths of a playlist, so a temporary
    playlist named after the first disc is written in /tmp.
    """
    with m3u.open(encoding="utf-8") as playlist:
        first_line = playlist.readline().rstrip()

    full_playlist = Path("/tmp") / Path(first_line).with_suffix(".m3u").name
    directory = m3u.parent

    with m3u.open(encoding="utf-8") as initial, full_playlist.open("w", encoding="utf-8") as output:
        for line in initial:
            # handle both "/MGScd1.chd" and "MGScd1.chd"
            new_path = directory / line[1:] if line[0] == "/" else directory / line
            output.write(str(new_path))

    return full_playlist


def find_bios(bios_lists: Mapping[str, Sequence[str]]) -> dict[str, str]:
    """Find the first BIOS file present for each region, ignoring the case of names."""
    try:
        files_lower = {file.name.lower(): file.name for file in BIOS.iterdir()}
    except OSError as err:
        raise RetroboxException(f"Unable to read BIOS directory: {BIOS}") from err

    found_bios: dict[str, str] = {}
    for region, bios_list in bios_lists.items():
        for bios in bios_list:
            if bios.lower() in files_lower:
                found_bios[region] = files_lower[bios.lower()]
                break
    return found_bios
