#!/usr/bin/env bash
# setup/utils/emulationstation.sh — build & install batocera-emulationstation
# from source, applying the RetroBox patch set (KDE-friendly quit/suspend/
# shutdown handling, safer gamelist cursor handling, custom window title,
# etc.) and enabling the ScreenScraper Dev API login, mirroring the flags
# from the original build.sh:
#
#   cmake -B build \
#     -DCEC=OFF -DGL=ON -DGLES=OFF -DGLES2=OFF \
#     -DCMAKE_BUILD_TYPE=Release -DBATOCERA=OFF \
#     -DSCREENSCRAPER_DEV_LOGIN="${SCREENSCRAPER_DEV_LOGIN}"
#
# Invoked by setup/setup.sh's setup_util() as:
#   bash setup/utils/emulationstation.sh -s     (source build)
#   bash setup/utils/emulationstation.sh -u     (uninstall)
#
# i.e. via `retrobox.sh --setup-util emulationstation`.
#
# Unlike a system-wide utility (see mangohud.sh), the binary and its data
# tree are installed directly into frontend/, next to retrobox.sh — no
# /usr/local, no sudo for the install step itself (only for the build
# dependencies). Every path is derived from this script's own location, so
# there's nothing to hardcode: this works the same regardless of where the
# retrobox checkout lives on disk.
#
# What -s does:
#   1. Removes any previous from-source install done by this same script.
#   2. Clones batocera-linux/batocera-emulationstation at ${ES_REF} (default:
#      master; override the env var to pin a tag/branch/commit).
#   3. Applies the bundled RetroBox patch (embedded below, so this script
#      has no extra .patch file to ship alongside it).
#   4. Installs build dependencies (dnf or apt).
#   5. Configures with CMake using the flags above, with ScreenScraper's dev
#      login baked in from $SCREENSCRAPER_DEV_LOGIN.
#   6. Builds natively with `cmake --build -j$(nproc)`.
#   7. Copies the resulting binary into frontend/ (as "emulationstation")
#      and syncs resources/ + locale/ alongside it, tracking every
#      file touched in a manifest so -u can remove exactly that later
#      without disturbing frontend/themes, frontend/music, etc.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
# shellcheck source=../lib/log.sh
source "${SCRIPT_DIR}/../lib/log.sh"

RETROBOX_ROOTDIR="$(cd "${SCRIPT_DIR}/../.." >/dev/null 2>&1 && pwd -P)"
FRONTEND_DIR="${RETROBOX_ROOTDIR}/frontend"

MANIFEST_FILE="${RETROBOX_ROOTDIR}/.retrobox_emulationstation.manifest"

# EmulationStation lives inside the Retrobox install tree (where the
# retrobox-emulationstation package puts it), so this needs write access to it.
if [[ ! -w "${FRONTEND_DIR}" || ! -w "${RETROBOX_ROOTDIR}" ]]; then
    log_err "${RETROBOX_ROOTDIR} is not writable by this user. Run: sudo retrobox --setup-util emulationstation"
    exit 1
fi
VERSION_FILE="${RETROBOX_ROOTDIR}/.retrobox_emulationstation.version"

ES_GIT_URL="https://github.com/batocera-linux/batocera-emulationstation.git"
ES_REF="${ES_REF:-master}"                      # tag / branch / commit to build
SCREENSCRAPER_DEV_LOGIN="${SCREENSCRAPER_DEV_LOGIN:-}"

WORKDIR="${TMPDIR:-/tmp}/retrobox-emulationstation-build"
SRC_DIR="${WORKDIR}/batocera-emulationstation"
BUILD_DIR="${SRC_DIR}/build"
PATCH_FILE="${WORKDIR}/retrobox.patch"

BIN_NAME="${BIN_NAME:-emulationstation}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

detect_pkg_manager() {
    if command -v dnf >/dev/null 2>&1; then
        echo dnf
    elif command -v apt-get >/dev/null 2>&1; then
        echo apt
    else
        echo unknown
    fi
}
PKG_MGR="$(detect_pkg_manager)"

