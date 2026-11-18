"""The row of each setting: label, editor, reset button, help and warnings.

A row only talks to the SettingsModel: it shows the value in effect, writes
every change to the model right away (the model keeps it pending until the
window applies it) and calls ``on_change`` so the window can update itself.
The editor depends on the kind of setting (schema.Kind): a check box, a menu
restricted to the allowed values, a folder field, the list of systems, a
number box (with its range and unit), a text field or a colour.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from retrobox.settings.model import is_valid_environ_name
from retrobox.settings.schema import FALSE, TRUE, Kind, Limits, Missing, setting_by_id

from .qt import (
    QAbstractItemView,
    QCheckBox,
    QColor,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFont,
    QFontMetrics,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QIcon,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRegularExpression,
    QRegularExpressionValidator,
    QSizePolicy,
    QSpinBox,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from retrobox.settings.model import SettingsModel
    from retrobox.settings.schema import Setting
    from retrobox.settings.systems import SystemInfo

    from .i18n import Translator

_LIST_SEPARATOR = os.pathsep  # as Retrobox splits these variables
_FOLDER_LIST_HEIGHT = 120
_SYSTEMS_SEPARATOR = ","
_SYSTEMS_LIST_HEIGHT = 260
_ENVIRON_TABLE_HEIGHT = 200
_COLOR_SWATCH = 22
_COLOR_FIELD_LETTERS = 11  # RRGGBBAA, and room around it


def _secondary_label(text: str = "") -> QLabel:
    """A small, dimmed, wrapping label (help lines)."""
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setEnabled(False)  # the palette's "disabled" text: dimmed, as KDE/GNOME do
    font = label.font()
    font.setPointSizeF(font.pointSizeF() * 0.9)
    label.setFont(font)
    return label


def _warning_label() -> QLabel:
    """A wrapping warning line, marked with a sign (no hard-coded colour, so it
    reads well with any theme)."""
    label = QLabel()
    label.setWordWrap(True)
    return label


def _fill_row(editor: QWidget) -> QWidget:
    """Compact editors (check box, menu, number, colour) keep their size,
    left-aligned, while the grid column still takes the free width (so help
    lines don't wrap)."""
    if not isinstance(editor, (QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox, _ColorEditor)):
        return editor
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(editor)
    layout.addStretch(1)
    return holder


def _icon_button(icon: str, fallback_text: str) -> QToolButton:
    button = QToolButton()
    themed = QIcon.fromTheme(icon)
    if themed.isNull():
        button.setText(fallback_text)
    else:
        button.setIcon(themed)
    button.setAutoRaise(True)
    return button


def _number_text(value: float, limits: Limits) -> str:
    """A number as written in the ini: no trailing zeros (``0.75``, ``1``)."""
    text = f"{value:.{limits.decimals}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _number(value: str, limits: Limits) -> float:
    """A number from the ini, in its range (an unreadable one: the minimum)."""
    try:
        number = float(value)
    except ValueError:
        number = limits.minimum
    return min(max(number, limits.minimum), limits.maximum)


def _number_editor(limits: Limits, on_edit: Callable[[str], None]) -> QWidget:
    """A number box with the range, step and unit of ``limits``; what is
    typed counts once it is done (Enter, or the focus leaving it)."""
    box: QSpinBox | QDoubleSpinBox
    if limits.decimals:
        box = QDoubleSpinBox()
        box.setDecimals(limits.decimals)
        box.setRange(limits.minimum, limits.maximum)
        box.setSingleStep(limits.step)
    else:
        box = QSpinBox()
        box.setRange(int(limits.minimum), int(limits.maximum))
        box.setSingleStep(int(limits.step))
    if limits.unit:
        box.setSuffix(f" {limits.unit}")
    box.setKeyboardTracking(False)
    box.valueChanged.connect(lambda value: on_edit(_number_text(value, limits)))
    return box


# ---------------------------------------------------------------- editors
class _TextEditor(QWidget):  # pylint: disable=too-few-public-methods
    """Free text (a format, a name)."""

    def __init__(self, on_edit: Callable[[str], None]) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.line = QLineEdit()
        self.line.setClearButtonEnabled(True)
        self.line.textEdited.connect(on_edit)
        layout.addWidget(self.line, 1)


class _ColorEditor(QWidget):  # pylint: disable=too-few-public-methods
    """A colour: a swatch that opens the colour picker (alpha included), and
    its ``RRGGBBAA`` to type."""

    def __init__(self, title: str, on_edit: Callable[[str], None]) -> None:
        super().__init__()
        self._title = title
        self._on_edit = on_edit
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._swatch = QToolButton()
        self._swatch.setFixedSize(_COLOR_SWATCH, _COLOR_SWATCH)
        self._swatch.clicked.connect(self._pick)
        self.line = QLineEdit()
        self.line.setValidator(
            QRegularExpressionValidator(QRegularExpression("[0-9A-Fa-f]{0,8}"), self.line)
        )
        width = QFontMetrics(self.line.font()).horizontalAdvance("F" * _COLOR_FIELD_LETTERS)
        self.line.setFixedWidth(width)
        self.line.textEdited.connect(self._typed)
        layout.addWidget(self._swatch)
        layout.addWidget(self.line)

    @staticmethod
    def _qcolor(value: str) -> QColor | None:
        value = value.strip()
        if len(value) not in (6, 8):
            return None
        try:
            red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
            alpha = int(value[6:8], 16) if len(value) == 8 else 255
        except ValueError:
            return None
        return QColor(red, green, blue, alpha)

    def _typed(self, text: str) -> None:
        if self._qcolor(text) is not None:
            self._paint(text)
            self._on_edit(text.upper())

    def _pick(self) -> None:
        current = self._qcolor(self.line.text()) or QColor(255, 255, 255)
        chosen = QColorDialog.getColor(
            current, self, self._title, QColorDialog.ColorDialogOption.ShowAlphaChannel
        )
        if chosen.isValid():
            value = "".join(
                f"{part:02X}"
                for part in (chosen.red(), chosen.green(), chosen.blue(), chosen.alpha())
            )
            self.show_value(value)
            self._on_edit(value)

    def _paint(self, value: str) -> None:
        color = self._qcolor(value)
        css = (
            f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"
            if color is not None else "transparent"
        )
        self._swatch.setStyleSheet(
            f"QToolButton {{ background: {css}; border: 1px solid palette(mid); }}"
        )

    def show_value(self, value: str) -> None:
        """Show ``value`` (``RRGGBBAA``), unless it is being typed."""
        if not self.line.hasFocus() and self.line.text().upper() != value.upper():
            self.line.setText(value.upper())
        self._paint(value)


class _FolderEditor(QWidget):  # pylint: disable=too-few-public-methods
    """One folder, typed or chosen with a browse button."""

    def __init__(self, translate: Translator, on_edit: Callable[[str], None]) -> None:
        super().__init__()
        self._on_edit = on_edit
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.line = QLineEdit()
        self.line.setClearButtonEnabled(True)
        self.line.textEdited.connect(on_edit)
        browse = QPushButton(translate("button.browse"))
        browse.setAutoDefault(False)
        browse.clicked.connect(self._browse)
        layout.addWidget(self.line, 1)
        layout.addWidget(browse)

    def _browse(self) -> None:
        current = self.line.text().strip()
        start = str(Path(current).expanduser()) if current else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "", start)
        if chosen:
            self.line.setText(chosen)
            self._on_edit(chosen)


