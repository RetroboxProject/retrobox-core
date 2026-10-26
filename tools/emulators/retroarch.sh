#!/usr/bin/env bash
## INSTALADOR DE RETROARCH
## FECHA DE CREACIÓN: 4 de agosto de 2026
set -eo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/retroarch"
SRC_DIR="${RETROBOX_EMULATORS_DIR}/_src"
RETROARCH_SRC="${SRC_DIR}/RetroArch"
TMP_DIR="$(mktemp -d)"
SOURCE_UPSTREAM="https://github.com/libretro/RetroArch.git"
MUPEN64_NEXT_UPSTREAM="https://github.com/libretro/mupen64plus-libretro-nx.git"
FLYCAST_UPSTREAM="https://github.com/flyinghead/flycast.git"
ARCH="$(uname -m)"

# Flags de optimización para el propio frontend (Ryzen 7 7435HS). OJO: esto NO
# optimiza los cores — son .so precompilados que se bajan de buildbot más abajo,
# no se compilan aquí. Si algún core concreto (FBNeo, Mupen64Plus-Next...) va
# con stuttering, la solución pasa por compilar ESE core en concreto, no el frontend.
EXTRA_CFLAGS="-O3 -march=native -pipe"

# Cores a descargar desde el buildbot oficial en la instalación por source.
# Nombre exacto = el que aparece en
# https://buildbot.libretro.com/nightly/linux/x86_64/latest/ sin el sufijo "_libretro.so.zip"
CORES=(
  fbneo
  mupen64plus_next
  # añade aquí el resto de cores que uses
)

# Cores que en no-x64 se compilan aparte (compile_<core>_from_source) en vez de
# usar el .so precompilado del buildbot, por choque de contexto GL/GLES entre
# cómo viene compilado ese core y cómo se configura el frontend en esta arquitectura.
CORES_COMPILADOS_APARTE_NO_X64=(
  mupen64plus_next
  flycast
)

## FUNCIONES

function error() {
  echo "[ERROR] $*." >&2
  exit 1
}

function desinstalar() {
  rm -r "${INSTALL_DIR}/app"
}

function check_deps() {
  echo "[INFO] Comprobando dependencias de compilación..."
  if command -v dnf &> /dev/null; then
    sudo dnf install -y \
      gcc-c++ cmake make git pkgconf-pkg-config \
      SDL2-devel vulkan-loader-devel vulkan-headers \
      mesa-libGL-devel mesa-libEGL-devel mesa-libGLES-devel libX11-devel \
      freetype-devel libxml2-devel \
      libavcodec-free-devel libavformat-free-devel libavutil-free-devel \
      libswresample-free-devel libswscale-free-devel \
      openal-soft-devel libsndfile-devel libusb1-devel \
      systemd-devel alsa-lib-devel pipewire-devel \
      || error "No se pudieron instalar las dependencias de compilación (dnf)"
  else
    sudo apt-get install -y \
      build-essential cmake make git unzip 7zip curl pkg-config \
      libsdl2-dev libsdl2-mixer-dev libvulkan-dev libx11-xcb-dev \
      libgl1-mesa-dev libegl1-mesa-dev libgles2-mesa-dev libx11-dev \
      libfreetype6-dev libxml2-dev \
      libavcodec-dev libavformat-dev libavutil-dev libswresample-dev libswscale-dev \
      libopenal-dev libsndfile1-dev libusb-1.0-0-dev \
      libudev-dev libasound2-dev libpipewire-0.3-dev \
      || error "No se pudieron instalar las dependencias de compilación (apt)"
  fi
}