as_root() {
    if [[ "${EUID}" -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

# ---------------------------------------------------------------------------
# Remove any previous install done by this script
# ---------------------------------------------------------------------------
# No sudo here: everything this script writes lives inside FRONTEND_DIR,
# which is part of the user's own retrobox checkout.

uninstall_from_manifest() {
    [[ -f "${MANIFEST_FILE}" ]] || { log_info "No install manifest to undo."; return 0; }
    log_info "Removing files listed in ${MANIFEST_FILE}..."
    tac "${MANIFEST_FILE}" | while IFS= read -r path; do
        [[ -e "${path}" || -L "${path}" ]] || continue
        rm -f "${path}" 2>/dev/null || rmdir "${path}" 2>/dev/null || true
    done
    rm -f "${MANIFEST_FILE}" "${VERSION_FILE}"
}

remove_existing_install() {
    if [[ -f "${MANIFEST_FILE}" ]]; then
        log_warn "A previous from-source install was detected — cleaning it up before rebuilding."
        uninstall_from_manifest
    fi
}

# ---------------------------------------------------------------------------
# Build dependencies
# ---------------------------------------------------------------------------
# Matches the libraries batocera-emulationstation's CMakeLists expects for a
# desktop-Linux build with CEC=OFF (no libcec needed) and GL=ON (no GLES).

install_build_deps() {
    log_info "Installing build dependencies (${PKG_MGR})..."
    case "${PKG_MGR}" in
        dnf)
            as_root dnf install -y \
                cmake ninja-build gcc gcc-c++ git make pkgconf-pkg-config \
                SDL2-devel freeimage-devel freetype-devel \
                libcurl-devel mesa-libGL-devel \
                boost-devel boost-filesystem boost-system boost-date-time boost-locale \
                pugixml-devel rapidjson-devel \
                vlc-devel alsa-lib-devel openssl-devel \
                gettext rsync
            ;;
        apt)
            as_root apt-get update
            as_root apt-get install -y \
                cmake ninja-build build-essential git pkg-config \
                libsdl2-dev libfreeimage-dev libfreetype6-dev \
                libcurl4-openssl-dev libgl1-mesa-dev \
                libboost-system-dev libboost-filesystem-dev \
                libboost-date-time-dev libboost-locale-dev \
                libpugixml-dev rapidjson-dev \
                libvlc-dev libvlccore-dev vlc-plugin-base \
                libasound2-dev libssl-dev \
                gettext rsync
            ;;
        *)
            log_warn "Unrecognized package manager; install cmake, ninja, SDL2, FreeImage, FreeType, curl, Boost (system/filesystem/date_time/locale), pugixml, rapidjson, libvlc, ALSA and OpenSSL (dev packages) manually."
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Fetch source
# ---------------------------------------------------------------------------

fetch_source() {
    rm -rf "${SRC_DIR}"
    log_info "Cloning batocera-emulationstation (${ES_REF})..."
    if git clone --quiet --recurse-submodules --depth 1 --branch "${ES_REF}" \
        "${ES_GIT_URL}" "${SRC_DIR}" 2>/dev/null; then
        return
    fi
    # ES_REF isn't a branch/tag (e.g. a raw commit sha) — fall back to a full
    # clone and check it out explicitly.
    log_warn "\"${ES_REF}\" isn't a branch/tag name — doing a full clone to check it out."
    git clone --quiet --recurse-submodules "${ES_GIT_URL}" "${SRC_DIR}"
    (cd "${SRC_DIR}" && git checkout --quiet "${ES_REF}" && git submodule update --init --recursive)
}

# ---------------------------------------------------------------------------
# RetroBox patch (embedded so this script has no external dependencies)
# ---------------------------------------------------------------------------

write_patch_file() {
    mkdir -p "${WORKDIR}"
    cat > "${PATCH_FILE}" <<'RETROBOX_PATCH_EOF'
diff --git a/.gitignore b/.gitignore
index c85af5817..982decd39 100644
--- a/.gitignore
+++ b/.gitignore
@@ -53,3 +53,7 @@ CPackSourceConfig.cmake
 /.vs/
 *.sqlite
 .DS_Store
+
+locale/
+locale/*
+build.sh
diff --git a/es-app/src/ApiSystem.cpp b/es-app/src/ApiSystem.cpp
index 60f0433cc..a84554a63 100644
--- a/es-app/src/ApiSystem.cpp
+++ b/es-app/src/ApiSystem.cpp
@@ -591,8 +591,7 @@ bool ApiSystem::launchKodi(Window *window)
 {
 	LOG(LogDebug) << "ApiSystem::launchKodi";
 
-	std::string commandline = InputManager::getInstance()->configureEmulators();
-	std::string command = "batocera-kodi " + commandline;
+	std::string command = "kodi";
 
 	ApiSystem::launchExternalWindow_before(window);
 
@@ -2122,8 +2121,7 @@ bool ApiSystem::isScriptingSupported(ScriptId script)
 #endif
 		break;
 	case ApiSystem::KODI:
-		executables.push_back("kodi");
-		break;
+		return executeScript("command -v kodi > /dev/null 2>&1");
 	case ApiSystem::WIFI:
 		executables.push_back("batocera-wifi");
 		break;
@@ -2159,7 +2157,8 @@ bool ApiSystem::isScriptingSupported(ScriptId script)
 		executables.push_back("batocera-padsinfo");
 		break;
 	case ApiSystem::EVMAPY:
-		executables.push_back("evmapy");
+		//executables.push_back("evmapy");
+		return true;
 		break;
 	case ApiSystem::BATOCERAPREGAMELISTSHOOK:
 		executables.push_back("batocera-preupdate-gamelists-hook");
@@ -2186,7 +2185,7 @@ bool ApiSystem::isScriptingSupported(ScriptId script)
 		executables.push_back("batocera-upgrade-torrent");
 		break;
 	case ApiSystem::SUSPEND:
-		return (Utils::FileSystem::exists("/usr/sbin/pm-suspend") && Utils::FileSystem::exists("/usr/bin/pm-is-supported") && executeScript("/usr/bin/pm-is-supported --suspend"));
+		return (Utils::FileSystem::exists("/usr/bin/systemctl"));
 	case ApiSystem::VERSIONINFO:
 		executables.push_back("batocera-version");
 		break;
@@ -2706,7 +2705,7 @@ bool ApiSystem::emuKill()
 void ApiSystem::suspend()
 {
 	LOG(LogDebug) << "ApiSystem::suspend";
-	executeScript("/usr/bin/batocera-shutdown gui");
+	executeScript("/usr/bin/systemctl suspend");
 }
 
 void ApiSystem::replugControllers_sindenguns()
diff --git a/es-app/src/guis/GuiMenu.cpp b/es-app/src/guis/GuiMenu.cpp
index 71d3c2419..d7529e405 100644
--- a/es-app/src/guis/GuiMenu.cpp
+++ b/es-app/src/guis/GuiMenu.cpp
@@ -218,11 +218,11 @@ GuiMenu::GuiMenu(Window *window, bool animate) : GuiComponent(window), mMenu(win
 		addEntry(_("UNLOCK USER INTERFACE MODE").c_str(), true, [this] { exitKidMode(); }, "iconAdvanced");
 	}
 
-#ifdef WIN32
+//#ifdef WIN32
 	addEntry(_("QUIT"), !Settings::getInstance()->getBool("ShowOnlyExit") || !Settings::getInstance()->getBool("ShowExit"), [this] { openQuitMenu(); }, "iconQuit");
-#else
-	addEntry(_("QUIT").c_str(), true, [this] { openQuitMenu(); }, "iconQuit");
-#endif
+//#else
+	//addEntry(_("QUIT").c_str(), true, [this] { openQuitMenu(); }, "iconQuit");
+//#endif
 	
 	addChild(&mMenu);
 	addVersionInfo();
@@ -1468,6 +1468,7 @@ void GuiMenu::openSystemSettings()
 	});
 
 	// Keyboard layout & variant
+
 #if !WIN32
 	
 	std::string curLayout = SystemConf::getInstance()->get("system.kblayout");
@@ -1480,7 +1481,7 @@ void GuiMenu::openSystemSettings()
 	auto keyboard_variant = std::make_shared<OptionListComponent<std::string>>(window, _("KEYBOARD VARIANT"), false);
 
 	// Populate Layouts
-	auto layouts = getScriptOutput("/usr/bin/batocera-keyboard list-layouts");
+	auto layouts = getScriptOutput("batocera-keyboard list-layouts");
 	bool layoutFound = false;
 	
 	for (const auto& l : layouts)
@@ -1499,7 +1500,7 @@ void GuiMenu::openSystemSettings()
 		bool noneSelected = (curVariant == "none" || curVariant.empty());
 		keyboard_variant->add(_("NONE"), "none", noneSelected);
 
-		auto variants = getScriptOutput("/usr/bin/batocera-keyboard list-variants " + layoutCode);
+		auto variants = getScriptOutput("batocera-keyboard list-variants " + layoutCode);
 		bool variantFound = false;
 		for (const auto& v : variants)
 		{
@@ -1521,7 +1522,7 @@ void GuiMenu::openSystemSettings()
 		keyboard_variant->clear();
 		keyboard_variant->add(_("NONE"), "none", true);
 		
-		auto variants = getScriptOutput("/usr/bin/batocera-keyboard list-variants " + newLayout);
+		auto variants = getScriptOutput("batocera-keyboard list-variants " + newLayout);
 		for (const auto& v : variants)
 		{
 			keyboard_variant->add(v.second, v.first, false);
@@ -1541,7 +1542,7 @@ void GuiMenu::openSystemSettings()
 			std::string selLayout = keyboard_layout->getSelected();
 			std::string selVariant = keyboard_variant->getSelected();
 			
-			std::string cmd = "/usr/bin/batocera-keyboard set \"" + selLayout + "\" \"" + selVariant + "\"";
+			std::string cmd = "batocera-keyboard set \"" + selLayout + "\" \"" + selVariant + "\"";
 			if (system(cmd.c_str()) == 0) {
 				SystemConf::getInstance()->set("system.kblayout", selLayout);
 				SystemConf::getInstance()->set("system.kbvariant", selVariant);
@@ -4584,13 +4585,15 @@ void GuiMenu::openQuitMenu()
 
 void GuiMenu::openQuitMenu_static(Window *window, bool quickAccessMenu, bool animate)
 {
-#ifdef WIN32
+//#ifdef WIN32
 	if (!quickAccessMenu && Settings::getInstance()->getBool("ShowOnlyExit") && Settings::getInstance()->getBool("ShowExit"))
 	{
-		Utils::Platform::quitES(Utils::Platform::QuitMode::QUIT);
+		window->pushGui(new GuiMsgBox(window, _("REALLY QUIT?"), 
+			_("YES"), [] { Utils::Platform::quitES(Utils::Platform::QuitMode::QUIT); },
+			_("NO"), nullptr));
 		return;
 	}
-#endif
+//#endif
 
 	auto s = new GuiSettings(window, (quickAccessMenu ? _("QUICK ACCESS") : _("QUIT")).c_str());
 	s->setCloseButton("select");
@@ -4745,7 +4748,7 @@ void GuiMenu::openQuitMenu_static(Window *window, bool quickAccessMenu, bool ani
 			_("NO"), nullptr));
 	}, "iconFastShutdown");
 
-#ifdef WIN32
+//#ifdef WIN32
 	if (Settings::getInstance()->getBool("ShowExit"))
 	{
 		s->addEntry(_("QUIT EMULATIONSTATION"), false, [window] {
@@ -4754,7 +4757,7 @@ void GuiMenu::openQuitMenu_static(Window *window, bool quickAccessMenu, bool ani
 				_("NO"), nullptr));
 		}, "iconQuit");
 	}
-#endif
+//#endif
 
 	if (quickAccessMenu && animate)
 		s->getMenu().animateTo(Vector2f((Renderer::getScreenWidth() - s->getMenu().getSize().x()) / 2, (Renderer::getScreenHeight() - s->getMenu().getSize().y()) / 2));
diff --git a/es-app/src/views/gamelist/BasicGameListView.cpp b/es-app/src/views/gamelist/BasicGameListView.cpp
index ceb4e6ef6..9b2337445 100644
--- a/es-app/src/views/gamelist/BasicGameListView.cpp
+++ b/es-app/src/views/gamelist/BasicGameListView.cpp
@@ -22,16 +22,21 @@ BasicGameListView::BasicGameListView(Window* window, FolderData* root)
 	mList.setDefaultZIndex(20);
 
 	mList.setCursorChangedCallback([&](const CursorState& /*state*/) 
-		{
-		updateThemeExtrasBindings();
-		  FileData* file = (mList.size() == 0 || mList.isScrolling()) ? NULL : mList.getSelected();
-		  if (file != nullptr)
-		    file->setSelectedGame();
-		  
-			if (mRoot->getSystem()->isCollection())
-				updateHelpPrompts();
-		});
-
+    {
+        updateThemeExtrasBindings();
+        if (mList.size() == 0 || mList.isScrolling())
+            return;
+
+        FileData* file = mList.getSelected();
+        if (file != nullptr)
+        {
+            // Opcional: añadir verificación si el tipo de archivo es válido
+            file->setSelectedGame();
+        }
+      
+        if (mRoot != nullptr && mRoot->getSystem() != nullptr && mRoot->getSystem()->isCollection())
+            updateHelpPrompts();
+    });
 	addChild(&mList);
 
 	populateList(root->getChildrenListToDisplay());
