"""The add-ons Retrobox installs with Kodi, enabled before Kodi starts.

Kodi keeps add-ons copied into its ``addons`` folder by hand disabled until
someone enables them in its add-on manager (its database, ``Addons<N>.db``,
says so). ``tools/emulators/kodi.sh`` puts the WebApp Launcher there, so
``retrobox-kodi-launch`` marks it enabled in that database each time Kodi is
started from Retrobox. Before Kodi's first start there is no database yet: Kodi then finds
the add-on on its own, and it is enabled from the next start on.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

# what kodi.sh installs with Kodi
RETROBOX_ADDONS: Final = ("plugin.program.webapplauncher",)

_DATABASE: Final = re.compile(r"Addons(\d+)\.db")


def _database(userdata: Path) -> Path | None:
    """The newest add-on database of that userdata folder, if Kodi made one."""
    folder = userdata / "Database"
    if not folder.is_dir():
        return None
    found = [(int(match.group(1)), path) for path in folder.iterdir()
             if (match := _DATABASE.fullmatch(path.name))]
    return max(found)[1] if found else None


def enable_addons(userdata: Path, addons: tuple[str, ...] = RETROBOX_ADDONS) -> list[str]:
    """Mark as enabled those of ``addons`` that are in Kodi's ``addons`` folder.

    Arguments:
        userdata: Kodi's userdata folder (its add-ons are in ``../addons``).
        addons: the add-on ids.

    Returns:
        The ids that were enabled (none when Kodi has no database yet).
    """
    present = [addon for addon in addons if (userdata.parent / "addons" / addon).is_dir()]
    database = _database(userdata) if present else None
    if database is None:
        return []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    enabled = []
    try:
        with sqlite3.connect(database, timeout=5) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(installed)")}
            if not {"addonID", "enabled"} <= columns:
                _logger.warning("%s has no table of installed add-ons", database)
                return []
            for addon in present:
                updated = connection.execute(
                    "UPDATE installed SET enabled = 1 WHERE addonID = ?", (addon,)
                ).rowcount
                if not updated:
                    values = {"addonID": addon, "enabled": 1, "installDate": now,
                              "lastUpdated": now, "origin": ""}
                    names = [name for name in values if name in columns]
                    connection.execute(
                        f"INSERT INTO installed ({', '.join(names)}) "
                        f"VALUES ({', '.join('?' for _ in names)})",
                        [values[name] for name in names],
                    )
                enabled.append(addon)
    except sqlite3.Error as error:
        _logger.warning("could not enable %s in %s: %s", ", ".join(present), database, error)
        return []
    return enabled
