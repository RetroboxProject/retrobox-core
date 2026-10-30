"""Full-screen "install the missing emulator" screen.

Ask -> install (with the installer output in a terminal box) -> result. Drawn
with SDL2's renderer; text is rasterised once per change with Pillow and kept
in textures, so the screen only redraws when something changes (at most
``_MAX_FPS`` times a second while the installer is printing) and sleeps in
SDL_WaitEvent the rest of the time.
"""

from __future__ import annotations

import contextlib
import ctypes
import enum
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import sdl2
from PIL import Image, ImageDraw, ImageFont

from .keys import key_bytes
from .pad import Action, PadInput, parse_mapping
from .process import InstallerProcess
from .terminal import Position, Row, TerminalBuffer

if TYPE_CHECKING:
    from collections.abc import Sequence

    _Font = ImageFont.FreeTypeFont | ImageFont.ImageFont

EXIT_INSTALLED = 0
EXIT_DECLINED = 10
EXIT_FAILED = 11
EXIT_UNAVAILABLE = 12

_MAX_FPS = 30
_CONFIRM_GUARD_MS = 300  # ignore a confirm still held from launching the game
_WHITE = (255, 255, 255)
_HINT = (190, 196, 210)
_SELECTION = (38, 79, 120)
_CURSOR = (200, 200, 200)
_ACCENT = (0, 95, 184)
_SCROLL_STEP = 3
_TERM_PAD = 8

# clipboard tools that keep serving the text after the window is gone
_CLIPBOARD_TOOLS = (
    ("wl-copy",),
    ("xclip", "-selection", "clipboard"),
    ("xsel", "--clipboard", "--input"),
)

_FONT_FALLBACKS = {
    "monospace": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ),
    "sans-serif:bold": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ),
    "sans-serif": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ),
}


class State(enum.Enum):
    """Steps of the screen."""

    ASK = enum.auto()
    INSTALLING = enum.auto()
    FAILED = enum.auto()
    DONE = enum.auto()


@dataclass(frozen=True, slots=True)
class Options:  # pylint: disable=too-many-instance-attributes
    """What the screen is about (see ``__main__`` for the command line)."""

    label: str
    command: Sequence[str]
    log_path: Path
    background: Path | None = None
    check_path: Path | None = None
    pad_guid: str | None = None
    pad_device: str | None = None
    pad_mapping: Sequence[str] = field(default_factory=tuple)


# ---------------------------------------------------------------------- fonts
def _font_file(pattern: str) -> str | None:
    """Ask fontconfig for a font file, falling back to well-known paths."""
    fc_match = shutil.which("fc-match")
    if fc_match:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            found = subprocess.run(
                [fc_match, "-f", "%{file}", pattern],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            ).stdout.strip()
            if found and Path(found).is_file():
                return found
    return next((path for path in _FONT_FALLBACKS[pattern] if Path(path).is_file()), None)


class _Fonts:  # pylint: disable=too-few-public-methods
    """The fonts of one layout, sized from the screen height."""

    _files: dict[str, str | None] = {}

    def __init__(self, height: int) -> None:
        self.title = self._load("sans-serif:bold", max(18, round(height / 24)))
        self.button = self._load("sans-serif", max(14, round(height / 40)))
        self.hint = self._load("sans-serif", max(11, round(height / 64)))
        self.mono = self._load("monospace", max(11, round(height / 60)))

    @classmethod
    def _load(cls, pattern: str, size: int) -> _Font:
        if pattern not in cls._files:
            cls._files[pattern] = _font_file(pattern)
        path = cls._files[pattern]
        if path:
            with contextlib.suppress(OSError):
                return ImageFont.truetype(path, size)
        try:
            return ImageFont.load_default(size)
        except TypeError:  # Pillow < 10.1
            return ImageFont.load_default()


def _line_height(font: _Font) -> int:
    if isinstance(font, ImageFont.FreeTypeFont):
        ascent, descent = font.getmetrics()
        return ascent + descent
    return int(font.getbbox("Ag")[3]) + 2