function check_deps_appimage() {
  echo "[INFO] Comprobando dependencias de la instalación por AppImage..."
  local falta=()
  command -v curl &> /dev/null || falta+=(curl)
  command -v 7z &> /dev/null || falta+=(7z)

  if [[ ${#falta[@]} -eq 0 ]]; then
    return
  fi

  if command -v dnf &> /dev/null; then
    sudo dnf install -y curl p7zip p7zip-plugins \
      || error "No se pudieron instalar las dependencias de la instalación por AppImage (dnf)"
  else
    sudo apt-get install -y curl p7zip-full \
      || error "No se pudieron instalar las dependencias de la instalación por AppImage (apt)"
  fi
}

# Compila mupen64plus_next desde fuente en vez de usar el .so precompilado del
# buildbot (choque de contexto GL/GLES en no-x64).
function compile_mupen64_next_from_source() {
  echo "[INFO] Compilando mupen64plus_next desde fuente (platform=unix, OpenGL de escritorio, RDP: GLideN64+angrylion+parallel, RSP: HLE+cxd4+parallel)..."
  local core_src="${SRC_DIR}/mupen64plus-libretro-nx"
  [[ -d "${core_src}" ]] && rm -rf "${core_src}"
  git clone --depth 1 --shallow-submodules --recursive "${MUPEN64_NEXT_UPSTREAM}" "${core_src}"

  local jobbs
  jobbs="$(nproc)"
  [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]] && jobbs=2

  local m64p_flags=(platform=unix CORE_NAME=mupen64plus_next HAVE_THR_AL=1 LLE=1 HAVE_PARALLEL_RSP=1 HAVE_PARALLEL_RDP=1)

  (
    cd "${core_src}" || exit 1
    make "${m64p_flags[@]}" clean
    make "${m64p_flags[@]}" -j"${jobbs}"
  ) || error "Fallo al compilar mupen64plus_next desde fuente"

  [[ -f "${core_src}/mupen64plus_next_libretro.so" ]] \
    || error "El build de mupen64plus_next terminó pero no encuentro mupen64plus_next_libretro.so"

  mkdir -p "${INSTALL_DIR}/app/share/retroarch/cores"
  cp "${core_src}/mupen64plus_next_libretro.so" "${INSTALL_DIR}/app/share/retroarch/cores/"
}

# Compila flycast desde fuente contra OpenGL de escritorio (-DUSE_GLES=OFF), por
# si el .so del buildbot para esta arch viene compilado GLES-only y no casa con
# el frontend (mismo patrón que mupen64plus_next, pero con CMake en vez de Makefile).
function compile_flycast_from_source() {
  echo "[INFO] Compilando flycast desde fuente (CMake, OpenGL de escritorio, sin GLES)..."
  local core_src="${SRC_DIR}/flycast"
  [[ -d "${core_src}" ]] && rm -rf "${core_src}"
  git clone --depth 1 --recursive "${FLYCAST_UPSTREAM}" "${core_src}"

  local jobbs
  jobbs="$(nproc)"
  [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]] && jobbs=2

  (
    cd "${core_src}" || exit 1
    mkdir -p build && cd build || exit 1
    cmake .. -DCMAKE_BUILD_TYPE=Release -DLIBRETRO=ON -DUSE_GLES=OFF -DUSE_GLES2=OFF \
      || exit 1
    cmake --build . -j"${jobbs}" || exit 1
  ) || error "Fallo al compilar flycast desde fuente"

  [[ -f "${core_src}/build/flycast_libretro.so" ]] \
    || error "El build de flycast terminó pero no encuentro flycast_libretro.so"

  mkdir -p "${INSTALL_DIR}/app/share/retroarch/cores"
  cp "${core_src}/build/flycast_libretro.so" "${INSTALL_DIR}/app/share/retroarch/cores/"
}

function download_cores() {
  # Mapeo de arquitectura detectada -> carpeta del buildbot
  local buildbot_arch=""
  case "${ARCH}" in
    x86_64|amd64)
      buildbot_arch="x86_64"
      ;;
    aarch64|arm64)
      buildbot_arch="aarch64"
      ;;
    armv7l|armhf)
      buildbot_arch="armhf"
      ;;
    i686|i386|x86)
      buildbot_arch="x86"
      ;;
    *)
      echo "[AVISO] Arquitectura no soportada para descarga de cores (detectada: ${ARCH}); saltando."
      return
      ;;
  esac

  mkdir -p "${INSTALL_DIR}/app/share/retroarch/cores"

  local base="https://buildbot.libretro.com/nightly/linux/${buildbot_arch}/latest"

  echo "[INFO] Obteniendo lista de cores disponibles desde el buildbot (${buildbot_arch})..."

  # Descargamos el índice HTML, filtramos los .so.zip, y limpiamos para quedarnos solo con el nombre del core
  local cores_list
  cores_list=$(curl -sfL "${base}/" | grep -oE '[a-zA-Z0-9_\-]+_libretro\.so\.zip' | sed -E 's/_libretro\.so\.zip//' | sort -u)

  if [[ -z "${cores_list}" ]]; then
    echo "[AVISO] No se pudo obtener la lista de cores del buildbot."
    return
  fi

  local core skip
  for core in ${cores_list}; do
    # Estos cores en no-x64 se compilan aparte (ver CORES_COMPILADOS_APARTE_NO_X64)
    # por el choque de contexto GL/GLES entre el .so precompilado y el frontend.
    skip=0
    if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]]; then
      for c in "${CORES_COMPILADOS_APARTE_NO_X64[@]}"; do
        [[ "${core}" == "${c}" ]] && skip=1 && break
      done
    fi
    if [[ "${skip}" -eq 1 ]]; then
      echo "[INFO] Saltando ${core} precompilado (se compila desde fuente en esta arquitectura)."
      continue
    fi
    echo "[INFO] Descargando core: ${core}..."
    if ! curl -sfL "${base}/${core}_libretro.so.zip" -o "${TMP_DIR}/${core}.zip"; then
      echo "[AVISO] No se pudo descargar el core '${core}', saltando"
      continue
    fi
    unzip -qo "${TMP_DIR}/${core}.zip" -d "${INSTALL_DIR}/app/share/retroarch/cores/"
    rm -f "${TMP_DIR}/${core}.zip"
  done
}

