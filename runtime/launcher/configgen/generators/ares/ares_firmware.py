"""Firmware (BIOS) lookup for Ares.

Ares reads the location of every firmware file from settings.bml, under
``<System>/Firmware/<Type>.<Region>``. Its own scan of the firmware folder
only runs from the settings window, which kiosk mode hides, so this module
does the same job at launch: it finds the files of the Retrobox BIOS folder
by their SHA-256 and returns the settings to write. Nothing is copied: Ares
opens the files where they are.

Only the top level of the folder is looked at, and files bigger than 10 MiB
are skipped, exactly as the scan of Ares does. The hashes are cached in the
Ares config folder, so the folder is read only when a file changes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .ares_paths import _ARES_BIOS, _ARES_FIRMWARE_INDEX

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

_MAX_FILE_SIZE = 10 * 1024 * 1024  # Ares does not hash bigger files
_READ_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class FirmwareEntry:
    """One firmware file that a system of Ares can load."""

    system: str  # settings section of the system (its name without spaces or brackets)
    kind: str  # the type, as Ares names it
    region: str
    sha256: str  # empty when Ares does not publish a hash for the file

    @property
    def key(self) -> str:
        """Return the settings path that holds the location of the file."""
        return f"{self.system}/Firmware/{self.kind}.{self.region}".replace(" ", "-")


# generated from the ``firmware.push_back`` calls of desktop-ui/emulator/*.cpp
FIRMWARE: tuple[FirmwareEntry, ...] = (
    FirmwareEntry(
        "Atari5200",
        "BIOS",
        "NTSC-U Four-port",
        "06b250f18983d058c0f156ce7ee88ae48b6eaf11e6f10f21dccf6ac7ffb6a6af",
    ),
    FirmwareEntry(
        "ColecoVision",
        "BIOS",
        "World",
        "990bf1956f10207d8781b619eb74f89b00d921c8d45c95c334c16c8cceca09ad",
    ),
    FirmwareEntry(
        "FamicomDiskSystem",
        "BIOS",
        "Japan",
        "fdc1a76e654feea993fcb38366e05ee5f4eb641f86fe6bebaeefd412e112dd72",
    ),
    FirmwareEntry(
        "GameBoyAdvance",
        "BIOS",
        "World",
        "fd2547724b505f487e6dcb29ec2ecff3af35a841a77ab2e85fd87350abd36570",
    ),
    FirmwareEntry(
        "GameGear",
        "BIOS",
        "World",
        "8c8a21335038285cfa03dc076100c1f0bfadf3e4ff70796f11f3dfaaab60eee2",
    ),
    FirmwareEntry(
        "MasterSystem",
        "BIOS",
        "US",
        "477617917a12a30f9f43844909dc2de6e6a617430f5c9a36306c86414a670d50",
    ),
    FirmwareEntry(
        "MasterSystem",
        "BIOS",
        "Japan",
        "67846e26764bd862f19179294347f7353a4166b62ac4198a5ec32933b7da486e",
    ),
    FirmwareEntry(
        "MasterSystem",
        "BIOS",
        "Europe",
        "477617917a12a30f9f43844909dc2de6e6a617430f5c9a36306c86414a670d50",
    ),
    FirmwareEntry(
        "MegaCD",
        "BIOS",
        "US",
        "fb477cdbf94c84424c2feca4fe40656d85393fe7b7b401911b45ad2eb991258c",
    ),
    FirmwareEntry(
        "MegaCD",
        "BIOS",
        "Japan",
        "7133fc2dd2fe5b7d0acd53a5f10f3d00b5d31270239ad20d74ef32393e24af88",
    ),
    FirmwareEntry(
        "MegaCD",
        "BIOS",
        "Europe",
        "fe608a2a07676a23ab5fd5eee2f53c9e2526d69a28aa16ccd85c0ec42e6933cb",
    ),
    FirmwareEntry(
        "LaserActiveSEGAPAC",
        "BIOS",
        "US",
        "e89b5a319f66406611ec82fe5c4aa6827c175a05135bd7bd177366cba0465021",
    ),
    FirmwareEntry(
        "LaserActiveSEGAPAC",
        "BIOS",
        "Japan",
        "dca942d977217f703d8d1c6eb1aeb6b32c78ecc421486bbb46c459d385161c94",
    ),
    FirmwareEntry(
        "MSX",
        "BIOS",
        "Japan",
        "413a2b601a94b3792e054be2439cc77a1819cceadbfa9542f88d51c7480f2ef0",
    ),
    FirmwareEntry(
        "MSX2",
        "MAIN",
        "Japan",
        "0c672d86ead61a97f49a583b88b7c1905da120645cd44f0c9f2baf4f4631e0b1",
    ),
    FirmwareEntry(
        "MSX2",
        "SUB",
        "Japan",
        "6c6f421a10c428d960b7ecc990f99af1c638147f747bddca7b0bf0e2ab738300",
    ),
    FirmwareEntry(
        "NeoGeoAES",
        "BIOS",
        "World",
        "",
    ),
    FirmwareEntry(
        "NeoGeoMVS",
        "BIOS",
        "World",
        "",
    ),
    FirmwareEntry(
        "NeoGeoPocketColor",
        "BIOS",
        "World",
        "8fb845a2f71514cec20728e2f0fecfade69444f8d50898b92c2259f1ba63e10d",
    ),
    FirmwareEntry(
        "NeoGeoPocket",
        "BIOS",
        "World",
        "0293555b21c4fac516d25199df7809b26beeae150e1d4504a050db32264a6ad7",
    ),
    FirmwareEntry(
        "Nintendo64DD",
        "BIOS",
        "Japan",
        "806400ec0df94b0755de6c5b8249d6b6a9866124c5ddbdac198bde22499bfb8b",
    ),
    FirmwareEntry(
        "Nintendo64DD",
        "BIOS",
        "US",
        "e9fec87a45fba02399e88064b9e2f8cf0f2106e351c58279a87f05da5bc984ad",
    ),
    FirmwareEntry(
        "Nintendo64DD",
        "BIOS",
        "DEV",
        "9c2962a8b994a29e4cd04b3a6e4ed730a751414655ab6a9799ebf5fc08b79d44",
    ),
    FirmwareEntry(
        "PCEngineCD",
        "System-Card 1.0",
        "Japan",
        "afe9f27f91ac918348555b86298b4f984643eafa2773196f2c5441ea84f0c3bb",
    ),
    FirmwareEntry(
        "PCEngineCD",
        "System Card 3.0",
        "Japan",
        "e11527b3b96ce112a037138988ca72fd117a6b0779c2480d9e03eaebece3d9ce",
    ),
    FirmwareEntry(
        "PCEngineCD",
        "System Card 3.0",
        "US",
        "cadac2725711b3c442bcf237b02f5a5210c96f17625c35fa58f009e0ed39e4db",
    ),
    FirmwareEntry(
        "PCEngineCD",
        "Games Express",
        "Japan",
        "4b86bb96a48a4ca8375fc0109631d0b1d64f255a03b01de70594d40788ba6c3d",
    ),
    FirmwareEntry(
        "LaserActiveNECPAC",
        "PAC-N10",
        "US",
        "0e87a3385a27b3a4cac51934819b7eefa5b3d690768d2495633838488cd0e2e4",
    ),
    FirmwareEntry(
        "LaserActiveNECPAC",
        "PAC-N1",
        "Japan",
        "459325690a458baebd77495c91e37c4dddfdd542ba13a821ce954e5bb245627f",
    ),
    FirmwareEntry(
        "LaserActiveNECPAC",
        "PCE-LP1",
        "Japan",
        "3f43b3b577117d84002e99cb0baeb97b0d65b1d70b4adadc68817185c6a687f0",
    ),
    FirmwareEntry(
        "LaserActiveNECPAC",
        "System-Card 1.0",
        "Japan",
        "afe9f27f91ac918348555b86298b4f984643eafa2773196f2c5441ea84f0c3bb",
    ),
    FirmwareEntry(
        "LaserActiveNECPAC",
        "Games Express",
        "Japan",
        "4b86bb96a48a4ca8375fc0109631d0b1d64f255a03b01de70594d40788ba6c3d",
    ),
    FirmwareEntry(
        "PlayStation",
        "BIOS",
        "US",
        "11052b6499e466bbf0a709b1f9cb6834a9418e66680387912451e971cf8a1fef",
    ),
    FirmwareEntry(
        "PlayStation",
        "BIOS",
        "Japan",
        "9c0421858e217805f4abe18698afea8d5aa36ff0727eb8484944e00eb5e7eadb",
    ),
    FirmwareEntry(
        "PlayStation",
        "BIOS",
        "Europe",
        "1faaa18fa820a0225e488d9f086296b8e6c46df739666093987ff7d8fd352c09",
    ),
    FirmwareEntry(
        "Saturn",
        "BIOS",
        "US",
        "",
    ),
    FirmwareEntry(
        "Saturn",
        "BIOS",
        "Japan",
        "",
    ),
    FirmwareEntry(
        "Saturn",
        "BIOS",
        "Europe",
        "",
    ),
    FirmwareEntry(
        "SuperGrafxCD",
        "Arcade Card",
        "Japan",
        "e11527b3b96ce112a037138988ca72fd117a6b0779c2480d9e03eaebece3d9ce",
    ),
)

# Ares publishes no hash for these, so they are found by name. The names are
# the usual ones of the Saturn dumps; they were not checked against Ares.
_FIRMWARE_BY_NAME: dict[str, tuple[str, ...]] = {
    "Saturn/Firmware/BIOS.US": ("mpr-17933.bin",),
    "Saturn/Firmware/BIOS.Europe": ("mpr-17933.bin",),
    "Saturn/Firmware/BIOS.Japan": ("sega_101.bin",),
}


def _sha256_of(path: Path) -> str:
    """Return the SHA-256 of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_READ_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_index(index_path: Path) -> dict[str, dict[str, object]]:
    """Return the cached hashes, or nothing when the cache is missing or broken."""
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_index(index_path: Path, index: dict[str, dict[str, object]]) -> None:
    """Write the cache; a failure only costs a new hashing at the next launch."""
    try:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(index, indent=1, sort_keys=True), encoding="utf-8")
    except OSError as error:
        _logger.warning("Could not write the Ares firmware index: %s", error)


