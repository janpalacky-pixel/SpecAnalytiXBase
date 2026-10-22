# src/views/dialogs/data_analysis/peak_list_dialog.py
"""Right-click on the plot -> Peak list... (also in the Peak Detection
Settings): every peak of the selected spectra in one table - position,
height, prominence, width at half height - with the settings of Detect Peaks,
to copy into Excel or export; the tab "Plot" draws one number of the peaks
against another (e.g. the position against the spectrum, to follow a band
through a series). Reset to defaults and the orange "?" (what each setting
means). src/modules/data_analysis/peak_list.py."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
                             QDoubleSpinBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                             QMessageBox, QPushButton, QShortcut, QTableWidget, QTableWidgetItem,
                             QTabWidget, QVBoxLayout, QWidget)

from src.modules.data_analysis import peak_list as pl
from src.views import icons
from src.views.dialogs.data_analysis.peak_settings_help import tooltip_of

_LINE_STYLES = ('-', '--', ':', '-.')


def _style(k, n):
    """Colour and line style of the k-th of n groups: 10 (or 20) different
    colours, then the same colours dashed, dotted, ..."""
    import matplotlib
    if n <= 10:
        return matplotlib.colormaps['tab10'](k % 10), '-'
    return matplotlib.colormaps['tab20'](k % 20), _LINE_STYLES[(k // 20) % len(_LINE_STYLES)]


class PeakListDialog(QDialog):

    def __init__(self, parent, spectra, threshold=0.5, prominence=0.1, distance=0.05,
                 mode='Positive', on_settings=None):
        super().__init__(parent)
        self.spectra = list(spectra)
        self.on_settings = on_settings
        self._tolerance_set = False
        n = len(self.spectra)
        self.setWindowTitle(f"Peak list – {n} spectr{'um' if n == 1 else 'a'}")
        self.setWindowFlags((self.windowFlags() | Qt.WindowMaximizeButtonHint)
                            & ~Qt.WindowContextHelpButtonHint)
        self.resize(900, 560)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        intro = QLabel(
            "The peaks of all selected spectra, found as Detect Peaks finds them (the settings are "
            "shared). Position and height are those of the highest (or lowest) point; FWHM is the "
            "width at half of the peak's prominence. Select rows and press Ctrl+C to paste them "
            "into Excel; the tab Plot draws them.")
        intro.setWordWrap(True)
        top.addWidget(intro, 1)
        self.help_button = icons.help_button("What each setting and column means")
        self.help_button.clicked.connect(self.show_settings_help)
        top.addWidget(self.help_button, 0, Qt.AlignTop)
        layout.addLayout(top)

        form = QHBoxLayout()
        self.threshold = self._spin(threshold, 0.0001, 1.0, "Threshold (height)")
        self.prominence = self._spin(prominence, 0.0, 1.0, "Prominence")
        self.distance = self._spin(distance, 0.0, 1.0, "Distance")
        self.mode = QComboBox()
        self.mode.addItems(["Positive", "Negative", "Both"])
        self.mode.setCurrentText(mode)
        self.mode.setToolTip(tooltip_of("Peaks (mode)"))
        for label, w in (("Threshold:", self.threshold), ("Prominence:", self.prominence),
                         ("Distance:", self.distance), ("Peaks:", self.mode)):
            form.addWidget(QLabel(label))
            form.addWidget(w)
        self.reset_button = QPushButton("Reset to defaults")
        self.reset_button.setAutoDefault(False)
        self.reset_button.setToolTip("Threshold 0.5, prominence 0.1, distance 0.05, Positive")
        self.reset_button.clicked.connect(self.reset_defaults)
        form.addWidget(self.reset_button)
        form.addStretch(1)
        layout.addLayout(form)

        self.tabs = QTabWidget()
        self.table = QTableWidget(0, len(pl.COLUMNS))
        self.table.setHorizontalHeaderLabels(pl.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table.horizontalHeader().resizeSection(0, 260)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)   # list order first
        self.table.setSortingEnabled(True)            # a click on a heading sorts by it
        self.tabs.addTab(self.table, "Table")
        self.tabs.addTab(self._build_plot_tab(), "Plot")
        self.tabs.currentChanged.connect(lambda _: self._draw_if_shown())
        layout.addWidget(self.tabs, 1)
        QShortcut(QKeySequence.Copy, self.table, activated=self.copy)
        self.summary = QLabel("")
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        self.copy_button = QPushButton("Copy")
        self.copy_button.setToolTip("Copy the selected rows (or all, when none is selected) with the "
                                    "column names, e.g. into Excel")
        self.copy_button.clicked.connect(self.copy)
        self.export_button = QPushButton("Export…")
        self.export_button.setToolTip("Save the peak list as Excel or CSV")
        self.export_button.clicked.connect(self.export)
        self.select_all_button = QPushButton("Select all")
        self.select_all_button.setToolTip("Select all rows of the table (also Ctrl+A)")
        self.select_all_button.clicked.connect(self.select_all_rows)
        self.unselect_all_button = QPushButton("Unselect all")
        self.unselect_all_button.clicked.connect(self.table.clearSelection)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        for b in (self.select_all_button, self.unselect_all_button, self.copy_button,
                  self.export_button, close):
            b.setAutoDefault(False)
        buttons.addWidget(self.select_all_button)
        buttons.addWidget(self.unselect_all_button)
        buttons.addSpacing(12)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.export_button)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        for w in (self.threshold, self.prominence, self.distance):
            w.valueChanged.connect(self.refresh)
        self.mode.currentIndexChanged.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.refresh()

    # -- the Plot tab
    def _build_plot_tab(self):
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
        from matplotlib.figure import Figure
        page = QWidget()
        v = QVBoxLayout(page)
        row = QHBoxLayout()
        self.x_combo = QComboBox()
        for text, key in pl.x_choices(self.spectra):
            self.x_combo.addItem(text, key)
        self.x_combo.setToolTip("x-axis: a value of the spectrum (its order, a value stored with "
                                "it, a number in its name) or a number of the peak")
        self.y_combo = QComboBox()
        self.y_combo.addItems(pl.Y_CHOICES)
        self.colour_combo = QComboBox()
        self.colour_combo.addItems(["Peak number", "Maximum / minimum", "One colour"])
        self.colour_combo.setToolTip("Peak number: the 1st, 2nd, ... peak of each spectrum "
                                     "(from low to high x)")
        self.tolerance_label = QLabel("same peak within \u00b1")
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setRange(0.0, 1e9)
        self.tolerance.setDecimals(3)
        self.tolerance.setKeyboardTracking(False)
        self.tolerance.setToolTip(
            "Peaks of different spectra closer than this (in x units) are the same peak and get "
            "one common position (their median). Set from the peaks' widths (half of the median "
            "FWHM); raise it when one band is split into two, lower it when two bands are merged.")
        self.join_check = QCheckBox("Join the same peak number")
        self.join_check.setToolTip(
            "Lines through the 1st peak of each spectrum, the 2nd peak of each, ... - to follow a "
            "band through a series (e.g. its position against the temperature). Each line has its "
            "own colour. With x a value of the spectrum the line goes along x; with x a number of "
            "the peak (e.g. Height) it goes from spectrum to spectrum in the order of the list. "
            "Not when x is the peak itself (its number or position): the points of one peak would "
            "lie above each other. The peak numbers count from low x, so when a peak appears or "
            "disappears in some spectra the numbers after it shift: to follow one band, sort the "
            "table by position, select its rows and tick Only the selected rows.")
        self.selected_check = QCheckBox("Only the selected rows")
        self.selected_check.setToolTip("Draw only the rows selected in the tab Table")
        self.legend_check = QCheckBox("Legend")
        self.legend_check.setChecked(True)
        self.legend_check.setToolTip("Show or hide the legend of the plot")
        row.addWidget(QLabel("x:"))
        row.addWidget(self.x_combo)
        row.addWidget(self.tolerance_label)
        row.addWidget(self.tolerance)
        for label, w in (("y:", self.y_combo), ("Colour:", self.colour_combo)):
            row.addWidget(QLabel(label))
            row.addWidget(w)
        row.addStretch(1)
        v.addLayout(row)
        row = QHBoxLayout()                       # second row: what to draw
        row.addWidget(self.join_check)
        row.addWidget(self.selected_check)
        row.addWidget(self.legend_check)
        row.addStretch(1)
        self.copy_plot_button = QPushButton("Copy plot")
        self.copy_plot_button.setAutoDefault(False)
        self.copy_plot_button.setToolTip("The plot as a picture, to paste into Word or PowerPoint")
        self.copy_plot_button.clicked.connect(self.copy_plot)
        row.addWidget(self.copy_plot_button)
        v.addLayout(row)
        self.figure = Figure(figsize=(7, 4.5), layout='constrained')
        self.canvas = FigureCanvasQTAgg(self.figure)
        v.addWidget(NavigationToolbar2QT(self.canvas, page))
        v.addWidget(self.canvas, 1)
        # the controls first, then the plot (so it is drawn with them up to date)
        self.x_combo.currentIndexChanged.connect(self._join_possible)
        self._join_possible()
        for w in (self.x_combo, self.y_combo, self.colour_combo):
            w.currentIndexChanged.connect(self._draw_if_shown)
        for w in (self.join_check, self.selected_check, self.legend_check):
            w.toggled.connect(self._draw_if_shown)
        self.tolerance.valueChanged.connect(self._draw_if_shown)
        return page

    def _x_is_the_peak(self):
        """x is the peak itself (its number or its position): the points of
        one peak lie above each other, a line through them means nothing."""
        key = self.x_combo.currentData()
        return bool(key) and (key[0] == 'band' or key == ('column', 'Peak'))

    def _join_possible(self, *_):
        """Join is offered unless x is the peak itself; the tolerance only
        for x = the peak by its position."""
        key = self.x_combo.currentData()
        self.join_check.setEnabled(bool(key) and not self._x_is_the_peak())
        band = bool(key) and key[0] == 'band'
        self.tolerance_label.setVisible(band)
        self.tolerance.setVisible(band)

    def select_all_rows(self):
        self.table.selectAll()
        self.table.setFocus()           # the selection shows in full colour

    def _draw_if_shown(self, *_):
        self._plot_stale = True
        if self.tabs.currentIndex() == 1:
            self.draw_plot()

    def _selection_changed(self):
        if self.selected_check.isChecked():
            self._draw_if_shown()

    def _plotted_rows(self):
        """Indices (into self.rows) of the rows to draw."""
        if self.selected_check.isChecked():
            picked = set()
            for i in self.table.selectionModel().selectedRows():
                item = self.table.item(i.row(), 0)
                if item is not None and item.data(Qt.UserRole) is not None:
                    picked.add(int(item.data(Qt.UserRole)))
            return sorted(picked)
        return list(range(len(self.rows)))

    def draw_plot(self):
        import numpy as np
        self._plot_stale = False
        self._join_possible()
        fig = self.figure
        fig.clear()
        ax = fig.add_subplot(111)
        keep = self._plotted_rows()
        rows = [self.rows[i] for i in keep]
        index = [self.row_spectrum[i] for i in keep]
        x_key = self.x_combo.currentData()
        x_name, y_name = self.x_combo.currentText(), self.y_combo.currentText()
        xs, ys = pl.plot_values(rows, index, self.spectra, x_key, y_name,
                                tolerance=self.tolerance.value())
        labels = None
        if x_key == ('band', 'label') and xs:
            centres = sorted(set(xs))
            labels = [pl.band_label(c, centres) for c in centres]
            where = {c: i for i, c in enumerate(centres)}
            xs = [where[x] for x in xs]
        points = [(x, y, r, i) for x, y, r, i in zip(xs, ys, rows, index) if x is not None]
        if x_key and x_key[0] == 'band':
            ax.set_xlabel("Peak position" + (" (common for the peak in all spectra)"
                                             if x_key[1] == 'position' else ""))
        else:
            ax.set_xlabel(x_name.replace('Spectrum: ', '').replace(
                ' (1st, 2nd, \u2026 in its spectrum)', ''))
        ax.set_ylabel(y_name)
        if not points:
            ax.text(0.5, 0.5, "No peaks to draw" if not rows else
                    "The spectra have no such value", ha='center', va='center',
                    transform=ax.transAxes, color='grey')
            self.canvas.draw_idle()
            return 0
        if labels is not None:
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=90 if len(labels) > 8 else 0,
                               fontsize=8 if len(labels) > 8 else None)
        colour = self.colour_combo.currentText()
        peak_numbers = sorted({r[1] for _, _, r, _ in points})
        if colour == "Peak number":
            groups, key, name = peak_numbers, (lambda r: r[1]), (lambda g: f"Peak {g}")
        elif colour == "Maximum / minimum":
            groups = [g for g in ('maximum', 'minimum') if any(r[2] == g for _, _, r, _ in points)]
            key, name = (lambda r: r[2]), str
        else:
            groups, key, name = [None], (lambda r: None), (lambda g: None)
        for k, g in enumerate(groups):
            sel = [(x, y) for x, y, r, _ in points if key(r) == g]
            col = _style(k, len(groups))[0] if g is not None else 'C0'
            gx, gy = np.array(sel).T
            ax.scatter(gx, gy, s=22, color=col, label=name(g) if g is not None else None,
                       zorder=3)
        if self.join_check.isChecked() and self.join_check.isEnabled():
            along_x = bool(x_key) and x_key[0] == 'spectrum'
            for k, g in enumerate(peak_numbers):
                sel = [(x, y, i) for x, y, r, i in points if r[1] == g]
                # along x (a value of the spectrum), else spectrum after spectrum
                sel.sort(key=(lambda p: (p[0], p[2])) if along_x else (lambda p: (p[2], p[0])))
                gx, gy = np.array([(x, y) for x, y, _ in sel]).T
                col, style = _style(k, len(peak_numbers))
                # with Colour = Peak number the points already name the peaks
                label = None if colour == "Peak number" else f"Peak {g} (line)"
                ax.plot(gx, gy, style, color=col, lw=1.2, alpha=0.8, zorder=2, label=label)
        handles, texts = ax.get_legend_handles_labels()
        if self.legend_check.isChecked() and texts:
            ax.legend(fontsize=8, loc='best', ncol=1 + (len(texts) - 1) // 16)
        ax.grid(True, alpha=0.3)
        ax.set_title(f"{len(points)} peaks", fontsize=10)
        self.canvas.draw_idle()
        return len(points)

    def copy_plot(self):
        from src.controllers.visualization.plot_clipboard import copy_figure
        if self._plot_stale:
            self.draw_plot()
        copy_figure(self.figure)
        self.summary.setText("The plot is on the clipboard – paste it into Word or PowerPoint.")

    # -- settings
    def reset_defaults(self):
        for w in (self.threshold, self.prominence, self.distance, self.mode):
            w.blockSignals(True)
        self.threshold.setValue(pl.DEFAULTS['threshold'])
        self.prominence.setValue(pl.DEFAULTS['prominence'])
        self.distance.setValue(pl.DEFAULTS['distance'])
        self.mode.setCurrentText(pl.DEFAULTS['mode'])
        for w in (self.threshold, self.prominence, self.distance, self.mode):
            w.blockSignals(False)
        self.refresh()

    def show_settings_help(self):
        from src.views.dialogs.data_analysis.peak_settings_help import PeakSettingsHelp
        self.settings_help = PeakSettingsHelp(self, columns=True)
        self.settings_help.show()
        return self.settings_help

    @staticmethod
    def _spin(value, lo, hi, name):
        box = QDoubleSpinBox()
        box.setRange(lo, hi)
        box.setDecimals(4)
        box.setSingleStep(0.01)
        box.setValue(value)
        box.setKeyboardTracking(False)
        box.setToolTip(f"{name}: {tooltip_of(name)}")
        return box

    def settings(self):
        return dict(threshold=self.threshold.value(), prominence=self.prominence.value(),
                    distance=self.distance.value(), mode=self.mode.currentText())

    def refresh(self, *_):
        s = self.settings()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.rows, self.row_spectrum = pl.peak_table_with_index(self.spectra, **s)
        finally:
            QApplication.restoreOverrideCursor()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            for c, v in enumerate(row):
                item = QTableWidgetItem()
                if isinstance(v, (int, float)):
                    item.setData(Qt.DisplayRole, float(f'{v:.6g}') if isinstance(v, float) else v)
                    item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                else:
                    item.setText(v)
                if c == 0:
                    item.setData(Qt.UserRole, r)            # the row in self.rows (also sorted)
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        if not self._tolerance_set and self.rows:      # from the first peaks found
            self._tolerance_set = True
            self.tolerance.blockSignals(True)
            self.tolerance.setValue(pl.default_tolerance(self.rows))
            self.tolerance.blockSignals(False)
        with_peaks = len({row[0] for row in self.rows})
        self.summary.setText(f"{len(self.rows)} peaks in {with_peaks} of {len(self.spectra)} spectra.")
        if self.on_settings is not None:
            self.on_settings(s)
        self._draw_if_shown()

    def _shown_rows(self, selected_only):
        rows = range(self.table.rowCount())
        if selected_only:
            picked = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
            rows = picked or rows
        out = []
        for r in rows:
            vals = []
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                d = item.data(Qt.DisplayRole) if item is not None else ''
                vals.append(d)
            out.append(vals)
        return out

    def copy(self):
        rows = self._shown_rows(selected_only=True)
        QApplication.clipboard().setText(pl.rows_as_text(rows))
        self.summary.setText(f"Copied {len(rows)} rows (with the column names).")

    def export(self):
        path, chosen = QFileDialog.getSaveFileName(
            self, "Export the peak list", "peak_list.xlsx",
            "Excel (*.xlsx);;CSV (*.csv);;Text, tab-separated (*.txt)")
        if not path:
            return None
        if '.' not in path.replace('\\', '/').split('/')[-1]:
            path += {'CSV': '.csv', 'Text': '.txt'}.get(chosen.split(' ')[0], '.xlsx')
        try:
            pl.export(self.rows, path)
        except Exception as exc:
            QMessageBox.warning(self, "Export", f"The peak list could not be saved:\n\n{exc}")
            return None
        self.summary.setText(f"Saved: {path}")
        return path