@@ -133,18 +138,40 @@ void BasicGameListView::resetLastCursor()
 
 void BasicGameListView::setCursor(FileData* cursor)
 {
-	if (cursor && !mList.setCursor(cursor) && !cursor->isPlaceHolder())
-	{
-		std::stack<FileData*> stack;
-		auto childrenToDisplay = mRoot->findChildrenListToDisplayAtCursor(cursor, stack);
-		if (childrenToDisplay != nullptr)
-		{
-			mCursorStack = stack;
-			populateList(*childrenToDisplay.get());
-			mList.setCursor(cursor);
-			TextToSpeech::getInstance()->say(cursor->getName());
-		}
-	}
+    if (cursor == nullptr)
+        return;
+
+    // We need to check if pointer exists within the current mList entries
+    const auto& entries = mList.getObjects();
+    bool pointerIsValid = false;
+    for (auto entry : entries)
+    {
+        if (entry == cursor)
+        {
+            pointerIsValid = true;
+            break;
+        }
+    }
+
+    // If pointer is corrupted (not being present in the list), we should abort to avoid SIGSEGV
+    if (!pointerIsValid)
+        return;
+
+    if (!mList.setCursor(cursor) && !cursor->isPlaceHolder())
+    {
+        std::stack<FileData*> stack;
+        if (mRoot == nullptr)
+            return;
+            
+        auto childrenToDisplay = mRoot->findChildrenListToDisplayAtCursor(cursor, stack);
+        if (childrenToDisplay != nullptr)
+        {
+            mCursorStack = stack;
+            populateList(*childrenToDisplay.get());
+            mList.setCursor(cursor);
+            TextToSpeech::getInstance()->say(cursor->getName());
+        }
+    }
 }
 
 void BasicGameListView::addPlaceholder()