# ------------------------------------------------------------------- textures
class _Texture:
    """An SDL texture and its size."""

    def __init__(self, renderer, image: Image.Image, streaming: bool = False) -> None:
        self.width, self.height = image.size
        rgba = image.mode == "RGBA"
        pixel_format = sdl2.SDL_PIXELFORMAT_RGBA32 if rgba else sdl2.SDL_PIXELFORMAT_RGB24
        access = sdl2.SDL_TEXTUREACCESS_STREAMING if streaming else sdl2.SDL_TEXTUREACCESS_STATIC
        self.handle = sdl2.SDL_CreateTexture(
            renderer, pixel_format, access, self.width, self.height
        )
        if not self.handle:
            raise RuntimeError(sdl2.SDL_GetError().decode(errors="replace"))
        if rgba:
            sdl2.SDL_SetTextureBlendMode(self.handle, sdl2.SDL_BLENDMODE_BLEND)
        self.update(image)

    def update(self, image: Image.Image) -> None:
        """Upload new pixels (same size and mode)."""
        pitch = self.width * (4 if image.mode == "RGBA" else 3)
        sdl2.SDL_UpdateTexture(self.handle, None, image.tobytes(), pitch)

    def draw(self, renderer, x: int, y: int) -> None:
        """Copy the texture 1:1 to (x, y)."""
        target = sdl2.SDL_Rect(x, y, self.width, self.height)
        sdl2.SDL_RenderCopy(renderer, self.handle, None, target)

    def destroy(self) -> None:
        """Free the texture."""
        if self.handle:
            sdl2.SDL_DestroyTexture(self.handle)
            self.handle = None


def _render_text(renderer, text: str, font: _Font, color=_WHITE) -> _Texture:
    left, top, right, bottom = font.getbbox(text)
    image = Image.new("RGBA", (max(1, int(right - left)), max(1, int(bottom - top))))
    ImageDraw.Draw(image).text((-left, -top), text, font=font, fill=(*color, 255))
    return _Texture(renderer, image)


def _contains(rect: sdl2.SDL_Rect, x: int, y: int) -> bool:
    return rect.x <= x < rect.x + rect.w and rect.y <= y < rect.y + rect.h


class _Button(NamedTuple):
    label: _Texture
    rect: sdl2.SDL_Rect  # mutable: placed after every button is sized
    result: str


