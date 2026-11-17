"""A minimal org.freedesktop.ScreenSaver service for the tests.

Prints one line per call (``Inhibit <args>`` / ``UnInhibit <args>``) and
answers Inhibit with the cookie 42. Run it on a private session bus
(``dbus-run-session``); it ends when the bus goes away.
"""

from __future__ import annotations

import sys

from jeepney import HeaderFields, MessageType, new_method_return
from jeepney.bus_messages import message_bus
from jeepney.io.blocking import open_dbus_connection

COOKIE = 42


def main() -> int:
    """Serve until the bus closes."""
    connection = open_dbus_connection(bus="SESSION")
    connection.send_and_get_reply(message_bus.RequestName("org.freedesktop.ScreenSaver"))
    print("ready", flush=True)
    while True:
        try:
            message = connection.receive()
        except (ConnectionError, OSError):
            return 0
        if message.header.message_type != MessageType.method_call:
            continue
        member = message.header.fields.get(HeaderFields.member)
        print(member, *message.body, flush=True)
        if member == "Inhibit":
            connection.send(new_method_return(message, "u", (COOKIE,)))
        else:
            connection.send(new_method_return(message))


if __name__ == "__main__":
    sys.exit(main())
