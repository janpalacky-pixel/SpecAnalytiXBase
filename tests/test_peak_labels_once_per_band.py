"""Detect Peaks, Labels: with many similar spectra the numbers are written
once per band (above its highest peak, the band's position) by default -
not on every peak; or on every peak, only on the current spectrum, or none.
The red dots mark every peak in all cases."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib
matplotlib.use('Agg')
import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
BANDS = (726.7, 814.8, 1139.2, 1437.6, 1597.8)


def _canvas(n=5):
    fig = Figure()
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    x = np.linspace(200, 1800, 1601)
    for i in range(n):
        y = sum((0.2 + 0.2 * i) * np.exp(-0.5 * ((x - c - 0.6 * i) / 9) ** 2) for c in BANDS)
        ax.plot(x, y, label=f'sp{i + 1}')
    return canvas


def _detect(canvas, labels, current=None, fmt='x_only'):
    from src.modules.data_analysis.peak_detection_manager import PeakDetector
    det = PeakDetector()
    det.detect_peaks(canvas, 0.0, 10, 0, 1, 'fixed', fmt, True, 0.1, 0.02, 'Positive',
                     labels=labels, current_label=current)
    return det


def test_once_per_band_writes_one_number_per_band_above_the_highest_peak():
    canvas = _canvas()
    det = _detect(canvas, 'band')
    assert len(det.peak_lines) == 5 * len(BANDS)                    # a dot on every peak
    assert len(det.peak_texts) == len(BANDS)                        # one number per band
    lines = canvas.figure.axes[0].get_lines()[:5]
    highest = max(line.get_ydata().max() for line in lines)
    for text in det.peak_texts:
        _, y = text.get_position()
        assert y == pytest.approx(highest, rel=0.01)                # on the highest spectrum
    written = sorted(float(t.get_text()) for t in det.peak_texts)
    assert written == pytest.approx([c + 1.2 for c in BANDS], abs=1.1)  # the band's median


def test_on_every_peak_and_none():
    assert len(_detect(_canvas(), 'all').peak_texts) == 5 * len(BANDS)
    det = _detect(_canvas(), 'none')
    assert det.peak_texts == [] and len(det.peak_lines) == 5 * len(BANDS)


def test_only_the_current_spectrum():
    det = _detect(_canvas(), 'current', current='sp3')
    assert len(det.peak_texts) == len(BANDS)
    assert len(_detect(_canvas(), 'current', current=None).peak_texts) == 0


def test_one_spectrum_alone_is_labelled_as_before():
    assert len(_detect(_canvas(n=1), 'band').peak_texts) == len(BANDS)


def test_x_and_y_values_show_the_height_of_the_labelled_peak():
    det = _detect(_canvas(), 'band', fmt='both')
    assert all(t.get_text().startswith('(') and ',' in t.get_text() for t in det.peak_texts)


def test_the_setting_in_the_window():
    from src.views.dialogs.data_analysis.peak_detection_dialog import DEFAULTS
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    from src.views.dialogs.data_analysis import peak_settings_help as psh
    x = np.linspace(0, 10, 200)
    dlg = PeakListDialog(None, [{'label': 'a', 'x_scale': x, 'y_scale': np.sin(x)}],
                         mark=lambda s: None, start_tab='mark')     # the Peaks window
    assert DEFAULTS['labels'] == 'band' and dlg.mark_settings()['labels'] == 'band'
    dlg.labels_combo.setCurrentIndex(dlg.labels_combo.findData('all'))
    assert dlg.mark_settings()['labels'] == 'all'
    dlg.reset_button.click()
    assert dlg.mark_settings()['labels'] == 'band'
    assert 'Once per band' in dlg.labels_combo.toolTip()
    dlg.help_button.click()
    assert 'Labels' in dlg.settings_help.text.toPlainText()
    assert any(n == 'Labels' for n, _, _ in psh.LABEL_HELP)


def test_the_controller_keeps_the_choice_and_finds_the_current_spectrum(tmp_path, monkeypatch):
    os.environ['SPECANALYTIXBASE_DATA_DIR'] = str(tmp_path)
    from PyQt5.QtWidgets import QMessageBox
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.data_analysis.peak_detection_dialog import DEFAULTS
    mc = MainController()
    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QListWidgetItem
        x = np.linspace(200, 1800, 801)
        mc.original_spectra = [
            {'label': f'raman_2comp : raman_{i}', 'x_scale': x, 'metadata': {'unique_id': f'id{i}'},
             'y_scale': np.exp(-0.5 * ((x - 800) / 10) ** 2) * (i + 1)} for i in range(3)]
        mc.spectra_list_widget.clear()
        for sp in mc.original_spectra:
            item = QListWidgetItem(sp['label'])
            item.setData(Qt.UserRole, sp['metadata']['unique_id'])
            mc.spectra_list_widget.addItem(item)
        mc.spectra_list_widget.setCurrentRow(1)
        pdc = mc.peak_detection_controller
        assert pdc.peak_labels == 'band'
        mc._display_labels = {}
        assert pdc._current_line_label() == 'raman_2comp : raman_1'
        mc._display_labels = {'raman_2comp : raman_1': 'raman_1'}      # shortened names
        assert pdc._current_line_label() == 'raman_1'
        seen = {}
        pdc.peak_detector.detect_peaks = lambda *a, **k: seen.update(k)
        pdc.apply_settings(dict(DEFAULTS, labels='current'))
        assert pdc.peak_labels == 'current'
        assert seen == {'labels': 'current', 'current_label': 'raman_1', 'snr': 8.0}
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()
