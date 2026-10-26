from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Final

from ..exceptions import RetroboxException

if TYPE_CHECKING:
    from .Generator import Generator

_LEGACY_GENERATOR_MAP: Final[dict[str, dict[str, tuple[str, str]]]] = {
    'duckstation': {
        'duckstation-legacy': ('duckstation_legacy.duckstationLegacyGenerator', 'DuckstationLegacyGenerator'),
    },
    'supermodel': {
        'supermodel-legacy': ('supermodel_legacy.supermodelLegacyGenerator', 'SupermodelLegacyGenerator'),
    }
}

_GENERATOR_MAP: Final[dict[str, tuple[str, str]]] = {
    'libretro': ('libretro.libretroGenerator', 'LibretroGenerator'),
    'ares': ('ares.ares_generator', 'AresGenerator'),
    'applewin': ('applewin.applewinGenerator', 'AppleWinGenerator'),
    'bigpemu': ('bigpemu.bigpemuGenerator', 'BigPEmuGenerator'),
    'bstone': ('bstone.bstoneGenerator', 'BstoneGenerator'),
    'catacombgl': ('catacombgl.catacombglGenerator', 'CatacombGLGenerator'),
    'cgenius': ('cgenius.cgeniusGenerator', 'CGeniusGenerator'),
    'clk': ('clk.clkGenerator', 'ClkGenerator'),
    'corsixth': ('corsixth.corsixthGenerator', 'CorsixTHGenerator'),
    'devilutionx': ('devilutionx.devilutionxGenerator', 'DevilutionXGenerator'),
    'dhewm3': ('dhewm3.dhewm3Generator', 'Dhewm3Generator'),
    'dolphin-emu': ('dolphin.dolphinGenerator', 'DolphinGenerator'),
    'dosbox': ('dosbox.dosboxGenerator', 'DosBoxGenerator'),
    'dosbox_staging': ('dosboxstaging.dosboxstagingGenerator', 'DosBoxStagingGenerator'),
    'dosboxx': ('dosboxx.dosboxxGenerator', 'DosBoxxGenerator'),
    'dxx-rebirth': ('dxx_rebirth.dxx_rebirthGenerator', 'DXX_RebirthGenerator'),
    'easyrpg': ('easyrpg.easyrpgGenerator', 'EasyRPGGenerator'),
    'ecwolf': ('ecwolf.ecwolfGenerator', 'ECWolfGenerator'),
    'eduke32': ('eduke32.eduke32Generator', 'EDuke32Generator'),
    'etlegacy': ('etlegacy.etlegacyGenerator', 'ETLegacyGenerator'),
    'fallout1-ce': ('fallout1.fallout1Generator', 'Fallout1Generator'),
    'fallout2-ce': ('fallout2.fallout2Generator', 'Fallout2Generator'),
    'gsplus': ('gsplus.gsplusGenerator', 'GSplusGenerator'),
    'gzdoom': ('gzdoom.gzdoomGenerator', 'GZDoomGenerator'),
    'hypseus-singe': ('hypseus_singe.hypseusSingeGenerator', 'HypseusSingeGenerator'),
    'ioquake3': ('ioquake3.ioquake3Generator', 'IOQuake3Generator'),
    'iortcw': ('iortcw.iortcwGenerator', 'IORTCWGenerator'),
    'jazz2-native': ('jazz2_native.jazz2_nativeGenerator', 'Jazz2_NativeGenerator'),
    'lindbergh-loader': ('lindbergh.lindberghGenerator', 'LindberghGenerator'),
    'melonds': ('melonds.melondsGenerator', 'MelonDSGenerator'),
    'model2emu': ('model2emu.model2emuGenerator', 'Model2EmuGenerator'),
    'mupen64plus': ('mupen.mupenGenerator', 'MupenGenerator'),
    'openjazz': ('openjazz.openjazzGenerator', 'OpenJazzGenerator'),
    'openjk': ('openjk.openjkGenerator', 'OpenJKGenerator'),
    'openjkdf2': ('openjkdf2.openjkdf2Generator', 'OpenJKDF2Generator'),
    'openmohaa': ('openmohaa.openmohaaGenerator', 'OpenMOHAAGenerator'),
    'ppsspp': ('ppsspp.ppssppGenerator', 'PPSSPPGenerator'),
    'scummvm': ('scummvm.scummvmGenerator', 'ScummVMGenerator'),
    'shadps4': ('shadps4.shadps4Generator', 'shadPS4Generator'),
    'theforceengine': ('theforceengine.theforceengineGenerator', 'TheForceEngineGenerator'),
    'thextech': ('thextech.thextechGenerator', 'TheXTechGenerator'),
    'tr1x': ('tr1x.tr1xGenerator', 'TR1XGenerator'),
    'tr2x': ('tr2x.tr2xGenerator', 'TR2XGenerator'),
    'vkquake': ('vkquake.vkquakeGenerator', 'VKQuakeGenerator'),
    'vkquake2': ('vkquake2.vkquake2Generator', 'VKQuake2Generator'),
    'vkquake3': ('ioquake3.ioquake3Generator', 'IOQuake3Generator'),
    'vpinball': ('vpinball.vpinballGenerator', 'VPinballGenerator'),
    'xash3d_fwgs': ('xash3d_fwgs.xash3dFwgsGenerator', 'Xash3dFwgsGenerator'),
    'xenia-canary': ('xenia.xeniaGenerator', 'XeniaGenerator'),
    'ymir': ('ymir.ymirGenerator', 'YmirGenerator'),
    'yquake2': ('yquake2.yquake2Generator', 'YQuake2Generator'),
    'tic80': ('tic80.tic80Generator', 'tic80Generator'),
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
    if (cores := _LEGACY_GENERATOR_MAP.get(emulator)) and core in cores:
        module_path, cls_name = cores[core]
    elif emulator in _GENERATOR_MAP:
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