diff --git a/es-core/src/Settings.cpp b/es-core/src/Settings.cpp
index 254ce34e6..6ab555a7f 100644
--- a/es-core/src/Settings.cpp
+++ b/es-core/src/Settings.cpp
@@ -153,7 +153,7 @@ void Settings::setDefaults()
 	mBoolMap["ShowOnlyExit"] = true;
 	mBoolMap["FullscreenBorderless"] = true;
 #else
-	mBoolMap["ShowOnlyExit"] = false;
+	mBoolMap["ShowOnlyExit"] = true;
 	mBoolMap["FullscreenBorderless"] = false;
 #endif
 	mBoolMap["TTS"] = false;
@@ -352,7 +352,7 @@ void Settings::setDefaults()
 #if defined(_WIN32) || defined(X86) || defined(X86_64)
 	mBoolMap["HideWindow"] = false;
 #else
-	mBoolMap["HideWindow"] = true;
+	mBoolMap["HideWindow"] = false;
 #endif
 
 	mBoolMap["HideWindowFullReinit"] = false;
diff --git a/es-core/src/renderers/Renderer.cpp b/es-core/src/renderers/Renderer.cpp
index c5d5f8788..4300dd9a8 100644
--- a/es-core/src/renderers/Renderer.cpp
+++ b/es-core/src/renderers/Renderer.cpp
@@ -236,7 +236,7 @@ namespace Renderer
 			}
 		}
 
