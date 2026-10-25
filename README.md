# retrobox-core

A proof-of-concept port of the [batocera](https://github.com/batocera-linux/batocera.linux) backend stack to a standard Linux desktop (Debian / KDE Plasma / Wayland), using `batocera-configgen` as a base.

The goal is to have a batocera/Retrobat-like experience if paired with a compiled [batocera-emulationstation](https://github.com/batocera-linux/batocera-emulationstation) frontend, featuring automatic emulator configuration, bezels, shaders, controller mapping — without having to reboot to other OS.

## Motivation

Batocera is excellent as a dedicated gaming system, but it needs to be booted as a whole OS. A few years ago, I discovered Retrobat, but it is Windows-only (there are some ways to run it on Linux with Wine/Lutris, but not all emulators work). RetroDeck, EmuDeck and ES-DE doesn't have all the goodies Retrobat and Batocera have, such as auto gamepad config (the most important thing for me).

This project brings the parts that matter most to a desktop Linux installation:

- `batocera-configgen` writing emulator configs automatically on game launch
- Bezels work in Vulkan-powered emulators (and RetroArch no matter the graphics API) via a patched MangoHud build -- the same approach batocera uses.
- Shader support on libretro 
- Adapted controller autoconfiguration for RetroArch, Flycast, Dolphin, PCSX2, PPSSPP, Cemu, Ryujinx and Eden. More to come.

## Architecture

```
EmulationStation
    └── on game launch → emulatorlauncher.sh
            ├── sync_settings.py   (es_settings.cfg → temporal batocera.conf in the runtime dir)
            └── configgen          (writes emulator configs, launches game)
                    ├── batocera-resolution  (stub → kscreen-doctor)
                    ├── batocera-vulkan      (stub → vulkaninfo)
                    └── gamepadly (custom-made new solution for hotkeys and pad2key configs on supported emulators and platforms)
```

This repo can be cloned and used from anywhere, or installed from the `.deb` into `/opt/retrobox`. Paths have been adapted to replace the `/userdata` hierarchy: see [Paths](#paths).

## Key changes vs upstream batocera-configgen

### Paths

Configuration is layered, read-only code and writable user data are separate, and the layout is the same whichever way Retrobox was installed (`.deb`, `install.sh`, a checkout).

**Read-only install** (`/opt/retrobox`, the `install.sh` prefix, or a checkout) is never written to.

**Configuration layers**, lowest priority first. Each mirrors the `resources/` tree (`systems_config/`, `emu_features/`, `hooks/retrohook.d/`, ...) and a file with the same relative path replaces the one below it; extra files add systems/features/hooks:

1. `<install dir>/resources` — shipped defaults
2. `/etc/retrobox` — administrator (optional; `RETROBOX_SYSCONFDIR`)
3. `~/.config/retrobox` — user (`RETROBOX_CONFIGDIR`)

`retrobox.ini` is merged the same way, key by key: `/etc/retrobox/retrobox.ini`, `/etc/retrobox/retrobox.ini.d/*.ini`, `~/.config/retrobox/retrobox.ini`, `~/.config/retrobox/retrobox.ini.d/*.ini` (drop-ins in alphabetical order). Retrobox never writes these files: defaults live in code and the files only hold changes. The package ships a commented template in `/etc/retrobox/retrobox.ini`.

**User directories:**

| Directory | Default | Override | Holds |
|---|---|---|---|
| config | `~/.config/retrobox` | `RETROBOX_CONFIGDIR` | `retrobox.ini(.d)`, overrides of `resources/` (same tree), `emulators/<emu>/` (each emulator's `XDG_CONFIG_HOME`), `frontend/` (EmulationStation home), `pad2key/profiles/`, `hooks/` |
| data | `~/.local/share/retrobox` | `RETROBOX_DATADIR` | `roms/`, `saves/`, `bios/`, `themes/` (the shipped *iconic* is linked in), `music/`, `decorations/` (+ `decorations-default/`), `shaders/`, `emulators/` (installed binaries), `screenshots/`, `recordings/`, `cheats/`, `overlay/` |
| state | `~/.local/state/retrobox` | `RETROBOX_STATEDIR` | `logs/`, installer manifests |

`$XDG_CONFIG_HOME`, `$XDG_DATA_HOME` and `$XDG_STATE_HOME` are honoured. `roms`, `saves` and `bios` can be moved on their own from `[paths]` in `retrobox.ini` (`roms_dir`, `saves_dir`, `bios_dir`); the first value found in the layers wins.

`runtime/paths` is the single place where all of this is resolved. Shell scripts get the result as `RETROBOX_*` variables (`python3 -m runtime.paths` prints them, `--get section.key` reads a merged ini value; `setup/lib/paths.sh` loads them).

Compared with batocera:

| batocera | here |
|---|---|
| `/userdata` | data dir (see above) |
| `/userdata/system/configs/<emu>` | `~/.config/retrobox/emulators/<emu>` |
| `/userdata/bios`, `/userdata/saves`, `/userdata/roms` | `bios/`, `saves/`, `roms/` in the data dir (or wherever `[paths]` says) |
| `/var/run/*` | `$XDG_RUNTIME_DIR/retrobox` (per user, 0700; `RETROBOX_RUNTIME_DIR`) |
| `/usr/share/batocera` | `<install dir>/resources` |
| `/usr/share/batocera/evmapy` | `<install dir>/resources/pad2key/profiles` (user profiles: `~/.config/retrobox/pad2key/profiles`) |

Emulators that keep their binary and their config together (redream, supermodel, model2emu, xenia, x16emu) still use `~/.local/share/retrobox/emulators/<emu>`.

### Stubs for batocera-only binaries

batocera ships several system-specific binaries that don't exist on a standard Linux install. Replacements:

- **`batocera-resolution`** — reimplemented in bash using `kscreen-doctor` (KDE Wayland)
- **`batocera-vulkan`** — reimplemented using `vulkaninfo`
- **`batocera-mouse`** — no-op stub

### ES settings sync

Emulators read their settings from `batocera.conf` (key=value). EmulationStation on a standard install writes to `es_settings.cfg` (XML). A small Python script (`resources/emulatorlauncher/configgen/sync_settings.py`) translates between them before each game launch, using a temporal file. This will be worked around in the future to allow reading directly from the XML.

### RetroArch paths

RetroArch uses `~/.config/retroarch`. The configgen is adapted accordingly, including core options path, info files, and the `input_overlay` path for bezels.

### Controller handling: evdev → SDL

All `evdev/` references in `dolphinControllers.py` are replaced with `SDL/`, and hat input formatting is corrected for SDL. I have also improved handling of third-party "Pro Controller" gamepads.

### libretroConfig bezel fix

A missing call to `bezelsUtil.getBezelInfos()` in the `else` branch of `writeBezelConfig()` caused bezels to silently fail. Fixed.

### renderConfig None guard

`system.renderconfig` could be `None` when no `rendering-defaults.yml` is found. Added a fallback `or {}` to prevent `TypeError` on shader lookup.

### Emulators of a well-known Nvidia Tegra X1 powered console (Eden, Ryujinx)

Generators adapted from a third-party batocera package. Paths converted to this environment standard, AppImage-specific HOME handling resolved.

## New components

### Gamepadly

A replacement for evmapy that only requires `python3-sdl` and `python3-pygame` to run. It takes evmapy mappings generated in EmulationStation (or made by hand, since they are JSON) and is able to map every gamepad button to keyboard keys or shortcuts, as well as mouse events. It's used by the majority of emulators to send Alt+F4 with Hotkey+Start combo.

### Apps

A set of app-like shortcuts to a number of web streaming services, as well as Kodi Media Center.

Chrome or Firefox must be installed for these services to work (except for Kodi, which, well, requires Kodi LOL).

It's expected to add support for other browsers such as Brave, since all Chromium browsers offer the kiosk mode I'm using in this feature.

`gamepadly` is used to map the Player1 gamepad to bring control to the webpages:

* `Left Analog`: move mouse cursor.
* `B` button (SNES layout): left click.
* `A` button (SNES layout): go to previous webpage (sends `Alt+Left Arrow`)
* `Y` button (SNES layout): nothing -- TODO: I'm planning to implement access to KDE Plasma's native On-Screen Keyboard
* `X` button (SNES layout): nothing -- TODO: I want it as a screenshot button.
* `D-Pad`: arrow keys.
* `Start`: Play/Pause button on media players.
* `Select`: `Tab`
* `L1`: PageUp
* `R1`: PageDown
* `Hotkey+L1`: Previous media
* `Hotkey+R1`: Next media
* `Hotkey+Up`: Increase system volume (sends `KEY_VOLUMEUP`)
* `Hotkey+Down`: Decrease system volume (sends `KEY_VOLUMEDOWN`)
* `Hotkey+Start`: Exit and go back to EmulationStation

## Setup

### From a release (recommended)

**Debian / Ubuntu (.deb):**

```bash
sudo apt install ./retrobox-core_<version>_amd64.deb   # use apt, not dpkg -i: it pulls the dependencies
                                                      # installs into /opt/retrobox, /usr/bin/retrobox
```

**Fedora (.rpm):**

```bash
sudo dnf install ./retrobox-core-<version>.x86_64.rpm   # same layout as the .deb; vlc-libs (RPM Fusion) is only recommended
```

**Fedora (.rpm):**

```bash
sudo dnf install ./retrobox-core-<version>.x86_64.rpm   # same layout as the .deb; vlc-libs (RPM Fusion) is only recommended
```

**Any supported distro (install.sh):**

```bash
curl -fsSL https://github.com/manu-romero-411/retrobox-core/releases/latest/download/install.sh | bash
# options: --prefix DIR  --user  --version X.Y.Z  --with COMPONENT  --no-deps  --uninstall  (see --help)
```

It installs the same layout as the package: `/opt/retrobox` (or `/var/opt/retrobox` if `/opt` isn't writable, or `--prefix`), a `retrobox` launcher in `/usr/local/bin`, udev rules and the optional `/etc/retrobox`. Dependencies come from apt/dnf (`setup/deps/*.list`); on immutable systems (ostree) or with `--no-deps` the Python ones go into a virtualenv inside the install and the script prints the system libraries to layer (e.g. with `rpm-ostree install`). Without root, `--user` installs under `~/.local`.

### Components

The core is modular: EmulationStation (`retrobox-emulationstation`, repo of the same name), and later MangoHud, gamepadly... are separate packages that depend on `retrobox-core` and install into the same `/opt/retrobox` (EmulationStation: `/opt/retrobox/frontend`, command `retrobox-emulationstation`). With `install.sh` add them with `--with emulationstation`; each one is a `retrobox-<name>-linux-amd64.tar.gz` (+ `SHA256SUMS`) in the release of its own repo, containing a `retrobox/` directory (merged into the prefix) and optionally a `links` file (`<command> <path under the prefix>`) for the launchers. Components already installed are updated along with the core. `retrobox` warns at startup if EmulationStation is missing.

### From a checkout

1. Clone this repo and run `./retrobox.sh --setup` (installs the dependencies from `setup/deps/` with apt or dnf, the udev rules and the git submodules).
2. `./retrobox.sh --setup-util emulationstation` (and `mangohud`) to build them from source, or install the component packages.

Python dependencies for a virtualenv: `pip install -r requirements.txt`.

### Building the packages

```bash
packaging/deb/build-deb.sh           # dist/retrobox-core_<version>_amd64.deb
packaging/rpm/build-rpm.sh           # dist/retrobox-core-<version>-1.x86_64.rpm (needs rpmbuild)
packaging/tarball/build-tarball.sh   # dist/retrobox-core-linux-amd64.tar.gz + SHA256SUMS (the install.sh payload)
```

The GitHub Actions workflow builds the three, smoke-tests them in Ubuntu 24.04, Debian 13 and Fedora containers and, for `v*` tags, publishes them with `install.sh` as a release.

## Directory layout

Install directory (read-only):

```
<install dir>/                 # a checkout, or /opt/retrobox
├── retrobox.sh                # main executable (/usr/bin/retrobox in the .deb)
├── VERSION                    # (packages only)
├── runtime/                   # launcher, configgen, startup, paths
├── resources/                 # systems, emulator features, hooks, helpers
├── frontend/                  # EmulationStation binary, shipped theme
├── setup/                     # installers (emulators, utils, music, bezels) and deps/*.list
└── venv/                      # (install.sh on immutable systems only)
```

System and user directories (see [Paths](#paths)):

```
/etc/retrobox/                 # optional admin layer: retrobox.ini, retrobox.ini.d/, <resources tree overrides>
~/.config/retrobox/            # retrobox.ini(.d), overrides, hooks/, pad2key/, frontend/ (ES home)
└── emulators/<emu>/           # each emulator's XDG_CONFIG_HOME
~/.local/share/retrobox/
├── roms/  saves/  bios/       # moveable from retrobox.ini
├── themes/  music/            # iconic is linked in; add your own
├── decorations/               # your bezels (and --setup-bezel packs)
├── decorations-default/       # RetroBat bezels (retrobox.sh --setup-bezel retrobat-bezels)
├── emulators/                 # installed by retrobox.sh --setup-emulator
└── shaders/  screenshots/  recordings/  cheats/  overlay/
~/.local/state/retrobox/       # logs/, packages/ (installer manifests)
```

EmulationStation (`--setup-util emulationstation`) and MangoHud (`--setup-util mangohud`) are part of the install directory, so installing them into `/opt/retrobox` needs `sudo`.

## License

This project is a derivative of [batocera-configgen](https://github.com/batocera-linux/batocera.linux/tree/master/package/batocera/core/batocera-configgen), part of the `batocera.linux` project which is licensed under the GPLv2 License.

All modifications are also released under GPLv2. See [LICENSE](LICENSE).

