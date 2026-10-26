import logging
import os
from pathlib import Path
import sys

from retrobox.paths import SCREENSHOTS

from .edenPaths import EDEN_DATA, SWITCH_DLC_DIR, SWITCH_ROMS, SWITCH_UPDATE_DIR
from .eden_controllers import _eden_write_controller_config
from ...utils.configparser import CaseSensitiveRawConfigParser
_logger = logging.getLogger(__name__)

def read_file_lower(path):
    try:
        return Path(path).read_text().strip().lower()
    except FileNotFoundError:
        return ""

def is_steamdeck():
    pname = read_file_lower("/sys/class/dmi/id/product_name")
    if pname in ("jupiter", "galileo") or "steam deck" in pname:
        return True
    return False

def _eden_write_config(edenConfigFile, edenConfigTemplateFile, system, playersControllers, emulator):
    _logger.warning("DEBUG: writeYuzuConfig() llamado, nplayers=%d", len(playersControllers))        # pads

    # ini file
    eden_config = CaseSensitiveRawConfigParser()

    if os.path.exists(edenConfigFile):
        eden_config.read(edenConfigFile)
    # Sinon première création depuis template
    elif os.path.exists(edenConfigTemplateFile):
        eden_config.read(edenConfigTemplateFile)
        # The template carries placeholders instead of fixed paths.
        tokens = {
            "@EDEN_DATA@": str(EDEN_DATA),
            "@SWITCH_ROMS@": str(SWITCH_ROMS),
            "@SCREENSHOTS@": str(SCREENSHOTS),
        }
        for section in eden_config.sections():
            for key, value in eden_config.items(section):
                new = value
                for token, real in tokens.items():
                    new = new.replace(token, real)
                if new != value:
                    eden_config.set(section, key, new)

# UI section
    if not eden_config.has_section("UI"):
        eden_config.add_section("UI")

    eden_config.set(
        "UI", "enable_discord_presence",
        system.config.get_bool('discordrpc', True, return_values=("true", "false"))
    )

    eden_config.set("UI", "enable_discord_presence\\default", "true")

    eden_config.set("UI", "check_for_updates_on_start", "false")
    eden_config.set("UI", "check_for_updates_on_start\\default", "false")

    eden_config.set("UI", "UIGameList\\cache_game_list", "true")
    eden_config.set("UI", "UIGameList\\cache_game_list\\default", "true")

    # Common external path (dlc/update)
    eden_config.set("UI", "Paths\\external_content_dirs\\size", "2")
    eden_config.set("UI", "Paths\\external_content_dirs\\1\\path", f"{SWITCH_UPDATE_DIR}")
    eden_config.set("UI", "Paths\\external_content_dirs\\2\\path", f"{SWITCH_DLC_DIR}")

    #citron shortcuts
    eden_config.set("UI", "Shortcuts\\shortcuts\\size", "1")#adjust to number of shortcut sets
    #exit citron
    eden_config.set("UI", "Shortcuts\\shortcuts\\1\\name", "Exit citron")
    eden_config.set("UI", "Shortcuts\\shortcuts\\1\\group", "Main Window")
    eden_config.set("UI", "Shortcuts\\shortcuts\\1\\keyseq", "Ctrl+Q")
    eden_config.set("UI", "Shortcuts\\shortcuts\\1\\controller_keyseq", "Minus+Plus")
    eden_config.set("UI", "Shortcuts\\shortcuts\\1\\context", "1")
    eden_config.set("UI", "Shortcuts\\shortcuts\\1\\repeat", "false")

    #exit eden
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Exit%20eden\\KeySeq\\default", "false")
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Exit%20eden\\KeySeq", "Ctrl+Q")
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Exit%20eden\\Controller_KeySeq\\default", "false")
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Exit%20eden\\Controller_KeySeq", "Home+Plus")
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Exit%20eden\\Context\\default", "true")
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Exit%20eden\\Context", "1")

    #fullscreen eden
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Fullscreen\\KeySeq\\default", "false")
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Fullscreen\\KeySeq", "F11")
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Fullscreen\\Controller_KeySeq\\default", "false")
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Fullscreen\\Controller_KeySeq", "Home+B")
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Fullscreen\\Context\\default", "true")
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Fullscreen\\Context", "1")

    #pause eden
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Continue\\Pause%20Emulation\\KeySeq\\default", "false")
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Continue\\Pause%20Emulation\\KeySeq", "F4")
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Continue\\Pause%20Emulation\\Controller_KeySeq\\default", "false")
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Continue\\Pause%20Emulation\\Controller_KeySeq", "")
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Continue\\Pause%20Emulation\\Context\\default", "true")
    eden_config.set("UI", "Shortcuts\\Main%20Window\\Continue\\Pause%20Emulation\\Context", "1")

    eden_config.set("UI", "Paths\\romsPath", str(SWITCH_ROMS))
    eden_config.set("UI", "Paths\\gamedirs\\1\\deep_scan", "true")
    eden_config.set("UI", "Paths\\gamedirs\\1\\deep_scan\\default", "false")
    eden_config.set("UI", "Paths\\gamedirs\\1\\expanded", "true")
    eden_config.set("UI", "Paths\\gamedirs\\1\\expanded\\default", "true")
    eden_config.set("UI", "Paths\\gamedirs\\1\\path", str(SWITCH_ROMS))
    eden_config.set("UI", "Paths\\gamedirs\\size", "3")

    # Interface language (citron)
    if system.isOptSet('eden_intlanguage'):
        eden_config.set("UI", "Paths\\language", system.config["eden_intlanguage"])
        eden_config.set("UI", "Paths\\language\\default", "false")
    else:
        eden_config.set("UI", "Paths\\language", "en")
        eden_config.set("UI", "Paths\\language\\default", "true")

    # Single Window Mode
    if system.isOptSet('single_window'):
        eden_config.set("UI", "singleWindowMode", system.config["single_window"])
        eden_config.set("UI", "singleWindowMode\\default", "false")
    else:
        eden_config.set("UI", "singleWindowMode", "true")
        eden_config.set("UI", "singleWindowMode\\default", "true")

    # User Profile select on boot
    if system.isOptSet('user_profile'):
        eden_config.set("UI", "select_user_on_boot", system.config["user_profile"])
        eden_config.set("UI", "select_user_on_boot\\default", "false")
    else:
        eden_config.set("UI", "select_user_on_boot", "true")
        eden_config.set("UI", "select_user_on_boot\\default", "true")

    # Skip Citron animation/message
    eden_config.set("UI", "showIntroAnimation", "false")
    eden_config.set("UI", "showIntroAnimation\\default", "false")
    eden_config.set("UI", "farewellShown", "true")
    eden_config.set("UI", "farewellShown\\default", "false")

    # Confirm exit off
    eden_config.set("UI", "confirmStop", "2")
    eden_config.set("UI", "confirmStop\\default", "false")

