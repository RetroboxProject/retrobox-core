"""Back in a web app: ``retrobox-webapp-back`` (``python3 -m retrobox.launcher.webapp_back``).

The pad profile of the web apps (``share/pad2key/profiles/apps.keys``) runs it
with the B button. It goes one page back in the history of the tab in front
and, when there is nowhere to go back to, closes that tab; closing the last
one quits the browser, which ends the game session and returns to
EmulationStation.

It talks to Chrome through the DevTools protocol: the Chrome generator starts
the browser with ``--remote-debugging-port=0`` (a free loopback port, which
Chrome records in ``<profile>/DevToolsActivePort``) and tells where the profile
is in ``<runtime dir>/webapp-profile``. Where that is not available (Firefox,
or a Chrome that is not running) it presses ``Alt+Left`` through uinput, which
every browser understands, so going back still works there.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import logging
import os
import socket
import struct
import sys
from pathlib import Path
from typing import Any, Final

from retrobox.configgen.utils.logger import setup_logging
from retrobox.paths import LOGS, RUNTIME_DIR

_logger = logging.getLogger(__name__)

PROFILE_POINTER: Final = RUNTIME_DIR / "webapp-profile"
_TIMEOUT: Final = 2.0
_GUID: Final = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WebSocket:
    """The bit of a WebSocket client the DevTools protocol needs (text frames only)."""

    def __init__(self, host: str, port: int, path: str) -> None:
        self._sock = socket.create_connection((host, port), timeout=_TIMEOUT)
        key = base64.b64encode(os.urandom(16))
        request = (
            f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key.decode()}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self._sock.sendall(request.encode())
        reply = b""
        while b"\r\n\r\n" not in reply:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise OSError("the browser closed the connection")
            reply += chunk
        head, _, self._buffer = reply.partition(b"\r\n\r\n")
        accept = base64.b64encode(hashlib.sha1(key + _GUID).digest())  # noqa: S324
        if b" 101 " not in head.split(b"\r\n", 1)[0] or accept not in head:
            raise OSError("the browser refused the WebSocket handshake")

    def close(self) -> None:
        """Close the connection."""
        self._sock.close()

    def send(self, text: str) -> None:
        """Send a text frame (client frames are masked)."""
        payload = text.encode()
        length = len(payload)
        if length < 126:
            header = struct.pack("!BB", 0x81, 0x80 | length)
        elif length < 65536:
            header = struct.pack("!BBH", 0x81, 0x80 | 126, length)
        else:
            header = struct.pack("!BBQ", 0x81, 0x80 | 127, length)
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self._sock.sendall(header + mask + masked)

    def _read(self, size: int) -> bytes:
        while len(self._buffer) < size:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise OSError("the browser closed the connection")
            self._buffer += chunk
        data, self._buffer = self._buffer[:size], self._buffer[size:]
        return data

    def receive(self) -> str:
        """The next text message (control frames are skipped; messages may be split)."""
        message = b""
        while True:
            first, second = self._read(2)
            length = second & 0x7F
            if length == 126:
                (length,) = struct.unpack("!H", self._read(2))
            elif length == 127:
                (length,) = struct.unpack("!Q", self._read(8))
            payload = self._read(length)  # servers do not mask
            opcode = first & 0x0F
            if opcode == 0x8:
                raise OSError("the browser closed the WebSocket")
            if opcode in (0x1, 0x0):
                message += payload
                if first & 0x80:
                    return message.decode()


class Devtools:
    """One DevTools connection to a target, with request/response matching."""

    def __init__(self, port: int, path: str) -> None:
        self._ws = WebSocket("127.0.0.1", port, path)
        self._next_id = 0

    def close(self) -> None:
        """Close the connection."""
        self._ws.close()

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        """Run a protocol command and return its result."""
        self._next_id += 1
        self._ws.send(json.dumps({"id": self._next_id, "method": method, "params": params}))
        while True:
            reply = json.loads(self._ws.receive())
            if reply.get("id") == self._next_id:
                if "error" in reply:
                    raise OSError(f"{method}: {reply['error'].get('message', reply['error'])}")
                return reply.get("result", {})


def _profile_dirs() -> list[Path]:
    """The profile folder the Chrome generator recorded."""
    try:
        recorded = PROFILE_POINTER.read_text(encoding="utf-8").strip()
    except OSError:
        return []
    return [Path(recorded)] if recorded else []


def _debugging_port() -> int | None:
    """The port Chrome listens on for DevTools, or None."""
    for folder in _profile_dirs():
        try:
            first = (folder / "DevToolsActivePort").read_text(encoding="utf-8").splitlines()[0]
            return int(first)
        except (OSError, IndexError, ValueError):
            continue
    return None


def _http_get(port: int, path: str) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=_TIMEOUT)
    try:
        connection.request("GET", path)
        return connection.getresponse().read().decode()
    finally:
        connection.close()


def _tab_in_front(port: int) -> dict[str, Any] | None:
    """The page that is showing: the only one whose visibilityState is "visible"."""
    pages = [t for t in json.loads(_http_get(port, "/json/list")) if t.get("type") == "page"]
    for page in pages:
        url = page.get("webSocketDebuggerUrl", "")
        if not url:
            continue
        devtools = Devtools(port, url.split(f":{port}", 1)[-1])
        try:
            state = devtools.call(
                "Runtime.evaluate", expression="document.visibilityState", returnByValue=True
            )
        except OSError:
            continue
        finally:
            devtools.close()
        if state.get("result", {}).get("value") == "visible":
            return page
    return pages[0] if pages else None


def go_back_or_close(port: int) -> str:
    """Go back in the tab in front, or close it. Returns what it did."""
    page = _tab_in_front(port)
    if page is None:
        raise OSError("the browser has no tab")
    devtools = Devtools(port, page["webSocketDebuggerUrl"].split(f":{port}", 1)[-1])
    try:
        history = devtools.call("Page.getNavigationHistory")
        index = int(history.get("currentIndex", 0))
        if index > 0:
            entry = history["entries"][index - 1]["id"]
            devtools.call("Page.navigateToHistoryEntry", entryId=entry)
            return "back"
    finally:
        devtools.close()
    # nothing behind: close the tab (the last one takes the browser with it)
    _http_get(port, f"/json/close/{page['id']}")  # answers in plain text
    return "closed"


def press_alt_left() -> None:
    """Press Alt+Left through uinput: the back shortcut of every browser."""
    import time  # pylint: disable=import-outside-toplevel

    from evdev import UInput, ecodes  # pylint: disable=import-outside-toplevel

    keys = [ecodes.KEY_LEFTALT, ecodes.KEY_LEFT]
    with UInput({ecodes.EV_KEY: keys}, name="retrobox-webapp-back") as keyboard:
        time.sleep(0.2)  # let the system notice the new device
        for key in keys:
            keyboard.write(ecodes.EV_KEY, key, 1)
            keyboard.syn()
        for key in reversed(keys):
            keyboard.write(ecodes.EV_KEY, key, 0)
            keyboard.syn()
        time.sleep(0.05)


def main() -> int:
    """Entry point; returns the exit status."""
    with setup_logging(LOGS / "retrobox-webapp-back.log"):
        port = _debugging_port()
        if port is not None:
            try:
                _logger.info("webapp back: %s", go_back_or_close(port))
                return 0
            except (OSError, ValueError, KeyError) as err:
                _logger.warning("DevTools not usable (%s): pressing Alt+Left", err)
        try:
            press_alt_left()
        except (ImportError, OSError) as err:
            _logger.error("cannot go back: %s", err)
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
