from __future__ import annotations

import filecmp
import logging
import os
import shutil
import stat
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING

from .model2emuPaths import M2EMU_EMUDIR, M2EMU_RESOURCES, M2EMU_WINEPREFIX, MODEL2_ROMS

from ... import Command
from retrobox.paths import configure_emulator, mkdir_if_not_exists
from ...exceptions import RetroboxException
from ...controller import generate_sdl_game_controller_config
from ...utils.configparser import CaseSensitiveConfigParser
from ..Generator import Generator

if TYPE_CHECKING:
    from ...typedefs import HotkeysContext

_logger = logging.getLogger(__name__)

class Model2EmuGenerator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "model2emu",
            "keys": { "exit": ["KEY_LEFTALT", "KEY_F4"] }
        }

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        import subprocess

        # 1. Definición de rutas
        mkdir_if_not_exists(M2EMU_WINEPREFIX)
        mkdir_if_not_exists(M2EMU_EMUDIR)

        # 2. The emulator itself is not shipped in the package: tools/emulators/model2emu.sh
        # downloads it into the WINEPREFIX. Fail early with a clear message if it is missing.
        if not (M2EMU_EMUDIR / "emulator_multicpu.exe").exists():
            raise RetroboxException(
                f"Model 2 emulator not found in {M2EMU_EMUDIR}: run 'retrobox --setup-emulator model2emu'"
            )
        ini_file = M2EMU_EMUDIR / "EMULATOR.INI"
        if ini_file.exists():
            ini_file.chmod(ini_file.stat().st_mode | stat.S_IRWXO)

        # 3. Configurar entorno de ejecución base
        env = os.environ.copy()
        env["WINEPREFIX"] = str(M2EMU_WINEPREFIX)
        env["WINEDEBUG"] = "-all"
        env["WINEDLLOVERRIDES"] = "d3d9=n,b" # Fuerza el uso de DXVK

        # 4. Instalación inicial de dependencias
        winetricks_done = M2EMU_WINEPREFIX / ".winetricks.done"
        if not winetricks_done.exists():
            _logger.info("Instalando dependencias de Wine y DXVK...")
            subprocess.run([
                "winetricks", "-q", "d3dx9", "d3dcompiler_42", "d3dcompiler_43", "d3dx9_42", "d3dx9_43", "xact", "xact_x64"
            ], env=env, check=True)
            winetricks_done.touch()

        # 5. Optional per-game scripts and input profiles, only when a resources
        # directory is present (it is not part of the package).
        if M2EMU_RESOURCES.is_dir():
            copy_updated_files(M2EMU_RESOURCES / "scripts", M2EMU_EMUDIR / "scripts")

            xinput_cfg_done = M2EMU_WINEPREFIX / ".xinput_cfg.done"
            if not xinput_cfg_done.exists():
                cfg_dest = M2EMU_EMUDIR / "CFG"
                cfg_dest.mkdir(parents=True, exist_ok=True)
                copy_updated_files(M2EMU_RESOURCES / "CFG", cfg_dest)
                xinput_cfg_done.touch()

        # .resolve() convierte "../roms/model2" en the real roms path (o la ruta real de Debian)
        #absolute_rom_dir = Path(os.path.realpath(rom)).parent.resolve()
        
        # Reemplazar barras de Linux (/) a Windows (\) para el emulador
        rom_directory_win = PureWindowsPath(MODEL2_ROMS)

        # Cambiar al directorio de trabajo del emulador
        os.chdir(M2EMU_EMUDIR)

        # 6. Preparar comando base
        commandArray: list[str | Path] = ["wine", M2EMU_EMUDIR / "emulator_multicpu.exe"]
        if not configure_emulator(rom):
            commandArray.extend([rom.stem])

        # 7. Modificación del archivo EMULATOR.INI
        configFileName = M2EMU_EMUDIR / "EMULATOR.INI"
        Config = CaseSensitiveConfigParser(interpolation=None)
        if configFileName.is_file():
            Config.read(configFileName)

        # Asegurar sección limpia
        if Config.has_section("RomDirs"):
            Config.remove_section("RomDirs")
        Config.add_section("RomDirs")
        Config.set("RomDirs", "Dir1", f"Z:{rom_directory_win}")

        # Si iteras subdirectorios adicionales, aplica la misma lógica:
        dirnum = 1
        if MODEL2_ROMS.exists():
            for possibledir in MODEL2_ROMS.iterdir():
                if possibledir.is_dir() and possibledir.name not in ["images", "media"]:
                    dirnum += 1
                    subdir_win = PureWindowsPath(possibledir.resolve())
                    Config.set("RomDirs", f"Dir{dirnum}", f"Z:{subdir_win}")

        # Opciones de Renderizado
        Config.set("Renderer", "FullScreenWidth", str(gameResolution["width"]))
        Config.set("Renderer", "FullScreenHeight", str(gameResolution["height"]))
        Config.set("Renderer", "FullMode", system.config.get("model2_renderRes", "4"))
        Config.set("Renderer", "AutoFull", "1")
        Config.set("Renderer", "ForceSync", "1")

        # 8. LUA script tweaks (widescreen, scanlines)
        lua_file_path = M2EMU_EMUDIR / "scripts" / f"{rom.stem}.lua"
        if lua_file_path.exists():
            modify_lua_widescreen(lua_file_path, system.config.get_bool("model2_ratio"))
            modify_lua_scanlines(lua_file_path, system.config.get_bool("model2_scanlines"))

        # Configuración general y de entrada
        Config.set("Renderer", "FakeGouraud", system.config.get("model2_fakeGouraud", "0"))
        Config.set("Renderer", "Bilinear", system.config.get("model2_bilinearFiltering", "1"))
        Config.set("Renderer", "Trilinear", system.config.get("model2_trilinearFiltering", "0"))
        Config.set("Renderer", "FilterTilemaps", system.config.get("model2_filterTilemaps", "0"))
        Config.set("Renderer", "ForceManaged", system.config.get("model2_forceManaged", "0"))
        Config.set("Renderer", "AutoMip", system.config.get("model2_enableMIP", "0"))
        Config.set("Renderer", "MeshTransparency", system.config.get("model2_meshTransparency", "0"))
        Config.set("Renderer", "FSAA", system.config.get("model2_fullscreenAA", "0"))
        Config.set("Input", "UseRawInput", system.config.get("model2_useRawInput", "0"))
        
        if crosshairs := system.config.get("model2_crossHairs"):
            Config.set("Renderer", "DrawCross", crosshairs)
        else:
            Config.set("Renderer", "DrawCross", "0")

        Config.set("Input", "XInput", system.config.get_bool("model2_xinput", return_values=("1", "0")))
        Config.set("Input", "EnableFF", system.config.get_bool("model2_forceFeedback", return_values=("1", "0")))

        # Forzar la desactivación de red o simulación local en EMULATOR.INI
        if not Config.has_section("Network"):
            Config.add_section("Network")
        
        # 0 = Desactivado/Simulado para que no se quede colgado esperando nodos
        Config.set("Network", "RxPort", "0")
        Config.set("Network", "TxPort", "0")

        # Guardar EMULATOR.INI
        with configFileName.open('w') as configfile:
            Config.write(configfile)

        # 9. Añadir controles de SDL al entorno
        env.update({
            "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(playersControllers),
            "SDL_JOYSTICK_HIDAPI": "0",
        })

        #env.update({"PULSE_LATENCY_MSEC": "20"})

        return Command.Command(array=commandArray, env=env)