# --------------------------------------------------------------------- screen
class SetupScreen:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """The window, its state machine and its event loop."""

    def __init__(self, options: Options) -> None:
        self._options = options
        self._state = State.ASK
        self._terminal = TerminalBuffer()
        self._process: InstallerProcess | None = None
        self._pad = PadInput(
            options.pad_guid, options.pad_device, parse_mapping(options.pad_mapping)
        )
        self._window = None
        self._renderer = None
        self._wake_event = 0
        self._shown_at = 0
        self._result = EXIT_DECLINED
        self._running = True
        self._dirty = True
        self._width = self._height = 0
        self._fonts: _Fonts | None = None
        self._background: _Texture | None = None
        self._message: _Texture | None = None
        self._message_pos = (0, 0)
        self._hint: _Texture | None = None
        self._hint_text = ""
        self._buttons: list[_Button] = []
        self._focus = 0
        self._term_rect = sdl2.SDL_Rect()
        self._term_texture: _Texture | None = None
        self._term_image: Image.Image | None = None
        self._cell_height = 1
        self._columns = 1
        self._visible_rows: list[Row] = []
        self._scroll = 0  # rows above the bottom of the log
        self._selecting = False

    # ------------------------------------------------------------ lifecycle
    def run(self) -> int:
        """Show the screen until the user is done; returns the exit code."""
        sdl2.SDL_SetHint(sdl2.SDL_HINT_RENDER_SCALE_QUALITY, b"1")
        sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, b"1")
        sdl2.SDL_SetHint(sdl2.SDL_HINT_VIDEO_MINIMIZE_ON_FOCUS_LOSS, b"0")
        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_GAMECONTROLLER) != 0:
            return EXIT_UNAVAILABLE
        try:
            if not self._open_window():
                return EXIT_UNAVAILABLE
            self._loop()
            return self._result
        finally:
            if self._process is not None:
                self._process.terminate()
            self._pad.close()
            self._free_textures()
            if self._background is not None:
                self._background.destroy()
            if self._renderer:
                sdl2.SDL_DestroyRenderer(self._renderer)
            if self._window:
                sdl2.SDL_DestroyWindow(self._window)
            sdl2.SDL_Quit()

    def _open_window(self) -> bool:
        # sized as the desktop too, in case nobody honours the fullscreen request
        mode = sdl2.SDL_DisplayMode()
        if sdl2.SDL_GetDesktopDisplayMode(0, ctypes.byref(mode)) != 0 or mode.w <= 0:
            mode.w, mode.h = 1280, 720
        self._window = sdl2.SDL_CreateWindow(
            b"Retrobox",
            sdl2.SDL_WINDOWPOS_CENTERED,
            sdl2.SDL_WINDOWPOS_CENTERED,
            mode.w,
            mode.h,
            sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP | sdl2.SDL_WINDOW_ALLOW_HIGHDPI,
        )
        if not self._window:
            return False
        for flags in (sdl2.SDL_RENDERER_PRESENTVSYNC, sdl2.SDL_RENDERER_SOFTWARE):
            self._renderer = sdl2.SDL_CreateRenderer(self._window, -1, flags)
            if self._renderer:
                break
        if not self._renderer:
            return False
        sdl2.SDL_SetRenderDrawBlendMode(self._renderer, sdl2.SDL_BLENDMODE_BLEND)
        sdl2.SDL_RaiseWindow(self._window)
        sdl2.SDL_StopTextInput()  # typing only goes to the installer, while it runs
        self._wake_event = sdl2.SDL_RegisterEvents(1)
        self._background = self._load_background()
        self._layout()
        self._shown_at = sdl2.SDL_GetTicks()
        return True

    def _load_background(self) -> _Texture | None:
        path = self._options.background
        if path is None:
            return None
        try:
            with Image.open(path) as image:
                return _Texture(self._renderer, image.convert("RGB"))
        except (OSError, RuntimeError, ValueError):
            return None

    def _free_textures(self) -> None:
        for texture in (self._message, self._hint, self._term_texture):
            if texture is not None:
                texture.destroy()
        for button in self._buttons:
            button.label.destroy()
        self._message = self._hint = self._term_texture = None
        self._buttons = []

    # --------------------------------------------------------------- layout
    def _layout(self) -> None:
        """Size everything for the current window and state."""
        width, height = ctypes.c_int(0), ctypes.c_int(0)
        sdl2.SDL_GetRendererOutputSize(self._renderer, ctypes.byref(width), ctypes.byref(height))
        if (width.value, height.value) != (self._width, self._height) or self._fonts is None:
            self._width, self._height = width.value, height.value
            self._fonts = _Fonts(self._height)
        self._free_textures()
        self._layout_message()
        self._layout_buttons()
        self._layout_terminal()
        self._set_hint(self._default_hint())
        self._dirty = True

    def _layout_message(self) -> None:
        label = self._options.label
        message = {
            State.ASK: f"The emulator {label} is not installed. Install it?",
            State.INSTALLING: f"Installing {label}, please wait",
            State.FAILED: f"Error installing {label}",
            State.DONE: f"Success installing {label}",
        }[self._state]
        self._message = _render_text(self._renderer, message, self._fonts.title)
        if self._state is State.ASK:
            top = self._height * 45 // 100 - self._message.height
        else:
            top = self._height * 47 // 100 - self._message.height // 2
        self._message_pos = ((self._width - self._message.width) // 2, top)

    def _layout_buttons(self) -> None:
        """Size the buttons of the state and centre them in a row below the message."""
        labels = {
            State.ASK: (("Yes", "yes"), ("No", "no")),
            State.FAILED: (("OK", "ok"),),
            State.DONE: (("OK", "ok"),),
        }.get(self._state, ())
        font = self._fonts.button
        height = round(font.size * 2.2) if isinstance(font, ImageFont.FreeTypeFont) else 40
        for text, result in labels:
            texture = _render_text(self._renderer, text, font)
            width = max(texture.width + height * 2, height * 3)
            self._buttons.append(_Button(texture, sdl2.SDL_Rect(0, 0, width, height), result))
        self._focus = min(self._focus, max(0, len(self._buttons) - 1))

        gap = height // 2
        x = (self._width - sum(b.rect.w for b in self._buttons) - gap * (len(labels) - 1)) // 2
        y = self._message_pos[1] + self._message.height + round(self._message.height * 0.8)
        for button in self._buttons:
            button.rect.x, button.rect.y = x, y
            x += button.rect.w + gap

    def _layout_terminal(self) -> None:
        """Lower third of the screen, middle half of its width."""
        top = 2 * self._height // 3
        bottom = self._height - self._height // 14
        self._term_rect = sdl2.SDL_Rect(self._width // 4, top, self._width // 2, bottom - top)
        self._term_image = None
        self._cell_height = _line_height(self._fonts.mono)
        cell_width = max(1.0, self._fonts.mono.getlength("M"))
        self._columns = max(10, int((self._term_rect.w - 2 * _TERM_PAD) // cell_width))
        if self._process is not None:
            self._process.resize(*self._term_size())

    def _term_size(self) -> tuple[int, int]:
        """Columns and rows of the terminal box."""
        return self._columns, self._page() + 1

    def _default_hint(self) -> str:
        if self._state is State.ASK:
            return "A / Enter: select     B / Esc: cancel"
        if self._state is State.INSTALLING:
            return ("Type here if the installer asks (e.g. sudo password)     "
                    "Ctrl+Shift+C / V: copy / paste     PgUp / PgDn: scroll")
        log = str(self._options.log_path).replace(str(Path.home()), "~", 1)
        return f"A / Enter: continue     Ctrl+C: copy log     Full log: {log}"

    def _set_hint(self, text: str) -> None:
        if text == self._hint_text and self._hint is not None:
            return
        if self._hint is not None:
            self._hint.destroy()
        self._hint_text = text
        self._hint = _render_text(self._renderer, text, self._fonts.hint, _HINT)
        self._dirty = True

    def _set_state(self, state: State) -> None:
        self._state = state
        self._focus = 0
        if state is State.INSTALLING:
            sdl2.SDL_StartTextInput()
        else:
            sdl2.SDL_StopTextInput()
        self._layout()

    # ----------------------------------------------------------------- loop
    def _loop(self) -> None:
        event = sdl2.SDL_Event()
        frame_ms = 1000 // _MAX_FPS
        last_frame = -frame_ms
        while self._running:
            if self._dirty:
                wait = max(0, last_frame + frame_ms - sdl2.SDL_GetTicks())
                got = sdl2.SDL_WaitEventTimeout(ctypes.byref(event), wait) if wait else 0
            else:
                got = sdl2.SDL_WaitEvent(ctypes.byref(event))
            while got:
                self._handle(event)
                got = sdl2.SDL_PollEvent(ctypes.byref(event))
            if self._dirty and self._running and sdl2.SDL_GetTicks() >= last_frame + frame_ms:
                self._draw()
                last_frame = sdl2.SDL_GetTicks()

    def _notify(self) -> None:
        """Called from the reader thread: wake the loop up."""
        event = sdl2.SDL_Event()
        event.type = self._wake_event
        sdl2.SDL_PushEvent(ctypes.byref(event))

    # --------------------------------------------------------------- events
    def _handle(self, event: sdl2.SDL_Event) -> None:  # pylint: disable=too-many-branches
        kind = event.type
        if kind == self._wake_event:
            self._collect_output()
        elif kind == sdl2.SDL_QUIT:
            self._quit()
        elif kind == sdl2.SDL_WINDOWEVENT:
            if event.window.event == sdl2.SDL_WINDOWEVENT_SIZE_CHANGED:
                self._layout()
            elif event.window.event in (sdl2.SDL_WINDOWEVENT_EXPOSED, sdl2.SDL_WINDOWEVENT_SHOWN):
                self._dirty = True
        elif kind == sdl2.SDL_JOYDEVICEADDED:
            self._pad.device_added(event.jdevice.which)
        elif kind == sdl2.SDL_JOYDEVICEREMOVED:
            self._pad.device_removed(event.jdevice.which)
        elif kind == sdl2.SDL_KEYDOWN:
            self._key(event.key.keysym.sym, event.key.keysym.mod)
        elif kind == sdl2.SDL_TEXTINPUT:
            self._send(bytes(event.text.text))
        elif kind == sdl2.SDL_MOUSEMOTION:
            self._mouse_motion(event.motion.x, event.motion.y)
        elif kind == sdl2.SDL_MOUSEBUTTONDOWN and event.button.button == sdl2.SDL_BUTTON_LEFT:
            self._mouse_down(event.button.x, event.button.y)
        elif kind == sdl2.SDL_MOUSEBUTTONUP and event.button.button == sdl2.SDL_BUTTON_LEFT:
            self._selecting = False
        elif kind == sdl2.SDL_MOUSEWHEEL:
            self._scroll_by(event.wheel.y * _SCROLL_STEP)
        else:
            action = self._pad.translate(event)
            if action is not None:
                self._action(action)

    def _key(self, key: int, mod: int) -> None:  # pylint: disable=too-many-return-statements
        if self._state is State.INSTALLING:
            self._terminal_key(key, mod)
            return
        ctrl = bool(mod & sdl2.KMOD_CTRL)
        if ctrl and key == sdl2.SDLK_c:
            self._copy()
            return
        if ctrl and key == sdl2.SDLK_a and self._state is not State.ASK:
            self._terminal.select_all()
            self._dirty = True
            return
        keys = {
            sdl2.SDLK_RETURN: Action.CONFIRM, sdl2.SDLK_KP_ENTER: Action.CONFIRM,
            sdl2.SDLK_SPACE: Action.CONFIRM, sdl2.SDLK_ESCAPE: Action.BACK,
            sdl2.SDLK_LEFT: Action.LEFT, sdl2.SDLK_RIGHT: Action.RIGHT,
            sdl2.SDLK_UP: Action.UP, sdl2.SDLK_DOWN: Action.DOWN,
        }
        if key in keys:
            self._action(keys[key])
        elif key == sdl2.SDLK_TAB and self._buttons:
            self._focus = (self._focus + 1) % len(self._buttons)
            self._dirty = True
        elif self._state is State.ASK and key in (sdl2.SDLK_y, sdl2.SDLK_n):
            self._choose("yes" if key == sdl2.SDLK_y else "no")
        elif key == sdl2.SDLK_PAGEUP:
            self._scroll_by(self._page())
        elif key == sdl2.SDLK_PAGEDOWN:
            self._scroll_by(-self._page())
        elif key == sdl2.SDLK_HOME:
            self._scroll_by(1 << 30)
        elif key == sdl2.SDLK_END:
            self._scroll_by(-(1 << 30))

    def _terminal_key(self, key: int, mod: int) -> None:
        """Keys while installing: they go to the installer, as in a terminal emulator.

        Ctrl+C copies when there is a selection (or with Shift), and interrupts
        the installer otherwise; PgUp/PgDn scroll and are not sent.
        """
        ctrl, shift = bool(mod & sdl2.KMOD_CTRL), bool(mod & sdl2.KMOD_SHIFT)
        if ctrl and key == sdl2.SDLK_c and (shift or self._terminal.selection() is not None):
            self._copy()
        elif (ctrl and shift and key == sdl2.SDLK_v) or (shift and key == sdl2.SDLK_INSERT):
            self._paste()
        elif key in (sdl2.SDLK_PAGEUP, sdl2.SDLK_PAGEDOWN):
            self._scroll_by(self._page() if key == sdl2.SDLK_PAGEUP else -self._page())
        else:
            data = key_bytes(key, mod)
            if data is not None:
                self._send(data)

    def _send(self, data: bytes) -> None:
        """Type into the installer's terminal, bringing the view back to the cursor."""
        if self._state is not State.INSTALLING or self._process is None or not data:
            return
        self._process.write(data)
        if self._scroll:
            self._scroll = 0
            self._dirty = True

    def _paste(self) -> None:
        text = sdl2.SDL_GetClipboardText() or b""
        # a terminal sends Enter as CR: the pty turns it into a newline
        self._send(text.replace(b"\r\n", b"\r").replace(b"\n", b"\r"))

    def _action(self, action: Action) -> None:
        if action is Action.CONFIRM:
            if self._buttons and sdl2.SDL_GetTicks() - self._shown_at >= _CONFIRM_GUARD_MS:
                self._choose(self._buttons[self._focus].result)
        elif action is Action.BACK:
            if self._state is State.ASK:
                self._choose("no")
        elif action in (Action.LEFT, Action.RIGHT) and self._buttons:
            step = -1 if action is Action.LEFT else 1
            self._focus = (self._focus + step) % len(self._buttons)
            self._dirty = True
        elif action in (Action.UP, Action.DOWN) and self._state is not State.ASK:
            self._scroll_by(1 if action is Action.UP else -1)

    def _choose(self, result: str) -> None:
        if result == "yes":
            self._start_install()
        elif result == "no":
            self._result = EXIT_DECLINED
            self._running = False
        elif result == "ok":
            self._result = EXIT_INSTALLED if self._state is State.DONE else EXIT_FAILED
            self._running = False

    def _quit(self) -> None:
        """The window was closed: stop whatever is going on, without launching."""
        if self._state is State.DONE:
            self._result = EXIT_INSTALLED
        elif self._state is not State.ASK:
            self._result = EXIT_FAILED
        self._running = False

    # ---------------------------------------------------------------- mouse
    def _mouse_motion(self, x: int, y: int) -> None:
        x, y = self._to_pixels(x, y)
        if self._selecting:
            self._terminal.cursor = self._position_at(x, y)
            self._dirty = True
            return
        for index, button in enumerate(self._buttons):
            if _contains(button.rect, x, y) and index != self._focus:
                self._focus = index
                self._dirty = True

    def _mouse_down(self, x: int, y: int) -> None:
        x, y = self._to_pixels(x, y)
        for button in self._buttons:
            if _contains(button.rect, x, y):
                self._choose(button.result)
                return
        if self._state is not State.ASK and _contains(self._term_rect, x, y):
            position = self._position_at(x, y)
            self._terminal.anchor = self._terminal.cursor = position
            self._selecting = True
        else:
            self._terminal.clear_selection()
        self._dirty = True

    def _to_pixels(self, x: int, y: int) -> tuple[int, int]:
        """Window coordinates -> renderer pixels (they differ on HiDPI screens)."""
        width, height = ctypes.c_int(0), ctypes.c_int(0)
        sdl2.SDL_GetWindowSize(self._window, ctypes.byref(width), ctypes.byref(height))
        if width.value <= 0 or height.value <= 0:
            return x, y
        return x * self._width // width.value, y * self._height // height.value

    def _position_at(self, x: int, y: int) -> Position:
        """The text position under a point of the terminal box."""
        if not self._visible_rows:
            return Position(self._terminal.first_line, 0)
        index = (y - self._term_rect.y - _TERM_PAD) // self._cell_height
        index = min(max(index, 0), len(self._visible_rows) - 1)
        row = self._visible_rows[index]
        text = self._terminal.line(row.line)[row.start:row.end]
        offset = x - self._term_rect.x - _TERM_PAD
        font = self._fonts.mono
        low, high = 0, len(text)
        while low < high:  # first column whose middle lies right of the pointer
            middle = (low + high) // 2
            if font.getlength(text[:middle + 1]) - font.getlength(text[middle]) / 2 <= offset:
                low = middle + 1
            else:
                high = middle
        return Position(row.line, row.start + low)

    # ------------------------------------------------------------- terminal
    def _page(self) -> int:
        return max(1, (self._term_rect.h - 2 * _TERM_PAD) // self._cell_height - 1)

    def _scroll_by(self, rows: int) -> None:
        if self._state is State.ASK:
            return
        total = self._terminal.row_count(self._columns)
        limit = max(0, total - self._page() - 1)
        scroll = min(max(self._scroll + rows, 0), limit)
        if scroll != self._scroll:
            self._scroll = scroll
            self._dirty = True

    def _copy(self) -> None:
        if self._state is State.ASK:
            return
        text = self._terminal.selected_text()
        if not text:
            return
        _copy_to_clipboard(text)
        lines = text.count("\n") + 1
        self._set_hint(f"Copied {lines} line{'s' if lines != 1 else ''} to the clipboard")

    # -------------------------------------------------------------- install
    def _start_install(self) -> None:
        self._set_state(State.INSTALLING)
        self._terminal.feed("$ " + " ".join(self._options.command) + "\n")
        self._process = InstallerProcess(self._notify)
        try:
            self._process.start(self._options.command, self._options.log_path, self._term_size())
        except OSError as error:
            self._process = None
            self._terminal.feed(f"Cannot run the installer: {error}\n")
            self._set_state(State.FAILED)

    def _collect_output(self) -> None:
        process = self._process
        if process is None:
            return
        text = process.take_output()
        if text:
            before = self._terminal.row_count(self._columns) if self._scroll else 0
            self._terminal.feed(text)
            if self._scroll:  # keep looking at the same rows while scrolled up
                self._scroll += self._terminal.row_count(self._columns) - before
            self._dirty = True
        if process.finished and self._state is State.INSTALLING:
            self._finish(process.returncode or 0)

    def _finish(self, status: int) -> None:
        check = self._options.check_path
        if status == 0 and check is not None and not check.exists():
            self._terminal.feed(f"\nThe installer finished, but {check} is still missing.\n")
            status = 1
        elif status != 0:
            self._terminal.feed(f"\nThe installer exited with status {status}.\n")
        self._process = None
        self._set_state(State.DONE if status == 0 else State.FAILED)

    # -------------------------------------------------------------- drawing
    def _draw(self) -> None:
        renderer = self._renderer
        sdl2.SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255)
        sdl2.SDL_RenderClear(renderer)
        if self._background is not None:
            self._draw_background()
        self._message.draw(renderer, *self._message_pos)
        for index, button in enumerate(self._buttons):
            self._draw_button(button, index == self._focus)
        if self._state is not State.ASK:
            self._draw_terminal()
        if self._hint is not None:
            margin = self._height // 14  # below the terminal
            self._hint.draw(
                renderer,
                (self._width - self._hint.width) // 2,
                self._height - (margin + self._hint.height) // 2,
            )
        sdl2.SDL_RenderPresent(renderer)
        self._dirty = False

    def _draw_background(self) -> None:
        """Scale the picture to cover the screen, cropping the overflow."""
        texture = self._background
        scale = max(self._width / texture.width, self._height / texture.height)
        src_w, src_h = round(self._width / scale), round(self._height / scale)
        source = sdl2.SDL_Rect(
            (texture.width - src_w) // 2, (texture.height - src_h) // 2, src_w, src_h
        )
        sdl2.SDL_RenderCopy(self._renderer, texture.handle, source, None)

    def _draw_button(self, button: _Button, focused: bool) -> None:
        renderer, rect = self._renderer, button.rect
        if focused:
            sdl2.SDL_SetRenderDrawColor(renderer, *_ACCENT, 255)
        else:
            sdl2.SDL_SetRenderDrawColor(renderer, 255, 255, 255, 28)
        sdl2.SDL_RenderFillRect(renderer, rect)
        sdl2.SDL_SetRenderDrawColor(renderer, 255, 255, 255, 255 if focused else 90)
        for inset in range(2 if focused else 1):
            border = sdl2.SDL_Rect(
                rect.x + inset, rect.y + inset, rect.w - 2 * inset, rect.h - 2 * inset
            )
            sdl2.SDL_RenderDrawRect(renderer, border)
        label = button.label
        label.draw(
            renderer, rect.x + (rect.w - label.width) // 2, rect.y + (rect.h - label.height) // 2
        )

    def _draw_terminal(self) -> None:
        """Rasterise the visible rows into the terminal texture and show it."""
        rect = self._term_rect
        if self._term_image is None:
            self._term_image = Image.new("RGB", (rect.w, rect.h))
            if self._term_texture is not None:
                self._term_texture.destroy()
            self._term_texture = _Texture(self._renderer, self._term_image, streaming=True)
        image = self._term_image
        image.paste((0, 0, 0), (0, 0, rect.w, rect.h))
        draw = ImageDraw.Draw(image)

        visible = self._page() + 1
        total = self._terminal.row_count(self._columns)
        self._scroll = min(self._scroll, max(0, total - visible))
        first = max(0, total - visible - self._scroll)
        self._visible_rows = self._terminal.rows(self._columns, first, visible, total)
        selection = self._terminal.selection()
        for index, row in enumerate(self._visible_rows):
            text = self._terminal.line(row.line)[row.start:row.end]
            y = _TERM_PAD + index * self._cell_height
            if selection is not None:
                self._draw_selection(draw, (row, text, y), selection)
            draw.text((_TERM_PAD, y), text, font=self._fonts.mono, fill=_WHITE)
        if self._state is State.INSTALLING:
            self._draw_cursor(draw)
        if total > visible:
            self._draw_scrollbar(draw, first, visible, total)
        draw.rectangle((0, 0, rect.w - 1, rect.h - 1), outline=(70, 74, 84))
        self._term_texture.update(image)
        self._term_texture.draw(self._renderer, rect.x, rect.y)

    def _draw_cursor(self, draw: ImageDraw.ImageDraw) -> None:
        """A block after the last character written, if that row is on screen."""
        line = self._terminal.cursor_line
        length = len(self._terminal.line(line))
        for index, row in enumerate(self._visible_rows):
            if row.line == line and row.end == length:
                font = self._fonts.mono
                width = font.getlength(" ")
                text = self._terminal.line(line)[row.start:row.end]
                x = min(_TERM_PAD + font.getlength(text), self._term_rect.w - _TERM_PAD - width)
                y = _TERM_PAD + index * self._cell_height
                draw.rectangle((x, y, x + width - 1, y + self._cell_height - 1), fill=_CURSOR)
                return

    def _draw_scrollbar(
        self, draw: ImageDraw.ImageDraw, first: int, visible: int, total: int
    ) -> None:
        track = self._term_rect.h - 2 * _TERM_PAD
        bar_h = max(self._cell_height, track * visible // total)
        bar_y = _TERM_PAD + (track - bar_h) * first // max(1, total - visible)
        right = self._term_rect.w - 3
        draw.rectangle((right - 3, bar_y, right, bar_y + bar_h), fill=(110, 110, 110))

    def _draw_selection(
        self, draw: ImageDraw.ImageDraw, placed: tuple[Row, str, int],
        selection: tuple[Position, Position],
    ) -> None:
        """Highlight the selected part of a row (``placed``: row, its text, its y)."""
        row, text, y = placed
        start, end = selection
        if not start.line <= row.line <= end.line:
            return
        # a selection running past a line end also covers one cell for the newline
        begin = max(start.column - row.start if row.line == start.line else 0, 0)
        stop = min(end.column - row.start if row.line == end.line else len(text) + 1, len(text) + 1)
        if begin >= stop:
            return
        font = self._fonts.mono
        x0 = _TERM_PAD + font.getlength(text[:begin])
        x1 = _TERM_PAD + font.getlength(text[:stop])
        if stop > len(text):
            x1 += font.getlength(" ")
        draw.rectangle((x0, y, x1 - 1, y + self._cell_height - 1), fill=_SELECTION)


# ------------------------------------------------------------------ clipboard
def _copy_to_clipboard(text: str) -> None:
    """Put text on the clipboard so that it outlives this window.

    SDL owns its clipboard only while the window exists, so a clipboard tool
    that stays behind is preferred when one is installed.
    """
    sdl2.SDL_SetClipboardText(text.encode())
    for command in _CLIPBOARD_TOOLS:
        tool = shutil.which(command[0])
        if tool is None:
            continue
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            if subprocess.run(
                [tool, *command[1:]], input=text.encode(), stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=3, check=False, start_new_session=True,
            ).returncode == 0:
                return
