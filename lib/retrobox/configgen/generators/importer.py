from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Final

from ..exceptions import RetroboxException

if TYPE_CHECKING:
    from .Generator import Generator

_GENERATOR_MAP: Final[dict[str, tuple[str, str]]] = {
    'libretro': ('libretro.libretroGenerator', 'LibretroGenerator'),
    'ares': ('ares.ares_generator', 'AresGenerator'),
    'dolphin-emu': ('dolphin.dolphinGenerator', 'DolphinGenerator'),
    'dosbox': ('dosbox.dosboxGenerator', 'DosBoxGenerator'),
    'melonds': ('melonds.melondsGenerator', 'MelonDSGenerator'),
    'model2emu': ('model2emu.model2emuGenerator', 'Model2EmuGenerator'),
    'ppsspp': ('ppsspp.ppssppGenerator', 'PPSSPPGenerator'),
    'scummvm': ('scummvm.scummvmGenerator', 'ScummVMGenerator'),
    'shadps4': ('shadps4.shadps4Generator', 'shadPS4Generator'),
    'eden': ('eden.edenGenerator', 'EdenGenerator'),
    'eden-emu': ('eden.edenGenerator', 'EdenGenerator'),
    'ryujinx': ('ryujinx.ryujinxGenerator', 'RyujinxGenerator'),
    'ryujinx-emu': ('ryujinx.ryujinxGenerator', 'RyujinxGenerator'),
    'heroic': ('heroic.heroicGenerator', 'HeroicGenerator'),
    'steam': ('steam.steamGenerator', 'SteamGenerator'),
    'lutris': ('lutris.lutrisGenerator', 'LutrisGenerator'),
    'chrome': ('chrome.chromeGenerator', 'ChromeGenerator'),
    'firefox': ('firefox.firefoxGenerator', 'FirefoxGenerator'),
}

def get_generator(emulator: str, core: str) -> Generator:
    if emulator in _GENERATOR_MAP:
        module_path, cls_name = _GENERATOR_MAP[emulator]
    else:
        module_path = f'{emulator}.{emulator}Generator'
        cls_name = f'{emulator[0].upper()}{emulator[1:]}Generator'

    try:
        module = import_module(f'..{module_path}', package=__name__)
        generator_cls: type[Generator] = getattr(module, cls_name)
    except ImportError as e:
        # Only a missing generator module means "no generator"; an ImportError raised
        # from inside it (a broken dependency, a bad import) is a different error.
        expected = f'{__package__}.{module_path}'
        if e.name is not None and (e.name == expected or expected.startswith(f'{e.name}.')):
            raise RetroboxException(f'No generator found for emulator {emulator}') from e

        raise RetroboxException(f'Error importing generator for emulator {emulator}') from e
    except AttributeError as e:
        raise RetroboxException(f'No generator found for emulator {emulator}') from e

    return generator_cls()
