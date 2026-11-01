"""``python3 -m retrobox.settingsui`` (what ``retrobox --settings`` runs)."""

from __future__ import annotations

import sys
from typing import Final

MISSING_QT: Final = (
    "the settings window needs Qt for Python: install PySide6 "
    "(Debian/Ubuntu: python3-pyside6.qtwidgets; Fedora: python3-pyside6) "
    "or PyQt6 (python3-pyqt6)."
)


def main(argv: list[str] | None = None) -> int:
    """Show the settings window; returns the exit status."""
    try:
        from .qt import QApplication, QIcon  # pylint: disable=import-outside-toplevel
    except ImportError:
        print(f"retrobox: {MISSING_QT}", file=sys.stderr)
        return 1

    # pylint: disable=import-outside-toplevel  # only once Qt is known to be there
    from retrobox.emusetup.launch import ICON
    from retrobox.utils.es_settings import read_es_settings
    from retrobox.paths import ES_SETTINGS_CFG
    from retrobox.settings.model import SettingsModel
    from retrobox.settings.systems import available_systems

    from .i18n import Translator
    from .window import SettingsWindow

    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("retrobox-settings")
    # Wayland app_id: the desktop entry that gives the window its name and icon
    app.setDesktopFileName("retrobox")
    if ICON.is_file():
        app.setWindowIcon(QIcon(str(ICON)))

    translate = Translator(read_es_settings(ES_SETTINGS_CFG).get("Language", ""))
    app.setApplicationDisplayName(translate("window.title"))
    window = SettingsWindow(SettingsModel(), translate, available_systems())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