-		if((sdlWindow = SDL_CreateWindow("EmulationStation", sdlWindowPosition.x(), sdlWindowPosition.y(), windowWidth, windowHeight, windowFlags)) == nullptr)
+		if((sdlWindow = SDL_CreateWindow("retrobox-emulationstation", sdlWindowPosition.x(), sdlWindowPosition.y(), windowWidth, windowHeight, windowFlags)) == nullptr)
 		{
 			LOG(LogError) << "Error creating SDL window!\n\t" << SDL_GetError();
 			return false;
diff --git a/es-core/src/utils/Platform.cpp b/es-core/src/utils/Platform.cpp
index 5fc9bb10a..7c7b5a29b 100644
--- a/es-core/src/utils/Platform.cpp
+++ b/es-core/src/utils/Platform.cpp
@@ -1,6 +1,8 @@
 #include "Platform.h"
 
 #include <SDL_events.h>
+#include <cstdlib>
+#include <sys/wait.h> // Para WIFEXITED y WEXITSTATUS
 
 #if WIN32
 #include <codecvt>
@@ -192,22 +194,59 @@ namespace Utils
 #endif
 		}
 
+		bool executeCommand(const char* command) {
+			int result = std::system(command);
+			return (result != -1 && WIFEXITED(result) && WEXITSTATUS(result) == 0);
+		}
+
 		int runShutdownCommand()
 		{
-#ifdef WIN32 // windows
-			return system("shutdown -s -t 0");
-#else // osx / linux
-		return system("shutdown -P -h now");
-#endif
+		#ifdef WIN32 // windows
+			return std::system("shutdown -s -t 0");
+		#else // osx / linux
+			// 1. Intento nativo KDE Plasma 6
+			if (executeCommand("qdbus org.kde.Shutdown /Shutdown org.kde.Shutdown.logoutAndShutdown > /dev/null 2>&1")) {
+				return 0;
+			}
+
+			// 2. Fallback a KDE Plasma 5 (ksmserver)
+			if (executeCommand("qdbus org.kde.ksmserver /ksmserver org.kde.ksmserver.logout 0 2 2 > /dev/null 2>&1")) {
+				return 0;
+			}
+
+			// 3. Fallback a systemctl (systemd)
+			if (executeCommand("systemctl poweroff > /dev/null 2>&1")) {
+				return 0;
+			}
+
+			// 4. Fallback final por comandos POSIX clásicos
+			return std::system("shutdown -P -h now");
+		#endif
 		}
 
 		int runRestartCommand()
 		{
-#ifdef WIN32 // windows
-			return system("shutdown -r -t 0");
-#else // osx / linux
-			return system("shutdown -r now");
-#endif
+		#ifdef WIN32 // windows
+			return std::system("shutdown -r -t 0");
+		#else // osx / linux
+			// 1. Intento nativo KDE Plasma 6
+			if (executeCommand("qdbus org.kde.Shutdown /Shutdown org.kde.Shutdown.logoutAndReboot > /dev/null 2>&1")) {
+				return 0;
+			}
+
+			// 2. Fallback a KDE Plasma 5 (ksmserver)
+			if (executeCommand("qdbus org.kde.ksmserver /ksmserver org.kde.ksmserver.logout 0 1 2 > /dev/null 2>&1")) {
+				return 0;
+			}
+
+			// 3. Fallback a systemctl (systemd)
+			if (executeCommand("systemctl reboot > /dev/null 2>&1")) {
+				return 0;
+			}
+
+			// 4. Fallback final por comandos POSIX clásicos
+			return std::system("shutdown -r now");
+		#endif
 		}
 
 		static QuitMode quitMode = QuitMode::QUIT;