# Core section
    if not eden_config.has_section("Core"):
        eden_config.add_section("Core")

    # Multicore
    if system.isOptSet('multicore'):
        eden_config.set("Core", "use_multi_core", system.config["multicore"])
        eden_config.set("Core", "use_multi_core\\default", "false")
    else:
        eden_config.set("Core", "use_multi_core", "true")
        eden_config.set("Core", "use_multi_core\\default", "true")

    # Memory layout
    if system.isOptSet('eden_memory_layout'):
        eden_config.set("Core", "memory_layout_mode", system.config["eden_memory_layout"])
        eden_config.set("Core", "memory_layout_mode\\default", "false")
    else:
        eden_config.set("Core", "memory_layout_mode", "0")
        eden_config.set("Core", "memory_layout_mode\\default", "true")

# Renderer section
    if not eden_config.has_section("Renderer"):
        eden_config.add_section("Renderer")

    # Extended Dynamic State Fix for V43 ZEN3
    if is_steamdeck():
        eden_config.set("Renderer", "extended_dynamic_state", "0")
        eden_config.set("Renderer", "extended_dynamic_state\\default", "false")
    # Aspect ratio
    if system.isOptSet('eden_ratio'):
        eden_config.set("Renderer", "aspect_ratio", system.config["eden_ratio"])
        eden_config.set("Renderer", "aspect_ratio\\default", "false")
    else:
        eden_config.set("Renderer", "aspect_ratio", "0")
        eden_config.set("Renderer", "aspect_ratio\\default", "true")

    # Graphical backend
    if system.isOptSet('gfxbackend'):
        eden_config.set("Renderer", "backend", system.config.get("gfxbackend"))
        eden_config.set("Renderer", "backend\\default", "false")
    else:
        eden_config.set("Renderer", "backend", "1")
        eden_config.set("Renderer", "backend\\default", "true")

    # Async Shader compilation
    if system.isOptSet('async_shaders'):
        eden_config.set("Renderer", "use_asynchronous_shaders", system.config["async_shaders"])
        eden_config.set("Renderer", "use_asynchronous_shaders\\default", "false")
    else:
        eden_config.set("Renderer", "use_asynchronous_shaders", "false")
        eden_config.set("Renderer", "use_asynchronous_shaders\\default", "true")

    # Assembly shaders
    if system.isOptSet('shaderbackend'):
        eden_config.set("Renderer", "shader_backend", system.config["shaderbackend"])
        eden_config.set("Renderer", "shader_backend\\default", "false")
    else:
        eden_config.set("Renderer", "shader_backend", "0")
        eden_config.set("Renderer", "shader_backend\\default", "true")

    # Async Gpu Emulation
    if system.isOptSet('async_gpu'):
        eden_config.set("Renderer", "use_asynchronous_gpu_emulation", system.config["async_gpu"])
        eden_config.set("Renderer", "use_asynchronous_gpu_emulation\\default", "false")
    else:
        eden_config.set("Renderer", "use_asynchronous_gpu_emulation", "true")
        eden_config.set("Renderer", "use_asynchronous_gpu_emulation\\default", "true")

    # NVDEC Emulation
    if system.isOptSet('nvdec_emu'):
        eden_config.set("Renderer", "nvdec_emulation", system.config["nvdec_emu"])
        eden_config.set("Renderer", "nvdec_emulation\\default", "false")
    else:
        eden_config.set("Renderer", "nvdec_emulation", "2")
        eden_config.set("Renderer", "nvdec_emulation\\default", "true")

    # Gpu Accuracy
    if system.isOptSet('gpuaccuracy'):
        eden_config.set("Renderer", "gpu_accuracy", system.config["gpuaccuracy"])
    else:
        eden_config.set("Renderer", "gpu_accuracy", "1")
    eden_config.set("Renderer", "gpu_accuracy\\default", "false")

    # Vsync
    if system.isOptSet('vsync'):
        eden_config.set("Renderer", "use_vsync", system.config["vsync"])
        eden_config.set("Renderer", "use_vsync\\default", "false")
        if system.config["vsync"] == "2":
            eden_config.set("Renderer", "use_vsync\\default", "true")
    else:
        eden_config.set("Renderer", "use_vsync", "1")
        eden_config.set("Renderer", "use_vsync\\default", "false")

    # Gpu cache garbage collection
    if system.isOptSet('gpu_cache_gc'):
        eden_config.set("Renderer", "use_caches_gc", system.config["gpu_cache_gc"])
    else:
        eden_config.set("Renderer", "use_caches_gc", "false")
    eden_config.set("Renderer", "use_caches_gc\\default", "false")

    # Max anisotropy
    if system.isOptSet('anisotropy'):
        eden_config.set("Renderer", "max_anisotropy", system.config["anisotropy"])
        eden_config.set("Renderer", "max_anisotropy\\default", "false")
    else:
        eden_config.set("Renderer", "max_anisotropy", "0")
        eden_config.set("Renderer", "max_anisotropy\\default", "true")

    # Fullscreen mode
    if system.isOptSet('fullscreen_mode'):
        eden_config.set("Renderer", "fullscreen_mode", system.config["fullscreen_mode"])
        eden_config.set("Renderer", "fullscreen_mode\\default", "false")
    else:
        eden_config.set("Renderer", "fullscreen_mode", "1")
        eden_config.set("Renderer", "fullscreen_mode\\default", "true")

    # Resolution scaler
    if system.isOptSet('resolution_scale'):
        print ("Use Resolution Scale for Eden :",system.config["resolution_scale"], file=sys.stderr)
        eden_config.set("Renderer", "resolution_setup", system.config["resolution_scale"])
        eden_config.set("Renderer", "resolution_setup\\default", "false")
    else:
        eden_config.set("Renderer", "resolution_setup", "2")
        eden_config.set("Renderer", "resolution_setup\\default", "true")

    # Scaling filter
    if system.isOptSet('scale_filter'):
        eden_config.set("Renderer", "scaling_filter", system.config["scale_filter"])
        eden_config.set("Renderer", "scaling_filter\\default", "false")
    else:
        eden_config.set("Renderer", "scaling_filter", "1")
        eden_config.set("Renderer", "scaling_filter\\default", "true")

    # FSR Quality
    if system.isOptSet('fsr_quality'):
        eden_config.set("Renderer", "fsr2_quality_mode", system.config["fsr_quality"])
        eden_config.set("Renderer", "fsr2_quality_mode\\default", "false")
    else:
        eden_config.set("Renderer", "fsr2_quality_mode", "0")
        eden_config.set("Renderer", "fsr2_quality_mode\\default", "true")

    # Anti aliasing method
    if system.isOptSet('aliasing_method'):
        eden_config.set("Renderer", "anti_aliasing", system.config["aliasing_method"])
        eden_config.set("Renderer", "anti_aliasing\\default", "false")
    else:
        eden_config.set("Renderer", "anti_aliasing", "0")
        eden_config.set("Renderer", "anti_aliasing\\default", "true")

    #ASTC Decoding Method
    if system.isOptSet('accelerate_astc'):
        eden_config.set("Renderer", "accelerate_astc", system.config["accelerate_astc"])
        eden_config.set("Renderer", "accelerate_astc\\default", "false")
    else:
        eden_config.set("Renderer", "accelerate_astc", "1")
        eden_config.set("Renderer", "accelerate_astc\\default", "true")

    # ASTC Texture Recompression
    if system.isOptSet('astc_recompression'):

        eden_config.set("Renderer", "astc_recompression", system.config["astc_recompression"])
        eden_config.set("Renderer", "astc_recompression\\default", "false")
        if system.config["astc_recompression"] == "0":
            eden_config.set("Renderer", "use_vsync\\default", "true")
        eden_config.set("Renderer", "async_astc", "false")
        eden_config.set("Renderer", "async_astc\\default", "true")
    else:
        eden_config.set("Renderer", "astc_recompression", "0")
        eden_config.set("Renderer", "astc_recompression\\default", "true")
        eden_config.set("Renderer", "async_astc", "false")
        eden_config.set("Renderer", "async_astc\\default", "true")

