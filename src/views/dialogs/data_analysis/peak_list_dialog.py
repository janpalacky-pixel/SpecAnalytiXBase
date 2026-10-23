# src/views/dialogs/data_analysis/peak_list_dialog.py
"""Right-click on the plot -> Peak list... (also in the Peak Detection
Settings): every peak of the selected spectra in one table - position,
height, prominence, width at half height - with the settings of Detect Peaks,
to copy into Excel or export; the tab "Plot" draws one number of the peaks
against another (e.g. the position against the spectrum, to follow a band
through a series). Reset to defaults and the orange "?" (what each setting
means). "Refine by fitting" adds fitted position, FWHM, height, area and R\u00b2
columns; the tab "Band table" turns the list round for Excel (one row per
spectrum, one column per band). src/modules/data_analysis/peak_list.py."""

import numpy as np
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
BAND_COLOUR = "Band (peak by its position)"


def _style(k, n):
    """Colour and line style of the k-th of n groups: 10 (or 20) different
    colours, then the same colours dashed, dotted, ..."""
    import matplotlib
    if n <= 10:
        return matplotlib.colormaps['tab10'](k % 10), '-'
    return matplotlib.colormaps['tab20'](k % 20), _LINE_STYLES[(k // 20) % len(_LINE_STYLES)]


class PeakListDialog(QDialog):
    """The Peak list window: the settings of Detect Peaks (shared with it via
    on_settings), the tab Table (one row per peak, see pl.COLUMNS) and the tab
    Plot. self.rows are the table rows, self.row_spectrum the spectrum of each."""

    def __init__(self, parent, spectra, threshold=0.0, prominence=0.1, distance=0.05,
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
        self.threshold = self._spin(threshold, 0.0, 1.0, "Threshold (height)")
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

        # Refine by fitting: each found peak fitted with a model band plus a
        # background (the same fit as the 2D map's peak-fit maps) - its
        # position between the measured points, width, height above the
        # background, area and fit quality, in extra columns.
        from src.modules.visualization_analysis import peak_fit_map as pfm
        fit_row = QHBoxLayout()
        self.refine_check = QCheckBox("Refine by fitting")
        self.refine_check.setToolTip(
            "Fit every found peak with a model band plus a background (least squares, the same "
            "fit as the 2D map's peak-fit maps): adds Fitted position (between the measured "
            "points), Fitted FWHM, Fitted height (above the background), Fitted area and R\u00b2. "
            "Each peak is fitted over \u00b1 1.5 FWHM around it, at most halfway to the next peak.")
        self.fit_shape = QComboBox()
        self.fit_shape.addItems(pfm.SHAPES)
        self.fit_shape.setToolTip("Gaussian: broad bands, solids. Lorentzian: narrow bands of "
                                  "liquids and gases. Pseudo-Voigt: a mix of both (fitted).")
        self.fit_baseline = QComboBox()
        self.fit_baseline.addItems(pfm.BASELINES)
        self.fit_baseline.setCurrentText('Linear')
        self.fit_baseline.setToolTip("The background under each peak: Linear (a sloping one), "
                                     "Constant, or None (baseline-corrected spectra).")
        self.fit_info = QLabel("")
        self.fit_info.setStyleSheet("color: grey;")
        fit_row.addWidget(self.refine_check)
        for label, w in (("shape:", self.fit_shape), ("background:", self.fit_baseline)):
            fit_row.addWidget(QLabel(label))
            fit_row.addWidget(w)
        fit_row.addWidget(self.fit_info, 1)
        layout.addLayout(fit_row)
        self._fit_controls_enabled()

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
        self.tabs.addTab(self._build_band_tab(), "Band table")
        self.tabs.currentChanged.connect(lambda _: self._draw_if_shown())
        layout.addWidget(self.tabs, 1)
        QShortcut(QKeySequence.Copy, self.table, activated=self.copy)
        QShortcut(QKeySequence.Copy, self.band_table_widget, activated=self.copy)
        self.summary = QLabel("")
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        self.copy_button = QPushButton("Copy")
        self.copy_button.setToolTip("Copy the selected rows (or all, when none is selected) with the "
                                    "column names, e.g. into Excel; in the tab Band table: the "
                                    "whole band table")
        self.copy_button.clicked.connect(self.copy)
        self.export_button = QPushButton("Export…")
        self.export_button.setToolTip("Save the peak list (in the tab Band table: the band table) "
                                      "as Excel or CSV")
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
        self.refine_check.toggled.connect(self._refine_toggled)
        for w in (self.fit_shape, self.fit_baseline):
            w.currentIndexChanged.connect(lambda *_: self.refine_check.isChecked() and self.refresh())
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.refresh()

    # -- the Plot tab
    def _build_plot_tab(self):
        """The tab Plot: x, y and Colour, the ± distance of a band, Join the
        same peak number / band, Only the selected rows, Legend, Copy plot."""
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
        from matplotlib.figure import Figure
        page = QWidget()
        v = QVBoxLayout(page)
        row = QHBoxLayout()
        self.x_combo = QComboBox()
        for text, key in pl.x_choices(self.spectra):
            self.x_combo.addItem(text, key)      # refilled by _refill_plot_choices
        self.x_combo.setToolTip("x-axis: a value of the spectrum (its order, a value stored with "
                                "it, a number in its name) or a number of the peak")
        self.y_combo = QComboBox()
        self.y_combo.addItems(pl.Y_CHOICES)
        for combo in (self.x_combo, self.y_combo):      # wide enough for the fitted values
            combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.colour_combo = QComboBox()
        self.colour_combo.addItems(["Peak number", "%s" % BAND_COLOUR, "Maximum / minimum",
                                    "One colour"])
        self.colour_combo.setToolTip(
            "Peak number: the 1st, 2nd, ... peak of each spectrum (from low to high x) - it "
            "shifts when a peak is missing in some spectra. Band: the peaks of all spectra at the "
            "same position (within \u00b1) get one colour, whatever their number.")
        self.tolerance_label = QLabel("same band within \u00b1")
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setRange(0.0, 1e9)
        self.tolerance.setDecimals(3)
        self.tolerance.setKeyboardTracking(False)
        self.tolerance.setToolTip(
            "Peaks of different spectra closer than this (in x units) are the same peak and get "
            "one common position (their median). Set from the peaks' widths (half of the median "
            "FWHM); raise it when one band is split into two, lower it when two bands are merged.")
        self.join_check = QCheckBox("Join the same")
        self.join_by = QComboBox()
        self.join_by.addItem("peak number", 'number')
        self.join_by.addItem("band (peak by its position)", 'band')
        self.join_by.setCurrentIndex(1)      # band: a line stays on its band (the better start)
        join_tip = (
            "Lines from spectrum to spectrum through the same peak - to follow a band through a "
            "series (e.g. its position against the temperature). Each line has its own colour. "
            "Peak number: through the 1st peak of each spectrum, the 2nd, ... - when a peak is "
            "missing in some spectra the numbers after it shift and a line jumps to the next band. "
            "Band: through the peaks at the same position (within \u00b1) - a line always stays on "
            "its band and simply ends where the band is not found. With x a value of the spectrum "
            "the line goes along x; with x a number of the peak (e.g. Height) it goes from spectrum "
            "to spectrum in the order of the list. Not when x is the peak itself (its number or "
            "position): the points of one peak would lie above each other.")
        self.join_check.setToolTip(join_tip)
        self.join_by.setToolTip(join_tip)
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
        row.addWidget(self.join_by)
        row.addSpacing(10)
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
        for w in (self.x_combo, self.colour_combo, self.join_by):
            w.currentIndexChanged.connect(self._join_possible)
        self.join_check.toggled.connect(self._join_possible)
        self._join_possible()
        for w in (self.x_combo, self.y_combo, self.colour_combo, self.join_by):
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

    def _joined_by_band(self):
        """Lines are drawn and follow the bands (not the peak numbers)."""
        return (self.join_check.isChecked() and self.join_check.isEnabled()
                and self.join_by.currentData() == 'band')

    def _join_possible(self, *_):
        """Join is offered unless x is the peak itself; the tolerance only
        when something groups the peaks by their position (x, Colour or
        Join)."""
        key = self.x_combo.currentData()
        possible = bool(key) and not self._x_is_the_peak()
        self.join_check.setEnabled(possible)
        self.join_by.setEnabled(possible)
        band = ((bool(key) and key[0] == 'band') or self.colour_combo.currentText() == BAND_COLOUR
                or self._joined_by_band())
        self.tolerance_label.setVisible(band)
        self.tolerance.setVisible(band)

    def select_all_rows(self):
        """Select all rows; the focus goes back to the table, so the selection
        is shown in its full colour (not the pale one of an unfocused table)."""
        self.table.selectAll()
        self.table.setFocus()           # the selection shows in full colour

    def _draw_if_shown(self, *_):
        self._plot_stale = True
        if self.tabs.currentIndex() == 1:
            self.draw_plot()
        elif self.tabs.currentIndex() == 2:
            self.fill_band_table()

    # -- the tab Band table
    def _build_band_tab(self):
        """One row per spectrum, one column per band (the peaks of all
        spectra at the same position), holding the chosen value - the
        peak list turned round for Excel (pl.band_table)."""
        page = QWidget()
        v = QVBoxLayout(page)
        row = QHBoxLayout()
        self.band_value_combo = QComboBox()
        self.band_value_combo.addItems(pl.y_choices(False))
        # wide enough for the fitted values added later (e.g. Fitted position)
        self.band_value_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.band_value_combo.setToolTip("What each cell holds: the position, height, prominence "
                                         "or FWHM of that spectrum's peak in that band (with "
                                         "Refine by fitting also the fitted values)")
        self.band_tolerance = QDoubleSpinBox()
        self.band_tolerance.setRange(0.0, 1e9)
        self.band_tolerance.setDecimals(3)
        self.band_tolerance.setKeyboardTracking(False)
        self.band_tolerance.setToolTip(
            "Peaks of different spectra closer than this (in x units) are one band - the same "
            "setting as \"same band within \u00b1\" in the tab Plot. Raise it when one band is "
            "split into two columns, lower it when two bands share one.")
        self.band_stored_check = QCheckBox("Stored values")
        self.band_stored_check.setChecked(True)
        self.band_stored_check.setToolTip("Also the values stored with the spectra (e.g. "
                                          "temperature_C, pH) as columns before the bands")
        for label, w in (("Value:", self.band_value_combo),
                         ("same band within \u00b1", self.band_tolerance)):
            row.addWidget(QLabel(label))
            row.addWidget(w)
        row.addWidget(self.band_stored_check)
        row.addStretch(1)
        v.addLayout(row)
        self.band_table_widget = QTableWidget(0, 1)
        self.band_table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # in the order of the spectra list until a heading is clicked
        self.band_table_widget.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        self.band_table_widget.setSortingEnabled(True)
        self.band_table_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.band_table_widget.horizontalHeader().resizeSection(0, 260)
        v.addWidget(self.band_table_widget, 1)
        self.band_info = QLabel("")
        self.band_info.setWordWrap(True)
        v.addWidget(self.band_info)
        # one tolerance for the Plot and the Band table
        self.band_tolerance.valueChanged.connect(
            lambda val: self.tolerance.value() != val and self.tolerance.setValue(val))
        self.tolerance.valueChanged.connect(
            lambda val: self.band_tolerance.value() != val and self.band_tolerance.setValue(val))
        self.band_value_combo.currentIndexChanged.connect(self._draw_if_shown)
        self.band_stored_check.toggled.connect(self._draw_if_shown)
        return page

    def fill_band_table(self):
        """Fill the tab Band table from the current peaks; returns
        (columns, rows) as shown (also used by Copy and Export)."""
        from src.modules.visualization import color_by_value as cbv
        if abs(self.band_tolerance.value() - self.tolerance.value()) > 1e-12:
            self.band_tolerance.blockSignals(True)
            self.band_tolerance.setValue(self.tolerance.value())
            self.band_tolerance.blockSignals(False)
        keys = cbv.metadata_keys(self.spectra) if self.band_stored_check.isChecked() else []
        columns, rows, merged = pl.band_table(
            self.rows, self.row_spectrum, self.spectra, self.band_value_combo.currentText(),
            self.tolerance.value(), keys)
        t = self.band_table_widget
        t.setSortingEnabled(False)
        t.clear()
        t.setColumnCount(len(columns))
        t.setHorizontalHeaderLabels(columns)
        t.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                item = QTableWidgetItem()
                if isinstance(val, (int, float)) and np.isfinite(val):
                    item.setData(Qt.DisplayRole, float(f'{val:.6g}'))
                    item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                elif isinstance(val, str):
                    item.setText(val)
                t.setItem(r, c, item)                       # empty: no peak in that band
        for c in range(1, len(columns)):
            t.resizeColumnToContents(c)
        t.setSortingEnabled(True)
        n_bands = len(columns) - 1 - len(keys)
        text = (f"{len(rows)} spectra \u00d7 {n_bands} bands, value: "
                f"{self.band_value_combo.currentText()}. Empty cell: no peak of that spectrum "
                "in that band. Copy (Ctrl+C) or Export\u2026 for Excel.")
        if merged:
            text += (f" {merged} peak(s) not shown: another peak of the same spectrum in the same "
                     "band is nearer the band's position. Lower \"same band within \u00b1\" to "
                     "give them their own columns.")
        self.band_info.setText(text)
        self._band_shown = (columns, rows)
        return columns, rows

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
        """Draw the tab Plot; returns the number of points. Each point is
        (x, y, row, spectrum index, band position): x and y as chosen; the
        band position groups the peaks of all spectra that lie within the
        ± distance (pl.band_positions) - used by x = Peak by its position,
        Colour = Band and Join the same band."""
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
        bands = pl.band_positions(rows, self.tolerance.value())     # the band of each row
        labels = None
        if x_key == ('band', 'label') and xs:
            centres = sorted(set(xs))
            labels = [pl.band_label(c, centres) for c in centres]
            where = {c: i for i, c in enumerate(centres)}
            xs = [where[x] for x in xs]
        points = [(x, y, r, i, b) for x, y, r, i, b in zip(xs, ys, rows, index, bands)
                  if x is not None]
        all_bands = sorted(set(bands))
        band_name = lambda b: f"Band {pl.band_label(b, all_bands)}"
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
        peak_numbers = sorted({p[2][1] for p in points})
        if colour == "Peak number":
            groups, key, name = peak_numbers, (lambda p: p[2][1]), (lambda g: f"Peak {g}")
        elif colour == BAND_COLOUR:
            groups = sorted({p[4] for p in points})
            key, name = (lambda p: p[4]), band_name
        elif colour == "Maximum / minimum":
            groups = [g for g in ('maximum', 'minimum') if any(p[2][2] == g for p in points)]
            key, name = (lambda p: p[2][2]), str
        else:
            groups, key, name = [None], (lambda p: None), (lambda g: None)
        for k, g in enumerate(groups):
            sel = [(p[0], p[1]) for p in points if key(p) == g]
            col = _style(k, len(groups))[0] if g is not None else 'C0'
            gx, gy = np.array(sel).T
            ax.scatter(gx, gy, s=22, color=col, label=name(g) if g is not None else None,
                       zorder=3)
        if self.join_check.isChecked() and self.join_check.isEnabled():
            along_x = bool(x_key) and x_key[0] == 'spectrum'
            if self.join_by.currentData() == 'band':
                lines = sorted({p[4] for p in points})
                of, line_name, same = (lambda p: p[4]), band_name, BAND_COLOUR
            else:
                lines = peak_numbers
                of, line_name, same = (lambda p: p[2][1]), (lambda g: f"Peak {g}"), "Peak number"
            for k, g in enumerate(lines):
                sel = [(p[0], p[1], p[3]) for p in points if of(p) == g]
                # along x (a value of the spectrum), else spectrum after spectrum
                sel.sort(key=(lambda q: (q[0], q[2])) if along_x else (lambda q: (q[2], q[0])))
                gx, gy = np.array([(x, y) for x, y, _ in sel]).T
                col, style = _style(k, len(lines))
                # when the points are coloured the same way they already name the lines
                label = None if colour == same else f"{line_name(g)} (line)"
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
        """Find the peaks again with the current settings and fill the table
        (and the plot, when shown); the first time also the ± distance."""
        s = self.settings()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.rows, self.row_spectrum = pl.peak_table_with_index(self.spectra, **s)
        finally:
            QApplication.restoreOverrideCursor()
        self.fit_info.setText("")
        if self.refine_check.isChecked() and self.rows:
            if not self._refine_rows():
                self.refine_check.blockSignals(True)
                self.refine_check.setChecked(False)      # cancelled: the plain list
                self.refine_check.blockSignals(False)
                self._fit_controls_enabled()
                self._refill_plot_choices()
        self.columns = pl.ALL_COLUMNS if self.refine_check.isChecked() else pl.COLUMNS
        self.table.setSortingEnabled(False)
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)
        self.table.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            for c, v in enumerate(row):
                item = QTableWidgetItem()
                if isinstance(v, float) and not np.isfinite(v):
                    pass                                    # a rejected fit: an empty cell
                elif isinstance(v, (int, float)):
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

    # -- Refine by fitting
    def _fit_controls_enabled(self):
        on = self.refine_check.isChecked()
        self.fit_shape.setEnabled(on)
        self.fit_baseline.setEnabled(on)

    def _refine_toggled(self, *_):
        self._fit_controls_enabled()
        self._refill_plot_choices()
        self.refresh()

    def _refine_rows(self):
        """Fit every peak (self.rows gets the fitted columns). A progress
        window with Cancel for long lists; False when cancelled."""
        from PyQt5.QtWidgets import QProgressDialog
        from src.modules.utils.progress_utils import OperationCancelled
        dialog = None
        if len(self.rows) > 200:
            dialog = QProgressDialog("Fitting the peaks\u2026", "Cancel", 0, len(self.rows), self)
            dialog.setWindowTitle("Refine by fitting")
            dialog.setMinimumDuration(300)

        def progress(done, total):
            if dialog is not None:
                dialog.setMaximum(total)
                dialog.setValue(done)
                QApplication.processEvents()
                if dialog.wasCanceled():
                    raise OperationCancelled()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.rows, text = pl.refine_by_fitting(
                self.rows, self.row_spectrum, self.spectra, self.fit_shape.currentText(),
                self.fit_baseline.currentText(), progress=progress)
        except OperationCancelled:
            return False
        finally:
            QApplication.restoreOverrideCursor()
            if dialog is not None:
                dialog.close()
        self.fit_info.setText(text + " Shown: the fitted values.")
        return True

    def _refill_plot_choices(self):
        """x and y of the tab Plot and the value of the Band table, with the
        fitted values when Refine by fitting is on. A measured value switches
        to its fitted one when it is switched on (Position (x) -> Fitted
        position, Height, FWHM) and back when it is switched off; the other
        choices are kept when still there."""
        fitted = self.refine_check.isChecked()
        x_text = pl.matching_value(self.x_combo.currentText(), fitted)
        y_text = pl.matching_value(self.y_combo.currentText(), fitted)
        for combo in (self.x_combo, self.y_combo):
            combo.blockSignals(True)
            combo.clear()
        for text, key in pl.x_choices(self.spectra, fitted=fitted):
            self.x_combo.addItem(text, key)
        self.y_combo.addItems(pl.y_choices(fitted))
        band_text = pl.matching_value(self.band_value_combo.currentText(), fitted)
        self.band_value_combo.blockSignals(True)
        self.band_value_combo.clear()
        self.band_value_combo.addItems(pl.y_choices(fitted))
        i = self.band_value_combo.findText(band_text)
        self.band_value_combo.setCurrentIndex(max(i, 0))
        self.band_value_combo.blockSignals(False)
        for combo, text in ((self.x_combo, x_text), (self.y_combo, y_text)):
            i = combo.findText(text)
            combo.setCurrentIndex(max(i, 0))
            combo.blockSignals(False)
        self._join_possible()

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
                vals.append('' if d is None else d)          # an empty cell (rejected fit)
            out.append(vals)
        return out

    def copy(self):
        if self.tabs.currentIndex() == 2:                # the tab Band table: all of it
            columns, rows = self.fill_band_table()
            QApplication.clipboard().setText(pl.rows_as_text(rows, columns))
            self.summary.setText(f"Copied the band table ({len(rows)} rows, with the column "
                                 "names).")
            return
        rows = self._shown_rows(selected_only=True)
        QApplication.clipboard().setText(pl.rows_as_text(rows, self.columns))
        self.summary.setText(f"Copied {len(rows)} rows (with the column names).")

    def export(self):
        path, chosen = QFileDialog.getSaveFileName(
            self, "Export the peak list",
            "band_table.xlsx" if self.tabs.currentIndex() == 2 else "peak_list.xlsx",
            "Excel (*.xlsx);;CSV (*.csv);;Text, tab-separated (*.txt)")
        if not path:
            return None
        if '.' not in path.replace('\\', '/').split('/')[-1]:
            path += {'CSV': '.csv', 'Text': '.txt'}.get(chosen.split(' ')[0], '.xlsx')
        try:
            if self.tabs.currentIndex() == 2:            # the tab Band table
                columns, rows = self.fill_band_table()
                pl.export(rows, path, columns)
            else:
                pl.export(self.rows, path, self.columns)
        except Exception as exc:
            QMessageBox.warning(self, "Export", f"The peak list could not be saved:\n\n{exc}")
            return None
        self.summary.setText(f"Saved: {path}")
        return path