function download_selected_cores() {
  if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]]; then
    echo "[AVISO] Descarga de cores solo soportada para x86_64 por ahora (arquitectura detectada: ${ARCH}); saltando."
    return
  fi

  mkdir -p "${INSTALL_DIR}/cores"
  local base="https://buildbot.libretro.com/nightly/linux/x86_64/latest"

  for core in "${CORES[@]}"; do
    echo "[INFO] Descargando core: ${core}..."
    if ! curl -sfL "${base}/${core}_libretro.so.zip" -o "${TMP_DIR}/${core}.zip"; then
      echo "[AVISO] No se pudo descargar el core '${core}', saltando"
      continue
    fi
    unzip -qo "${TMP_DIR}/${core}.zip" -d "${INSTALL_DIR}/app/share/retroarch/cores/"
    rm -f "${TMP_DIR}/${core}.zip"
  done
}

function download_frontend_assets() {
  local base="https://buildbot.libretro.com/assets/frontend"

  local zip dest
  for entry in \
    "info.zip:${INSTALL_DIR}/app/share/retroarch/cores" \
    "assets.zip:${INSTALL_DIR}/app/share/retroarch/assets" \
    "autoconfig.zip:${INSTALL_DIR}/app/share/retroarch/autoconfig" \
    "cheats.zip:${INSTALL_DIR}/app/share/retroarch/cheats" \
    "database-rdb.zip:${INSTALL_DIR}/app/share/retroarch/database/rdb" \
    "shaders_slang.zip:${INSTALL_DIR}/app/share/retroarch/shaders" \
    "overlays.zip:${INSTALL_DIR}/app/share/retroarch/overlays"
  do
    zip="${entry%%:*}"
    dest="${entry#*:}"
    mkdir -p "${dest}"
    echo "[INFO] Descargando ${zip}..."
    if ! curl -sfL "${base}/${zip}" -o "${TMP_DIR}/${zip}"; then
      echo "[AVISO] No se pudo descargar ${zip}, saltando"
      continue
    fi
    unzip -qo "${TMP_DIR}/${zip}" -d "${dest}/"
    rm -f "${TMP_DIR}/${zip}"
  done
}

function generate_config() {
  if [[ -f "${INSTALL_DIR}/config/retroarch.cfg" ]]; then
    echo "[INFO] Ya existe ${INSTALL_DIR}/config/retroarch.cfg, no se sobreescribe (para no perder ajustes tocados a mano)."
    return
  fi

  mkdir -p "${INSTALL_DIR}/config/retroarch"
}

function install_source() {
  mkdir -p "${SRC_DIR}"
  check_deps

  echo "[INFO] Clonando RetroArch..."
  git clone --recursive "${SOURCE_UPSTREAM}" "${RETROARCH_SRC}"

  echo "[INFO] Configurando con OpenGL de escritorio"
  local gl_flags=(--enable-opengl)
  echo "[INFO] Configurando y compilando (prefijo: ${INSTALL_DIR}/app)..."

  (
    cd "${RETROARCH_SRC}" || exit 1
    CFLAGS="${EXTRA_CFLAGS}" CXXFLAGS="${EXTRA_CFLAGS}" ./configure \
      --prefix="${INSTALL_DIR}/app" \
      "${gl_flags[@]}" \
      --enable-vulkan --enable-pipewire --enable-alsa --enable-networking --enable-discord \
      || exit 1
    make -j"$(nproc)" || exit 1
    make install || exit 1
  ) || error "Fallo al compilar/instalar RetroArch. Revisa la salida de configure/make arriba"

  # "make install" con --prefix coloca bin/retroarch de forma autocontenida;
  # el resultado en INSTALL_DIR/app no depende de que _src/ siga existiendo.
  [[ -x "${INSTALL_DIR}/app/bin/retroarch" ]] \
    || error "El build terminó pero no encuentro el binario instalado en ${INSTALL_DIR}/app/bin/retroarch"

  download_cores

  if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]]; then
    compile_mupen64_next_from_source
    compile_flycast_from_source
  fi

  download_frontend_assets
  generate_config

  echo "[INFO] Limpiando fuentes temporales..."
  rm -rf "${SRC_DIR}" "${TMP_DIR}"
  echo "[INFO] Instalación desde source completada. Binario: ${INSTALL_DIR}/app/bin/retroarch"
  echo "[INFO] Config: ${INSTALL_DIR}/config/retroarch.cfg — lánzalo con: ${INSTALL_DIR}/app/bin/retroarch -c ${INSTALL_DIR}/config/retroarch.cfg"
}

