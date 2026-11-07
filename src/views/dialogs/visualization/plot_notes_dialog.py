# src/views/dialogs/visualization/plot_notes_dialog.py
"""Your own labels on the plot (band labels, texts, arrows):
  * NotesTable - the list: text, size, colour, rotation, bold, delete (used
    in "Labels on the plot…" and in Save plot for publication › Labels);
  * PlotNotesDialog - the window "Labels on the plot…";
  * NoteEditDialog - one label, after a double-click on it.
Every change is drawn at once (through PlotNotesController)."""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                             QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from src.modules.visualization.plot_notes import HEADS, KINDS, fmt
from src.views.dialogs.misc.rich_text import RichTextButton, RichTextEditor


def _colour_button(colour):
    from src.views.dialogs.visualization.publication_dialog import ColourButton
    return ColourButton(colour)


class NotesTable(QTableWidget):
    """The labels in a table; changes go to the controller at once."""
    COLUMNS = ["Kind", "Text", "At x", "Size", "Colour", "Rotation", "Bold", "Head", ""]
    changed = pyqtSignal()

    def __init__(self, controller, parent=None):
        super().__init__(0, len(self.COLUMNS), parent)
        self.controller = controller
        self._building = False
        self.setHorizontalHeaderLabels(self.COLUMNS)
        self.verticalHeader().setVisible(False)
        # every column keeps its width (drag a column's edge in the header to make it
        # wider): the table does not jump when the window or the bar beside it moves
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(30)
        for col, width in ((0, 70), (1, 150), (2, 52), (3, 78), (4, 52), (5, 80), (6, 40),
                           (7, 100), (8, 72)):
            self.setColumnWidth(col, width)
        self.setToolTip("Each label: its text - click it to change it (superscript, Greek\n"
                        "letters, signs); an arrow: the text at its tail, may be empty;\n"
                        "size (an arrow: also its line and head), colour, rotation of the text,\n"
                        "bold; Delete removes it.")
        self.refresh()

    def refresh(self):
        if self._building:
            return
        self._building = True
        try:
            notes = self.controller.notes.notes
            kinds = dict(KINDS)
            self.setRowCount(len(notes))
            for i, n in enumerate(notes):
                kind = QTableWidgetItem(kinds.get(n['kind'], n['kind']))
                kind.setFlags(kind.flags() & ~Qt.ItemIsEditable)
                self.setItem(i, 0, kind)
                text = RichTextButton(n['text'], "Text of the label")
                text.setPlaceholderText("(no text)" if n['kind'] == 'arrow' else "")
                text.textChanged.connect(lambda v, i=i: self._set(i, text=v))
                self.setCellWidget(i, 1, text)
                at = QTableWidgetItem(fmt(n['x']))
                at.setFlags(at.flags() & ~Qt.ItemIsEditable)
                self.setItem(i, 2, at)
                size = QDoubleSpinBox()
                size.setRange(3, 48)
                size.setSingleStep(0.5)
                size.setSuffix(" pt")
                size.setValue(float(n['fontsize']))
                size.valueChanged.connect(lambda v, i=i: self._set(i, fontsize=v))
                self.setCellWidget(i, 3, size)
                colour = _colour_button(n['color'])
                colour.changed.connect(lambda v, i=i: self._set(i, color=v))
                self.setCellWidget(i, 4, colour)
                rot = QDoubleSpinBox()
                rot.setRange(-180, 180)
                rot.setSingleStep(15)
                rot.setSuffix("°")
                rot.setValue(float(n['rotation']))
                rot.valueChanged.connect(lambda v, i=i: self._set(i, rotation=v))
                self.setCellWidget(i, 5, rot)
                bold = QCheckBox()
                bold.setChecked(bool(n['bold']))
                bold.toggled.connect(lambda v, i=i: self._set(i, bold=v))
                holder = QWidget()
                hb = QHBoxLayout(holder)
                hb.setContentsMargins(8, 0, 0, 0)
                hb.addWidget(bold)
                self.setCellWidget(i, 6, holder)
                if n['kind'] == 'arrow':
                    head = QComboBox()
                    for key, name in HEADS:
                        head.addItem(name, key)
                    head.setCurrentIndex(max(0, head.findData(n.get('head', 'tip'))))
                    head.setToolTip("Head: where the arrow's head is - at its tip, at its "
                                    "text, at both ends, or none.")
                    head.currentIndexChanged.connect(
                        lambda _k, i=i, w=head: self._set(i, head=w.currentData()))
                    self.setCellWidget(i, 7, head)
                else:
                    self.removeCellWidget(i, 7)
                    empty = QTableWidgetItem("")
                    empty.setFlags(Qt.NoItemFlags)
                    self.setItem(i, 7, empty)
                delete = QPushButton("Delete")
                delete.setAutoDefault(False)
                delete.clicked.connect(lambda _c=False, i=i: self._delete(i))
                self.setCellWidget(i, 8, delete)
                self.setRowHeight(i, 28)
        finally:
            self._building = False

    def _set(self, i, **values):
        if self._building:
            return
        self.controller.notes.update(i, **values)
        self._building = True                  # the table stays (no rebuild while typing)
        try:
            self.controller.redraw()
        finally:
            self._building = False
        self.changed.emit()

    def _delete(self, i):
        self.controller.notes.remove(i)
        self.controller.selected = None
        self.controller.redraw()
        self.changed.emit()


