
# src/controllers/peak_detection_controller.py
from src.views.dialogs.data_analysis.peak_detection_dialog import PeakDetectionDialog
from src.modules.data_analysis.peak_detection_manager import PeakDetector

class PeakDetectionController:
    def __init__(self, main_controller):
        self.controller = main_controller
        self.peak_detector = PeakDetector()
        
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
        """The Peak Detection Settings: Apply marks the peaks on the plot (the
        window stays open), Close closes it."""
        dialog = PeakDetectionDialog(
            self.controller.view,
            threshold=self.peak_threshold,
            prominence=self.peak_prominence,
            distance=self.peak_distance,
            peak_mode=self.peak_detection_mode,
            font_size=self.peak_font_size,
            rotation=self.peak_rotation,
            decimals=self.peak_decimals,
            format_type=self.peak_format_type,
            number_format=self.peak_number_format,
            apply_callback=self.apply_settings,
            labels=self.peak_labels,
            snr=self.peak_snr,
        )
        dialog.peak_controller = self              # its "Peak list..." button
        self.dialog = dialog
        dialog.exec_()
        return dialog

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
        """Right-click on the plot -> Peak list...: every peak of the selected
        spectra in a table, with the settings of Detect Peaks (changed there,
        they are kept for Detect Peaks too)."""
        from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
        if spectra is None:
            spectra = list(getattr(self.controller, 'selected_spectra', None) or [])
        if not spectra:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self.controller.view, "Peak list",
                                    "Select the spectra whose peaks you want to list.")
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
                                open_data_table=self.open_bands_in_data_table)
        self.peak_list_dialog = dialog
        dialog.exec_()
        return dialog

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
        dlg.values.add_bands(value_name, bands)
        dlg.tabs.setCurrentWidget(dlg.values)
        self.band_data_table_dialog = dlg
        dlg.exec_()
        return dlg

    def clear_peaks(self):
        """Clear all detected peaks."""
        canvas = self.controller.static_canvas
        self.peak_detector.clear_peaks(canvas)