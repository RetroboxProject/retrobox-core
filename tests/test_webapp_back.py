"""Tests for retrobox-webapp-back: history check against a fake DevTools server."""
from __future__ import annotations

import base64
import hashlib
import json
import socket
import struct
import threading
from typing import Any

import pytest

from retrobox.launcher import webapp_back

_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _frame(text: str) -> bytes:
    payload = text.encode()
    if len(payload) < 126:
        return struct.pack("!BB", 0x81, len(payload)) + payload
    return struct.pack("!BBH", 0x81, 126, len(payload)) + payload


def _read_frame(conn: socket.socket) -> str:
    def need(size: int) -> bytes:
        data = b""
        while len(data) < size:
            data += conn.recv(size - len(data))
        return data

    _, second = need(2)
    length = second & 0x7F
    if length == 126:
        (length,) = struct.unpack("!H", need(2))
    mask = need(4)
    body = bytes(b ^ mask[i % 4] for i, b in enumerate(need(length)))
    return body.decode()


class FakeChrome:  # pylint: disable=too-few-public-methods
    """A DevTools endpoint with one visible page and a given navigation history."""

    def __init__(self, current_index: int) -> None:
        self.current_index = current_index
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed: list[str] = []
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(8)
        self.port = self.server.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        request = b""
        while b"\r\n\r\n" not in request:
            request += conn.recv(4096)
        lines = request.decode().split("\r\n")
        path = lines[0].split()[1]
        if "Upgrade: websocket" not in request.decode():
            if path == "/json/list":
                body = json.dumps([{
                    "id": "TAB1", "type": "page",
                    "webSocketDebuggerUrl": f"ws://127.0.0.1:{self.port}/devtools/page/TAB1",
                }]).encode()
            else:
                self.closed.append(path.rsplit("/", 1)[-1])
                body = b"Target is closing"
            conn.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body)
                + body
            )
            conn.close()
            return
        key = next(l.split(": ")[1] for l in lines if l.startswith("Sec-WebSocket-Key"))
        accept = base64.b64encode(hashlib.sha1(key.encode() + _GUID).digest()).decode()
        conn.sendall(
            ("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
             f"Connection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n").encode()
        )
        try:
            while True:
                message = json.loads(_read_frame(conn))
                self.calls.append((message["method"], message["params"]))
                result: dict[str, Any] = {}
                if message["method"] == "Runtime.evaluate":
                    result = {"result": {"value": "visible"}}
                elif message["method"] == "Page.getNavigationHistory":
                    result = {
                        "currentIndex": self.current_index,
                        "entries": [{"id": 10 + i} for i in range(self.current_index + 1)],
                    }
                conn.sendall(_frame(json.dumps({"id": message["id"], "result": result})))
        except (OSError, ValueError, IndexError):
            conn.close()


@pytest.fixture(name="chrome")
def _chrome(request: pytest.FixtureRequest) -> FakeChrome:
    return FakeChrome(request.param)


@pytest.mark.parametrize("chrome", [2], indirect=True)
def test_goes_back_when_there_is_history(chrome: FakeChrome) -> None:
    """With pages behind, it navigates to the previous history entry."""
    assert webapp_back.go_back_or_close(chrome.port) == "back"
    assert ("Page.navigateToHistoryEntry", {"entryId": 11}) in chrome.calls
    assert not chrome.closed


@pytest.mark.parametrize("chrome", [0], indirect=True)
def test_closes_the_tab_without_history(chrome: FakeChrome) -> None:
    """With nothing behind, it closes the tab."""
    assert webapp_back.go_back_or_close(chrome.port) == "closed"
    assert chrome.closed == ["TAB1"]
