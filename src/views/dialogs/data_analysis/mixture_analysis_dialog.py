# src/views/dialogs/data_analysis/mixture_analysis_dialog.py
"""Analysis & Visualization -> Data Analysis -> Mixture analysis (known
components): tick which of the selected spectra are the known components;
every other selected spectrum is described as a sum of them (classical least
squares). Results: amounts, fractions, R^2 and residual per spectrum, and a
plot of the fit of the spectrum chosen in the table. The calculation is
src/modules/data_analysis/mixture_analysis.py."""

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
                             QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                             QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                             QShortcut, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from src.modules.data_analysis import mixture_analysis as ma


class MixtureAnalysisDialog(QDialog):

    def __init__(self, parent, spectra):
        super().__init__(parent)
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
        from matplotlib.figure import Figure
        self.spectra = list(spectra)
        self.fits, self.columns, self.rows = [], [], []
        self.setWindowTitle("Mixture analysis (known components)")
        self.setWindowFlags((self.windowFlags() | Qt.WindowMaximizeButtonHint)
                            & ~Qt.WindowContextHelpButtonHint)
        self.resize(1180, 720)
        outer = QVBoxLayout(self)
        intro = QLabel(
            "Each spectrum is described as a sum of known component spectra: spectrum ≈ "
            "a₁·component₁ + a₂·component₂ + … (least squares). "
            "Tick the known components in the list (e.g. the pure substances); all other selected "
            "spectra are analysed. The amounts are in the units of the component spectra.")
        intro.setWordWrap(True)
        top = QHBoxLayout()
        top.addWidget(intro, 1)
        from src.views.icons import help_button
        self.help_button = help_button("How the mixture analysis works")
        self.help_button.clicked.connect(self.show_help)
        top.addWidget(self.help_button, 0, Qt.AlignTop)
        outer.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("Known components (tick them)")
        bv = QVBoxLayout(box)
        self.list = QListWidget()
        for s in self.spectra:
            item = QListWidgetItem(str(s.get('label', '')))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.list.addItem(item)
        bv.addWidget(self.list)
        lv.addWidget(box, 1)
        opts = QGroupBox("Options")
        form = QFormLayout(opts)
        self.nonneg = QCheckBox("Amounts never negative")
        self.nonneg.setChecked(True)
        self.nonneg.setToolTip("Non-negative least squares: a substance cannot be present in a "
                               "negative amount. Untick for plain least squares.")
        form.addRow(self.nonneg)
        self.background = QComboBox()
        for key, text in ma.BACKGROUNDS.items():
            self.background.addItem(text, key)
        self.background.setToolTip("Also fit a background: a constant offset, or an offset and a "
                                   "slope (e.g. a baseline that was not fully removed)")
        form.addRow("Background:", self.background)
        self.use_range = QCheckBox("Only the x-range")
        xs = [np.asarray(s['x_scale'], float) for s in self.spectra if len(s['x_scale'])]
        lo = float(min(x.min() for x in xs)) if xs else 0.0
        hi = float(max(x.max() for x in xs)) if xs else 1.0
        self.x_from, self.x_to = QDoubleSpinBox(), QDoubleSpinBox()
        for w, v in ((self.x_from, lo), (self.x_to, hi)):
            w.setRange(-1e9, 1e9)
            w.setDecimals(3)
            w.setValue(v)
            w.setEnabled(False)
        self.use_range.toggled.connect(self.x_from.setEnabled)
        self.use_range.toggled.connect(self.x_to.setEnabled)
        rr = QHBoxLayout()
        rr.addWidget(self.x_from)
        rr.addWidget(QLabel("to"))
        rr.addWidget(self.x_to)
        form.addRow(self.use_range)
        form.addRow(rr)
        lv.addWidget(opts)
        self.calc_button = QPushButton("Calculate")
        self.calc_button.setAutoDefault(False)
        self.calc_button.clicked.connect(self.calculate)
        lv.addWidget(self.calc_button)
        splitter.addWidget(left)

        right = QSplitter(Qt.Vertical)
        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemSelectionChanged.connect(self.show_fit)
        QShortcut(QKeySequence.Copy, self.table, activated=self.copy)
        right.addWidget(self.table)
        plot = QWidget()
        pv = QVBoxLayout(plot)
        pv.setContentsMargins(0, 0, 0, 0)
        self.figure = Figure(figsize=(7, 4.5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        pv.addWidget(NavigationToolbar2QT(self.canvas, plot))
        pv.addWidget(self.canvas, 1)
        right.addWidget(plot)
        right.setSizes([260, 420])
        splitter.addWidget(right)
        splitter.setSizes([330, 850])
        try:
            from src.views.dialogs.misc.splitter_utils import no_collapse
            no_collapse(splitter, 200)
            no_collapse(right, 120)
        except Exception:
            pass
        outer.addWidget(splitter, 1)

        self.message = QLabel("Tick the known components, then click Calculate.")
        self.message.setWordWrap(True)
        outer.addWidget(self.message)
        buttons = QHBoxLayout()
        self.copy_button = QPushButton("Copy")
        self.copy_button.setToolTip("Copy the selected rows (or all) with the column names, e.g. "
                                    "into Excel")
        self.copy_button.clicked.connect(self.copy)
        self.export_button = QPushButton("Export…")
        self.export_button.clicked.connect(self.export)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        for b in (self.copy_button, self.export_button, close):
            b.setAutoDefault(False)
            if b is not close:
                b.setEnabled(False)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.export_button)
        buttons.addStretch(1)
        buttons.addWidget(close)
        outer.addLayout(buttons)

    # -- choices
    def components(self):
        return [s for i, s in enumerate(self.spectra)
                if self.list.item(i).checkState() == Qt.Checked]

    def samples(self):
        return [s for i, s in enumerate(self.spectra)
                if self.list.item(i).checkState() != Qt.Checked]

    def set_components(self, labels):
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setCheckState(Qt.Checked if item.text() in labels else Qt.Unchecked)

    def _say(self, text, error=False):
        self.message.setText(text)
        self.message.setStyleSheet("color: #C62828;" if error else "")

    # -- calculation
    def calculate(self):
        comps, samples = self.components(), self.samples()
        if not comps:
            self._say("Tick at least one known component in the list.", error=True)
            return None
        if not samples:
            self._say("Every selected spectrum is ticked as a component: leave the spectra to "
                      "analyse unticked.", error=True)
            return None
        bg = self.background.currentData()
        x_range = (self.x_from.value(), self.x_to.value()) if self.use_range.isChecked() else None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.fits = ma.analyse(samples, comps, self.nonneg.isChecked(), bg, x_range)
        finally:
            QApplication.restoreOverrideCursor()
        names = [str(c.get('label', '')) for c in comps]
        self.columns = ma.table_columns(names, bg)
        self.rows = ma.table_rows(self.fits, bg)
        self.table.clear()
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)
        self.table.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            for c, v in enumerate(row):
                item = QTableWidgetItem(v if isinstance(v, str) else
                                        ('—' if not np.isfinite(v) else f'{v:.6g}'))
                if not isinstance(v, str):
                    item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, min(self.table.columnWidth(0), 260))
        failed = [f for f in self.fits if f.error]
        r2 = [f.r2 for f in self.fits if np.isfinite(f.r2)]
        text = f"{len(self.fits)} spectra analysed with {len(comps)} component(s)"
        if r2:
            text += f"; R² from {min(r2):.4f} to {max(r2):.4f}"
        if failed:
            text += f". {len(failed)} could not be analysed: {failed[0].error}"
        self._say(text + ".", error=bool(failed))
        self.copy_button.setEnabled(True)
        self.export_button.setEnabled(True)
        if self.rows:
            self.table.selectRow(0)
        return self.fits

    def show_fit(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        self.figure.clear()
        if not rows or rows[0] >= len(self.fits):
            self.canvas.draw_idle()
            return
        f = self.fits[rows[0]]
        names = self.columns[1:1 + len(f.amounts)]
        ax, axr = self.figure.subplots(2, 1, sharex=True, gridspec_kw={'height_ratios': [3, 1]})
        if not f.error:
            ax.plot(f.x, f.y, color='black', lw=1.4, label=f.label)
            ax.plot(f.x, f.fit, color='#D62728', lw=1.2, ls='--', label='sum of the components')
            for part, name in zip(f.parts, names):
                ax.plot(f.x, part, lw=1, alpha=0.8, label=name.replace('Amount of ', ''))
            axr.plot(f.x, f.residual, color='#555555', lw=0.8)
            axr.axhline(0, color='#999999', lw=0.6)
            ax.set_title(f"R² = {f.r2:.4f}", fontsize=10)
        else:
            ax.text(0.5, 0.5, f.error, ha='center', va='center', wrap=True, transform=ax.transAxes)
        ax.legend(fontsize=8, loc='best') if len(f.amounts) <= 12 and not f.error else None
        axr.set_ylabel('residual', fontsize=9)
        axr.set_xlabel('x')
        try:
            self.figure.tight_layout()
        except Exception:
            pass
        self.canvas.draw_idle()

    # -- copy, export, help
    def copy(self):
        if not self.rows:
            return
        picked = sorted({i.row() for i in self.table.selectedIndexes()}) or range(len(self.rows))
        QApplication.clipboard().setText(ma.rows_as_text(self.columns, [self.rows[r] for r in picked]))
        self._say(f"Copied {len(picked)} rows (with the column names).")

    def export(self):
        if not self.rows:
            return None
        path, chosen = QFileDialog.getSaveFileName(
            self, "Export the mixture analysis", "mixture_analysis.xlsx",
            "Excel (*.xlsx);;CSV (*.csv);;Text, tab-separated (*.txt)")
        if not path:
            return None
        if '.' not in path.replace('\\', '/').split('/')[-1]:
            path += {'CSV': '.csv', 'Text': '.txt'}.get(chosen.split(' ')[0], '.xlsx')
        try:
            ma.export(self.columns, self.rows, path)
        except Exception as exc:
            QMessageBox.warning(self, "Export", f"The results could not be saved:\n\n{exc}")
            return None
        self._say(f"Saved: {path}")
        return path

    def show_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'user_guide', 'mixture-analysis')
