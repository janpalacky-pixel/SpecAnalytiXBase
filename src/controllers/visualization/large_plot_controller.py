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
* Legend with more entries than "Maximum Legend Items" (Legend window): an
  evenly spread subset is listed (legend_properties_manager.py) and the
  same strip above the plot says so, with Show all / Choose... / Settings...
  (both notes share one strip).
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAction, QApplication, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QMessageBox, QProgressDialog, QPushButton, QRadioButton, QSizePolicy, QSpinBox,
    QVBoxLayout, QWidget)

from src.modules.utils.app_logger import get_logger
from src.modules.visualization.large_selection import (
    DEFAULT_DIALOG_COUNT, DEFAULT_SETTINGS, is_large, needs_preview, normalized_dialog_count,
    normalized_settings, preview_indices)

logger = get_logger(__name__)

PREFERENCES_KEY = 'large_plot_settings'
DIALOG_COUNT_KEY = 'large_plot_dialog_count'
PORTION = 500          # spectra drawn per step when drawing in portions
LEGEND_ASK_ABOVE = 500  # "Show all" legend entries: ask first above this many


def _preferences():
    try:
        from src.modules.misc.session_files import Preferences
        return Preferences()
    except Exception:
        return None


def dialog_draw_limit():
    """How many spectra a tool window draws at most (the setting 'Tool
    windows: draw at most ...' in View -> Plotting many spectra...)."""
    prefs = _preferences()
    stored = prefs.get(DIALOG_COUNT_KEY, DEFAULT_DIALOG_COUNT) if prefs is not None \
        else DEFAULT_DIALOG_COUNT
    return normalized_dialog_count(stored)


class LargePlotSettingsDialog(QDialog):

    def __init__(self, settings, parent=None, dialog_count=DEFAULT_DIALOG_COUNT):
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
        self.dialog_spin = QSpinBox()
        self.dialog_spin.setRange(10, 10_000_000)
        self.dialog_spin.setSingleStep(100)
        self.dialog_spin.setValue(normalized_dialog_count(dialog_count))
        self.dialog_spin.setSuffix(" spectra")
        self.dialog_spin.setToolTip(
            "Tool windows such as FFT Denoising, X-axis alignment, Isosbestic Point\n"
            "Detection or 2D Correlation redraw their plots after every change. With\n"
            "more spectra than this they draw an evenly spread subset (the plot title\n"
            "says e.g. '100 of 3 000 shown'); the calculation always uses all spectra.")
        form.addRow("Tool windows: draw at most", self.dialog_spin)
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
        self.dialog_spin.setValue(DEFAULT_DIALOG_COUNT)

    def settings(self):
        return normalized_settings({
            'threshold': self.threshold_spin.value(),
            'preview_count': self.count_spin.value(),
            'mode': 'preview' if self.preview_radio.isChecked() else 'all',
        })

    def dialog_count(self):
        return normalized_dialog_count(self.dialog_spin.value())