def hash_bios_folder(bios_dir: Path, index_path: Path) -> dict[str, Path]:
    """Return ``{sha256: file}`` for the files of the top level of the BIOS folder.

    A file is hashed again only when its size or its modification time changed.
    """
    if not bios_dir.is_dir():
        return {}

    cached = _load_index(index_path)
    index: dict[str, dict[str, object]] = {}
    by_hash: dict[str, Path] = {}

    with os.scandir(bios_dir) as entries:
        for entry in sorted(entries, key=lambda item: item.name):
            try:
                if not entry.is_file():
                    continue
                stat = entry.stat()
            except OSError:
                continue
            if stat.st_size == 0 or stat.st_size >= _MAX_FILE_SIZE:
                continue

            known = cached.get(entry.name, {})
            if known.get("size") == stat.st_size and known.get("mtime_ns") == stat.st_mtime_ns:
                digest = str(known.get("sha256", ""))
            else:
                try:
                    digest = _sha256_of(bios_dir / entry.name)
                except OSError:
                    continue
            index[entry.name] = {
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": digest,
            }
            by_hash.setdefault(digest, bios_dir / entry.name)

    if index != cached:
        _save_index(index_path, index)
    return by_hash


def firmware_settings(
    bios_dir: Path = _ARES_BIOS,
    index_path: Path = _ARES_FIRMWARE_INDEX,
) -> dict[str, str]:
    """Return ``{settings path: file}`` for every firmware found in the BIOS folder.

    The firmware that is not found is left out, so what the person assigned
    from the Ares window keeps working.
    """
    by_hash = hash_bios_folder(bios_dir, index_path)
    found: dict[str, str] = {}
    for entry in FIRMWARE:
        if entry.sha256:
            location = by_hash.get(entry.sha256)
            if location is not None:
                found[entry.key] = str(location)
            continue
        for name in _FIRMWARE_BY_NAME.get(entry.key, ()):
            candidate = bios_dir / name
            if candidate.is_file():
                found[entry.key] = str(candidate)
                break
    return found
