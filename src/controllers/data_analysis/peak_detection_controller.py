
# src/controllers/peak_detection_controller.py
"""Right-click on the plot -> Detect Peaks / Peak list... / Clear Peaks: the
Peaks window (PeakListDialog) - Detect Peaks opens it on its tab "Mark on the
plot", Peak list... on its tab "List" - and the marks on the main plot."""
from src.modules.data_analysis.peak_detection_manager import PeakDetector

class PeakDetectionController:
    def __init__(self, main_controller):
        self.controller = main_controller
        self.peak_detector = PeakDetector()
        self.fit_artists = []              # Peak list > Show on the main plot
        
        # Default settings (Reset to defaults in the window puts these back)
        from src.views.dialogs.data_analysis.peak_detection_dialog import DEFAULTS
        self.peak_threshold = DEFAULTS['threshold']
        self.peak_prominence = DEFAULTS['prominence']
        self.peak_distance = DEFAULTS['distance']
        self.peak_detection_mode = DEFAULTS['peak_mode']
        self.peak_snr = DEFAULTS['snr']                 # minimum signal-to-noise
        self.peak_font_size = DEFAULTS['font_size']
        self.peak_rotation = DEFAULTS['rotation']
        self.peak_decimals = DEFAULTS['decimals']
        self.peak_number_format = DEFAULTS['number_format']
        self.peak_format_type = DEFAULTS['format_type']
        self.peak_labels = DEFAULTS['labels']          # once per band, every peak, ...
        self.show_labels = True

    def show_dialog(self):
        """Right-click on the plot -> Detect Peaks: the Peaks window on its tab
        "Mark on the plot"."""
        return self.show_peaks('mark')

    def apply_settings(self, settings):
        """Keep the settings and mark the peaks on the plot."""
        self.peak_threshold = settings['threshold']
        self.peak_font_size = settings['font_size']
        self.peak_rotation = settings['rotation']
        self.peak_decimals = settings['decimals']
        self.peak_number_format = settings['number_format']
        self.peak_format_type = settings['format_type']
        self.peak_prominence = settings['prominence']
        self.peak_distance = settings['distance']
        self.peak_detection_mode = settings['peak_mode']
        self.peak_labels = settings.get('labels', self.peak_labels)
        self.peak_snr = settings.get('snr', self.peak_snr)
        self.detect_peaks()

    def detect_peaks(self):
        """Detect peaks using the current settings."""
        canvas = self.controller.static_canvas
        self.peak_detector.detect_peaks(
            canvas,
            self.peak_threshold,
            self.peak_font_size,
            self.peak_rotation,
            self.peak_decimals,
            self.peak_number_format,
            self.peak_format_type,
            self.show_labels,
            self.peak_prominence,
            self.peak_distance,
            self.peak_detection_mode,
            labels=self.peak_labels,
            current_label=self._current_line_label(),
            snr=self.peak_snr,
        )

    def _current_line_label(self):
        """The legend text of the spectrum highlighted in the spectra list
        (what its line on the plot is called), or None."""
        from PyQt5.QtCore import Qt
        from src.modules.utils.spectrum_identity import spectrum_key
        widget = getattr(self.controller, 'spectra_list_widget', None)
        item = widget.currentItem() if widget is not None else None
        if item is None:
            return None
        key = item.data(Qt.UserRole)
        for sp in getattr(self.controller, 'original_spectra', []) or []:
            if spectrum_key(sp) == key:
                label = sp.get('label', '')
                shown = getattr(self.controller, '_display_labels', None) or {}
                return shown.get(label, label)
        return None

    def show_peak_list(self, spectra=None):
        """Right-click on the plot -> Peak list...: the Peaks window on its tab
        "List" (every peak of the selected spectra in a table)."""
        return self.show_peaks('list', spectra)

    def show_peaks(self, tab='list', spectra=None):
        """The Peaks window of the selected spectra: one set of settings for
        the list, its plot, the band table and the marks on the main plot
        (kept here for the next time)."""
        from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
        if spectra is None:
            spectra = list(getattr(self.controller, 'selected_spectra', None) or [])
        if not spectra:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self.controller.view, "Peaks",
                                    "Select the spectra whose peaks you want to find.")
            return None

        def keep(settings):
            self.peak_threshold = settings['threshold']
            self.peak_prominence = settings['prominence']
            self.peak_distance = settings['distance']
            self.peak_detection_mode = settings['mode']
            self.peak_snr = settings.get('snr', self.peak_snr)

        dialog = PeakListDialog(self.controller.view, spectra,
                                threshold=self.peak_threshold, prominence=self.peak_prominence,
                                distance=self.peak_distance, mode=self.peak_detection_mode,
                                snr=self.peak_snr, on_settings=keep,
                                open_data_table=self.open_bands_in_data_table,
                                show_fits=self.show_fits_on_plot,
                                mark=self.apply_settings, clear_marks=self.clear_marks,
                                mark_settings=self._mark_settings(), start_tab=tab,
                                show_peak=self.show_peak_on_plot)
        self.peak_list_dialog = self.dialog = dialog
        # beside the plot: zoom and pan the main plot while the window is open
        from src.views.plot_only_mode import run_beside_plot
        run_beside_plot(dialog, "Peaks")
        self._keep_mark_settings(dialog.mark_settings())
        return dialog

    def _mark_settings(self):
        return {'labels': self.peak_labels, 'font_size': self.peak_font_size,
                'rotation': self.peak_rotation, 'decimals': self.peak_decimals,
                'number_format': self.peak_number_format, 'format_type': self.peak_format_type}

    def _keep_mark_settings(self, s):
        """How the numbers on the plot are written, for the next time."""
        self.peak_labels = s.get('labels', self.peak_labels)
        self.peak_font_size = s.get('font_size', self.peak_font_size)
        self.peak_rotation = s.get('rotation', self.peak_rotation)
        self.peak_decimals = s.get('decimals', self.peak_decimals)
        self.peak_number_format = s.get('number_format', self.peak_number_format)
        self.peak_format_type = s.get('format_type', self.peak_format_type)

    def open_bands_in_data_table(self, parent, spectra, value_name, bands):
        """Peak list > Band table > Open in the Data table: the Data table of
        the same spectra, on its tab Values per spectrum, with one column per
        band (b1, b2, ...). Formula columns of its tab Points can be added to
        the spectra list as usual."""
        from src.views.dialogs.data_analysis.data_table_dialog import DataTableDialog
        main = self.controller
        tables = getattr(main, 'data_table_controller', None)
        dlg = DataTableDialog(parent, spectra,
                              commit_callback=tables.add_spectra if tables is not None else None)
        # the Band table's "same band within +-": a band whose position moved a
        # little (more peaks joined it) fills its old column again
        tolerance = getattr(parent, 'tolerance', None)
        dlg.values.add_bands(value_name, bands,
                             tolerance.value() if hasattr(tolerance, 'value') else None)
        dlg.tabs.setCurrentWidget(dlg.values)
        self.band_data_table_dialog = dlg
        dlg.exec_()
        return dlg

    FIT_GID = 'peak_list_fit'
    SHOWN_GID = 'peak_list_shown'

    def show_peak_on_plot(self, spectrum, x, y):
        """Peaks window, a double-click in the tab List: the spectrum of that
        peak highlighted on the main plot (a wide pale band under its line)
        and the peak circled, with the spectrum's name and the position (in a
        stacked plot at its line's offset). The view does not change. Removed
        by the next double-click, Clear Peaks or a new plot. Returns True if
        the spectrum is on the plot now."""
        import numpy as np
        from src.modules.data_analysis import peak_list as pl
        canvas = getattr(self.controller, 'static_canvas', None)
        self._remove_shown()
        if canvas is None:
            return False
        sx = np.asarray(spectrum.get('x_scale', []), dtype=float)
        sy = np.asarray(spectrum.get('y_scale', []), dtype=float)
        own = (self.FIT_GID, self.SHOWN_GID)
        for ax in canvas.figure.get_axes():
            for line in ax.get_lines():
                if line.get_gid() in own:
                    continue
                offset = pl.line_offset(line.get_xdata(), line.get_ydata(), sx, sy)
                if offset is None:
                    continue
                limits = ax.get_xlim(), ax.get_ylim()
                band, = ax.plot(line.get_xdata(), line.get_ydata(), color=line.get_color(),
                                lw=line.get_linewidth() + 5, alpha=0.3, solid_capstyle='round',
                                zorder=line.get_zorder() - 0.1, label='_nolegend_',
                                gid=self.SHOWN_GID)
                ring, = ax.plot([x], [y + offset], 'o', ms=15, mfc='none', mec='#D84315',
                                mew=2.2, zorder=7, label='_nolegend_', gid=self.SHOWN_GID)
                name = str(spectrum.get('label', ''))
                text = ax.annotate(f"{name}\n{x:g}", (x, y + offset), xytext=(0, 16),
                                   textcoords='offset points', ha='center', va='bottom',
                                   fontsize=9, color='#D84315', zorder=8,
                                   bbox=dict(boxstyle='round,pad=0.25', fc='white',
                                             ec='#D84315', alpha=0.9))
                text.set_gid(self.SHOWN_GID)
                self.shown_artists = [band, ring, text]
                ax.set_xlim(limits[0])
                ax.set_ylim(limits[1])
                canvas.draw_idle()
                return True
        canvas.draw_idle()
        return False

    def _remove_shown(self):
        for artist in getattr(self, 'shown_artists', []):
            try:
                artist.remove()
            except (ValueError, AttributeError, NotImplementedError):  # gone with a new plot
                pass
        self.shown_artists = []

    def show_fits_on_plot(self, curves):
        """Peak list > Show on the main plot: draw the fitted peaks, curves =
        [(spectrum, x, y)], dashed over their spectra on the main plot (also
        a stacked plot: each curve gets its line's offset); None or [] removes
        them. The axis limits stay as they are. Returns the number drawn - a
        spectrum that is not on the plot now is left out."""
        import numpy as np
        from src.modules.data_analysis import peak_list as pl
        canvas = getattr(self.controller, 'static_canvas', None)
        self._remove_fits()
        if canvas is None:
            return 0
        drawn = 0
        if curves:
            for ax in canvas.figure.get_axes():
                lines = [ln for ln in ax.get_lines() if ln.get_gid() != self.FIT_GID]
                limits = ax.get_xlim(), ax.get_ylim()
                cache = {}
                for spectrum, x, y in curves:
                    key = id(spectrum)
                    if key not in cache:
                        sx = np.asarray(spectrum.get('x_scale', []), dtype=float)
                        sy = np.asarray(spectrum.get('y_scale', []), dtype=float)
                        cache[key] = next(
                            ((b, ln) for ln in lines
                             for b in [pl.line_offset(ln.get_xdata(), ln.get_ydata(), sx, sy)]
                             if b is not None), None)
                    hit = cache[key]
                    if hit is None:
                        continue
                    offset, _line = hit
                    artist, = ax.plot(x, np.asarray(y, dtype=float) + offset, ls='--', lw=1.2,
                                      color='black', alpha=0.85, zorder=5, label='_nolegend_',
                                      gid=self.FIT_GID)
                    self.fit_artists.append(artist)
                    drawn += 1
                ax.set_xlim(limits[0])
                ax.set_ylim(limits[1])
        canvas.draw_idle()
        return drawn

    def _remove_fits(self):
        for artist in self.fit_artists:
            try:
                artist.remove()
            except (ValueError, AttributeError):       # already gone with a new plot
                pass
        self.fit_artists = []

    def clear_marks(self):
        """The Peaks window, Remove the marks: the red dots and their numbers
        (the fitted peaks drawn by Show on the main plot stay)."""
        self.peak_detector.clear_peaks(self.controller.static_canvas)

    def clear_peaks(self):
        """Clear all detected peaks (and the fitted peaks of the Peak list)."""
        canvas = self.controller.static_canvas
        self._remove_fits()
        self._remove_shown()
        self.peak_detector.clear_peaks(canvas)