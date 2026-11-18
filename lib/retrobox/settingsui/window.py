"""The settings window: navigation on the left, one page per entry, buttons.

Layout, top-down: the pages of schema.PAGES (title, short description, then
one framed group per schema.Group with its settings aligned in a grid) next
to the navigation list; under them, a status line and the buttons. A page
whose program is not installed is left out (the overlay's, see
``shown_pages``); each page edits its own file (``Page.ini``), all of them
saved together:

* Apply: save, stay open;
* Accept and exit: save and close;
* Accept and open Retrobox: save, start Retrobox and close;
* Close: close without saving.

Apply is only enabled when something changed. If saving fails, the window
says why and stays open, keeping the changes. Shortcuts: Ctrl+S applies,
Escape closes.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING, Callable

from retrobox.settings.schema import PAGES

from .editors import EnvironEditor, SettingRow, bold
from .launch import launch_retrobox
from .qt import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QIcon,
    QKeySequence,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSize,
    QStackedWidget,
    Qt,
    QTimer,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from retrobox.settings.model import SettingsModel
    from retrobox.settings.schema import Group, Page
    from retrobox.settings.systems import SystemInfo

    from .i18n import Translator

_NAV_WIDTH = 210
_NAV_ICON = 22
_TITLE_SCALE = 1.5
_STATUS_TIMEOUT_MS = 4000
_DEFAULT_SIZE = QSize(980, 700)


def shown_pages() -> tuple[Page, ...]:
    """The pages whose program is installed (all of retrobox.ini's)."""
    return tuple(page for page in PAGES if not page.requires or shutil.which(page.requires))


# pylint: disable-next=too-few-public-methods,too-many-instance-attributes
class SettingsWindow(QMainWindow):
    """The whole settings window (see the module docstring)."""

    def __init__(
        self,
        models: Mapping[str, SettingsModel],
        translate: Translator,
        systems: list[SystemInfo],
    ) -> None:
        """``models``: the model of each page's file (``Page.ini``)."""
        super().__init__()
        self._models = dict(models)
        self._tr = translate
        self._systems = systems
        self._rows: list[SettingRow] = []
        self._environ: list[EnvironEditor] = []

        self.setWindowTitle(translate("window.title"))
        self.resize(_DEFAULT_SIZE)

        self._nav = QListWidget()
        self._stack = QStackedWidget()
        self._status = QLabel()
        self._apply = self._button("button.apply", "dialog-ok-apply", self._on_apply)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(self._body(), 1)
        layout.addWidget(self._separator())
        layout.addLayout(self._button_bar())
        self.setCentralWidget(central)

        QShortcut(QKeySequence.StandardKey.Save, self, activated=self._on_apply)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.close)
        self._refresh(force=True)

    # ------------------------------------------------------------ building
    def _body(self) -> QHBoxLayout:
        self._nav.setFixedWidth(_NAV_WIDTH)
        self._nav.setIconSize(QSize(_NAV_ICON, _NAV_ICON))
        self._nav.setSpacing(2)
        for page in (page for page in PAGES if page.ini in self._models):
            item = QListWidgetItem(QIcon.fromTheme(page.icon), self._tr(f"page.{page.id}"))
            self._nav.addItem(item)
            self._stack.addWidget(self._page(page))
        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.setCurrentRow(0)

        body = QHBoxLayout()
        body.addWidget(self._nav)
        body.addWidget(self._stack, 1)
        return body

    def _page(self, page: Page) -> QScrollArea:
        content = QWidget()
        layout = QVBoxLayout(content)
        title = QLabel(self._tr(f"page.{page.id}"))
        title.setFont(bold(title.font(), _TITLE_SCALE))
        description = QLabel(self._tr.optional(f"page.{page.id}.help"))
        description.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addSpacing(6)
        first_row = len(self._rows)
        grids = []
        for group in page.groups:
            box, grid = self._group(group, self._models[page.ini])
            layout.addWidget(box)
            if grid is not None:
                grids.append(grid)
        layout.addStretch(1)

        # one label column for the whole page, so every editor starts at the same x
        widths = [row.label_width() for row in self._rows[first_row:]]
        for grid in grids:
            grid.setColumnMinimumWidth(0, max(widths, default=0))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _group(self, group: Group, model: SettingsModel) -> tuple[QGroupBox, QGridLayout | None]:
        box = QGroupBox(self._tr(f"group.{group.id}"))
        layout = QVBoxLayout(box)
        help_text = self._tr.optional(f"group.{group.id}.help")
        if help_text:
            description = QLabel(help_text)
            description.setWordWrap(True)
            layout.addWidget(description)

        if group.custom_environ:
            editor = EnvironEditor(model, self._tr, self._refresh)
            self._environ.append(editor)
            layout.addWidget(editor)
            return box, None

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(2)
        row = 0
        for setting in group.settings:
            setting_row = SettingRow(setting, model, self._tr, self._refresh, self._systems)
            row = setting_row.place(grid, row)
            self._rows.append(setting_row)
        layout.addLayout(grid)
        return box, grid

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _button(self, text: str, icon: str, slot: Callable[[], object]) -> QPushButton:
        button = QPushButton(QIcon.fromTheme(icon), self._tr(text))
        button.setAutoDefault(False)  # Enter in a field must not save (or start Retrobox)
        button.clicked.connect(slot)
        return button

    def _button_bar(self) -> QHBoxLayout:
        buttons = QHBoxLayout()
        buttons.addWidget(self._status, 1)
        buttons.addWidget(self._apply)
        buttons.addWidget(self._button("button.accept", "dialog-ok", self._on_accept))
        buttons.addWidget(
            self._button("button.accept_open", "media-playback-start", self._on_accept_open)
        )
        buttons.addWidget(self._button("button.close", "dialog-close", self.close))
        return buttons

    # ------------------------------------------------------------- actions
    def _refresh(self, force: bool = False) -> None:
        """Show the model's state everywhere (after every change)."""
        for row in self._rows:
            row.refresh()
        for editor in self._environ:
            editor.refresh(force)
        self._apply.setEnabled(self._dirty)
        if self._dirty:
            self._status.clear()

    @property
    def _dirty(self) -> bool:
        return any(model.dirty for model in self._models.values())

    def _save(self) -> bool:
        """Apply the changes, file by file; on failure, say why and keep
        those of the file that failed (and the ones after it)."""
        for model in self._models.values():
            try:
                model.apply()
            except OSError as error:
                QMessageBox.critical(
                    self, self._tr("window.title"),
                    self._tr("window.save_failed", file=model.user_file, error=error),
                )
                self._refresh(force=True)
                return False
        self._refresh(force=True)
        return True

    def _on_apply(self) -> None:
        if self._dirty and self._save():
            self._status.setText(self._tr("window.saved"))
            QTimer.singleShot(_STATUS_TIMEOUT_MS, self._status.clear)

    def _on_accept(self) -> None:
        if self._save():
            self.close()

    def _on_accept_open(self) -> None:
        if not self._save():
            return
        try:
            launch_retrobox()
        except OSError as error:
            QMessageBox.critical(
                self, self._tr("window.title"), self._tr("window.open_failed", error=error)
            )
            return
        self.close()
