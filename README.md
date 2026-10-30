# retrobox-core

A proof-of-concept port of the [batocera](https://github.com/batocera-linux/batocera.linux) backend stack to a standard Linux desktop (Debian / KDE Plasma / Wayland), using `batocera-configgen` as a base.

The goal is to have a batocera/Retrobat-like experience if paired with a compiled [batocera-emulationstation](https://github.com/batocera-linux/batocera-emulationstation) frontend, featuring automatic emulator configuration, bezels, shaders, controller mapping — without having to reboot to other OS.

## Motivation

Batocera is excellent as a dedicated gaming system, but it needs to be booted as a whole OS. A few years ago, I discovered Retrobat, but it is Windows-only (there are some ways to run it on Linux with Wine/Lutris, but not all emulators work). RetroDeck, EmuDeck and ES-DE doesn't have all the goodies Retrobat and Batocera have, such as auto gamepad config (the most important thing for me).

This project brings the parts that matter most to a desktop Linux installation:

- `batocera-configgen` writing emulator configs automatically on game launch
- Bezels work in Vulkan-powered emulators (and RetroArch no matter the graphics API) via a patched MangoHud build -- the same approach batocera uses.
- Shader support on libretro 
- Adapted controller autoconfiguration for RetroArch, Flycast, Dolphin, PCSX2, PPSSPP, Cemu, Ryujinx, Eden and sm2-emu (Model 2). More to come.

## Architecture

```
EmulationStation (separate package)
    └── on game launch → bin/retrobox-launch      (python3 -m retrobox.launcher)
            └── configgen   (lib/retrobox/configgen: writes emulator configs, launches game)
                    ├── libexec/stubs/batocera-resolution  (stub → kscreen-doctor / wlr-randr / xrandr)
                    ├── libexec/stubs/batocera-vulkan      (stub → vulkaninfo)
                    └── gamepadly (system Python package: hotkeys and pad2key configs on supported emulators and platforms)
```

This repo can be cloned and used from anywhere, or installed from the `.deb` into `/opt/retrobox`. Paths have been adapted to replace the `/userdata` hierarchy: see [Paths](#paths).

## Key changes vs upstream batocera-configgen

### Paths

Configuration is layered, read-only code and writable user data are separate, and the layout is the same whichever way Retrobox was installed (`.deb`, `install.sh`, a checkout).

**Read-only install** (`/opt/retrobox`, the `install.sh` prefix, or a checkout) is never written to.

**Configuration layers**, lowest priority first. Each mirrors the `share/` tree (`systems_config/`, `emu_features/`, `hooks/retrohook.d/`, ...) and a file with the same relative path replaces the one below it; extra files add systems/features/hooks:

1. `<install dir>/share` — shipped defaults
2. `/etc/retrobox` — administrator (optional; `RETROBOX_SYSCONFDIR`)
3. `~/.config/retrobox` — user (`RETROBOX_CONFIGDIR`)

`retrobox.ini` is merged the same way, key by key: `/etc/retrobox/retrobox.ini`, `/etc/retrobox/retrobox.ini.d/*.ini`, `~/.config/retrobox/retrobox.ini`, `~/.config/retrobox/retrobox.ini.d/*.ini` (drop-ins in alphabetical order). Retrobox never writes these files: defaults live in code and the files only hold changes. The package ships a commented template in `/etc/retrobox/retrobox.ini`.

**User directories:**

| Directory | Default | Override | Holds |
|---|---|---|---|
| config | `~/.config/retrobox` | `RETROBOX_CONFIGDIR` | `retrobox.ini(.d)`, overrides of `share/` (same tree), `emulators/<emu>/` (each emulator's `XDG_CONFIG_HOME`), `frontend/` (EmulationStation home), `pad2key/profiles/`, `hooks/` |
| data | `~/.local/share/retrobox` | `RETROBOX_DATADIR` | `roms/`, `saves/`, `bios/`, `themes/`, `music/`, `decorations/` (+ `decorations-default/`), `shaders/`, `emulators/` (installed binaries), `screenshots/`, `recordings/`, `cheats/`, `overlay/` |
| state | `~/.local/state/retrobox` | `RETROBOX_STATEDIR` | `logs/`, installer manifests |

`$XDG_CONFIG_HOME`, `$XDG_DATA_HOME` and `$XDG_STATE_HOME` are honoured. The data and state directories can also be set from `[paths]` in `retrobox.ini` (`data_dir`, `state_dir`; the environment variables win), and `roms`, `saves` and `bios` can be moved on their own (`roms_dir`, `saves_dir`, `bios_dir`); the last layer that sets a key wins. A value may be quoted and may end in ` # comment`. If a configured `roms_dir`/`saves_dir`/`bios_dir` is not a readable directory, Retrobox warns on stderr and uses the default one (unless `autocorrect_paths = false`).

`lib/retrobox/paths` is the single place where all of this is resolved. Shell scripts get the result as `RETROBOX_*` variables (`PYTHONPATH=<install dir>/lib python3 -m retrobox.paths` prints them, `--get section.key` reads a merged ini value; `tools/lib/paths.sh` loads them).

Compared with batocera:

| batocera | here |
|---|---|
| `/userdata` | data dir (see above) |
| `/userdata/system/configs/<emu>` | `~/.config/retrobox/emulators/<emu>` |
| `/userdata/bios`, `/userdata/saves`, `/userdata/roms` | `bios/`, `saves/`, `roms/` in the data dir (or wherever `[paths]` says) |
| `/var/run/*` | `$XDG_RUNTIME_DIR/retrobox` (per user, 0700; `RETROBOX_RUNTIME_DIR`) |
| `/usr/share/batocera` | `<install dir>/share` |
| `/usr/share/batocera/evmapy` | `<install dir>/share/pad2key/profiles` (user profiles: `~/.config/retrobox/pad2key/profiles`) |

Emulators that keep their binary and their config together (redream, supermodel, model2emu) still use `~/.local/share/retrobox/emulators/<emu>`.

### Stubs for batocera-only binaries

batocera ships several system-specific binaries that don't exist on a standard Linux install. Replacements (in `libexec/stubs/`):

- **`batocera-resolution`** — reimplemented in bash using `kscreen-doctor` (KDE Wayland)
- **`batocera-vulkan`** — reimplemented using `vulkaninfo`
- **`batocera-mouse`** — no-op stub

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

A replacement for evmapy, now a standalone project ([`gamepadly`](https://github.com/RetroboxProject/gamepadly), package `python3-gamepadly`, recommended by the core packages; install it separately). It only requires `pygame` and `evdev`. It takes evmapy mappings generated in EmulationStation (or made by hand, since they are JSON) and is able to map every gamepad button to keyboard keys or shortcuts, as well as mouse events. It's used by the majority of emulators to send Alt+F4 with Hotkey+Start combo.

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
sudo apt install ./retrobox-core_<version>_all.deb   # use apt, not dpkg -i: it pulls the dependencies
                                                      # installs into /opt/retrobox, /usr/bin/retrobox
```

**Fedora (.rpm):**

```bash
sudo dnf install ./retrobox-core-<version>-1.noarch.rpm   # same layout as the .deb; vlc-libs (RPM Fusion) is only recommended
```

**Fedora (.rpm):**

```bash
sudo dnf install ./retrobox-core-<version>-1.noarch.rpm   # same layout as the .deb; vlc-libs (RPM Fusion) is only recommended
```

**Any supported distro (install.sh):**

```bash
curl -fsSL https://github.com/RetroboxProject/retrobox-core/releases/latest/download/install.sh | bash
# options: --prefix DIR  --user  --version X.Y.Z  --with COMPONENT  --no-deps  --uninstall  (see --help)
```

It installs the same layout as the package: `/opt/retrobox` (or `/var/opt/retrobox` if `/opt` isn't writable, or `--prefix`), a `retrobox` launcher in `/usr/local/bin`, udev rules and the optional `/etc/retrobox`. Dependencies come from apt/dnf (`tools/deps/*.list`, shipped in the tarball's `extras/`, not in the installed tree); on immutable systems (ostree) or with `--no-deps` the Python ones go into a virtualenv inside the install and the script prints the system libraries to layer (e.g. with `rpm-ostree install`). Without root, `--user` installs under `~/.local`.

### Components

The core is modular. EmulationStation ([`retrobox-emulationstation`](https://github.com/RetroboxProject/retrobox-emulationstation)) and the patched MangoHud ([`retrobox-mangohud`](https://github.com/RetroboxProject/retrobox-mangohud)) are separate projects; [`gamepadly`](https://github.com/RetroboxProject/gamepadly) (pad-to-keyboard mapper, a regular Python package) is too. `retrobox-core` ships no frontend, no MangoHud, no theme (not even *iconic*) and compiles nothing.

- **Packages (.deb/.rpm):** `retrobox-core` only *recommends* `retrobox-emulationstation`, `retrobox-mangohud` and `python3-gamepadly`; install them with the package manager. Those packages are built per architecture (amd64, arm64); the core is architecture-independent (`_all.deb`, `noarch.rpm`).
- **install.sh:** `--with emulationstation` / `--with mangohud` downloads the component's own `install.sh` (the one at the root of its repository, or `--with NAME=<URL or local path>`) and runs it:

  ```
  install.sh --prefix DIR --bin-dir DIR [--no-deps] [--user]
  install.sh --uninstall --prefix DIR --bin-dir DIR
  ```

  with `RETROBOX_PREFIX`, `RETROBOX_BIN_DIR`, `RETROBOX_ARCH` (`amd64`, `arm64` or the raw `uname -m`) and `RETROBOX_CORE_VERSION` in the environment. The contract for a component installer: pick the build for `RETROBOX_ARCH` (and say so clearly if there is none), write only below `--prefix` (plus its commands into `--bin-dir`), and remove everything it installed on `--uninstall`. The same files go in the packages as in the install: ES in `<prefix>/frontend/`, MangoHud in `<prefix>/libexec/mangohud/` (`bin/mangohud` and `share/vulkan/implicit_layer.d/`), with no installers, docs or helper scripts left in the tree. `install.sh` keeps a copy of each component installer in `<prefix>/.components/<name>/` to update it with the core and to remove it on `--uninstall`.

`retrobox` warns at startup if EmulationStation is missing; without the patched MangoHud it falls back to a system-wide `mangohud`.

### From a checkout

1. Clone this repo and run `retrobox --setup` (installs the dependencies from `tools/deps/` with apt or dnf and the udev rules; gamepadly is installed separately with its own `install.sh` or `python3-gamepadly`).
2. EmulationStation, MangoHud and the themes (e.g. *iconic*) are separate components: install their packages, or their `install.sh` into the checkout (`install.sh --with ...` does it for a normal install).

Python dependencies for a virtualenv: `pip install -r requirements.txt`.

### Building the packages

```bash
packaging/deb/build-deb.sh           # dist/retrobox-core_<version>_all.deb
packaging/rpm/build-rpm.sh           # dist/retrobox-core-<version>-1.noarch.rpm (needs rpmbuild)
packaging/tarball/build-tarball.sh   # dist/retrobox-core-all.tar.gz + SHA256SUMS (the install.sh payload)
```

The GitHub Actions workflow builds the three, smoke-tests them in Ubuntu 24.04, Debian 13 and Fedora containers and, for `v*` tags, publishes them with `install.sh` as a release.

## Directory layout

Install directory (read-only):

```
<install dir>/                 # a checkout, or /opt/retrobox: the repo IS the installed tree
├── bin/                       # commands: retrobox (/usr/bin/retrobox in the packages), retrobox-launch, retrobox-exit, retrobox-screenshot...
├── lib/
│   └── retrobox/              # the Python package: paths, startup, launcher, configgen, utils
├── libexec/                   # internal helpers: emuconfig/ (per-emulator config launchers), stubs/, mangohud/ (from the retrobox-mangohud component)
├── share/                     # read-only defaults (the lowest config layer): systems_config/, emu_features/, configgen/, hooks/, pad2key/, labwc/...
├── system/                    # files for the host: udev rules, kernel/sysctl tuning
├── tools/                     # installers (emulators, utils, music, bezels) and deps/*.list
├── frontend/                  # EmulationStation seed config; the frontend and themes are separate packages
├── VERSION                    # (packages only)
└── venv/                      # (install.sh on immutable systems only)
```

Only in the repository (not installed): `dev/` (helper scripts and notes for developers), `packaging/`, `install.sh`, `.github/`, `.vscode/`. Python modules are run with `PYTHONPATH=<install dir>/lib`: `python3 -m retrobox.startup` (what `bin/retrobox` runs) and `python3 -m retrobox.launcher` (`bin/retrobox-launch`).

System and user directories (see [Paths](#paths)):

```
/etc/retrobox/                 # optional admin layer: retrobox.ini, retrobox.ini.d/, <share tree overrides>
~/.config/retrobox/            # retrobox.ini(.d), overrides, hooks/, pad2key/, frontend/ (ES home)
└── emulators/<emu>/           # each emulator's XDG_CONFIG_HOME
~/.local/share/retrobox/
├── roms/  saves/  bios/       # moveable from retrobox.ini
├── themes/  music/            # your themes and menu music
├── decorations/               # your bezels (and --setup-bezel packs)
├── decorations-default/       # RetroBat bezels (retrobox --setup-bezel retrobat-bezels)
├── emulators/                 # installed by retrobox --setup-emulator
└── shaders/  screenshots/  recordings/  cheats/  overlay/
~/.local/state/retrobox/       # logs/, packages/ (installer manifests)
```

Components install into the same directory, so installing them into `/opt/retrobox` needs `sudo`.

## License

This project is a derivative of [batocera-configgen](https://github.com/batocera-linux/batocera.linux/tree/master/package/batocera/core/batocera-configgen), part of the `batocera.linux` project which is licensed under the GPLv2 License.

All modifications are also released under GPLv2. See [LICENSE](LICENSE).