class PlotNotesDialog(QDialog):
    """Labels on the plot…: the list of your labels."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Labels on the plot")
        self.setWindowFlags((self.windowFlags() | Qt.WindowMaximizeButtonHint)
                            & ~Qt.WindowMinimizeButtonHint)
        box = QVBoxLayout(self)
        hint = QLabel("Add labels with a right-click on the plot: <b>Label the band here</b>, "
                      "<b>Add text here</b>, <b>Add an arrow here</b>. On the plot: click a label "
                      "to choose it (Delete key: delete it), double-click to change it, drag to "
                      "move it.")
        hint.setWordWrap(True)
        box.addWidget(hint)
        self.table = NotesTable(controller)
        box.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.delete_all_button = QPushButton("Delete all")
        self.delete_all_button.setAutoDefault(False)
        self.delete_all_button.setToolTip("Delete all: every label on the plot.")
        self.delete_all_button.clicked.connect(self._delete_all)
        row.addWidget(self.delete_all_button)
        row.addStretch(1)
        close = QPushButton("Close")
        close.setAutoDefault(False)
        close.clicked.connect(self.close)
        row.addWidget(close)
        from src.views import icons
        help_button = icons.help_button("Labels on the plot")
        help_button.clicked.connect(self._help)
        row.addWidget(help_button)
        box.addLayout(row)
        self.resize(720, 360)
        self.refresh()

    def refresh(self):
        self.table.refresh()
        self.delete_all_button.setEnabled(bool(self.controller.notes.notes))

    def _delete_all(self):
        if QMessageBox.question(self, "Labels on the plot", "Delete all labels on the plot?") \
                == QMessageBox.Yes:
            self.controller.clear()

    def _help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'user_guide', 'plot-labels')


class NoteEditDialog(QDialog):
    """One label (after a double-click on it): text, size, colour, rotation,
    bold; Delete removes it. exec_(): 1 OK, 0 Cancel, DELETE."""
    DELETE = 2

    def __init__(self, note, parent=None):
        super().__init__(parent)
        kinds = dict(KINDS)
        self.setWindowTitle(f"Label: {kinds.get(note['kind'], note['kind'])}")
        form = QFormLayout(self)
        self.text_edit = RichTextEditor(note['text'], multiline=True)
        if note['kind'] == 'arrow':
            self.text_edit.edit.setPlaceholderText("(no text: only the arrow)")
        form.addRow("Text:" if note['kind'] != 'arrow' else "Text at the tail:", self.text_edit)
        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(3, 48)
        self.size_spin.setSingleStep(0.5)
        self.size_spin.setSuffix(" pt")
        self.size_spin.setValue(float(note['fontsize']))
        if note['kind'] == 'arrow':
            self.size_spin.setToolTip("Size: of the text and of the arrow (its line and head).\n"
                                      "Its length and direction: drag its ends on the plot.")
        form.addRow("Size:", self.size_spin)
        self.colour = _colour_button(note['color'])
        form.addRow("Colour:", self.colour)
        self.rot_spin = QDoubleSpinBox()
        self.rot_spin.setRange(-180, 180)
        self.rot_spin.setSingleStep(15)
        self.rot_spin.setSuffix("°")
        self.rot_spin.setValue(float(note['rotation']))
        if note['kind'] == 'arrow':
            self.rot_spin.setToolTip("Rotation: of the arrow's text. The arrow itself: drag its\n"
                                     "tail end on the plot to turn it.")
        form.addRow("Rotation:", self.rot_spin)
        self.bold_check = QCheckBox("Bold")
        self.bold_check.setChecked(bool(note['bold']))
        form.addRow("", self.bold_check)
        self.head_combo = None
        if note['kind'] == 'arrow':
            self.head_combo = QComboBox()
            for key, name in HEADS:
                self.head_combo.addItem(name, key)
            self.head_combo.setCurrentIndex(max(0, self.head_combo.findData(
                note.get('head', 'tip'))))
            self.head_combo.setToolTip("Head: at the tip (pointing at the place), at the "
                                       "text, at both ends, or none.")
            form.addRow("Head:", self.head_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        delete = buttons.addButton("Delete", QDialogButtonBox.DestructiveRole)
        delete.setToolTip("Delete: this label.")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        delete.clicked.connect(lambda: self.done(self.DELETE))
        form.addRow(buttons)

    def values(self):
        values = {'text': self.text_edit.text(), 'fontsize': self.size_spin.value(),
                  'color': self.colour.colour(), 'rotation': self.rot_spin.value(),
                  'bold': self.bold_check.isChecked()}
        if self.head_combo is not None:
            values['head'] = self.head_combo.currentData()
        return values