RETROBOX_PATCH_EOF
}

apply_patch() {
    write_patch_file
    cd "${SRC_DIR}"
    log_info "Applying the RetroBox patch..."
    git apply --whitespace=nowarn -p1 "${PATCH_FILE}" 2>/dev/null \
        || patch -p1 --forward < "${PATCH_FILE}" \
        || { log_err "The RetroBox patch could not be applied (upstream may have drifted from the base this patch was made against)."; exit 1; }
    cd - >/dev/null
}

# ---------------------------------------------------------------------------
# ScreenScraper login check
# ---------------------------------------------------------------------------

check_screenscraper_login() {
    if [[ -z "${SCREENSCRAPER_DEV_LOGIN}" ]]; then
        log_warn "SCREENSCRAPER_DEV_LOGIN is empty — the binary will build fine, but ScreenScraper's Dev API login won't be baked in."
        log_warn 'Set it like: SCREENSCRAPER_DEV_LOGIN="devid=devid&devpassword=devpassword" retrobox.sh --setup-util emulationstation'
    else
        log_info "ScreenScraper Dev login will be enabled at build time."
    fi
}

# ---------------------------------------------------------------------------
# Configure, build, install
# ---------------------------------------------------------------------------

# CMake generator to use. Ninja avoids a double shell re-parse of compiler
# flags (Make invokes the compiler through /bin/sh -c "...", which can eat
# quote characters embedded in -D defines — that's exactly what was breaking
# SCREENSCRAPER_DEV_LOGIN's quoted string literal). Fall back to Make if
# ninja isn't installed for some reason.
select_generator() {
    if command -v ninja >/dev/null 2>&1; then
        echo "Ninja"
    else
        log_warn "ninja not found — falling back to Unix Makefiles. If SCREENSCRAPER_DEV_LOGIN baking breaks, install ninja (ninja-build)."
        echo "Unix Makefiles"
    fi
}

