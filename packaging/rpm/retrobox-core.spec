# Spec for retrobox-core. The file tree is not built here: build-rpm.sh stages
# it with packaging/stage.sh (shared with the .deb and the install.sh tarball)
# and this spec only packs it. Placeholders (@...@) are filled by build-rpm.sh.
%global debug_package %{nil}
%global __os_install_post %{nil}
%global _build_id_links none

Name:           retrobox-core
Version:        @VERSION@
Release:        1
Summary:        Retrobox core: batocera-style backend for a Linux desktop
License:        GPL-2.0-only
URL:            https://github.com/RetroboxProject/retrobox-core
BuildArch:      noarch
Conflicts:      retrobox
@REQUIRES@
Recommends:     retrobox-emulationstation
Recommends:     retrobox-mangohud
Recommends:     python3-gamepadly
@RECOMMENDS@

%description
Port of the batocera backend stack (batocera-configgen) to a standard Linux
desktop. Writes emulator configuration automatically on game launch and
handles bezels, shaders and gamepad auto-configuration, to be used with the
retrobox-emulationstation frontend.

The project is installed under /opt/retrobox (read-only) with an optional
system-wide configuration layer in /etc/retrobox. User data (ROMs, saves,
BIOS) lives in ~/.local/share/retrobox and user settings in
~/.config/retrobox, never in /opt/retrobox.

The EmulationStation frontend (retrobox-emulationstation), the patched
MangoHud build (retrobox-mangohud) and the emulators are separate packages.

%install
cp -a %{stagedir}/. %{buildroot}/

%post
# Byte-compile the runtime: the install tree is read-only for users, so Python
# could never cache it on its own. Removed again in %preun.
if command -v python3 >/dev/null 2>&1; then
    python3 -m compileall -q /opt/retrobox/lib >/dev/null 2>&1 || :
fi
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules >/dev/null 2>&1 || :
    udevadm trigger --subsystem-match=input --subsystem-match=hidraw \
        --action=change >/dev/null 2>&1 || :
fi
:

%preun
# On removal (not upgrade) delete the .pyc files from %post, otherwise rpm
# cannot remove /opt/retrobox/lib (it doesn't know about them).
if [ "$1" -eq 0 ]; then
    find /opt/retrobox -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || :
fi
:

%postun
if [ "$1" -eq 0 ] && command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules >/dev/null 2>&1 || :
fi
:

%files
/opt/retrobox
%dir /etc/retrobox
%config(noreplace) /etc/retrobox/retrobox.ini
%dir /etc/retrobox/retrobox.ini.d
/usr/bin/retrobox
/usr/lib/udev/rules.d/64-retrobox.rules
/usr/share/applications/retrobox.desktop
/usr/share/icons/hicolor/scalable/apps/retrobox.svg
%license /usr/share/doc/retrobox-core/copyright

%changelog
* @CHANGELOG_DATE@ Manu Romero <manu4.2012@gmail.com> - @VERSION@-1
- Automated build