function install_appimage() {
  if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]]; then
    error "Instalación por AppImage solo soportada para x86_64 por ahora (arquitectura detectada: ${ARCH})"
  fi

  desinstalar 2>/dev/null || true
  check_deps_appimage

  local url="https://buildbot.libretro.com/nightly/linux/x86_64/RetroArch.7z"
  local archive="${TMP_DIR}/RetroArch.7z"
  local extract_dir="${TMP_DIR}/extracted"

  echo "[INFO] Descargando RetroArch AppImage..."
  curl -fSL -o "${archive}" "${url}" || error "No se pudo descargar el AppImage de RetroArch"

  echo "[INFO] Extrayendo ${archive}..."
  mkdir -p "${extract_dir}"
  7z x -y -o"${extract_dir}" "${archive}" >/dev/null \
    || error "Fallo al extraer el .7z descargado"

  local appimage="${extract_dir}/RetroArch-Linux-x86_64/RetroArch-Linux-x86_64.AppImage"
  [[ -f "${appimage}" ]] || error "No se ha encontrado el AppImage tras la extracción"
  chmod +x "${appimage}"

  echo "[INFO] Descomprimiendo el AppImage (--appimage-extract)..."
  (
    cd "${extract_dir}" || exit 1
    "${appimage}" --appimage-extract >/dev/null 2>&1 || exit 1
  ) || error "Fallo al descomprimir el AppImage"

  # El binario y compañía viven dentro de squashfs-root/usr (bin/, lib/, share/),
  # no en la raíz de squashfs-root (que solo trae el AppRun, el .desktop y el icono).
  [[ -d "${extract_dir}/squashfs-root/usr" ]] \
    || error "Estructura de squashfs-root inesperada: no existe usr/ dentro"

  mkdir -p "${INSTALL_DIR}/app"
  cp -r "${extract_dir}/squashfs-root/usr"/* "${INSTALL_DIR}/app"
  cp -r "${extract_dir}/squashfs-root/AppRun" "${INSTALL_DIR}/app"

  [[ -x "${INSTALL_DIR}/app/bin/retroarch" ]] \
    || error "El AppImage se descomprimió pero no encuentro el binario en ${INSTALL_DIR}/app/bin/retroarch"

  # El AppImage trae su propia config "portable" en .home/.config/retroarch
  # (cores, assets, autoconfig, cheats, database, shaders, overlays, retroarch.cfg...).
  # La asimilamos a la misma estructura que usa la instalación por source
  # (INSTALL_DIR/app/share/retroarch) en lugar de dejarla en un directorio aparte.
  local home_cfg="${extract_dir}/RetroArch-Linux-x86_64/RetroArch-Linux-x86_64.AppImage.home/.config/retroarch"
  if [[ -d "${home_cfg}" ]]; then
    echo "[INFO] Asimilando la configuración embebida del AppImage a ${INSTALL_DIR}/app/share/retroarch..."
    mkdir -p "${INSTALL_DIR}/app/share/retroarch"
    cp -r "${home_cfg}"/* "${INSTALL_DIR}/app/share/retroarch/"
  fi

  # Igual que en la instalación por source, el retroarch.cfg definitivo vive en
  # INSTALL_DIR/config/retroarch.cfg. Si el AppImage trajo uno y todavía no
  # existe ninguno ahí, lo promovemos; si ya existe uno (instalación previa
  # tocada a mano), lo respetamos.
  mkdir -p "${INSTALL_DIR}/config"
  if [[ -f "${INSTALL_DIR}/app/share/retroarch/retroarch.cfg" ]]; then
    if [[ ! -f "${INSTALL_DIR}/config/retroarch.cfg" ]]; then
      mv "${INSTALL_DIR}/app/share/retroarch/retroarch.cfg" "${INSTALL_DIR}/config/retroarch.cfg"
    else
      rm -f "${INSTALL_DIR}/app/share/retroarch/retroarch.cfg"
    fi
  fi
  generate_config

  echo "[INFO] Limpiando temporales..."
  rm -rf "${extract_dir}" "${archive}"

  # Igual que en la instalación por source: bajamos los cores desde el
  # buildbot de libretro en vez de usar el RetroArch_cores.7z del AppImage.
  download_cores

  rm -rf "${TMP_DIR}"
  echo "[INFO] Instalación por AppImage completada. Binario: ${INSTALL_DIR}/app/bin/retroarch"
  echo "[INFO] Config: ${INSTALL_DIR}/config/retroarch.cfg — lánzalo con: ${INSTALL_DIR}/app/bin/retroarch -c ${INSTALL_DIR}/config/retroarch.cfg"
}

## LLAMADAS
case "$1" in
"-s") install_source;;
"-a") install_appimage;;
"-u"|"-d") desinstalar;;
*)  exit 1;;
esac

exit 0
