# src/controllers/visualization/large_plot_controller.py
"""Plotting very many selected spectra (see
src/modules/visualization/large_selection.py for why and what).

* More selected spectra than the threshold (View -> Plotting many spectra…,
  default 2 000) in an Overlay, Grid or Waterfall plot: a preview of an
  evenly spread subset (default 1 000) is drawn, with a note above the plot
  and a "Plot all" button. The selection is not changed: every analysis
  uses all selected spectra.
* "Plot all" (or the setting "Always plot all"): in an Overlay plot the
  lines are drawn in portions of PORTION spectra onto the canvas, with a
  progress dialog and Stop. Stop keeps what is drawn, removes the rest
  from the plot and switches Interactive Update off -- the plot then stays
  as it is until Refresh Plot. Other plot types draw everything at once.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAction, QApplication, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QProgressDialog, QPushButton, QRadioButton, QSizePolicy, QSpinBox, QVBoxLayout, QWidget)

from src.modules.utils.app_logger import get_logger
from src.modules.visualization.large_selection import (
    DEFAULT_SETTINGS, is_large, needs_preview, normalized_settings, preview_indices)

logger = get_logger(__name__)

PREFERENCES_KEY = 'large_plot_settings'
PORTION = 500          # spectra drawn per step when drawing in portions


def _preferences():
    try:
        from src.modules.misc.session_files import Preferences
        return Preferences()
    except Exception:
        return None


class LargePlotSettingsDialog(QDialog):

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plotting many spectra")
        s = normalized_settings(settings)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Drawing thousands of spectra takes long (about 5 s per 1 000 spectra of 1 600 "
            "points on a typical computer) and cannot be interrupted once it has started. "
            "Above the limit below, Overlay, Grid and Waterfall plots therefore show a "
            "preview: an evenly spread subset of the selected spectra. The selection itself "
            "is not changed — every analysis uses all selected spectra.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(10, 10_000_000)
        self.threshold_spin.setSingleStep(500)
        self.threshold_spin.setValue(s['threshold'])
        form.addRow("More selected spectra than:", self.threshold_spin)
        self.preview_radio = QRadioButton("Show a preview of")
        self.all_radio = QRadioButton("Always plot all (Overlay plot: in portions, "
                                      "with progress and Stop)")
        self.count_spin = QSpinBox()
        self.count_spin.setRange(10, 10_000_000)
        self.count_spin.setSingleStep(100)
        self.count_spin.setValue(s['preview_count'])
        self.count_spin.setSuffix(" spectra")
        row = QHBoxLayout()
        row.addWidget(self.preview_radio)
        row.addWidget(self.count_spin)
        row.addStretch(1)
        form.addRow("Then:", row)
        form.addRow("", self.all_radio)
        (self.preview_radio if s['mode'] == 'preview' else self.all_radio).setChecked(True)
        self.preview_radio.toggled.connect(self.count_spin.setEnabled)
        self.count_spin.setEnabled(s['mode'] == 'preview')
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel
                                   | QDialogButtonBox.RestoreDefaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._defaults)
        layout.addWidget(buttons)

    def _defaults(self):
        d = DEFAULT_SETTINGS
        self.threshold_spin.setValue(d['threshold'])
        self.count_spin.setValue(d['preview_count'])
        self.preview_radio.setChecked(d['mode'] == 'preview')
        self.all_radio.setChecked(d['mode'] != 'preview')

    def settings(self):
        return normalized_settings({
            'threshold': self.threshold_spin.value(),
            'preview_count': self.count_spin.value(),
            'mode': 'preview' if self.preview_radio.isChecked() else 'all',
        })


class LargePlotController:

    def __init__(self, main):
        self.main = main
        self._plot_all_once = False
        self.last_info = None
        self._build_menu()

    # -- settings
    def settings(self):
        prefs = _preferences()
        stored = prefs.get(PREFERENCES_KEY, {}) if prefs is not None else {}
        return normalized_settings(stored if isinstance(stored, dict) else {})

    def set_settings(self, settings):
        prefs = _preferences()
        if prefs is not None:
            prefs.set(PREFERENCES_KEY, normalized_settings(settings))

    def edit_settings(self):
        dialog = LargePlotSettingsDialog(self.settings(), self.main.view)
        if dialog.exec_() == QDialog.Accepted:
            self.set_settings(dialog.settings())
            if getattr(self.main, 'selected_spectra', None):
                self.main.plot_spectra()

    def _build_menu(self):
        view_menu = getattr(getattr(self.main, 'view', None), 'menuView', None)
        if view_menu is None:
            return
        action = QAction("Plotting many spectra…", view_menu)
        action.setObjectName("actionPlottingManySpectra")
        action.setToolTip("Preview limit for large selections (Overlay, Grid, Waterfall plots)")
        action.triggered.connect(self.edit_settings)
        view_menu.addAction(action)

    # -- one plot
    def request_plot_all(self):
        """The 'Plot all' button: draw every selected spectrum once."""
        self._plot_all_once = True
        self.main.plot_spectra()

    def choose(self, spectra, plot_type, progress_callback=None):
        """(spectra to draw, info) for one plot. info: n (selected), shown,
        preview (bool), progressive (draw the Overlay plot in portions)."""
        n = len(spectra)
        s = self.settings()
        plot_all, self._plot_all_once = self._plot_all_once, False
        if needs_preview(n, plot_type, s, plot_all):
            chosen = [spectra[i] for i in preview_indices(n, s['preview_count'])]
            info = {'n': n, 'shown': len(chosen), 'preview': True, 'progressive': False}
        else:
            chosen = spectra
            info = {'n': n, 'shown': n, 'preview': False,
                    'progressive': (plot_type == 'Overlay plot' and progress_callback is None
                                    and is_large(n, plot_type, s))}
        info['stopped_at'] = None
        self.last_info = info
        return chosen, info

    def finish(self, plot_widget, canvas, info):
        """After the plot widget is in the window: draw in portions if
        needed, then show the note above the plot."""
        if info.get('progressive'):
            try:
                self._draw_in_portions(canvas, info)
            except Exception:
                logger.exception("Drawing the spectra in portions failed")
                canvas.draw_idle()
        if info.get('preview') or info.get('stopped_at') is not None:
            layout = plot_widget.layout()
            if layout is not None:
                layout.insertWidget(0, self._banner(info), 0)

    def _draw_in_portions(self, canvas, info):
        groups = getattr(canvas, 'spectrum_artists', None)
        fig = canvas.figure
        if not groups or not fig.axes:
            canvas.draw()
            return
        ax = fig.axes[0]
        for group in groups:
            for artist in group:
                artist.set_visible(False)
        QApplication.processEvents()          # the plot widget is now shown
        canvas.draw()                         # axes, labels, legend: quick without the lines
        n = len(groups)
        progress = QProgressDialog(f"Plotting {n} spectra…", "Stop", 0, n, self.main.view)
        progress.setWindowTitle("Plotting")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        progress.show()
        drawn = 0
        try:
            for start in range(0, n, PORTION):
                for group in groups[start:start + PORTION]:
                    for artist in group:
                        artist.set_visible(True)
                        ax.draw_artist(artist)
                drawn = min(n, start + PORTION)
                canvas.blit(ax.bbox)
                progress.setValue(drawn)
                progress.setLabelText(f"Plotting spectra…\n{drawn} / {n}")
                QApplication.processEvents()
                # A redraw requested meanwhile (e.g. by a resize) would draw
                # everything again in one go; the portions already cover it.
                canvas._draw_pending = False
                if progress.wasCanceled() and drawn < n:
                    break
            legend = ax.get_legend()
            if legend is not None and legend.get_visible():
                ax.draw_artist(legend)            # back on top of the lines
                canvas.blit(ax.bbox)
        finally:
            progress.close()
        if drawn < n:
            for group in groups[drawn:]:
                for artist in group:
                    artist.remove()
            info['stopped_at'] = drawn
            self._switch_off_interactive_update()

    def _switch_off_interactive_update(self):
        """Stop also switches Interactive Update off, without clearing the
        plot (unchecking it by hand clears the plot until Refresh Plot)."""
        main = self.main
        checkbox = getattr(main, 'interactive_mode_checkbox', None)
        if checkbox is None or not checkbox.isChecked():
            return
        checkbox.blockSignals(True)
        checkbox.setChecked(False)
        checkbox.blockSignals(False)
        selector = getattr(main, 'spectrum_selector', None)
        if selector is not None and hasattr(selector, 'update_groupbox_states'):
            selector.update_groupbox_states(False)
        button = getattr(main, 'refresh_plot_button', None)
        if button is not None:
            button.setVisible(True)

    def _banner(self, info):
        box = QWidget()
        box.setObjectName("largePlotBanner")
        box.setStyleSheet("#largePlotBanner { background:#FFF3E0; border:1px solid #FFB74D; }")
        box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)   # a thin line, not half the plot
        row = QHBoxLayout(box)
        row.setContentsMargins(6, 2, 6, 2)
        n = info['n']
        if info.get('stopped_at') is not None:
            text = (f"Plotting stopped: {info['stopped_at']:,} of {n:,} spectra drawn. "
                    f"Interactive Update is off; analyses use all {n:,} selected spectra.")
        else:
            text = (f"Preview: {info['shown']:,} of {n:,} selected spectra drawn (evenly "
                    f"spread). Analyses use all {n:,}.")
        label = QLabel(text.replace(',', ' '))
        label.setObjectName("largePlotBannerText")
        label.setWordWrap(True)
        row.addWidget(label, 1)
        plot_all = QPushButton("Plot all")
        plot_all.setObjectName("largePlotAllButton")
        plot_all.setToolTip("Draw every selected spectrum (Overlay plot: in portions, "
                            "with progress and Stop)")
        plot_all.clicked.connect(self.request_plot_all)
        row.addWidget(plot_all)
        settings = QPushButton("Settings…")
        settings.setToolTip("View → Plotting many spectra…")
        settings.clicked.connect(self.edit_settings)
        row.addWidget(settings)
        return box
