"""Keyboard -> bytes for the installer's terminal, as a terminal emulator sends them.

Printable text arrives through SDL_TEXTINPUT (so keyboard layouts and dead
keys just work); this module covers the keys that produce no text: Enter,
Backspace, arrows, Ctrl+letter...
"""

from __future__ import annotations

from typing import Final

import sdl2

_SPECIAL_KEYS: Final[dict[int, bytes]] = {
    sdl2.SDLK_RETURN: b"\r",
    sdl2.SDLK_KP_ENTER: b"\r",
    sdl2.SDLK_BACKSPACE: b"\x7f",
    sdl2.SDLK_TAB: b"\t",
    sdl2.SDLK_ESCAPE: b"\x1b",
    sdl2.SDLK_UP: b"\x1b[A",
    sdl2.SDLK_DOWN: b"\x1b[B",
    sdl2.SDLK_RIGHT: b"\x1b[C",
    sdl2.SDLK_LEFT: b"\x1b[D",
    sdl2.SDLK_HOME: b"\x1b[H",
    sdl2.SDLK_END: b"\x1b[F",
    sdl2.SDLK_DELETE: b"\x1b[3~",
}


def key_bytes(key: int, mod: int) -> bytes | None:
    """What a key press sends to the terminal, or None when it sends nothing.

    Ctrl+C is not special here: the caller decides first whether it copies.
    """
    if mod & sdl2.KMOD_CTRL and not mod & sdl2.KMOD_ALT:
        if sdl2.SDLK_a <= key <= sdl2.SDLK_z:
            return bytes((key - sdl2.SDLK_a + 1,))
        if key == sdl2.SDLK_BACKSPACE:
            return b"\x08"
        return None
    return _SPECIAL_KEYS.get(key)
