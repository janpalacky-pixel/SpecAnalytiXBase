# src/views/dialogs/visualization/publication_dialog.py
"""File › Save plot for publication…: the plot as a journal, a page or a
slide needs it - its size (cm), text, font, axes (titles, ranges, ticks,
frame), the spectra's lines (colours, styles, markers, each one or all at
once), grid, legend and a heatmap's colours - at 300/600/1200 dpi (TIFF, PNG)
or as PDF / SVG / EPS, with a preview in which the legend can be moved with
the mouse; printing with a print preview; the settings kept as named
profiles. Everything starts "as in the plot". The plot on the screen is not
changed (publication_figure / publication_style work on a copy)."""

import os

from PyQt5.QtCore import QObject, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QDoubleValidator, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox,
                             QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
                             QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
                             QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
                             QTabWidget, QVBoxLayout, QWidget)

from src.modules.visualization import publication_figure as pf
from src.views.dialogs.misc.rich_text import RichTextButton
from src.modules.visualization import publication_style as pst

PREF_KEY = 'publication_figure'
# The choices are kept while the program runs (the next time the window is
# opened), not after it is closed - each start begins "as in the plot";
# what should stay longer is saved as a profile. Only the place of the bar
# between the settings and the preview is kept for good.
_SESSION = {}
_SESSION_PANEL = {}                 # the bar's place, also only while the program runs
PROFILES_KEY = 'publication_profiles'
KEEP = pst.KEEP
AS_IN_PLOT = "as in the plot"
# kept for the next time only in a profile, not by themselves: they belong
# to one plot (its titles, ranges, spectra ...)
DATA_KEYS = ('x_title', 'y_title', 'title_mode', 'title_text', 'x_min', 'x_max', 'y_min',
             'y_max', 'x_step', 'y_step', 'series', 'legend_title', 'c_min', 'c_max',
             'cbar_label')


def all_defaults():
    return dict(pf.DEFAULTS, **pst.STYLE_DEFAULTS)