configure_build() {
    local generator
    generator="$(select_generator)"
    log_info "Configuring the build with CMake (generator: ${generator})..."

    # IMPORTANT: pass the RAW value here, with no extra quotes added by us.
    # Upstream's own CMakeLists.txt already does:
    #   add_definitions(-DSCREENSCRAPER_DEV_LOGIN="${SCREENSCRAPER_DEV_LOGIN}")
    # i.e. it wraps our cache variable in double quotes itself before handing
    # it to the compiler. If we also wrap our value in quotes here, the two
    # layers stack into `""devid=...""`, which GCC parses as an (invalid)
    # user-defined string literal suffix `operator""devid` — exactly the
    # cryptic error this used to produce. One layer of quoting only.
    cmake -B "${BUILD_DIR}" -S "${SRC_DIR}" \
        -G "${generator}" \
        -DCEC=OFF \
        -DGL=ON \
        -DGLES=OFF \
        -DGLES2=OFF \
        -DCMAKE_BUILD_TYPE=Release \
        -DBATOCERA=OFF \
        -DDISABLE_KODI=OFF \
        -DSCREENSCRAPER_DEV_LOGIN="${SCREENSCRAPER_DEV_LOGIN}"
}

compile_build() {
    log_info "Compiling (this can take a while)..."
    cmake --build "${BUILD_DIR}" -j"$(nproc)"
}