# Cpu Section
    if not eden_config.has_section("Cpu"):
        eden_config.add_section("Cpu")

    # Cpu Accuracy
    if system.isOptSet('cpuaccuracy'):
        eden_config.set("Cpu", "cpu_accuracy", system.config["cpuaccuracy"])
        eden_config.set("Cpu", "cpu_accuracy\\default", "false")
    else:
        eden_config.set("Cpu", "cpu_accuracy", "0")
        eden_config.set("Cpu", "cpu_accuracy\\default", "true")

# System section
    if not eden_config.has_section("System"):
        eden_config.add_section("System")

    # Language
    if system.isOptSet('language'):
        eden_config.set("System", "language_index", system.config["language"])
        eden_config.set("System", "language_index\\default", "false")
    else:
        eden_config.set("System", "language_index", "1")
        eden_config.set("System", "language_index\\default", "true")

    # Audio Mode
    if system.isOptSet('audio_mode'):
        eden_config.set("System", "sound_index", system.config["audio_mode"])
        eden_config.set("System", "sound_index\\default", "false")
    else:
        eden_config.set("System", "sound_index", "1")
        eden_config.set("System", "sound_index\\default", "true")

    # Region
    if system.isOptSet('region'):
        eden_config.set("System", "region_index", system.config["region"])
        eden_config.set("System", "region_index\\default", "false")
    else:
        eden_config.set("System", "region_index", "1")
        eden_config.set("System", "region_index\\default", "true")

    # Dock Mode
    if system.isOptSet('dock_mode'):
        if system.config["dock_mode"] == "1":
            eden_config.set("System", "use_docked_mode", "1")
            eden_config.set("System", "use_docked_mode\\default", "true")
        elif system.config["dock_mode"] == "0":
            eden_config.set("System", "use_docked_mode", "0")
            eden_config.set("System", "use_docked_mode\\default", "false")
    else:
        eden_config.set("System", "use_docked_mode", "1")
        eden_config.set("System", "use_docked_mode\\default", "true")

    eden_config = _eden_write_controller_config(system, playersControllers, emulator, eden_config)

# telemetry section
    if not eden_config.has_section("WebService"):
        eden_config.add_section("WebService")
    eden_config.set("WebService", "enable_telemetry", "false")
    eden_config.set("WebService", "enable_telemetry\\default", "false")
    eden_config.set("WebService", "enable_auto_update_check", "false")
    eden_config.set("WebService", "enable_auto_update_check\\default", "false")

# Services section
    if not eden_config.has_section("Services"):
        eden_config.add_section("Services")
    eden_config.set("Services", "bcat_backend", "none")
    eden_config.set("Services", "bcat_backend\\default", "none")

    ### update the configuration file
    if not os.path.exists(os.path.dirname(edenConfigFile)):
        os.makedirs(os.path.dirname(edenConfigFile))

    with open(edenConfigFile, 'w') as configfile:
        eden_config.write(configfile)
