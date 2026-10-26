from typing import Final

from retrobox.paths import BIOS, EMULATORS_CONFIG, ROMS

PICO8_BIN_PATH: Final = BIOS / "pico-8" / "pico8"
PICO8_ROOT_PATH: Final = ROMS / "pico8"
PICO8_CONTROLLERS: Final = \
    EMULATORS_CONFIG / "lexaloffle" / ".lexaloffle" / "pico-8" / "sdl_controllers.txt"
VOX_BIN_PATH: Final = BIOS / "voxatron" / "vox"
VOX_ROOT_PATH: Final = ROMS / "voxatron"
VOX_CONTROLLERS: Final = \
    EMULATORS_CONFIG / "lexaloffle" / ".lexaloffle" / "Voxatron" / "sdl_controllers.txt"