class _FolderListEditor(QWidget):  # pylint: disable=too-few-public-methods
    """Several folders, one per row (they are saved ":"-separated)."""

    def __init__(self, translate: Translator, on_edit: Callable[[str], None]) -> None:
        super().__init__()
        self._on_edit = on_edit
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.default = _secondary_label()
        self._list = QListWidget()
        self._list.setMinimumHeight(_FOLDER_LIST_HEIGHT)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.itemChanged.connect(lambda _item: self._changed())

        buttons = QHBoxLayout()
        add = QPushButton(QIcon.fromTheme("list-add"), translate("button.add"))
        remove = QPushButton(QIcon.fromTheme("list-remove"), translate("button.remove"))
        for button in (add, remove):
            button.setAutoDefault(False)
        add.clicked.connect(self._add)
        remove.clicked.connect(self._remove)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)

        layout.addWidget(self._list)
        layout.addWidget(self.default)
        layout.addLayout(buttons)

    def _folders(self) -> list[str]:
        return [
            text for text in (self._list.item(i).text().strip() for i in range(self._list.count()))
            if text
        ]

    def _changed(self) -> None:
        self.default.setVisible(self._list.count() == 0)
        self._on_edit(_LIST_SEPARATOR.join(dict.fromkeys(self._folders())))

    def _add(self) -> None:
        folders = self._folders()
        start = str(Path(folders[-1]).expanduser()) if folders else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "", start)
        if chosen and chosen not in folders:
            self._list.addItem(self._item(chosen))
            self._changed()

    def _remove(self) -> None:
        for item in self._list.selectedItems():
            self._list.takeItem(self._list.row(item))
        self._changed()

    @staticmethod
    def _item(folder: str) -> QListWidgetItem:
        item = QListWidgetItem(folder)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)  # double-click to edit
        return item

    def show_value(self, value: str, default: str) -> None:
        """Show the folders of ``value`` (":"-separated), or ``default`` when none."""
        folders = [folder.strip() for folder in value.split(_LIST_SEPARATOR) if folder.strip()]
        if folders != self._folders():
            self._list.blockSignals(True)
            self._list.clear()
            for folder in folders:
                self._list.addItem(self._item(folder))
            self._list.blockSignals(False)
        self.default.setText(default)
        self.default.setVisible(not folders)