def modify_lua_widescreen(file_path: Path, condition: bool) -> None:
    with file_path.open('r') as lua_file:
        lines = lua_file.readlines()

    modified_lines: list[str] = []
    for line in lines:
        if condition:
            if "wide=false" in line:
                modified_line = line.replace("wide=false", "wide=true")
            else:
                modified_line = line  # No change
            modified_lines.append(modified_line)
        else:
            if "wide=true" in line:
                modified_line = line.replace("wide=true", "wide=false")
            else:
                modified_line = line  # No change
            modified_lines.append(modified_line)

    with file_path.open('w') as lua_file:
        lua_file.writelines(modified_lines)

def modify_lua_scanlines(file_path: Path, condition: bool) -> None:
    with file_path.open('r') as lua_file:
        original_lines = lua_file.readlines()

    modified_lines: list[str] = []
    scanlines_line_added = False

    for line in original_lines:
        if "TestSurface = Video_CreateSurfaceFromFile" in line:
            modified_lines.append(line)
            if "Options.scanlines.value=" not in line and not scanlines_line_added:
                modified_lines.append(f'\tOptions.scanlines.value={"1" if condition else "0"}\r\n')
                scanlines_line_added = True
        elif "Options.scanlines.value=" in line:
            if condition:
                modified_lines.append(line.replace("Options.scanlines.value=0", "Options.scanlines.value=1"))
            else:
                modified_lines.append(line.replace("Options.scanlines.value=1", "Options.scanlines.value=0"))
        else:
            modified_lines.append(line)

    with file_path.open('w') as lua_file:
        lua_file.writelines(modified_lines)


def copy_updated_files(source_path: Path, destination_path: Path) -> None:
    if not source_path.is_dir():
        return
    destination_path.mkdir(parents=True, exist_ok=True)
    dcmp = filecmp.dircmp(source_path, destination_path)

    # Copy missing files and files needing updates from source to destination
    for name in dcmp.left_only + dcmp.diff_files:
        src = source_path / name
        dst = destination_path / name

        if src.is_dir():
            shutil.copytree(src, dst)
            _logger.debug("Copying directory %s to %s", src, dst)
        else:
            shutil.copy2(src, dst)
            _logger.debug("Copying file %s to %s", src, dst)