# Copies a data directory produced/needed by the build (resources/, locale/)
# into frontend/, recording every touched file in the manifest so -u can
# undo exactly this install without disturbing anything else already living
# under frontend/ (themes/, music/, share/, etc.).
sync_data_dir() {
    local name="$1" src="${SRC_DIR}/$1" dst="${FRONTEND_DIR}/$1"

    [[ -d "${src}" ]] || { log_info "No ${name}/ produced by the build, skipping."; return 0; }

    log_info "Syncing ${name}/ into ${FRONTEND_DIR}..."
    mkdir -p "${dst}"
    if command -v rsync >/dev/null 2>&1; then
        rsync -a "${src}/" "${dst}/"
    else
        cp -a "${src}/." "${dst}/"
    fi
    find "${dst}" -type f -o -type l
}

install_build() {
    log_info "Installing into ${FRONTEND_DIR}..."
    mkdir -p "${FRONTEND_DIR}"

    # Upstream's CMakeLists.txt pins EXECUTABLE_OUTPUT_PATH to the source
    # root (CMAKE_CURRENT_SOURCE_DIR), not the build directory, regardless
    # of where we point -B — so the linked binary lands at
    # SRC_DIR/emulationstation, not BUILD_DIR/emulationstation. Check the
    # source root first and only fall back to BUILD_DIR in case that ever
    # changes upstream.
    local es_bin="${SRC_DIR}/emulationstation"
    if [[ ! -f "${es_bin}" ]]; then
        es_bin="${BUILD_DIR}/emulationstation"
    fi
    if [[ ! -f "${es_bin}" ]]; then
        log_err "Build finished but the emulationstation binary wasn't found in either ${SRC_DIR} or ${BUILD_DIR} — check the build log above."
        exit 1
    fi

    install -m 0755 "${es_bin}" "${FRONTEND_DIR}/${BIN_NAME}"

    {
        echo "${FRONTEND_DIR}/${BIN_NAME}"
        sync_data_dir resources
        sync_data_dir locale
    } > "${MANIFEST_FILE}"

    (cd "${SRC_DIR}" && git rev-parse --short HEAD 2>/dev/null || echo "${ES_REF}") \
        > "${VERSION_FILE}"
}

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

do_install() {
    remove_existing_install
    rm -rf "${WORKDIR}"
    mkdir -p "${WORKDIR}"

    check_screenscraper_login
    install_build_deps
    fetch_source
    apply_patch
    configure_build
    compile_build
    install_build

    rm -rf "${WORKDIR}"
    log_ok "batocera-emulationstation ($(cat "${VERSION_FILE}" 2>/dev/null || echo "${ES_REF}")) installed as ${FRONTEND_DIR}/${BIN_NAME}."
}

do_uninstall() {
    uninstall_from_manifest
    log_ok "batocera-emulationstation uninstalled from ${FRONTEND_DIR}."
}

usage() {
    echo "Usage: $(basename "${BASH_SOURCE[0]}") -s | -u"
    echo "  -s   build and install batocera-emulationstation from source (RetroBox patch set)"
    echo "  -u   uninstall the install done by this script"
    echo
    echo "Env vars:"
    echo "  ES_REF                  branch/tag/commit to build (default: master)"
    echo "  SCREENSCRAPER_DEV_LOGIN ScreenScraper dev login query string,"
    echo "                          e.g. \"devid=manuromero411&devpassword=z1HSAoLQNB1\""
    echo "  BIN_NAME                override the installed binary name"
    echo "                          (default: emulationstation, or"
    echo "                          emulationstation_arm64 on aarch64/arm64 hosts)"
}

case "$1" in
    "-s")
        do_install
        ;;
    "-u")
        do_uninstall
        ;;
    *)
        usage
        exit 1
        ;;
esac