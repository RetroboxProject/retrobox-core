# retrobox-core

A port of the [batocera](https://github.com/batocera-linux/batocera.linux) backend stack to a standard Linux desktop (Debian, Ubuntu or Fedora; KDE Plasma, labwc or X11), using `batocera-configgen` as a base.

The goal is to have a batocera/Retrobat-like experience if paired with [retrobox-emulationstation](https://github.com/RetroboxProject/retrobox-emulationstation), a build of batocera-emulationstation, featuring automatic emulator configuration, bezels, shaders, controller mapping — without having to reboot to other OS.

## Motivation

Batocera is excellent as a dedicated gaming system, but it needs to be booted as a whole OS. A few years ago, I discovered Retrobat, but it is Windows-only (there are some ways to run it on Linux with Wine/Lutris, but not all emulators work). RetroDeck, EmuDeck and ES-DE doesn't have all the goodies Retrobat and Batocera have, such as auto gamepad config (the most important thing for me).

This project brings the parts that matter most to a desktop Linux installation:

- `batocera-configgen` writing emulator configs automatically on game launch
- Bezels: RetroArch draws them itself; the other emulators get them through a patched MangoHud build, the same approach batocera uses.
- Shaders on RetroArch and ares.
- Controller autoconfiguration for RetroArch, ares, Azahar, Cemu, Dolphin, Eden, Flycast, MAME, melonDS, PCSX2, PPSSPP, Redream, RPCS3, Ryujinx, ScummVM and sm2-emu (Model 2).
- Gamepad hotkeys (Hotkey+Start to exit, etc.) on every emulator through [gamepadly](https://github.com/RetroboxProject/gamepadly).

## Architecture

```
EmulationStation (separate package)
    └── on game launch → bin/retrobox-launch      (python3 -m retrobox.launcher)
            ├── configgen   (lib/retrobox/configgen: writes emulator configs, builds the command)
            │       ├── libexec/stubs/batocera-resolution  (stub → kscreen-doctor / wlr-randr / xrandr)
            │       └── libexec/stubs/batocera-vulkan      (stub → vulkaninfo)
            └── gamepadly   (separate Python package: hotkeys and pad2key profiles while the game runs)
```

This repo can be cloned and used from anywhere, or installed into `/opt/retrobox` with the `.deb`, the `.rpm` or `install.sh`. Paths have been adapted to replace the `/userdata` hierarchy: see [Paths](#paths).

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

Other `[core]` keys: `ignore_systems` (systems hidden from the menu, e.g. `gba,psp`) and `steam_sync`, `heroic_sync`, `lutris_sync`: on every start, add the games installed in that launcher to its system (`.steam`, `.heroic`, `.lynx` entries). Each one takes:

| Value | Entries go to (and the ES system reads from) |
|---|---|
| `none` (default) | nothing is synced; the system reads `<roms_dir>/<launcher>` |
| `on-base-dir` | always `<data dir>/roms/<launcher>`, wherever `roms_dir` points |
| `follow-roms-dir` | `<roms_dir>/<launcher>` (which may be `<data dir>/roms` or anywhere else) |

They replace the old `--pcgames-sync` flag, which is now ignored with a warning; the `true`/`false` values of v0.0.25 still work (as `follow-roms-dir`/`none`), with a warning.

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

- **`batocera-resolution`**: bash wrapper over `kscreen-doctor` (KDE Wayland), `wlr-randr` (labwc and other wlroots compositors) or `xrandr` (X11)
- **`batocera-vulkan`**: reimplemented with `vulkaninfo`
- **`batocera-keyboard`**, **`getLocalXDisplay`**: minimal replacements for the configgen calls that expect them

### Emulator configuration

Each emulator gets its own `XDG_CONFIG_HOME` under `~/.config/retrobox/emulators/<emu>` (RetroArch: `~/.config/retrobox/emulators/retroarch/retroarch/retroarch.cfg`), so nothing in your regular `~/.config` is touched. Controller configs use SDL device names instead of batocera's evdev ones where the emulator supports it (Dolphin, Azahar...).

The Eden and Ryujinx generators were adapted from a third-party batocera package.

## New components

### Gamepadly

A replacement for evmapy, now a standalone project ([`gamepadly`](https://github.com/RetroboxProject/gamepadly), package `python3-gamepadly`, recommended by the core packages; install it separately). The launcher starts it with every game: it reads evmapy-style JSON profiles (`share/pad2key/profiles/*.keys`, overridable in `~/.config/retrobox/pad2key/profiles`) and maps gamepad buttons to keys, shortcuts and mouse events, e.g. Hotkey+Start to Alt+F4. Without it the game still runs, but with no gamepad hotkeys.

### Bezels and aspect ratios

A bezel is looked up in this order, in your `decorations/<set>` first and then in `decorations-default/<set>`: the game (`games/<system>/<rom>.png`, then `games/<rom>.png`), the system (`systems/<system>.png`, with its alternative decoration and language variants) and `default.png`. Before any of those, the same order is tried with the screen's aspect ratio appended to the name: on a 16:10 screen, `systems/megadrive_16_10.png` beats `games/megadrive/Sonic.png`, and `games/fbneo/truxton2_16_10.png` beats both. The suffix is `_<width>_<height>` of a common ratio (`1_1`, `5_4`, `4_3`, `3_2`, `16_10`, `16_9`, `21_9`, `32_9`; a 2560x1080 screen still counts as `21_9`) or of the screen's exact one, and the bezel's `.info`, `.lay` and `.zip` carry it too (`megadrive_16_10.info`). A bezel made for another ratio is stretched or narrowed to the screen, unless *Stretch bezels* is turned off for the game.

### Emulator setup screen

When a game needs an emulator that has an installer in `tools/emulators/` but isn't installed, a full-screen dialog (`python3 -m retrobox.emusetup`) offers to install it, shows the installer's output (and takes keyboard input, e.g. a sudo password) and launches the game afterwards. It borrows the fonts of the current EmulationStation theme (the menu font for the message and buttons, the help font for the hint line; EmulationStation's default font if the theme sets none, and a system font if a theme font lacks a glyph), follows EmulationStation's language (or the system locale; English, Spanish, Catalan, Galician, Portuguese, French, Italian, German, Dutch, Polish and Russian) and uses the application menu's logo and window class (`retrobox-emulationstation`, the same as EmulationStation and the `StartupWMClass` of `retrobox.desktop`). Its background is `share/emusetup/background.png`, replaceable from `/etc/retrobox` or `~/.config/retrobox` like any shared file. The same screen shows the downloads done before EmulationStation starts (default theme, bezels and shaders); when there is no theme yet, it uses the first of Noto Sans, Liberation Sans and DejaVu Sans that is installed. Its confirm and back buttons are EmulationStation's: the south button confirms by default (Xbox layout) and the east one with *Switch confirm & cancel buttons* on (Nintendo layout); RetroArch's menus follow the same option (`menu_swap_ok_cancel_buttons`, written on every launch).

**Updating an emulator:** hold the **hotkey** while a game starts (the hotkey button of any controller, as mapped in EmulationStation, or **Shift** on a keyboard) and the same screen offers to install that game's emulator again, to get its latest version. The installer then works in a separate folder (`<data dir>/emulators/.update-<name>/`) and the installed emulator is only replaced once the new one is complete: its configuration and data are carried over (the `config` folder, files the new version doesn't ship, and a few known files such as Redream's `redream.cfg` or Supermodel's `NVRAM`), and if anything fails, or the screen is closed halfway, the installed version is left untouched. Either way the game starts afterwards. Keep it held until the screen appears. Controllers are read through SDL, with the button numbers of `es_input.cfg`; keyboards are read from their evdev devices, which needs the `input` group (the packages and `install.sh` add you to it); `RETROBOX_REINSTALL_EMULATOR=1` in the environment has the same effect.

### Apps

An `apps` system with app-like shortcuts to web streaming services (opened in Chrome or Firefox kiosk mode, so one of them must be installed) and Kodi (which needs Kodi).

`gamepadly` maps the player 1 gamepad so the web pages can be used without a mouse (`share/pad2key/profiles/apps.keys`; buttons in SNES layout):

| Input | Action |
|---|---|
| Left stick / right stick | Move the mouse cursor / scroll |
| D-pad | Arrow keys |
| B | Left click |
| A | Back (`Alt+Left`) |
| Start / Select | Play/Pause / `Tab` |
| L1 / R1 | Page Up / Page Down |
| Hotkey+L1 / Hotkey+R1 | Previous / next media |
| Hotkey+Up / Hotkey+Down | System volume up / down |
| Hotkey+Y | `Meta+O` (on-screen keyboard shortcut) |
| Hotkey+X | `Meta+SysRq` (screenshot) |
| Hotkey+Start | Exit back to EmulationStation |

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

**Any supported distro (install.sh):**

```bash
curl -fsSL https://github.com/RetroboxProject/retrobox-core/releases/latest/download/install.sh | bash
# options: --prefix DIR  --user  --version X.Y.Z  --with COMPONENT  --no-deps  --uninstall  (see --help)
```

It installs the same layout as the package: `/opt/retrobox` (or `/var/opt/retrobox` if `/opt` isn't writable, or `--prefix`), a `retrobox` launcher in `/usr/local/bin`, the application menu entry and its icon in `/usr/local/share` (the packages use `/usr/share`; `--user`, `~/.local/share`), udev rules and the optional `/etc/retrobox`. Dependencies come from apt/dnf (`tools/deps/*.list`, shipped in the tarball's `extras/`, not in the installed tree); on immutable systems (ostree) or with `--no-deps` the Python ones go into a virtualenv inside the install and the script prints the system libraries to layer (e.g. with `rpm-ostree install`). Without root, `--user` installs under `~/.local`.

### Components

The core is modular. EmulationStation ([`retrobox-emulationstation`](https://github.com/RetroboxProject/retrobox-emulationstation)), the patched MangoHud ([`retrobox-mangohud`](https://github.com/RetroboxProject/retrobox-mangohud)) and the labwc gaming session on its own TTY ([`retrobox-labwc`](https://github.com/RetroboxProject/retrobox-labwc)) are separate projects; [`gamepadly`](https://github.com/RetroboxProject/gamepadly) (pad-to-keyboard mapper, a regular Python package) is too. `retrobox-core` ships no frontend, no MangoHud, no theme and compiles nothing. If EmulationStation finds no theme at all (neither in `<install dir>/frontend/themes` nor in `<data dir>/themes`), `retrobox` downloads the latest commit of [*es-theme-iconic*](https://github.com/manu-creative-411/es-theme-iconic) into `<data dir>/themes` before starting; `retrobox --update-default-theme` downloads it again (update, or reinstall if it was removed) and then starts. The [RetroBat bezels](https://github.com/RetroBat-Official/retrobat-bezels) (the default decorations) are downloaded the same way into `<data dir>/decorations-default`, and [Retrobox's shaders](https://github.com/RetroboxProject/retrobox-shaders) into the shaders folder (`<data dir>/shaders`, or `SHADERS_DIR`), but only on the first start (the bezels, only if their folder holds no files yet); `retrobox --update-default-bezels` / `--update-default-shaders` get them again. The bezels replace their folder, which belongs to Retrobox; the shaders are merged into theirs, so your own shaders there are kept. All these downloads show their progress on the setup screen (see *Emulator setup screen*), can be cancelled with B / Esc, never replace a working copy with a broken one, and if they fail Retrobox says so and starts anyway.

- **Packages (.deb/.rpm):** `retrobox-core` only *recommends* `retrobox-emulationstation`, `retrobox-mangohud` and `python3-gamepadly` (and *suggests* `retrobox-labwc`); install them with the package manager. Those packages are built per architecture (amd64, arm64); the core is architecture-independent (`_all.deb`, `noarch.rpm`).
- **install.sh:** `--with emulationstation` / `--with mangohud` / `--with labwc` downloads the component's own `install.sh` (the one at the root of its repository, or `--with NAME=<URL or local path>`) and runs it:

  ```
  install.sh --prefix DIR --bin-dir DIR [--no-deps] [--user]
  install.sh --uninstall --prefix DIR --bin-dir DIR
  ```

  with `RETROBOX_PREFIX`, `RETROBOX_BIN_DIR`, `RETROBOX_ARCH` (`amd64`, `arm64` or the raw `uname -m`) and `RETROBOX_CORE_VERSION` in the environment. The contract for a component installer: pick the build for `RETROBOX_ARCH` (and say so clearly if there is none), write only below `--prefix` (plus its commands into `--bin-dir`), and remove everything it installed on `--uninstall`. The same files go in the packages as in the install: ES in `<prefix>/frontend/`, MangoHud in `<prefix>/libexec/mangohud/` (`bin/mangohud` and `share/vulkan/implicit_layer.d/`), with no installers, docs or helper scripts left in the tree. `install.sh` keeps a copy of each component installer in `<prefix>/.components/<name>/` to update it with the core and to remove it on `--uninstall`.

`retrobox` warns at startup if EmulationStation is missing; without the patched MangoHud it falls back to a system-wide `mangohud`.

### From a checkout

1. Clone this repo and run `retrobox --setup` (installs the dependencies from `tools/deps/` with apt or dnf and the udev rules; gamepadly is installed separately with its own `install.sh` or `python3-gamepadly`).
2. EmulationStation, MangoHud and the themes (e.g. *iconic*) are separate components: install their packages, or their `install.sh` into the checkout (`install.sh --with ...` does it for a normal install). Without any theme, *iconic* is downloaded on the first start (see above).

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
├── bin/                       # commands: retrobox (/usr/bin/retrobox in the packages), retrobox-launch, retrobox-emukill, retrobox-exit, retrobox-screenshot...
├── lib/
│   └── retrobox/              # the Python package: paths, startup, launcher, configgen, utils
├── libexec/                   # internal helpers: emuconfig/ (per-emulator config launchers), stubs/, mangohud/ (from the retrobox-mangohud component)
├── share/                     # read-only defaults (the lowest config layer): systems_config/, emu_features/, configgen/, hooks/, pad2key/...
├── tools/                     # installers (emulators/, music/, decorations/), deps/*.list, setup scripts
├── frontend/                  # EmulationStation seed config (the retrobox-emulationstation component installs here)
├── VERSION                    # (packages only)
└── venv/                      # (install.sh on immutable systems only)
```

Only in the repository (not installed): `dev/` (helper scripts and notes for developers), `packaging/`, `system/` (installed into `/usr/lib/udev` and polkit instead), `install.sh`, `.github/`, `.vscode/`. Python modules are run with `PYTHONPATH=<install dir>/lib`: `python3 -m retrobox.startup` (what `bin/retrobox` runs) and `python3 -m retrobox.launcher` (`bin/retrobox-launch`).

System and user directories (see [Paths](#paths)):

```
/etc/retrobox/                 # optional admin layer: retrobox.ini, retrobox.ini.d/, <share tree overrides>
~/.config/retrobox/            # retrobox.ini(.d), overrides, hooks/, pad2key/, frontend/ (ES home)
└── emulators/<emu>/           # each emulator's XDG_CONFIG_HOME
~/.local/share/retrobox/
├── roms/  saves/  bios/       # moveable from retrobox.ini
├── themes/  music/            # your themes and menu music
├── decorations/               # your bezels (and --setup-bezel packs)
├── decorations-default/       # RetroBat bezels (first start; retrobox --update-default-bezels)
├── emulators/                 # installed by retrobox --setup-emulator
├── shaders/                   # Retrobox shaders (first start; retrobox --update-default-shaders) and yours
└── screenshots/  recordings/  cheats/  overlay/
~/.local/state/retrobox/       # logs/, packages/ (installer manifests)
```

Components install into the same directory, so installing them into `/opt/retrobox` needs `sudo`.

### Logs

Every Retrobox tool, bash or Python, prints the same kind of line: `[INFO]`, `[ OK ]`, `[WARN]` or `[ERR ]`, then a `yyyy-mm-dd_hh:mm:ss` timestamp and the message (colored on a terminal; `NO_COLOR=1` turns colors off). The terminal shows `INFO` and above; `RETROBOX_DEBUG=1` adds the `[DBG ]` lines. The files in `~/.local/state/retrobox/logs/` (`retrobox-startup.log`, `retrobox-launch.log`, rotated) always hold everything, with the source location of each line.

## License

This project is a derivative of [batocera-configgen](https://github.com/batocera-linux/batocera.linux/tree/master/package/batocera/core/batocera-configgen), part of the `batocera.linux` project which is licensed under the GPLv2 License.

All modifications are also released under GPLv2. See [LICENSE](LICENSE).