class LargePlotController:

    def __init__(self, main):
        self.main = main
        self._plot_all_once = False
        self.last_info = None
        self._plot_widget = None       # the plot on screen and its strip (note)
        self._canvas = None
        self._strip = None
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
        dialog = LargePlotSettingsDialog(self.settings(), self.main.view,
                                         dialog_count=dialog_draw_limit())
        if dialog.exec_() == QDialog.Accepted:
            self.set_settings(dialog.settings())
            prefs = _preferences()
            if prefs is not None:
                prefs.set(DIALOG_COUNT_KEY, dialog.dialog_count())
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
        self._plot_widget, self._canvas, self._strip = plot_widget, canvas, None
        self.update_banner()

    def update_banner(self):
        """(Re)build the strip above the plot: the preview / stopped note
        and the legend note, whichever applies (also after the Legend window
        or a strip button changed the legend)."""
        widget = self._plot_widget
        try:
            layout = widget.layout() if widget is not None else None
        except RuntimeError:                  # the plot widget was replaced
            layout = None
        if layout is None:
            return
        if self._strip is not None:
            layout.removeWidget(self._strip)
            self._strip.hide()
            self._strip.setParent(None)       # gone at once, not only at the next event loop
            self._strip.deleteLater()
            self._strip = None
        info = self.last_info or {}
        legend = self.legend_info()
        if not (info.get('preview') or info.get('stopped_at') is not None or legend):
            return
        self._strip = self._banner(info, legend)
        layout.insertWidget(0, self._strip, 0)

    def legend_info(self):
        """{'total', 'shown', 'mode'} of the visible legend that lists only some
        of its entries (the axes with the most entries), else None."""
        canvas = self._canvas
        best = None
        try:
            axes = canvas.figure.axes if canvas is not None else []
        except RuntimeError:
            axes = []
        for ax in axes:
            leg = ax.get_legend()
            info = getattr(ax, '_legend_entries_info', None)
            if leg is None or not leg.get_visible() or not info:
                continue
            if info['mode'] == 'all':
                continue
            if best is None or info['total'] > best['total']:
                best = dict(info, ax=ax)
        return best

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

    def _banner(self, info, legend=None):
        box = QWidget()
        box.setObjectName("largePlotBanner")
        box.setStyleSheet("#largePlotBanner { background:#FFF3E0; border:1px solid #FFB74D; }")
        box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)   # a thin line, not half the plot
        rows = QVBoxLayout(box)
        rows.setContentsMargins(6, 2, 6, 2)
        rows.setSpacing(2)
        if info.get('preview') or info.get('stopped_at') is not None:
            rows.addLayout(self._plot_row(info))
        if legend:
            rows.addLayout(self._legend_row(legend))
        return box

    def _plot_row(self, info):
        row = QHBoxLayout()
        n = info['n']
        if info.get('stopped_at') is not None:
            text = (f"Plotting stopped: {info['stopped_at']:,} of {n:,} spectra drawn. "
                    f"Interactive Update is off; analyses use all {n:,} selected spectra.")
        else:
            text = (f"Preview: {info['shown']:,} of {n:,} selected spectra drawn (evenly "
                    f"spread). Analyses use all {n:,}.")
        label = QLabel(text.replace(',', '\u202f'))
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
        return row

    def _legend_row(self, legend):
        row = QHBoxLayout()
        what = ("drawn spectra" if (self.last_info or {}).get('preview') else "spectra")
        how = "your choice" if legend['mode'] == 'chosen' else "evenly spread"
        label = QLabel(f"Legend: {legend['shown']:,} of {legend['total']:,} {what} listed "
                       f"({how}).".replace(',', '\u202f'))
        label.setObjectName("legendBannerText")
        label.setWordWrap(True)
        row.addWidget(label, 1)
        show_all = QPushButton("Show all")
        show_all.setObjectName("legendShowAllButton")
        show_all.setToolTip("List every entry in the legend (ticks \"Show All Legend Items\" "
                            "in the Legend window, so it stays on)")
        show_all.clicked.connect(self.legend_show_all)
        row.addWidget(show_all)
        choose = QPushButton("Choose…")
        choose.setObjectName("legendChooseButton")
        choose.setToolTip("Pick the spectra listed in the legend (by name, range or every "
                          "n-th), for this plot")
        choose.clicked.connect(self.legend_choose)
        row.addWidget(choose)
        if legend['mode'] == 'chosen':
            auto = QPushButton("Evenly spread")
            auto.setObjectName("legendAutoButton")
            auto.setToolTip("Forget the choice: list an evenly spread subset again")
            auto.clicked.connect(self.legend_clear_choice)
            row.addWidget(auto)
        settings = QPushButton("Settings…")
        settings.setObjectName("legendSettingsButton")
        settings.setToolTip("The Legend window (☰ Legend): maximum number of entries, "
                            "position, font, …")
        settings.clicked.connect(self._legend_settings)
        row.addWidget(settings)
        return row

    # -- legend actions (strip buttons)
    def _legend_manager(self):
        return getattr(self.main, 'legend_manager', None)

    def _reapply_legend(self):
        manager = self._legend_manager()
        canvas = self._canvas
        if manager is None or canvas is None:
            return
        for ax in canvas.figure.axes:
            manager.apply_settings_to_legend(ax)
        canvas.draw_idle()
        self.update_banner()

    def legend_show_all(self):
        manager = self._legend_manager()
        legend = self.legend_info()
        if manager is None:
            return
        total = legend['total'] if legend else 0
        if total > LEGEND_ASK_ABOVE and QMessageBox.question(
                self.main.view, "Show all legend entries",
                f"The legend would list {total:,} entries. That takes long to draw and "
                f"covers the plot. Show all of them?".replace(',', '\u202f'),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        manager.update_settings({'show_all_items': True})
        manager.set_chosen(None, None)
        self._reapply_legend()

    def legend_choose(self):
        manager = self._legend_manager()
        legend = self.legend_info()
        if manager is None or not legend:
            return
        _, labels = legend['ax'].get_legend_handles_labels()
        from src.views.dialogs.misc.spectra_selection_dialog import SpectraSelectionDialog
        dlg = SpectraSelectionDialog(parent=self.main.view, total_spectra=len(labels),
                                     title="Spectra listed in the legend", labels=labels)
        if dlg.exec_() != QDialog.Accepted:
            return
        params = dlg.get_selection_parameters() or {}
        picked = [i for i in params.get('indices', []) if 0 <= i < len(labels)]
        current = manager.chosen_indices(labels)
        if current is None:
            current = [labels.index(t) for t in self._listed_texts(legend['ax'])
                       if t in labels]
        action = params.get('action', 'select')
        if action == 'add':
            picked = sorted(set(current) | set(picked))
        elif action == 'remove':
            picked = sorted(set(current) - set(picked))
        manager.set_chosen(labels, picked)
        self._reapply_legend()

    @staticmethod
    def _listed_texts(ax):
        leg = ax.get_legend()
        return [t.get_text() for t in leg.get_texts()] if leg is not None else []

    def legend_clear_choice(self):
        manager = self._legend_manager()
        if manager is not None:
            manager.set_chosen(None, None)
            self._reapply_legend()

    def _legend_settings(self):
        controller = getattr(self.main, 'legend_properties_controller', None)
        if controller is not None:
            controller.show_dialog()