class _SystemsEditor(QWidget):  # pylint: disable=too-few-public-methods
    """The systems as a checkable, filterable list."""

    def __init__(
        self, translate: Translator, systems: list[SystemInfo], on_edit: Callable[[str], None]
    ) -> None:
        super().__init__()
        self._translate = translate
        self._on_edit = on_edit
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        self._filter = QLineEdit()
        self._filter.setPlaceholderText(translate("systems.filter"))
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._apply_filter)
        self._count = QLabel()
        top.addWidget(self._filter, 1)
        top.addWidget(self._count)

        self._list = QListWidget()
        self._list.setMinimumHeight(_SYSTEMS_LIST_HEIGHT)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for system in systems:
            text = system.fullname
            if system.manufacturer:
                text = f"{text}  ·  {system.manufacturer}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, system.name)
            item.setToolTip(system.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._list.addItem(item)
        self._list.itemChanged.connect(lambda _item: self._changed())

        layout.addLayout(top)
        layout.addWidget(self._list)

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for index in range(self._list.count()):
            item = self._list.item(index)
            haystack = f"{item.text()} {item.data(Qt.ItemDataRole.UserRole)}".lower()
            item.setHidden(bool(needle) and needle not in haystack)

    def _checked(self) -> list[str]:
        return [
            self._list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._list.count())
            if self._list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def _changed(self) -> None:
        checked = self._checked()
        self._count.setText(self._translate("systems.hidden", count=len(checked)))
        self._on_edit(_SYSTEMS_SEPARATOR.join(sorted(checked)))

    def show_value(self, value: str) -> None:
        """Check the systems of ``value`` (comma-separated)."""
        wanted = {name.strip().lower() for name in value.split(_SYSTEMS_SEPARATOR) if name.strip()}
        self._list.blockSignals(True)
        for index in range(self._list.count()):
            item = self._list.item(index)
            checked = item.data(Qt.ItemDataRole.UserRole) in wanted
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._list.blockSignals(False)
        self._count.setText(self._translate("systems.hidden", count=len(self._checked())))


# -------------------------------------------------------------------- row
class SettingRow:  # pylint: disable=too-many-instance-attributes
    """One setting, laid out on two or three rows of a group's grid."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        setting: Setting,
        model: SettingsModel,
        translate: Translator,
        on_change: Callable[[], None],
        systems: list[SystemInfo],
    ) -> None:
        self.setting = setting
        self._model = model
        self._tr = translate
        self._on_change = on_change

        self.label = QLabel(translate(setting.id))
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.reset = _icon_button("edit-undo", "↺")
        self.reset.clicked.connect(lambda: self._edit(None))
        self.help = _secondary_label()
        self.warning = _warning_label()
        self.editor = self._make_editor(systems)
        self.label.setBuddy(self.editor)
        self.field = _fill_row(self.editor)

    # ------------------------------------------------------------ layout
    def label_width(self) -> int:
        """Width the label needs, in bold (how it looks once customised)."""
        metrics = QFontMetrics(bold(self.label.font(), 1.0))
        return metrics.horizontalAdvance(self.label.text()) + 4

    def place(self, grid: QGridLayout, row: int) -> int:
        """Put the widgets on ``grid`` from ``row`` on; returns the next free row."""
        if self.setting.kind in (Kind.SYSTEMS, Kind.DIRECTORY_LIST):  # tall: label on top
            align = Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight
            grid.addWidget(self.label, row, 0, align)
            grid.addWidget(self.reset, row, 2, Qt.AlignmentFlag.AlignTop)
        else:
            grid.addWidget(self.label, row, 0)
            grid.addWidget(self.reset, row, 2)
        grid.addWidget(self.field, row, 1)
        grid.addWidget(self.help, row + 1, 1)
        grid.addWidget(self.warning, row + 2, 1)
        return row + 3

    def _make_editor(self, systems: list[SystemInfo]) -> QWidget:
        kind = self.setting.kind
        if kind is Kind.BOOL:
            box = QCheckBox()
            box.toggled.connect(lambda on: self._edit(TRUE if on else FALSE))
            return box
        if kind is Kind.CHOICE:
            combo = QComboBox()
            for value in self.setting.choices:
                combo.addItem(self._choice_label(value), value)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            combo.activated.connect(lambda index: self._edit(combo.itemData(index)))
            return combo
        return self._field_editor(systems)

    def _field_editor(self, systems: list[SystemInfo]) -> QWidget:
        """The editors that are fields: lists, numbers, text, colour, folder."""
        kind = self.setting.kind
        if kind is Kind.SYSTEMS:
            return _SystemsEditor(self._tr, systems, self._edit)
        if kind is Kind.DIRECTORY_LIST:
            return _FolderListEditor(self._tr, self._edit)
        if kind in (Kind.INTEGER, Kind.DECIMAL) and self.setting.limits is not None:
            return _number_editor(self.setting.limits, self._edit)
        if kind is Kind.TEXT:
            return _TextEditor(self._edit)
        if kind is Kind.COLOR:
            return _ColorEditor(self._tr(self.setting.id), self._edit)
        return _FolderEditor(self._tr, self._edit)

    # ------------------------------------------------------------ values
    def _choice_label(self, value: str) -> str:
        return self._tr.optional(f"choice.{value}") or value

    def _display(self, value: str) -> str:
        """A value as the user reads it (for the reset button's tooltip)."""
        kind = self.setting.kind
        if kind is Kind.BOOL:
            return self._tr("value.on" if value == TRUE else "value.off")
        if kind is Kind.CHOICE:
            return self._choice_label(value)
        limits = self.setting.limits
        if value and limits is not None and limits.unit:
            return f"{value} {limits.unit}"
        if not value:
            automatic = kind in (Kind.DIRECTORY_LIST, Kind.TEXT)
            return self._tr("value.automatic" if automatic else "value.empty")
        return value

    def _edit(self, value: str | None) -> None:
        self._model.set(self.setting, value)
        self._on_change()

    def refresh(self) -> None:
        """Show the model's state: value, custom or not, locked, warnings."""
        setting, model = self.setting, self._model
        locked = model.locked_by(setting)
        custom = model.is_custom(setting)
        inherited = model.inherited(setting)

        self._show_value(model.value(setting), inherited)

        font = self.label.font()
        font.setBold(custom and locked is None)
        self.label.setFont(font)
        self.editor.setEnabled(locked is None)
        self.reset.setEnabled(custom and locked is None)
        self.reset.setToolTip(self._tr("button.reset", value=self._display(inherited)))

        help_text = self._tr.optional(f"{setting.id}.help")
        if locked is not None:
            help_text = self._tr("value.locked", file=str(locked))
        self.help.setText(help_text)
        self.help.setVisible(bool(help_text))

        warning = self._missing_warning(model.user_value(setting)) if locked is None else ""
        self.warning.setText(f"⚠ {warning}" if warning else "")
        self.warning.setVisible(bool(warning))

    def _show_value(self, value: str, inherited: str) -> None:
        editor = self.editor
        editor.blockSignals(True)
        try:
            if isinstance(editor, QCheckBox):
                editor.setChecked(value == TRUE)
            elif isinstance(editor, QComboBox):
                index = editor.findData(value)
                if index < 0:  # a value the menu doesn't offer: show it anyway
                    editor.addItem(value, value)
                    index = editor.count() - 1
                editor.setCurrentIndex(index)
            elif isinstance(editor, (QSpinBox, QDoubleSpinBox)) and self.setting.limits:
                number = _number(value, self.setting.limits)
                editor.setValue(int(number) if isinstance(editor, QSpinBox) else number)
            elif isinstance(editor, _ColorEditor):
                editor.show_value(value)
            elif isinstance(editor, _TextEditor):
                user = self._model.user_value(self.setting) or ""
                if not editor.line.hasFocus() and editor.line.text() != user:
                    editor.line.setText(user)
                editor.line.setPlaceholderText(
                    self._tr("value.default", value=self._display(inherited))
                )
            elif isinstance(editor, _SystemsEditor):
                editor.show_value(value)
            elif isinstance(editor, _FolderListEditor):
                editor.show_value(
                    self._model.user_value(self.setting) or "",
                    self._tr("value.default", value=self._display(inherited)),
                )
            elif isinstance(editor, _FolderEditor):
                # never rewrite what is being typed (a path equal to the
                # default is stored as "no value", for instance)
                user = self._model.user_value(self.setting) or ""
                if not editor.line.hasFocus() and editor.line.text() != user:
                    editor.line.setText(user)
                editor.line.setPlaceholderText(
                    self._tr("value.default", value=self._display(inherited))
                )
        finally:
            editor.blockSignals(False)

    def _missing_warning(self, user: str | None) -> str:
        """Why a configured folder that doesn't exist won't be used as is."""
        missing = self.setting.missing
        if missing is None or not user or Path(user).expanduser().is_dir():
            return ""
        if missing is Missing.CREATED:
            return self._tr("missing.created")
        if missing is Missing.AUTOCORRECT:
            if self._model.value(setting_by_id("core.autocorrect_paths")) != TRUE:
                return self._tr("missing.as_written")
        return self._tr("missing.default")


# ----------------------------------------------------------------- environ
class EnvironEditor(QWidget):  # pylint: disable=too-few-public-methods
    """The free [environ] variables: an editable two-column table."""

    def __init__(
        self, model: SettingsModel, translate: Translator, on_change: Callable[[], None]
    ) -> None:
        super().__init__()
        self._model = model
        self._tr = translate
        self._on_change = on_change
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(
            [translate("environ.name"), translate("environ.value")]
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setMinimumHeight(_ENVIRON_TABLE_HEIGHT)
        self._table.itemChanged.connect(lambda _item: self._changed())

        buttons = QHBoxLayout()
        add = QPushButton(QIcon.fromTheme("list-add"), translate("button.add"))
        remove = QPushButton(QIcon.fromTheme("list-remove"), translate("button.remove"))
        for button in (add, remove):
            button.setAutoDefault(False)
        add.clicked.connect(self._add)
        remove.clicked.connect(self._remove)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)

        self._invalid = _warning_label()
        self._invalid.hide()

        layout.addWidget(self._table)
        layout.addLayout(buttons)
        layout.addWidget(self._invalid)

    def _rows(self) -> list[tuple[str, str]]:
        rows = []
        for row in range(self._table.rowCount()):
            name, value = self._table.item(row, 0), self._table.item(row, 1)
            rows.append(((name.text() if name else "").strip(), value.text() if value else ""))
        return rows

    def _changed(self) -> None:
        rows = [(name, value) for name, value in self._rows() if name]
        invalid = [name for name, _ in rows if not is_valid_environ_name(name)]
        self._invalid.setText("⚠ " + self._tr("environ.invalid", names=", ".join(invalid)))
        self._invalid.setVisible(bool(invalid))
        self._model.set_custom_environ(dict(rows))
        self._on_change()

    def _add(self) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(""))
        self._table.setItem(row, 1, QTableWidgetItem(""))
        self._table.setCurrentCell(row, 0)
        self._table.editItem(self._table.item(row, 0))

    def _remove(self) -> None:
        rows = sorted({index.row() for index in self._table.selectedIndexes()}, reverse=True)
        if not rows and self._table.currentRow() >= 0:
            rows = [self._table.currentRow()]
        for row in rows:
            self._table.removeRow(row)
        self._changed()

    def refresh(self, force: bool = False) -> None:
        """Show the model's variables.

        Only when ``force``d (start, after saving): otherwise the table is
        what the user is typing, rows with an unfinished or invalid name
        included, and the model follows it.
        """
        if not force:
            return
        variables = self._model.custom_environ()
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        for name, value in variables.items():
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(name))
            self._table.setItem(row, 1, QTableWidgetItem(value))
        self._table.blockSignals(False)


def bold(font: QFont, factor: float) -> QFont:
    """``font``, bold and ``factor`` times bigger (titles)."""
    font = QFont(font)
    font.setBold(True)
    font.setPointSizeF(font.pointSizeF() * factor)
    return font