class PreviewLabel(QLabel):
    """The preview picture; a legend, a title or a label in it can be dragged
    with the mouse (`legend_moved(axes number, dx, dy)`, `text_moved(key, dx,
    dy)`, in the picture's pixels, y down); a title or label clicked
    (`clicked(key)`), double-clicked (`double_clicked(key)`); the Delete key
    (`delete_pressed()`)."""
    legend_moved = pyqtSignal(int, float, float)
    text_moved = pyqtSignal(str, float, float)
    clicked = pyqtSignal(object)
    double_clicked = pyqtSignal(str)
    delete_pressed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)      # the Delete key reaches it after a click
        self.boxes = []                 # [(axes number or key, box, frame)] in pixels
        self.ratio = 1.0                # picture pixels per screen pixel
        self.selected = None            # the key of the chosen label (a dashed frame)
        self._drag = None               # (key, QRectF, start point)
        self._shift = QPointF(0, 0)

    def _rect(self, box):
        return QRectF(box[0] / self.ratio, box[1] / self.ratio,
                      (box[2] - box[0]) / self.ratio, (box[3] - box[1]) / self.ratio)

    def _arrow_end_at(self, pos):
        """(key, part) of an arrow's end or middle under the mouse: 'tip',
        'tail' or 'shaft' - or None."""
        import math
        p = QPointF(pos)
        for key, box, extra in self.boxes:
            if not isinstance(extra, dict) or 'tip' not in extra:
                continue
            tip = QPointF(extra['tip'][0] / self.ratio, extra['tip'][1] / self.ratio)
            tail = QPointF(extra['tail'][0] / self.ratio, extra['tail'][1] / self.ratio)
            for part, end in (('tip', tip), ('tail', tail)):
                if math.hypot(p.x() - end.x(), p.y() - end.y()) <= 8:
                    return key, part
            dx, dy = tail.x() - tip.x(), tail.y() - tip.y()
            length2 = dx * dx + dy * dy
            if length2 > 0:
                t = max(0.0, min(1.0, ((p.x() - tip.x()) * dx + (p.y() - tip.y()) * dy) / length2))
                if math.hypot(p.x() - tip.x() - t * dx, p.y() - tip.y() - t * dy) <= 4:
                    return key, 'shaft'
        return None

    def dragged_arrow(self):
        """While an arrow is dragged: (tip, tail, text box or None) where they
        are now, in screen pixels - drawn at once over the picture, so the
        arrow follows the mouse (the picture itself is made again only when
        the mouse is let go). None when no arrow is dragged."""
        if self._drag is None or not isinstance(self._drag[0], str) or '|' not in self._drag[0]:
            return None
        key, _, part = self._drag[0].partition('|')
        found = next((b for b in self.boxes if b[0] == key), None)
        if found is None or not isinstance(found[2], dict) or 'tip' not in found[2]:
            return None
        extra, d = found[2], self._shift
        tip = QPointF(extra['tip'][0] / self.ratio, extra['tip'][1] / self.ratio)
        tail = QPointF(extra['tail'][0] / self.ratio, extra['tail'][1] / self.ratio)
        box = self._rect(found[1]) if extra.get('text') else None
        if part in ('tip', 'shaft'):
            tip = tip + d
        if part in ('tail', 'shaft'):
            tail = tail + d
            box = box.translated(d) if box is not None else None
        elif box is not None and part == 'tip':
            pass                                   # the text stays where it is
        return tip, tail, box

    def _legend_at(self, pos):
        # the smallest box first: a label inside the plot before the legend over it
        for i, box, frame in sorted(self.boxes, key=lambda b: (b[1][2] - b[1][0]) *
                                    (b[1][3] - b[1][1])):
            r = self._rect(box)
            if r.adjusted(-2, -2, 2, 2).contains(QPointF(pos)):
                return i, r
        return None

    def mousePressEvent(self, event):
        end = self._arrow_end_at(event.pos()) if event.button() == Qt.LeftButton else None
        if end is not None:                        # an arrow's end: turn / stretch / move it
            self._drag = (f"{end[0]}|{end[1]}", QRectF(), QPointF(event.pos()))
            self._shift = QPointF(0, 0)
            self.setCursor(Qt.ClosedHandCursor)
            return
        hit = self._legend_at(event.pos()) if event.button() == Qt.LeftButton else None
        if hit is None:
            if event.button() == Qt.LeftButton and self.selected is not None:
                self.clicked.emit(None)
            return super().mousePressEvent(event)
        self._drag = (hit[0], hit[1], QPointF(event.pos()))
        self._shift = QPointF(0, 0)
        self.setCursor(Qt.ClosedHandCursor)

    def mouseDoubleClickEvent(self, event):
        hit = self._legend_at(event.pos())
        if hit is not None and isinstance(hit[0], str):
            self._drag = None
            self.double_clicked.emit(hit[0])

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self._shift = QPointF(event.pos()) - self._drag[2]
            self.update()
            return
        on = self._arrow_end_at(event.pos()) or self._legend_at(event.pos())
        self.setCursor(Qt.OpenHandCursor if on else Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self._drag is None:
            return super().mouseReleaseEvent(event)
        i = self._drag[0]
        shift = QPointF(event.pos()) - self._drag[2]
        self._drag = None
        self.setCursor(Qt.OpenHandCursor)
        self.update()
        if abs(shift.x()) + abs(shift.y()) >= 2:
            if isinstance(i, str):
                self.text_moved.emit(i, shift.x() * self.ratio, shift.y() * self.ratio)
            else:
                self.legend_moved.emit(i, shift.x() * self.ratio, shift.y() * self.ratio)
        elif isinstance(i, str):
            self.clicked.emit(i.split('|')[0])     # a click, not a drag: chosen

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.selected is not None:
            self.delete_pressed.emit()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = None
        if self.selected is not None:
            found = next((b for b in self.boxes if b[0] == self.selected), None)
            if found is not None:
                painter = QPainter(self)
                painter.setPen(QPen(QColor('#1976D2'), 1, Qt.DashLine))
                painter.drawRect(self._rect(found[1]).adjusted(-2, -2, 2, 2))
                extra = found[2]
                if isinstance(extra, dict) and 'tip' in extra:   # an arrow: its two ends
                    painter.setPen(QPen(QColor('#1976D2'), 1))
                    painter.setBrush(QColor('white'))
                    for x, y in (extra['tip'], extra['tail']):
                        painter.drawRect(QRectF(x / self.ratio - 3.5, y / self.ratio - 3.5, 7, 7))
        arrow = self.dragged_arrow()
        if arrow is not None:                      # the arrow follows the mouse at once
            tip, tail, box = arrow
            painter = painter or QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor('#1976D2'), 1.5))
            painter.drawLine(tail, tip)
            painter.setBrush(QColor('white'))
            painter.setPen(QPen(QColor('#1976D2'), 1))
            for end in (tip, tail):
                painter.drawRect(QRectF(end.x() - 3.5, end.y() - 3.5, 7, 7))
            if box is not None:
                painter.setPen(QPen(Qt.darkBlue, 1, Qt.DashLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(box.adjusted(-2, -2, 2, 2))
        if self._drag is not None and not self._drag[1].isNull():
            painter = painter or QPainter(self)
            painter.setPen(QPen(Qt.darkBlue, 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._drag[1].translated(self._shift))
        if painter is not None:
            painter.end()


class ColourButton(QPushButton):
    """A button showing a colour; a click opens the colour window."""
    changed = pyqtSignal(str)

    def __init__(self, colour='#000000'):
        super().__init__()
        self.setFixedSize(46, 22)
        self.setAutoDefault(False)
        self._colour = colour
        self._paint()
        self.clicked.connect(self._choose)

    def colour(self):
        return self._colour

    def set_colour(self, colour, quiet=True):
        self._colour = colour or '#000000'
        self._paint()
        if not quiet:
            self.changed.emit(self._colour)

    def _paint(self):
        self.setStyleSheet(f"QPushButton {{ background-color: {self._colour}; "
                           "border: 1px solid #888; border-radius: 3px; }")

    def _choose(self):
        # the window's parent is not this button: its colour (style sheet) would
        # colour every button of the colour window too
        dlg = QColorDialog(QColor(self._colour), self.window())
        dlg.setWindowTitle("Colour")
        dlg.setOption(QColorDialog.DontUseNativeDialog)
        self._keep = _BrightFromBlack(dlg)
        if dlg.exec_() == QDialog.Accepted:
            self.set_colour(dlg.currentColor().name(), quiet=False)


class _BrightFromBlack(QObject):
    """In the colour window, a click in the colour field picks only the hue
    and saturation - from black (no brightness) the colour stays black. Then
    the colour clicked is taken in full brightness."""

    def __init__(self, dialog):
        super().__init__(dialog)
        self.dialog = dialog
        for w in dialog.findChildren(QWidget):
            if w.metaObject().className() == 'QColorPicker':
                w.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseMove) and \
                self.dialog.currentColor().value() == 0:
            r = obj.contentsRect()
            x = min(max(event.pos().x() - r.x(), 0), r.width() - 1)
            y = min(max(event.pos().y() - r.y(), 0), r.height() - 1)
            hue = int(360 - x * 360 / max(1, r.width() - 1)) % 360
            sat = int(255 - y * 255 / max(1, r.height() - 1))
            self.dialog.setCurrentColor(QColor.fromHsv(hue, max(0, min(255, sat)), 255))
            return True
        return False


class PublicationDialog(QDialog):
    def __init__(self, figure, parent=None, preferences=None, folder='', notes=None,
                 title=None, tab=None):
        """title: the window's title (e.g. "... - 2D map"); tab: the tab to
        show first (e.g. "Printing" for Print...)."""
        super().__init__(parent)
        self.setWindowTitle(title or "Save plot for publication")
        self.notes = notes              # PlotNotesController: your labels on the plot
        if notes is not None:
            notes.select(None)          # no frame of a chosen label in the picture
        # can be maximized, not minimized (a hidden window that waits for an answer
        # would only confuse)
        self.setWindowFlags((self.windowFlags() | Qt.WindowMaximizeButtonHint)
                            & ~Qt.WindowMinimizeButtonHint)
        self.figure = figure
        self.preferences = preferences
        self.folder = folder
        self.saved_path = None
        self.legend_xy = {}             # {axes number: (x, y)}: legends moved by the mouse
        self.moved = {}                 # {key: (dx, dy) points}: titles / labels dragged
        self.series_rows = []           # the table's changes, one dict per spectrum
        self._render_dpi = 96.0         # of the preview picture (for dragging)
        self._history, self._at = [], -1    # undo / redo: the states of the window
        self._restoring = False
        self._fields = {}               # key -> (get, set)
        self._quiet = False
        self._info = pst.current(figure)
        self._series = pst.series(figure)
        from src.views import icons
        self._icons = icons

        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addLayout(self._profile_row())
        self.tabs = QTabWidget()
        info = self._info
        # like Origin's plot details: one tab for each part; a tab only when the
        # plot has that part (no Heatmap tab without a heatmap ...)
        self.tab_pages = {}
        for name, build, shown in (
                ("Page", self._size_tab, True),
                ("Text", self._text_tab, True),
                ("Axes", self._axes_tab, True),
                ("Lines", self._lines_tab, info['has_lines']),
                ("Legend", self._legend_tab, info['has_legend']),
                ("Labels", self._labels_tab,
                 info['has_bands'] or info['has_cursors'] or info['has_notes']
                 or bool(info.get('marks')) or notes is not None),
                ("Heatmap", self._heatmap_tab, info['has_colours']),
                ("Printing", self._print_tab, True)):
            page = build()
            self.tab_pages[name] = page
            if shown:
                self.tabs.addTab(page, name)
        if tab in self.tab_pages and self.tabs.indexOf(self.tab_pages[tab]) >= 0:
            self.tabs.setCurrentWidget(self.tab_pages[tab])
        left.addWidget(self.tabs, 1)
        self.pixels_label = QLabel()
        self.pixels_label.setStyleSheet("color: #555;")
        left.addWidget(self.pixels_label)
        left.addLayout(self._buttons())
        holder = QWidget()
        holder.setLayout(left)
        holder.setMinimumWidth(420)
        side = QWidget()
        side.setLayout(self._preview_side())
        side.setMinimumWidth(300)
        # a splitter between the settings and the preview: drag it to give
        # either side more room (its place is kept for the next time)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(holder)
        self.splitter.addWidget(side)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(7)
        self.splitter.setToolTip("Drag to give the settings or the preview more room.")
        layout.addWidget(self.splitter)
        try:                            # not stored for good any more (also not the bar)
            if self.preferences is not None and self.preferences.get(PREF_KEY) is not None:
                self.preferences.remove(PREF_KEY)
        except Exception:
            pass
        self._panel_width = max(420, int(_SESSION_PANEL.get('width', 660)))        # set again when the window is shown
        self.splitter.setSizes([self._panel_width, 700])
        self.splitter.splitterMoved.connect(lambda *_: self._splitter_moved())

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._update_preview)
        self._history_timer = QTimer(self)        # Undo: a change kept once it has settled
        self._history_timer.setSingleShot(True)
        self._history_timer.setInterval(500)
        self._history_timer.timeout.connect(self._record)
        self._show(self._stored())
        self._changed()
        self._history_timer.stop()
        self._record()

    # ------------------------------------------------------------------ fields
    def _bind(self, key, widget, kind='value'):
        """Keep `widget` as the setting `key` (kinds: value (spin box), data
        (combo box), check, text, number (empty = None), colour)."""
        if kind == 'value':
            get, set_ = widget.value, lambda v: widget.setValue(float(v or 0))
            widget.valueChanged.connect(lambda *_: self._changed())
        elif kind == 'int':
            get, set_ = widget.value, lambda v: widget.setValue(int(v or 0))
            widget.valueChanged.connect(lambda *_: self._changed())
        elif kind == 'data':
            def set_(v, w=widget):
                k = w.findData(v)
                w.setCurrentIndex(k if k >= 0 else 0)
            get = widget.currentData
            widget.currentIndexChanged.connect(lambda *_: self._changed())
        elif kind == 'check':
            get, set_ = widget.isChecked, lambda v: widget.setChecked(bool(v))
            widget.toggled.connect(lambda *_: self._changed())
        elif kind == 'text':
            get, set_ = (lambda w=widget: w.text().strip()), lambda v: widget.setText(v or '')
            widget.textChanged.connect(lambda *_: self._changed())
        elif kind == 'number':
            widget.setValidator(QDoubleValidator())

            def get(w=widget):
                try:
                    return float(w.text().replace(',', '.')) if w.text().strip() else None
                except ValueError:
                    return None
            set_ = (lambda v, w=widget: w.setText('' if v is None else f"{float(v):g}"))
            widget.textChanged.connect(lambda *_: self._changed())
        elif kind == 'colour':
            get, set_ = widget.colour, widget.set_colour
            widget.changed.connect(lambda *_: self._changed())
        self._fields[key] = (get, set_)
        return widget

    def _combo(self, items, key=None):
        w = QComboBox()
        for data, text in items:
            w.addItem(text, data)
        if key:
            self._bind(key, w, 'data')
        return w

    def _spin(self, lo, hi, step, decimals, suffix='', key=None, special=None):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setDecimals(decimals)
        w.setSingleStep(step)
        w.setSuffix(suffix)
        if special:
            w.setSpecialValueText(special)             # shown at the lowest value
        if key:
            self._bind(key, w, 'value')
        return w

    def _ask(self, title, html):
        """An orange "?" that explains `title` in a small window."""
        b = self._icons.help_button(title)
        b.clicked.connect(lambda: QMessageBox.information(self, title, html))
        return b

    @staticmethod
    def _row(*widgets, stretch=True):
        box = QHBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        for w in widgets:
            if isinstance(w, QLabel):
                w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)   # no gaps
            box.addWidget(w)
        if stretch:
            box.addStretch(1)
        return box

    @staticmethod
    def _page(form):
        w = QWidget()
        w.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidget(w)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        return scroll

    # ------------------------------------------------------------------ profiles
    def _profile_row(self):
        row = QHBoxLayout()
        row.addWidget(QLabel("Profile:"))
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(150)
        self.profile_combo.setToolTip(
            "Profile: your settings saved under a name (e.g. \"Journal X, 1 column\").\n"
            "Choose one to use it again.")
        row.addWidget(self.profile_combo, 1)
        self.save_profile_button = QPushButton("Save as…")
        self.save_profile_button.setAutoDefault(False)
        self.save_profile_button.setToolTip(
            "Save as: all settings of this window under a name, to use them again\n"
            "for a similar plot.")
        self.save_profile_button.clicked.connect(lambda: self.save_profile())
        row.addWidget(self.save_profile_button)
        self.delete_profile_button = QPushButton("Delete")
        self.delete_profile_button.setAutoDefault(False)
        self.delete_profile_button.setToolTip("Delete: the profile chosen in the list.")
        self.delete_profile_button.clicked.connect(lambda: self.delete_profile())
        row.addWidget(self.delete_profile_button)
        row.addWidget(self._ask("Profiles", (
            "<b>Profiles</b> keep all settings of this window under a name - e.g. "
            "<i>Journal X, 1 column</i> or <i>Thesis, A4</i>.<br><br>"
            "<b>Save as…</b>: type a name; the settings as they are now are saved "
            "(the same name again: replaced).<br>"
            "<b>Choose a profile</b> in the list: its settings are used at once - also "
            "for another plot.<br><b>Delete</b>: removes the chosen profile.<br><br>"
            "A profile also keeps the axis titles, ranges and the spectra's own colours "
            "(1st, 2nd, ... spectrum), so it suits similar data. Without a profile, "
            "the window keeps only the general look for the next time (size, text, "
            "font, ticks, colours ...), not what belongs to one plot.<br>"
            "<b>Restore defaults</b> puts everything back as at first.")))
        self._fill_profiles()
        self.profile_combo.activated.connect(lambda *_: self._profile_chosen())
        return row

    def profiles(self):
        try:
            stored = self.preferences.get(PROFILES_KEY) if self.preferences is not None else {}
        except Exception:
            stored = {}
        return dict(stored) if isinstance(stored, dict) else {}

    def _fill_profiles(self, current=None):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem("(none)", None)
        for name in sorted(self.profiles(), key=str.lower):
            self.profile_combo.addItem(name, name)
        k = self.profile_combo.findData(current) if current else 0
        self.profile_combo.setCurrentIndex(max(k, 0))
        self.profile_combo.blockSignals(False)
        self.delete_profile_button.setEnabled(self.profile_combo.currentData() is not None)

    def save_profile(self, name=None):
        if name is None:
            name, ok = QInputDialog.getText(self, "Save profile", "Name of the profile:",
                                            text=self.profile_combo.currentData() or '')
            if not ok:
                return None
        name = (name or '').strip()
        if not name or self.preferences is None:
            return None
        profiles = self.profiles()
        profiles[name] = self.settings()
        try:
            self.preferences.set(PROFILES_KEY, profiles)
        except Exception:
            return None
        self._fill_profiles(name)
        return name

    def delete_profile(self, name=None):
        name = name or self.profile_combo.currentData()
        profiles = self.profiles()
        if not name or name not in profiles or self.preferences is None:
            return False
        del profiles[name]
        try:
            self.preferences.set(PROFILES_KEY, profiles)
        except Exception:
            return False
        self._fill_profiles()
        return True

    def apply_profile(self, name):
        s = self.profiles().get(name)
        if not isinstance(s, dict):
            return False
        self.legend_xy = {}
        self._show(dict(all_defaults(), **s))
        self._fill_profiles(name)
        self._changed()
        return True

    def _profile_chosen(self):
        name = self.profile_combo.currentData()
        self.delete_profile_button.setEnabled(name is not None)
        if name:
            self.apply_profile(name)

    # ------------------------------------------------------------------ tabs
    def _size_tab(self):
        form = QFormLayout()
        self.column_combo = QComboBox()
        for name, width, height in pf.SIZES:
            self.column_combo.addItem(pf.size_text(name, width, height), (width, height))
        self.column_combo.addItem("own size", None)
        self.column_combo.setToolTip("Size: of the picture - see the orange ? for the choices.")
        self.column_combo.currentIndexChanged.connect(lambda *_: self._column_chosen())
        form.addRow("Size:", self._row(self.column_combo, self._ask("Size", (
            "<b>1 column (8.5 cm), 1.5 columns (11.4 cm), 2 columns (17.5 cm)</b>: the usual "
            "widths of a picture in a journal - across one column, one and a half, or the "
            "whole width of the page. Only the width changes; the height stays.<br><br>"
            "<b>Portrait</b>: the page standing upright (taller than wide); "
            "<b>landscape</b>: lying on its side (wider than tall) - as in Word and the "
            "printer's window.<br>"
            "<b>A4 landscape, full page</b> (at first): 26.7 cm wide × 18 cm high - all of a "
            "landscape A4 sheet inside 1.5 cm margins (29.7 - 3 = 26.7, 21 - 3 = 18).<br>"
            "<b>A4 portrait, full page</b>: 18 cm wide × 26.7 cm high - all of a portrait "
            "A4 sheet.<br>"
            "<b>A4 portrait, half page</b>: 18 cm wide × 13.5 cm high - the width of a "
            "portrait A4 sheet, half its height (a plot in a report or a thesis, with text "
            "above or below it).<br>"
            "<b>A5 / Letter landscape, full page</b>: all of that sheet, likewise.<br>"
            "<b>Slide 16:9 / 4:3, full slide</b>: a whole PowerPoint slide.<br>"
            "This is the size of the <i>picture</i>; the paper it is printed on is chosen in "
            "the Printing tab (A4 at first).<br>"
            "<b>own size</b>: shown when Width or Height are typed.<br><br>"
            "For a page or a slide a larger Text size (e.g. 12-16 pt) reads better.")),
            stretch=False))
        self.width_spin = self._spin(1.0, 50.0, 0.5, 1, " cm", 'width_cm')
        self.width_spin.setToolTip("Width: the width of the picture in the paper.")
        self.width_spin.valueChanged.connect(lambda *_: self._match_column())
        form.addRow("Width:", self.width_spin)
        self.height_spin = self._spin(1.0, 50.0, 0.5, 1, " cm", 'height_cm')
        self.height_spin.setToolTip("Height: the height of the picture in the paper.")
        self.height_spin.valueChanged.connect(lambda *_: self._match_column())
        form.addRow("Height:", self.height_spin)
        self.dpi_combo = self._combo([(d, f"{d} dpi") for d in pf.DPI_CHOICES], 'dpi')
        self.dpi_combo.setToolTip(
            "Resolution of a TIFF or PNG picture (dots per inch):\n"
            "300 dpi: photographs, colour pictures\n"
            "600 dpi: line art, plots (most journals)\n"
            "1200 dpi: very fine lines\n"
            "PDF, SVG and EPS are sharp at any size (no dots).")
        form.addRow("Resolution:", self.dpi_combo)
        return self._page(form)

    def _text_tab(self):
        form = QFormLayout()
        fonts = [('', AS_IN_PLOT)] + [(f, f) for f in pst.installed_fonts()]
        self.family_combo = self._combo(fonts, 'font_family')
        self.family_combo.setToolTip(
            "Font: of all text. Journals often ask for Arial or Helvetica\n"
            "(Times New Roman in some). Only fonts on this computer are listed.")
        form.addRow("Font:", self.family_combo)
        self.font_spin = self._spin(4.0, 36.0, 0.5, 1, " pt", 'font_pt')
        self.font_spin.setToolTip(
            "Text size: of all text - unless a size below is set\n"
            "(titles 1 pt larger, the legend 1 pt smaller). Journals usually ask for 6-9 pt.")
        form.addRow("Text size:", self._row(self.font_spin, self._ask("Text sizes", (
            "<b>Text size</b> sets every text at once: the axis titles, the numbers and the "
            "labels get it, the plot title 1 pt more, the legend 1 pt less.<br>"
            "Each kind of text can have its own size instead (below): <b>Axis titles</b>, "
            "<b>Numbers</b> on the axes, <b>Legend</b>, <b>Plot title</b>; the labels in the "
            "Labels tab (band markers' labels; your own labels: "
            "each its own size). <i>automatic</i> = from Text size.<br>Journals usually want 6-9 pt in the printed size; for a slide "
            "14-20 pt.")), stretch=False))
        form.addRow(QLabel("<b>Own sizes</b> (automatic: from Text size)"))
        self.size_spins = {}
        for key, name, tip in (
                ('axis_title_pt', "Axis titles", "the titles of the axes, e.g. Raman shift"),
                ('tick_pt', "Numbers", "the numbers on the axes (and of a colour bar)"),
                ('legend_pt', "Legend", "the names in the legend"),
                ('title_pt', "Plot title", "the title above the plot")):
            w = self._spin(0, 36, 0.5, 1, " pt", key, "automatic")
            w.setToolTip(f"{name}: the size of {tip}.\nAutomatic: from Text size.")
            self.size_spins[key] = w
            form.addRow(f"{name}:", w)
        form.addRow(QLabel("<b>Plot title</b>"))
        plot_title = self._info['title']
        shown = (plot_title[:25] + "…") if len(plot_title) > 26 else plot_title
        self.title_combo = self._combo([(KEEP, f"as in the plot ({shown or 'none'})"),
                                        ('hide', "no title"), ('own', "own:")], 'title_mode')
        self.title_combo.setToolTip(
            "Plot title: above the plot. As in the plot: the main plot's own title\n"
            "(e.g. Waterfall plot - 28 spectra; an Overlay has none).\n"
            "Journals usually want none -\n"
            "the caption is in the text. Own: type it on the right\n"
            "(with several plots, one title above all of them).\n"
            "Drag it in the preview to move it.")
        self.title_edit = self._bind('title_text', RichTextButton(title="Plot title"), 'text')
        self.title_edit.setPlaceholderText(self._info['title'] or "title")
        form.addRow("Title:", self._row(self.title_combo, self.title_edit, stretch=False))
        self.short_check = self._bind('short_names', QCheckBox("Short names"), 'check')
        self.short_check.setToolTip(
            "Short names: the spectra's names (legend, titles, a heatmap's rows)\n"
            "only with the part that tells them apart: \"raman_2comp_clean : raman_12\"\n"
            "-> \"raman_12\" (as \"shorten names\" in the main window).")
        form.addRow("", self.short_check)
        return self._page(form)

    def _ask_row(self, title, html):
        """A row with only an orange "?" (explaining the rows above)."""
        return self._row(QLabel(""), self._ask(title, html))

    def _axes_tab(self):
        form = QFormLayout()
        info = self._info
        self.x_title_edit = self._bind('x_title', RichTextButton(title="X title"), 'text')
        self.x_title_edit.setPlaceholderText(info['x_title'] or AS_IN_PLOT)
        self.x_title_edit.setToolTip(
            "X title: the title of the x axis, e.g. Raman shift (cm⁻¹).\n"
            "Empty: as in the plot (shown in grey).")
        form.addRow("X title:", self.x_title_edit)
        self.y_title_edit = self._bind('y_title', RichTextButton(title="Y title"), 'text')
        self.y_title_edit.setPlaceholderText(info['y_title'] or AS_IN_PLOT)
        self.y_title_edit.setToolTip("Y title: the title of the y axis. Empty: as in the plot.")
        form.addRow("Y title:", self.y_title_edit)
        for axis in ('x', 'y'):
            w = self._combo([(KEEP, AS_IN_PLOT), ('on', "shown"), ('off', "hidden")],
                            f'{axis}_numbers')
            w.setToolTip(f"{axis.upper()} numbers: the numbers of the {axis} axis shown or hidden\n"
                         "(e.g. hidden on a y axis in arbitrary units).")
            setattr(self, f'{axis}_numbers_combo', w)
            form.addRow(f"{axis.upper()} numbers:", w)
        for axis, rng in (('x', info['x_range']), ('y', info['y_range'])):
            lo = self._bind(f'{axis}_min', QLineEdit(), 'number')
            hi = self._bind(f'{axis}_max', QLineEdit(), 'number')
            for w, v in ((lo, rng[0] if rng else None), (hi, rng[1] if rng else None)):
                w.setPlaceholderText(f"{v:.4g}" if v is not None else "auto")
                w.setMaximumWidth(90)
            lo.setToolTip(f"{axis.upper()} from / to: the range shown. Empty: as in the plot "
                          "(its range in grey).")
            hi.setToolTip(lo.toolTip())
            setattr(self, f'{axis}_min_edit', lo)
            setattr(self, f'{axis}_max_edit', hi)
            form.addRow(f"{axis.upper()} from:", self._row(lo, QLabel("to"), hi))
        self.x_dir_combo = self._combo([(KEEP, AS_IN_PLOT), ('increasing', "increasing →"),
                                        ('decreasing', "decreasing ←")], 'x_dir')
        self.x_dir_combo.setToolTip(
            "X direction: increasing to the right, or decreasing\n"
            "(e.g. IR spectra: 4000 on the left, 400 on the right).")
        form.addRow("X direction:", self.x_dir_combo)
        self.x_step_spin = self._spin(0, 1e6, 1, 3, key='x_step', special="automatic")
        self.y_step_spin = self._spin(0, 1e9, 0.1, 4, key='y_step', special="automatic")
        for w in (self.x_step_spin, self.y_step_spin):
            w.setToolTip("Tick step: the distance of two numbers on the axis, e.g. 200\n"
                         "-> 400, 600, 800 ... 0: automatic.")
        form.addRow("X tick step:", self.x_step_spin)
        form.addRow("Y tick step:", self.y_step_spin)
        self.minor_combo = self._combo([(KEEP, AS_IN_PLOT), ('on', "on"), ('off', "off")],
                                       'minor_ticks')
        self.minor_combo.setToolTip("Minor ticks: short ticks between the numbered ones.")
        form.addRow("Minor ticks:", self.minor_combo)
        self.tick_dir_combo = self._combo([(KEEP, AS_IN_PLOT), ('out', "outside"),
                                           ('in', "inside"), ('inout', "across")], 'tick_dir')
        self.tick_dir_combo.setToolTip("Ticks: pointing out of the frame, into it, or across it.")
        self.tick_len_spin = self._spin(0, 20, 0.5, 1, " pt", 'tick_len', AS_IN_PLOT)
        self.tick_len_spin.setToolTip("Tick length: of the numbered ticks (the minor ones 60 %).")
        form.addRow("Ticks:", self._row(self.tick_dir_combo, QLabel("length"),
                                        self.tick_len_spin))
        self.mirror_combo = self._combo([(KEEP, AS_IN_PLOT), ('on', "on all four sides"),
                                         ('off', "left and bottom only")], 'mirror_ticks')
        self.mirror_combo.setToolTip("Ticks also on the top and right side of the frame.")
        form.addRow("Tick sides:", self.mirror_combo)
        self.frame_combo = self._combo([(KEEP, AS_IN_PLOT), ('box', "box (all four sides)"),
                                        ('open', "open (left and bottom)")], 'frame')
        self.frame_combo.setToolTip("Frame: the lines around the plot.")
        self.frame_spin = self._spin(0, 5, 0.25, 2, " pt", 'frame_pt', AS_IN_PLOT)
        self.frame_spin.setToolTip("Frame width: of the frame and the ticks.")
        form.addRow("Frame:", self._row(self.frame_combo, QLabel("width"), self.frame_spin, self._ask(
            "Frame and ticks", (
                "<b>Frame</b>: <i>box</i> - lines on all four sides; <i>open</i> - only the "
                "left and bottom axis (common in many journals).<br>"
                "<b>Frame width</b>: the thickness of these lines and of the ticks.<br>"
                "<b>Ticks</b>: <i>outside</i> / <i>inside</i> the frame or <i>across</i> it, "
                "and their length.<br><b>Tick sides</b>: ticks also on the top and right "
                "side (with a box).<br><b>Tick step</b>: e.g. 200 gives 400, 600, 800 ...; "
                "0 = automatic.<br><b>Minor ticks</b>: short ticks between the numbered "
                "ones.")), stretch=False))
        self._grid_rows(form)
        return self._page(form)

    def _lines_tab(self):
        page = QWidget()
        box = QVBoxLayout(page)
        form = QFormLayout()
        self.plot_as_combo = self._combo([(KEEP, AS_IN_PLOT), ('lines', "lines"),
                                          ('points', "points"), ('both', "lines and points")],
                                         'plot_as')
        self.plot_as_combo.setToolTip(
            "Plot as: the spectra as lines, as points (markers only) or both.")
        self.marker_combo = self._combo(list(pst.MARKERS), 'marker')
        self.marker_combo.setToolTip("Marker: the shape of the points.")
        form.addRow("Plot as:", self._row(self.plot_as_combo, self.marker_combo))
        self.marker_size_spin = self._spin(0.5, 20, 0.5, 1, " pt", 'marker_size')
        self.marker_size_spin.setToolTip("Marker size: of the points.")
        self.marker_every_spin = QSpinBox()
        self.marker_every_spin.setRange(1, 1000)
        self.marker_every_spin.setPrefix("every ")
        self.marker_every_spin.setSuffix(". point")
        self.marker_every_spin.setSpecialValueText("on every point")
        self.marker_every_spin.setToolTip(
            "Markers on every n-th measured point only - a spectrum has hundreds of\n"
            "points, so a marker on each makes a thick line (e.g. every 20th).")
        self._bind('marker_every', self.marker_every_spin, 'int')
        form.addRow("Markers:", self._row(self.marker_size_spin, self.marker_every_spin))
        self.line_spin = self._spin(0.1, 5.0, 0.25, 2, " pt", 'line_pt')
        self.line_spin.setToolTip(
            "Lines at least: thinner lines are drawn this thick (thicker ones stay).\n"
            "Journals usually ask for at least 0.5-1 pt.")
        form.addRow("Lines at least:", self.line_spin)
        self.palette_combo = self._combo([(KEEP, AS_IN_PLOT)] + list(pst.PALETTES), 'palette')
        self.palette_combo.setToolTip("Colours: a colour set for all spectra (see the ?).")
        self.palette_combo.currentIndexChanged.connect(lambda *_: self._refresh_colours())
        form.addRow("Colours:", self._row(self.palette_combo, self._ask("Colours", (
            "<b>Colours</b> for all spectra at once (the table below can still change "
            "each one):<br>"
            "<b>colour-blind safe (Okabe-Ito)</b>: 8 colours told apart also by people "
            "with colour blindness - a good choice for most papers.<br>"
            "<b>matplotlib's 10 colours</b>: the usual colours of the main window.<br>"
            "<b>all black</b> / <b>black, different line styles</b>: for a black-and-white "
            "print (solid, dashed, dotted, dash-dot in turn).<br>"
            "<b>shades of grey</b>: from black to light grey.<br>"
            "<b>viridis, cividis, plasma, cool-warm</b>: colours changing step by step - "
            "for a series (e.g. concentrations or temperatures in order).")),
            stretch=False))
        box.addLayout(form)
        self.series_table = QTableWidget(0, 7)
        self.series_table.setHorizontalHeaderLabels(
            ["Show", "Spectrum", "Name in legend", "Colour", "Line", "Width", "Marker"])
        self.series_table.verticalHeader().setVisible(False)
        header = self.series_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)     # widths stay; drag to change
        header.setStretchLastSection(False)
        for col, width in ((0, 44), (1, 90), (2, 130), (3, 54), (4, 112), (5, 72), (6, 100)):
            self.series_table.setColumnWidth(col, width)
        self.series_table.setToolTip(
            "Each spectrum: Show (untick: left out), Name in legend (empty: as it is),\n"
            "Colour (click), Line style, Width (0: as set above), Marker.")
        title = QLabel("Each spectrum:")
        reset = QPushButton("All as set above")
        reset.setAutoDefault(False)
        reset.setToolTip("All as set above: the table's own changes undone.")
        reset.clicked.connect(lambda: self._reset_series())
        box.addLayout(self._row(title, reset))
        box.addWidget(self.series_table, 1)
        self._build_series_table()
        return page

    def _grid_rows(self, form):
        self.grid_combo = self._combo([(KEEP, AS_IN_PLOT), ('off', "no grid"),
                                       ('major', "at the numbers"),
                                       ('both', "at the numbers and between")], 'grid')
        self.grid_combo.setToolTip("Grid: lines across the plot at the numbers of the axes\n"
                                   "(and between them, thinner).")
        form.addRow("Grid:", self.grid_combo)
        self.grid_axis_combo = self._combo([('both', "both axes"), ('x', "x only (vertical lines)"),
                                            ('y', "y only (horizontal lines)")], 'grid_axis')
        self.grid_axis_combo.setToolTip("Which axes have grid lines.")
        form.addRow("Grid for:", self.grid_axis_combo)
        self.grid_colour = self._bind('grid_color', ColourButton('#b0b0b0'), 'colour')
        self.grid_colour.setToolTip("Colour of the grid lines.")
        self.grid_style_combo = self._combo(list(pst.LINE_STYLES), 'grid_style')
        self.grid_style_combo.setToolTip("Line style of the grid lines.")
        self.grid_width_spin = self._spin(0.1, 3, 0.1, 2, " pt", 'grid_pt')
        self.grid_width_spin.setToolTip("Width of the grid lines.")
        form.addRow("Grid lines:", self._row(self.grid_colour, self.grid_style_combo,
                                             self.grid_width_spin))

    def _labels_tab(self):
        form = QFormLayout()
        info = self._info
        if info['has_bands']:
            form.addRow(QLabel("<b>Band markers</b>"))
            self.band_labels_combo = self._combo([(KEEP, "shown"), ('off', "hidden")],
                                                 'band_labels')
            self.band_labels_combo.setToolTip("Band markers' labels: shown or left out.")
            form.addRow("Labels:", self.band_labels_combo)
            self.band_rotation_combo = self._combo([(KEEP, AS_IN_PLOT),
                                                    ('horizontal', "horizontal"),
                                                    ('vertical', "vertical (upwards)")],
                                                   'band_rotation')
            self.band_rotation_combo.setToolTip("Band markers' labels: horizontal or vertical.")
            form.addRow("Label direction:", self.band_rotation_combo)
            self.band_lines_combo = self._combo([(KEEP, "shown"), ('off', "hidden")],
                                                'band_lines')
            self.band_lines_combo.setToolTip(
                "Band markers' lines: shown or left out (e.g. only the label above a band).")
            form.addRow("Lines:", self.band_lines_combo)
            self.band_size_spin = self._spin(0, 36, 0.5, 1, " pt", 'band_pt', "automatic")
            self.band_size_spin.setToolTip("Size of the band markers' labels (automatic: Text "
                                           "size).")
            form.addRow("Label size:", self.band_size_spin)
        if info['has_cursors']:
            form.addRow(QLabel("<b>Pinned cursors</b>"))
            self.cursors_combo = self._combo([(KEEP, "shown"), ('off', "left out")], 'cursors')
            self.cursors_combo.setToolTip("Pinned cursors (dotted lines with their x value):\n"
                                          "in the picture or left out.")
            form.addRow("Pinned cursors:", self.cursors_combo)
            self.cursor_size_spin = self._spin(0, 36, 0.5, 1, " pt", 'cursor_pt', "automatic")
            self.cursor_size_spin.setToolTip("Size of the pinned cursors' values (automatic: "
                                             "Text size).")
            form.addRow("Value size:", self.cursor_size_spin)
        self.mark_combos = {}
        if info.get('marks'):
            # the marks of a tool window's plot (2D Map: the clicked pixel,
            # the regions, the reference pixels; a spectrum's shaded range)
            form.addRow(QLabel("<b>Marks on the plot</b>"))
            for gid in info['marks']:
                key, name = pst.MARKS[gid]
                combo = self._combo([(KEEP, "shown"), ('off', "left out")], key)
                combo.setToolTip(f"{name}: in the picture or left out.")
                self.mark_combos[key] = combo
                form.addRow(name + ":", combo)
        if self.notes is not None:
            form.addRow(QLabel("<b>Your labels</b> (also on the main plot)"))
            from src.views.dialogs.visualization.plot_notes_dialog import NotesTable
            self.notes_table = NotesTable(self.notes)
            self.notes_table.setMinimumHeight(150)
            self.notes_table.changed.connect(self._notes_changed)
            form.addRow(self.notes_table)
            add_text = QPushButton("Add text")
            add_text.setAutoDefault(False)
            add_text.setToolTip("Add text: a new text in the middle of the plot - drag it to its "
                                "place.")
            add_text.clicked.connect(lambda: self.add_note('text'))
            add_arrow = QPushButton("Add an arrow")
            add_arrow.setAutoDefault(False)
            add_arrow.setToolTip("Add an arrow: a new arrow in the middle of the plot - drag its "
                                 "text (tail) to turn it.\nIts tip and the whole arrow: drag "
                                 "them on the main plot.")
            add_arrow.clicked.connect(lambda: self.add_note('arrow'))
            form.addRow(self._row(add_text, add_arrow))
        hint = QLabel("In the preview: drag a label, the plot title or the legend to move it; "
                      "click one of your labels to choose it (Delete key: delete it), "
                      "double-click it to change it.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555;")
        form.addRow(hint)
        form.addRow(self._row(QLabel(""), self._ask("Labels", (
            "<b>Band markers</b> (main window › Band markers…, right-click › Add a band "
            "marker here, or a click on the plot with the Cursor ticked): their labels shown "
            "or hidden, horizontal or vertical, and their lines shown or hidden - e.g. only "
            "the number above a band, as in many papers.<br>"
            "<b>Marks on the plot</b> (a tool window's plot, e.g. 2D Map): the + of the "
            "clicked pixel, the outlines of the regions (ROI), the numbered reference "
            "pixels, a spectrum's shaded range - each kept in the picture or left out "
            "(only the kinds the plot has are shown).<br>"
            "<b>Your labels</b> (main window: right-click on the plot › Label the band here, "
            "Add text here, Add an arrow here; or <i>Add text</i> / <i>Add an arrow</i> here): "
            "the same labels as on the main plot - a change here changes them there too. "
            "Their text, size, colour, rotation and bold in the table; in the preview click "
            "one to choose it (the Delete key deletes it), double-click to change it, drag "
            "it to move it (an arrow: its text or tail - the arrow turns).<br>"
            "<b>Drag</b> a band marker's label, the plot title or "
            "the legend in the preview to move it - only in the picture.<br>"
            "<b>Undo</b> (Ctrl+Z) takes back any of these changes.<br>"
            "Sizes: band markers' labels here (automatic: Text "
            "size); your own labels: each its own size in the table."))))
        return self._page(form)

    def _legend_tab(self):
        form = QFormLayout()
        self.legend_combo = QComboBox()
        for key, text in pf.LEGENDS:
            self.legend_combo.addItem(text, key)
        self.legend_combo.setToolTip(
            "Legend: where it goes (its text 1 pt smaller than Text size).\n"
            "You can also drag the legend in the preview with the mouse.")
        self.place_combo = QComboBox()
        for key, text in pf.PLACES:
            self.place_combo.addItem(text, key)
        self.place_combo.setToolTip(
            "Inside the plot: over the plot's frame (the plot keeps its size).\n"
            "Outside the plot: beside, above or below it, not over the axes' numbers\n"
            "or titles; the picture keeps its size, so the plot in it gets smaller.")
        self._bind('legend', self.legend_combo, 'data')
        self._bind('legend_place', self.place_combo, 'data')
        self.legend_combo.currentIndexChanged.connect(lambda *_: self._legend_chosen())
        self.place_combo.currentIndexChanged.connect(lambda *_: self._legend_chosen())
        form.addRow("Place:", self._row(self.legend_combo, self.place_combo, self._ask(
            "Legend place", (
                "<b>Best place</b>: inside the plot where it covers the fewest lines.<br>"
                "<b>Top right … Bottom</b>: that side or corner of the plot, and then:<br>"
                "&nbsp;- <i>inside the plot</i>: over the plot area; the plot keeps its "
                "size, the legend may cover some lines;<br>"
                "&nbsp;- <i>outside the plot</i>: beside, above or below it, not over the "
                "numbers or titles of the axes. The picture keeps its size, so the plot in "
                "it gets narrower (left/right) or lower (top/bottom).<br>"
                "Outside, the corners (e.g. Top right) are beside the plot, at its top.<br>"
                "<b>Drag</b> the legend in the preview to put it anywhere; choosing a place "
                "here puts it there again.")), stretch=False))
        self.ncol_spin = QSpinBox()
        self.ncol_spin.setRange(0, 10)
        self.ncol_spin.setSpecialValueText("automatic")
        self.ncol_spin.setToolTip("Columns: of the legend (0: automatic).")
        self._bind('legend_ncol', self.ncol_spin, 'int')
        form.addRow("Columns:", self.ncol_spin)
        self.legend_frame_combo = self._combo([(KEEP, AS_IN_PLOT), ('on', "with a frame"),
                                               ('off', "without a frame")], 'legend_frame')
        form.addRow("Frame:", self.legend_frame_combo)
        self.legend_title_edit = self._bind('legend_title', RichTextButton(title="Legend title"),
                                            'text')
        self.legend_title_edit.setPlaceholderText("none")
        self.legend_title_edit.setToolTip("Title: a line above the legend's names, e.g. Samples.")
        form.addRow("Title:", self.legend_title_edit)
        hint = QLabel("The names: Lines tab › Name in legend; short names: Size & text tab.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555;")
        form.addRow("", hint)
        return self._page(form)

    def _heatmap_tab(self):
        form = QFormLayout()
        if not self._info['has_colours']:
            note = QLabel("This plot has no colour map (Heatmap, 2D map …).")
            note.setStyleSheet("color: #555;")
            form.addRow(note)
        self.cmap_combo = self._combo([(KEEP, AS_IN_PLOT)] + [(c, c) for c in pst.CMAPS], 'cmap')
        self.cmap_combo.setToolTip(
            "Colour map: the colours of a heatmap. viridis / cividis are read well\n"
            "also in grey and by colour-blind people; Greys / gray for black-and-white;\n"
            "RdBu_r / coolwarm for values around zero (e.g. differences).")
        form.addRow("Colour map:", self.cmap_combo)
        lo = self._bind('c_min', QLineEdit(), 'number')
        hi = self._bind('c_max', QLineEdit(), 'number')
        for w in (lo, hi):
            w.setPlaceholderText("auto")
            w.setMaximumWidth(90)
        self.c_min_edit, self.c_max_edit = lo, hi
        form.addRow("Values from:", self._row(lo, QLabel("to"), hi, self._ask(
            "Colour range", (
                "<b>Values from … to</b>: the values of the first and the last colour.<br>"
                "Lower values get the first colour, higher ones the last.<br>"
                "Empty: as in the plot (from the lowest to the highest value).<br>"
                "Use the same range for several pictures to compare them.")), stretch=False))
        self.cbar_edit = self._bind('cbar_label', RichTextButton(title="Colour bar title"),
                                    'text')
        self.cbar_edit.setPlaceholderText(AS_IN_PLOT)
        self.cbar_edit.setToolTip("Colour bar title: e.g. Intensity (counts).")
        form.addRow("Colour bar title:", self.cbar_edit)
        return self._page(form)

    def _print_tab(self):
        form = QFormLayout()
        self.fit_combo = self._combo([(True, "Fit to page"),
                                      (False, "Actual size (Width × Height)")], 'print_fit')
        self.fit_combo.setToolTip("On paper: how large the picture is printed (see the ?).")
        form.addRow("On paper:", self._row(self.fit_combo, self._ask("Printing", (
            "<b>On paper</b>: <i>Fit to page</i> - as large as the paper lets it (the text "
            "grows with it), so the print preview looks much the same for every Size; "
            "<i>Actual size</i> - its size in cm (Page tab), as it will be in the journal, "
            "e.g. 8.5 cm wide on A4.<br><b>Paper</b>: A4 at first; A5, A3, Letter.<br>"
            "<b>Page</b>: <i>automatic</i> - landscape for a picture wider than tall "
            "with Fit to page; or always <i>portrait</i> / <i>landscape</i>. The printer's "
            "window can still change it (Orientation).<br><b>Position</b>: centre of the page or top left.<br>"
            "<b>Grey</b>: in shades of grey - to see whether the lines can still be told "
            "apart in a black-and-white copy.<br><b>Caption</b>: a line of text under the "
            "picture (not in the saved file).<br><br><b>Print preview…</b> shows the page "
            "first (paper, portrait / landscape, then Print); <b>Print…</b> goes straight to "
            "the printer window (also Microsoft Print to PDF).")), stretch=False))
        self.paper_combo = self._combo(list(pf.PAPERS), 'paper')
        self.paper_combo.setToolTip("Paper: the paper the picture is printed on (A4 at first).\n"
                                    "The printer window can still change it.")
        form.addRow("Paper:", self.paper_combo)
        self.orientation_combo = self._combo([('auto', "automatic"),
                                              ('portrait', "portrait (upright)"),
                                              ('landscape', "landscape (on its side)")],
                                             'print_orientation')
        self.orientation_combo.setToolTip("Page: portrait or landscape (automatic: landscape for\n"
                                          "a wide picture with Fit to page).")
        form.addRow("Page:", self.orientation_combo)
        self.centre_combo = self._combo([(True, "Centre of the page"), (False, "Top left")],
                                        'print_centre')
        self.centre_combo.setToolTip("Position: where on the page the picture is printed.")
        form.addRow("Position:", self.centre_combo)
        self.grey_check = self._bind('print_grey', QCheckBox("Grey (black and white)"), 'check')
        self.grey_check.setToolTip(
            "Grey: printed in shades of grey - to see whether the lines can be\n"
            "told apart in a black-and-white copy of the paper. The preview shows\n"
            "it in grey too; a saved file stays in colour.")
        form.addRow("", self.grey_check)
        self.caption_edit = QLineEdit()
        self.caption_edit.setPlaceholderText("(none)")
        self.caption_edit.setToolTip(
            "Caption: a line of text printed under the picture\n"
            "(e.g. the sample and the date). Not in the saved file.")
        form.addRow("Caption:", self.caption_edit)
        return self._page(form)

    def _buttons(self):
        icons = self._icons
        self.save_button = QPushButton("Save…")
        self.save_button.setIcon(icons.standard('SP_DialogSaveButton', self))
        self.save_button.setToolTip(
            "Save: choose the file and its kind (TIFF, PNG, PDF, SVG, EPS).")
        self.save_button.setAutoDefault(False)            # Enter in a number box: not Save
        self.save_button.clicked.connect(lambda: self.save())
        self.preview_button = QPushButton("Print preview…")
        self.preview_button.setIcon(icons.standard('SP_FileDialogContentsView', self))
        self.preview_button.setAutoDefault(False)
        self.preview_button.setToolTip(
            "Print preview: the printed page, before printing - there the paper\n"
            "(A4, Letter ...), portrait or landscape, and then Print.")
        self.preview_button.clicked.connect(lambda: self.print_preview())
        self.print_button = QPushButton("Print…")
        self.print_button.setIcon(icons.standard('SP_FileDialogDetailedView', self))
        self.print_button.setAutoDefault(False)
        self.print_button.setToolTip(
            "Print: choose the printer (or Microsoft Print to PDF) and print\n"
            "as set in the Printing tab.")
        self.print_button.clicked.connect(lambda: self.print_figure())
        self.defaults_button = QPushButton("Restore defaults")
        self.defaults_button.setAutoDefault(False)
        self.defaults_button.setToolTip(
            "Restore defaults: all choices back as they were at first\n"
            "(A4 landscape, full page: 26.7 cm wide × 18 cm high, 12 pt, 600 dpi,\n"
            "everything else as in the plot;\n"
            "your labels: 8 pt, black, not turned, not bold - their texts and places stay).\n"
            "Undo takes it back.")
        self.defaults_button.clicked.connect(lambda: self.restore_defaults())
        close = QPushButton("Close")
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        help_button = icons.help_button("Saving a plot for a publication")
        help_button.clicked.connect(self._help)
        box = QVBoxLayout()
        box.addLayout(self._row(self.save_button, self.preview_button, self.print_button,
                                stretch=False))
        self.undo_button = QPushButton("\u21b6 Undo")
        self.undo_button.setAutoDefault(False)
        self.undo_button.setToolTip("Undo (Ctrl+Z): the last change in this window\n"
                                    "(also dragging the legend or a label).")
        self.undo_button.clicked.connect(lambda: self.undo())
        self.redo_button = QPushButton("\u21b7 Redo")
        self.redo_button.setAutoDefault(False)
        self.redo_button.setToolTip("Redo (Ctrl+Y): the change undone again.")
        self.redo_button.clicked.connect(lambda: self.redo())
        from PyQt5.QtGui import QKeySequence
        from PyQt5.QtWidgets import QShortcut
        for keys, slot in ((QKeySequence.Undo, self.undo), (QKeySequence.Redo, self.redo),
                           (QKeySequence("Ctrl+Y"), self.redo)):
            QShortcut(keys, self, activated=slot)
        row2 = QHBoxLayout()
        row2.addWidget(self.undo_button)
        row2.addWidget(self.redo_button)
        row2.addWidget(self.defaults_button)
        row2.addStretch(1)
        row2.addWidget(close)
        row2.addWidget(help_button)
        box.addLayout(row2)
        return box

    def _preview_side(self):
        right = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(QLabel("Preview:"))
        self.zoom_combo = self._combo([(True, "Fit the window"), (False, "Real size (roughly)")],
                                      'preview_fit')
        self.zoom_combo.setToolTip(
            "Preview: Fit the window - the whole picture as large as the window lets it\n"
            "(the text grows with it, as on paper; larger when the window is maximized).\n"
            "Real size: about as large as on paper.")
        top.addWidget(self.zoom_combo)
        hint = QLabel("Drag the legend, title or labels.")
        hint.setStyleSheet("color: #555;")
        top.addWidget(hint)
        top.addStretch(1)
        right.addLayout(top)
        self.preview = PreviewLabel()
        self.preview.legend_moved.connect(self._legend_moved)
        self.preview.text_moved.connect(self._text_moved)
        self.preview.clicked.connect(self._text_clicked)
        self.preview.double_clicked.connect(self._text_double_clicked)
        self.preview.delete_pressed.connect(self._delete_chosen)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.preview)
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumSize(480, 380)
        right.addWidget(self.scroll, 1)
        return right

    # ------------------------------------------------------------------ the spectra table
    def _build_series_table(self):
        t = self.series_table
        t.setRowCount(len(self._series))
        self._row_widgets = []
        for i, sp in enumerate(self._series):
            show = QCheckBox()
            show.setChecked(True)
            holder = QWidget()
            hb = QHBoxLayout(holder)
            hb.setContentsMargins(6, 0, 0, 0)
            hb.addWidget(show)
            t.setCellWidget(i, 0, holder)
            name_item = QTableWidgetItem(sp['label'].rsplit(' : ', 1)[-1])
            name_item.setToolTip(sp['label'])
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            t.setItem(i, 1, name_item)
            legend = RichTextButton(title="Name in the legend")
            legend.setPlaceholderText("as it is")
            t.setCellWidget(i, 2, legend)
            colour = ColourButton(sp['color'])
            t.setCellWidget(i, 3, colour)
            style = QComboBox()
            style.addItem("as set", None)
            for k, text in pst.LINE_STYLES:
                style.addItem(text, k)
            t.setCellWidget(i, 4, style)
            width = QDoubleSpinBox()
            width.setRange(0, 10)
            width.setSingleStep(0.25)
            width.setDecimals(2)
            width.setSpecialValueText("as set")
            t.setCellWidget(i, 5, width)
            marker = QComboBox()
            marker.addItem("as set", None)
            marker.addItem("none", '')
            for k, text in pst.MARKERS:
                marker.addItem(text, k)
            t.setCellWidget(i, 6, marker)
            t.setRowHeight(i, 28)
            ws = {'show': show, 'name': legend, 'color': colour, 'style': style,
                  'width': width, 'marker': marker}
            self._row_widgets.append(ws)
            show.toggled.connect(lambda v, i=i: self._row_changed(i, 'show', v))
            legend.textChanged.connect(lambda v, i=i: self._row_changed(i, 'name', v.strip()))
            colour.changed.connect(lambda v, i=i: self._row_changed(i, 'color', v))
            style.currentIndexChanged.connect(
                lambda _k, i=i, w=style: self._row_changed(i, 'style', w.currentData()))
            width.valueChanged.connect(lambda v, i=i: self._row_changed(i, 'width', v))
            marker.currentIndexChanged.connect(
                lambda _k, i=i, w=marker: self._row_changed(i, 'marker', w.currentData()))

    def _row_changed(self, i, key, value):
        if self._quiet:
            return
        while len(self.series_rows) <= i:
            self.series_rows.append({})
        row = self.series_rows[i]
        if key == 'show':
            empty = value is True                  # shown: as in the plot
        elif key == 'marker':
            empty = value is None                  # '' = no marker, a real choice
        elif key == 'width':
            empty = not value
        else:
            empty = value in (None, '')
        if empty:
            row.pop(key, None)
        else:
            row[key] = value
        self._changed()

    def _reset_series(self):
        self.series_rows = []
        self._show_series()
        self._changed()

    def _show_series(self):
        """The table as series_rows says (and the colours as set above)."""
        self._quiet = True
        try:
            colours = self._base_colours()
            for i, ws in enumerate(self._row_widgets):
                row = self.series_rows[i] if i < len(self.series_rows) else {}
                ws['show'].setChecked(row.get('show', True) is not False)
                ws['name'].setText(row.get('name', ''))
                ws['color'].set_colour(row.get('color') or colours[i])
                k = ws['style'].findData(row.get('style'))
                ws['style'].setCurrentIndex(k if k >= 0 else 0)
                ws['width'].setValue(float(row.get('width') or 0))
                k = ws['marker'].findData(row['marker']) if 'marker' in row else 0
                ws['marker'].setCurrentIndex(k if k >= 0 else 0)
        finally:
            self._quiet = False

    def _base_colours(self):
        palette = self.palette_combo.currentData()
        if palette and palette != KEEP:
            return pst.palette_colors(palette, len(self._series))
        return [sp['color'] for sp in self._series]

    def _refresh_colours(self):
        """A new colour set: the table shows it (own colours stay)."""
        if self._quiet:
            return
        colours = self._base_colours()
        for i, ws in enumerate(getattr(self, '_row_widgets', [])):
            row = self.series_rows[i] if i < len(self.series_rows) else {}
            if not row.get('color'):
                ws['color'].set_colour(colours[i])

    # ------------------------------------------------------------------ settings
    def _stored(self):
        s = all_defaults()
        s.update({k: v for k, v in _SESSION.items() if k not in DATA_KEYS})
        s['legend'], s['legend_place'] = pf.legend_choice(s.get('legend'), s.get('legend_place'))
        return s

    def _show(self, s):
        """Put the choices `s` into the window (without saving them again)."""
        self._quiet = True
        try:
            for key, (get, set_) in self._fields.items():
                if key in s:
                    try:
                        set_(s[key])
                    except (TypeError, ValueError):
                        pass
            self.series_rows = [dict(r) for r in (s.get('series') or []) if isinstance(r, dict)]
            self._place_enabled()
            self._match_column()
        finally:
            self._quiet = False
        self._show_series()

    def settings(self):
        s = {key: get() for key, (get, _set) in self._fields.items()}
        s['dpi'] = int(s['dpi'])
        s['print_fit'] = bool(s['print_fit'])
        s['print_centre'] = bool(s['print_centre'])
        s['preview_fit'] = bool(s['preview_fit'])
        s['series'] = [dict(r) for r in self.series_rows]
        return s

    def _choices(self):
        """The choices for publication_figure (with the moved legends)."""
        s = self.settings()
        return {'font_pt': s['font_pt'], 'line_pt': s['line_pt'], 'legend': s['legend'],
                'legend_place': s['legend_place'], 'short_names': s['short_names'],
                'legend_xy': dict(self.legend_xy), 'moved': dict(self.moved),
                'style': {k: s[k] for k in pst.STYLE_DEFAULTS if k in s}}

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, '_panel_width', None):
            # the settings' width as left last time (in pixels; the preview gets the rest)
            total = sum(self.splitter.sizes())
            if total > self._panel_width + 300:
                self.splitter.setSizes([self._panel_width, total - self._panel_width])
            self._panel_width = None

    def _splitter_moved(self):
        self._keep_panel_width()
        if self.zoom_combo.currentData():
            self._timer.start()                    # the preview fills its new room

    def _keep_panel_width(self):
        """The bar's place is kept while the program runs (as the other
        choices); each start begins with the bar at its first place."""
        _SESSION_PANEL['width'] = int(self.splitter.sizes()[0])

    def _remember(self):
        """The general look is kept for the next opening while the program
        runs; what belongs to this plot only in a profile. For good: only the
        place of the bar between the settings and the preview."""
        if self._quiet:
            return
        try:
            s = self.settings()
        except Exception:
            return
        _SESSION.clear()
        _SESSION.update({k: v for k, v in s.items() if k not in DATA_KEYS})

    def restore_defaults(self):
        """Everything of this window back as at first: all choices (all tabs),
        the table of spectra, dragged legends / titles / labels, the caption,
        the chosen profile - and the look of your labels (size, colour,
        rotation, bold; their texts and places stay). Undo takes it back."""
        self.legend_xy = {}
        self.moved = {}
        self.preview.selected = None
        self.caption_edit.clear()
        if self.notes is not None:
            from src.modules.visualization.plot_notes import DEFAULT
            for i in range(len(self.notes.notes)):
                self.notes.notes.update(i, **{k: DEFAULT[k] for k in
                                              ('fontsize', 'color', 'rotation', 'bold')})
            self.notes.redraw()
            if getattr(self, 'notes_table', None) is not None:
                self.notes_table.refresh()
        self._show(all_defaults())
        self._fill_profiles()
        self._changed()

    def _render(self, dpi):
        s = self.settings()
        return pf.render(self.figure, s['width_cm'], s['height_cm'], dpi, **self._choices())

    def _picture(self, dpi):
        return self._render(dpi)[0]

    def _column_chosen(self):
        size = self.column_combo.currentData()
        if size is None or self._quiet:
            return
        width, height = size
        for spin, value in ((self.width_spin, width), (self.height_spin, height)):
            if value is not None:
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        self._changed()

    def _match_column(self):
        w, h = self.width_spin.value(), self.height_spin.value()
        last = self.column_combo.count() - 1
        k = last
        for i in range(last):
            width, height = self.column_combo.itemData(i)
            if abs(width - w) < 1e-6 and (height is None or abs(height - h) < 1e-6):
                k = i
                if height is not None:
                    break                       # a page / slide fits better than a column
        self.column_combo.blockSignals(True)
        self.column_combo.setCurrentIndex(k)
        self.column_combo.blockSignals(False)

    def _place_enabled(self):
        self.place_combo.setEnabled(self.legend_combo.currentData() not in ('best', 'none'))

    def _legend_chosen(self):
        self._place_enabled()
        if not self._quiet:
            self.legend_xy = {}                 # a chosen place: the moved legend goes there

    def _legend_moved(self, i, dx, dy):
        for k, box, frame in self.preview.boxes:
            if k == i:
                self.legend_xy[i] = pf.moved_legend(box, frame, dx, dy)
                self._update_preview()
                self._history_timer.start()
                return

    def _text_moved(self, key, dx, dy):
        """A title or label dragged by (dx, dy) pixels of the preview (y down):
        kept in points, so the same in the saved picture at any size. Your own
        labels move on the main plot too (they are the same labels)."""
        k = 72.0 / (self._render_dpi or 96.0)
        key, _, part = key.partition('|')          # an arrow's end: 'tip', 'tail', 'shaft'
        i = self._note_index(key)
        if i is not None:
            self._move_note(i, key, dx, dy, part or None)
        else:
            x, y = self.moved.get(key, (0.0, 0.0))
            self.moved[key] = (x + dx * k, y - dy * k)
        self._update_preview()
        self._history_timer.start()

    def _move_note(self, i, key, dx, dy, part=None):
        """Your label i dragged in the preview by (dx, dy) pixels (y down):
        its new place in the plot's units - so it is there on the main plot
        too, at any size of either. An arrow: part 'tip' (only the tip moves),
        'tail' or its text (it turns and stretches), 'shaft' (all of it)."""
        box = next((b for b in self.preview.boxes if b[0] == key), None)
        if box is None or not box[2]:
            return
        x0, y0, x1, y1 = box[1]
        n = self.notes.notes.notes[i]
        extra = box[2]
        if n['kind'] == 'arrow' and 'tip' in extra and part != 'shaft' and \
                (part in ('tip', 'tail') or n['text']):
            if part == 'tip':
                x, y = pf.pixel_to_data(extra, extra['tip'][0] + dx, extra['tip'][1] + dy)
                self.notes.notes.update(i, x=x, y=y)
            else:                                      # the tail (or its text)
                tx, ty = pf.pixel_to_data(extra, extra['tail'][0] + dx, extra['tail'][1] + dy)
                self.notes.notes.update(i, tx=tx, ty=ty)
            self.notes.redraw()
            return
        if n['kind'] == 'arrow':                       # the middle: all of it moves
            a = pf.pixel_to_data(box[2], x0, y0)
            b = pf.pixel_to_data(box[2], x0 + dx, y0 + dy)
            ddx, ddy = b[0] - a[0], b[1] - a[1]
            values = {'x': n['x'] + ddx, 'y': n['y'] + ddy}
            if n['tx'] is not None:
                values.update(tx=n['tx'] + ddx, ty=n['ty'] + ddy)
        else:
            cx = (x0 + x1) / 2 + dx
            cy = (y1 if n['kind'] == 'band' else (y0 + y1) / 2) + dy   # where the text sits
            tx, ty = pf.pixel_to_data(box[2], cx, cy)
            values = {'x': tx, 'y': ty} if n['kind'] == 'text' else {'tx': tx, 'ty': ty}
        self.notes.notes.update(i, **values)
        self.notes.redraw()

    def _note_index(self, key):
        """The number of your label for a preview key 'note:<axes>:<n>'."""
        if self.notes is None or not isinstance(key, str) or not key.startswith('note:'):
            return None
        i = int(key.split(':')[2])
        return i if 0 <= i < len(self.notes.notes) else None

    def _text_clicked(self, key):
        """A click on one of your labels in the preview: chosen (Delete
        deletes it); elsewhere: none chosen."""
        self.preview.selected = key if self._note_index(key) is not None else None
        self.preview.update()

    def _text_double_clicked(self, key):
        i = self._note_index(key)
        if i is not None:
            self.preview.selected = None
            self.notes.edit(i, parent=self)
            self._notes_changed()

    def _delete_chosen(self):
        i = self._note_index(self.preview.selected)
        self.preview.selected = None
        if i is not None:
            self.notes.notes.remove(i)
            self.notes.redraw()
            self._notes_changed()

    def add_note(self, kind):
        """A new text or arrow in the middle of the plot (drag it to its place)."""
        if self.notes is None:
            return None
        i = self.notes.add_in_middle(kind, "text" if kind == 'text' else "")
        if i is None and getattr(self.notes, 'scaled', lambda: False)():
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Labels",
                "Labels cannot be added while \u201cscale each\u201d is on (Basic plot "
                "options): they are placed in the spectra's own units.\n\n"
                "Untick \u201cscale each\u201d to add and see your labels.")
            return None
        self.notes.select(None)
        self._notes_changed()
        return i

    def _notes_changed(self):
        """Your labels changed (table, dragging, deleting): the table and the
        preview follow; kept for Undo."""
        if getattr(self, 'notes_table', None) is not None:
            self.notes_table.refresh()
        self._update_preview()
        self._history_timer.start()

    # ------------------------------------------------------------------ undo / redo
    def _state(self):
        notes = self.notes.to_dict() if self.notes is not None else None
        return (self.settings(), dict(self.legend_xy), dict(self.moved), notes)

    def _record(self):
        """Keep the window's state for Undo (after a change has settled)."""
        if self._restoring:
            return
        state = self._state()
        if self._history and self._at >= 0 and self._history[self._at] == state:
            return
        del self._history[self._at + 1:]
        self._history.append(state)
        self._history = self._history[-200:]
        self._at = len(self._history) - 1
        self._undo_buttons()

    def _undo_buttons(self):
        if hasattr(self, 'undo_button'):
            self.undo_button.setEnabled(self._at > 0)
            self.redo_button.setEnabled(self._at < len(self._history) - 1)

    def _go_to(self, at):
        self._history_timer.stop()
        self._at = at
        settings, legend_xy, moved, notes = self._history[at]
        self._restoring = True
        try:
            self._show(settings)
            self.legend_xy, self.moved = dict(legend_xy), dict(moved)
            if self.notes is not None and notes is not None \
                    and notes != self.notes.to_dict():
                self.notes.from_dict(notes)
                if getattr(self, 'notes_table', None) is not None:
                    self.notes_table.refresh()
            self._changed()
            self._update_preview()
        finally:
            self._restoring = False
        self._undo_buttons()

    def undo(self):
        self._record()                        # a change not yet kept: kept first
        if self._at > 0:
            self._go_to(self._at - 1)
            return True
        return False

    def redo(self):
        if self._at < len(self._history) - 1:
            self._go_to(self._at + 1)
            return True
        return False

    def _changed(self):
        if self._quiet:
            return
        s = self.settings()
        w, h = pf.pixels(s['width_cm'], s['height_cm'], s['dpi'])
        self.pixels_label.setText(f"TIFF / PNG: {w} × {h} pixels at {s['dpi']} dpi")
        self._remember()
        self._timer.start()
        if hasattr(self, '_history_timer') and not self._restoring:
            self._history_timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.zoom_combo.currentData():
            self._timer.start()

    def _real_dpi(self):
        """The window's pixels in one real inch of the screen, for Real size:
        from the screen's physical size (its dots per inch divided by the
        display scaling, e.g. 150 %) - Windows' "logical" 96 dpi is the same
        on every screen, so on a fine laptop screen the picture was about
        half as large as on paper. A screen that reports no sensible size
        (some projectors, TVs): the logical value."""
        logical = float(self.logicalDpiX() or 96)
        try:
            screen = self.screen() if hasattr(self, 'screen') else None
            if screen is None:
                from PyQt5.QtWidgets import QApplication
                screen = QApplication.primaryScreen()
            physical = float(screen.physicalDotsPerInchX())
            ratio = float(self.devicePixelRatioF() or 1.0)
        except Exception:
            return logical
        real = physical / ratio
        return real if 40.0 <= real <= 400.0 else logical

    def _preview_dpi(self):
        s = self.settings()
        real = self._real_dpi()
        if not s['preview_fit']:
            return real
        view = self.scroll.viewport().size()
        w_in, h_in = s['width_cm'] / 2.54, s['height_cm'] / 2.54
        return max(20.0, min((view.width() - 4) / w_in, (view.height() - 4) / h_in))

    def _update_preview(self):
        ratio = self.devicePixelRatioF() if hasattr(self, 'devicePixelRatioF') else 1.0
        try:
            self._render_dpi = self._preview_dpi() * ratio
            data, boxes = self._render(self._render_dpi)
        except Exception:
            self.preview.boxes = []
            self.preview.setText("(no preview)")
            return
        pix = QPixmap()
        pix.loadFromData(data, 'PNG')
        if self.grey_check.isChecked():               # as it will be printed
            from PyQt5.QtGui import QImage
            pix = QPixmap.fromImage(pix.toImage().convertToFormat(QImage.Format_Grayscale8))
        pix.setDevicePixelRatio(ratio)
        self.preview.ratio = ratio
        self.preview.boxes = boxes
        self.preview.setPixmap(pix)

    def save(self, path=None):
        """Ask for the file (or `path`) and save; returns the path or None."""
        s = self.settings()
        if path is None:
            filters = ";;".join(f"{name} (*.{ext})" for name, ext in pf.FORMATS)
            start = os.path.join(self.folder or '', 'figure.tif')
            path, chosen = QFileDialog.getSaveFileName(self, "Save plot for publication",
                                                       start, filters)
            if not path:
                return None
            ext = next((e for n, e in pf.FORMATS if chosen.startswith(n)), 'tif')
            if '.' not in os.path.basename(path):
                path += '.' + ext
        try:
            pf.save_for_publication(self.figure, path, s['width_cm'], s['height_cm'], s['dpi'],
                                    **self._choices())
        except Exception as exc:
            QMessageBox.warning(self, "Save plot for publication",
                                f"The picture could not be saved:\n{exc}")
            return None
        self._remember()
        self.saved_path = path
        return path

    # ------------------------------------------------------------------ printing
    def _new_printer(self):
        from PyQt5.QtGui import QPageLayout
        from PyQt5.QtPrintSupport import QPrinter
        from src.modules.utils.app_logger import crash_watch_paused
        s = self.settings()
        with crash_watch_paused():                # asking Windows about printers
            printer = QPrinter(QPrinter.HighResolution)
            from PyQt5.QtGui import QPageSize
            paper = {'A4': QPageSize.A4, 'A5': QPageSize.A5, 'A3': QPageSize.A3,
                     'Letter': QPageSize.Letter}.get(s.get('paper') or 'A4', QPageSize.A4)
            printer.setPageSize(QPageSize(paper))     # A4 unless another is chosen
            if s['print_orientation'] in ('portrait', 'landscape'):
                wide = s['print_orientation'] == 'landscape'
            elif s['print_fit']:
                wide = s['width_cm'] > s['height_cm']
            else:
                wide = s['width_cm'] > 19.0
            printer.setPageOrientation(QPageLayout.Landscape if wide else QPageLayout.Portrait)
        return printer

    def paint_page(self, printer):
        """Draw the picture (and the caption) on the printer's page."""
        from PyQt5.QtGui import QFont, QImage
        from PyQt5.QtPrintSupport import QPrinter
        from src.modules.utils.app_logger import crash_watch_paused
        s = self.settings()
        res = printer.resolution() or 600
        page = printer.pageRect(QPrinter.DevicePixel)
        caption = self.caption_edit.text().strip()
        caption_h = res * 0.4 if caption else 0.0
        pic_w, pic_h = s['width_cm'] / 2.54 * res, s['height_cm'] / 2.54 * res
        x, y, w, h = pf.print_place(page.width(), page.height(), pic_w, pic_h,
                                    s['print_fit'], s['print_centre'], caption_h)
        scale = w / pic_w
        dpi = min(600.0, float(res)) * scale             # sharp, not too many pixels
        dpi = min(dpi, 9000 / max(s['width_cm'], s['height_cm']) * 2.54)
        image = QImage.fromData(self._picture(max(72.0, dpi)), 'PNG')
        if s['print_grey']:
            image = image.convertToFormat(QImage.Format_Grayscale8)
        painter = QPainter()
        with crash_watch_paused():
            if not painter.begin(printer):
                QMessageBox.warning(self, "Print", "The printer could not be started.")
                return False
            try:
                painter.drawImage(QRectF(x, y, w, h), image)
                if caption:
                    font = QFont(self.font())
                    font.setPointSizeF(12)
                    painter.setFont(font)
                    painter.drawText(QRectF(x, y + h + res * 0.08, max(w, res * 3), caption_h),
                                     Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, caption)
            finally:
                painter.end()
        return True

    def print_figure(self, printer=None):
        """Print as set in Printing; without `printer` the printer is asked
        for first."""
        from PyQt5.QtPrintSupport import QPrintDialog
        from src.modules.utils.app_logger import crash_watch_paused
        if printer is None:
            printer = self._new_printer()
            with crash_watch_paused():
                if QPrintDialog(printer, self).exec_() != QDialog.Accepted:
                    return False
        ok = self.paint_page(printer)
        self._remember()
        return ok

    def print_preview(self, run=True):
        """The print preview (paper, portrait / landscape, Print). Returns the
        preview window."""
        from PyQt5.QtPrintSupport import QPrintPreviewDialog
        from src.modules.utils.app_logger import crash_watch_paused
        # the printer must live as long as the preview (Qt does not keep it:
        # a temporary one was deleted by Python at once - a crash)
        self._preview_printer = self._new_printer()
        with crash_watch_paused():
            dlg = QPrintPreviewDialog(self._preview_printer, self)
        dlg.setWindowTitle("Print preview")
        dlg.setWindowFlags((dlg.windowFlags() | Qt.WindowMaximizeButtonHint)
                           & ~Qt.WindowMinimizeButtonHint)
        dlg.paintRequested.connect(self.paint_page)
        dlg.resize(900, 700)
        if run:
            with crash_watch_paused():
                dlg.exec_()
        return dlg

    def _help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'user_guide', 'publication')
