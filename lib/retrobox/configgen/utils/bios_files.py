import hashlib
from pathlib import Path

from retrobox.configgen.exceptions import RetroboxException
from retrobox.paths import BIOS

MIN_KEYFILE_SIZE = 1024  # 1 KB


def _calculate_checksum(ruta: Path, algoritmo: str = "sha256") -> str:
    h = hashlib.new(algoritmo)
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(8192), b""):
            h.update(bloque)
    return h.hexdigest()


def check_biosfile(bios_path, checksum_ref=None, min_size=None) -> bool:
    ruta = Path(BIOS / bios_path)

    if not ruta.exists():
        raise RetroboxException(f"Missing bios file: {bios_path}")

    if min_size is not None and ruta.stat().st_size < min_size:
        raise RetroboxException(
            f"Bios file too small: {bios_path} "
            f"({ruta.stat().st_size} bytes, expected >= {min_size})"
        )

    if checksum_ref is not None:
        calculated = _calculate_checksum(ruta)
        if calculated != checksum_ref:
            raise RetroboxException(
                f"Checksum mismatch for {bios_path}: "
                f"expected {checksum_ref}, got {calculated}"
            )

    return True