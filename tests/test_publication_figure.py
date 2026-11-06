"""Save plot for publication: a copy in a journal's column width, one text
size, lines at least so thick, at the chosen dpi - the plot on the screen
unchanged; the window remembers the choices."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


def _figure():
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    fig = Figure(figsize=(10, 6))
    FigureCanvasQTAgg(fig)
    ax = fig.add_subplot()
    ax.plot([1, 2, 3], [1, 4, 9], lw=0.5, label='file : sp001')
    ax.plot([1, 2, 3], [2, 5, 7], lw=2.0, label='file : sp002')
    ax.grid(True)
    ax.set_xlabel('Wavenumber')
    ax.set_title('Spectra')
    ax.legend()
    return fig


@pytest.mark.parametrize('ext', ['tif', 'png', 'pdf', 'svg', 'eps'])
def test_saved_in_each_kind(tmp_path, ext):
    from src.modules.visualization import publication_figure as pf
    fig = _figure()
    path = str(tmp_path / f'fig.{ext}')
    copy = pf.save_for_publication(fig, path, 8.5, 6.5, 600, 8, 1.0)
    assert os.path.getsize(path) > 1000
    assert tuple(fig.get_size_inches()) == (10, 6) and fig.axes[0].lines[0].get_linewidth() == 0.5
    assert copy.get_size_inches()[0] == pytest.approx(8.5 / 2.54)
    assert copy.axes[0].lines[0].get_linewidth() == 1.0
    assert copy.axes[0].xaxis.label.get_fontsize() == 8 and copy.axes[0].title.get_fontsize() == 9
    if ext == 'tif':
        from PIL import Image
        im = Image.open(path)
        assert im.size == pytest.approx(pf.pixels(8.5, 6.5, 600), abs=2)
        assert round(im.info['dpi'][0]) == 600


def test_the_window(tmp_path):
    from src.views.dialogs.visualization.publication_dialog import PREF_KEY, PublicationDialog

    class Prefs(dict):
        def set(self, k, v):
            self[k] = v
    prefs = Prefs()
    dlg = PublicationDialog(_figure(), preferences=prefs)
    dlg.column_combo.setCurrentIndex(2)                         # 2 columns
    assert dlg.width_spin.value() == 17.5
    dlg.width_spin.setValue(10.0)
    assert dlg.column_combo.currentData() is None               # own width
    dlg.dpi_combo.setCurrentIndex(dlg.dpi_combo.findData(300))
    assert '1181' in dlg.pixels_label.text()                    # 10 cm at 300 dpi
    path = dlg.save(str(tmp_path / 'f.png'))
    assert path and os.path.exists(path) and prefs[PREF_KEY]['dpi'] == 300
    again = PublicationDialog(_figure(), preferences=prefs)
    assert again.width_spin.value() == 10.0 and again.dpi_combo.currentData() == 300


def test_legend_short_names_and_thin_grid():
    from src.modules.visualization import publication_figure as pf
    fig = _figure()
    copy = pf.copy_for_publication(fig, 8.5, 6.5, 8, 1.0)
    ax = copy.axes[0]
    leg = ax.get_legend()
    assert [t.get_text() for t in leg.get_texts()] == ['sp001', 'sp002']     # short names
    assert leg.get_texts()[0].get_fontsize() == 7                             # 1 pt smaller
    assert ax.get_lines()[1].get_linewidth() == 2.0                           # thicker kept
    assert all(g.get_linewidth() <= 0.5 for g in ax.get_xgridlines())         # grid stays thin
    right = pf.copy_for_publication(fig, 8.5, 6.5, 8, 1.0, legend='right', short_names=False)
    assert right.axes[0].get_legend().get_texts()[0].get_text() == 'file : sp001'
    assert pf.copy_for_publication(fig, 8.5, 6.5, legend='none').axes[0].get_legend() is None
    assert fig.axes[0].get_legend().get_texts()[0].get_text() == 'file : sp001'   # screen: same


def test_a_heatmap_with_a_colour_bar(tmp_path):
    import numpy as np
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    from src.modules.visualization import publication_figure as pf
    fig = Figure(figsize=(12, 6))
    FigureCanvasQTAgg(fig)
    ax = fig.add_subplot()
    im = ax.imshow(np.random.default_rng(0).random((3, 20)), aspect='auto')
    ax.set_yticks(range(3))
    ax.set_yticklabels(['f : a1', 'f : a2', 'f : a3'])
    fig.colorbar(im, ax=ax)
    path = str(tmp_path / 'heat.png')
    copy = pf.save_for_publication(fig, path, 8.5, 6.5, 300, 8, 1.0)
    assert os.path.getsize(path) > 1000
    assert [t.get_text() for t in copy.axes[0].get_yticklabels()] == ['a1', 'a2', 'a3']


def test_the_buttons_enter_and_print(tmp_path, monkeypatch):
    """Save (a click passes no file name: it is asked for), Enter in a number
    box does not save, the choices kept without saving, Print to a PDF."""
    from PyQt5.QtPrintSupport import QPrinter
    from PyQt5.QtWidgets import QFileDialog
    from src.views.dialogs.visualization.publication_dialog import PREF_KEY, PublicationDialog

    class Prefs(dict):
        def set(self, k, v):
            self[k] = v
    prefs = Prefs()
    target = str(tmp_path / 'clicked')
    monkeypatch.setattr(QFileDialog, 'getSaveFileName',
                        staticmethod(lambda *a, **k: (target, 'TIFF (*.tif)')))
    dlg = PublicationDialog(_figure(), preferences=prefs)
    assert not dlg.save_button.autoDefault() and not dlg.save_button.isDefault()
    dlg.save_button.click()
    assert dlg.saved_path == target + '.tif' and os.path.exists(target + '.tif')
    dlg.height_spin.setValue(7.5)                                   # no saving
    dlg.legend_combo.setCurrentIndex(dlg.legend_combo.findData('bottom'))
    dlg.place_combo.setCurrentIndex(dlg.place_combo.findData('outside'))
    assert prefs[PREF_KEY]['height_cm'] == 7.5 and prefs[PREF_KEY]['legend'] == 'bottom'
    assert prefs[PREF_KEY]['legend_place'] == 'outside'
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(tmp_path / 'printed.pdf'))
    assert dlg.print_figure(printer)
    assert os.path.getsize(tmp_path / 'printed.pdf') > 1000


def _box(copy, artist):
    copy.draw_without_rendering()
    return artist.get_window_extent()


@pytest.mark.parametrize('position', ['right', 'upper right', 'left', 'top', 'bottom'])
def test_legend_outside_the_plot(position):
    """Outside: beside, above or below the plot and its labels, all in the picture."""
    from src.modules.visualization import publication_figure as pf
    copy = pf.copy_for_publication(_figure(), 8.5, 6.5, 8, 1.0, legend=position,
                                   legend_place='outside')
    ax = copy.axes[0]
    leg = ax.get_legend()
    lb, frame = _box(copy, leg), ax.bbox
    fig = copy.bbox
    assert lb.x0 >= -1 and lb.x1 <= fig.x1 + 1 and lb.y0 >= -1 and lb.y1 <= fig.y1 + 1
    if 'right' in position:
        assert lb.x0 > frame.x1
    elif position == 'left':
        numbers = ax.yaxis.get_tightbbox(copy._get_renderer()).x0
        assert lb.x1 < numbers                           # left of the y axis' numbers
    elif position == 'top':
        assert lb.y0 > ax.title.get_window_extent().y1 - 1
    else:
        assert lb.y1 < ax.xaxis.label.get_window_extent().y0 + 1


def test_legend_inside_corners_and_the_old_choices():
    from src.modules.visualization import publication_figure as pf
    copy = pf.copy_for_publication(_figure(), 8.5, 6.5, 8, legend='lower left')
    ax = copy.axes[0]
    lb, frame = _box(copy, ax.get_legend()), ax.bbox
    assert frame.x0 <= lb.x0 < frame.x0 + 20 and frame.y0 <= lb.y0 < frame.y0 + 20
    assert pf.legend_choice('inside') == ('best', 'inside')
    assert pf.legend_choice('right') == ('right', 'outside')
    assert pf.legend_choice('below') == ('bottom', 'outside')
    assert pf.legend_choice('best', 'outside') == ('best', 'inside')


def test_moving_the_legend_with_the_mouse():
    """The legend dragged in the preview: in the saved picture it is where it was dropped."""
    from src.modules.visualization import publication_figure as pf
    fig = _figure()
    _, boxes = pf.render(fig, 8.5, 6.5, 100, font_pt=8)
    i, box, frame = boxes[0]
    xy = pf.moved_legend(box, frame, -60, 40)              # 60 px left, 40 px down
    _, moved = pf.render(fig, 8.5, 6.5, 100, font_pt=8, legend_xy={i: xy})
    assert moved[0][1][0] == pytest.approx(box[0] - 60, abs=2)
    assert moved[0][1][3] == pytest.approx(box[3] + 40, abs=2)


def test_the_window_moves_the_legend_and_restores_defaults():
    from src.views.dialogs.visualization.publication_dialog import PREF_KEY, PublicationDialog

    class Prefs(dict):
        def set(self, k, v):
            self[k] = v
    prefs = Prefs()
    dlg = PublicationDialog(_figure(), preferences=prefs)
    assert dlg.windowFlags() & Qt.WindowMaximizeButtonHint
    assert not dlg.place_combo.isEnabled()                       # Best place: inside
    dlg._update_preview()
    assert dlg.preview.boxes
    dlg.preview.legend_moved.emit(0, -30.0, 20.0)
    assert 0 in dlg.legend_xy
    dlg.legend_combo.setCurrentIndex(dlg.legend_combo.findData('top'))
    assert dlg.legend_xy == {} and dlg.place_combo.isEnabled()  # a chosen place again
    k = dlg.column_combo.findText('A4 page, sideways', Qt.MatchStartsWith)
    dlg.column_combo.setCurrentIndex(k)
    assert (dlg.width_spin.value(), dlg.height_spin.value()) == (26.7, 18.0)
    dlg.font_spin.setValue(14)
    dlg.restore_defaults()
    s = dlg.settings()
    for key, value in pf_defaults().items():
        assert s[key] == value, key
    assert prefs[PREF_KEY]['width_cm'] == 8.5 and dlg.column_combo.currentIndex() == 0


def pf_defaults():
    from src.modules.visualization import publication_figure as pf
    return pf.DEFAULTS


def test_without_the_mouse_cursor_and_with_short_titles():
    """The cursor that follows the mouse is not in the picture (pinned ones are);
    short names also in titles (Grid plot)."""
    from src.modules.visualization import publication_figure as pf
    fig = _figure()
    ax = fig.axes[0]
    ax.set_title('file : sp001')
    ax.annotate('x = 2\nfile : sp001: 4', xy=(2, 0.9), gid=pf.CURSOR_GID)
    ax.axvline(2, gid=pf.CURSOR_GID)
    ax.axvline(1.5, gid=pf.CURSOR_GID + '_pinned')
    copy = pf.copy_for_publication(fig, 8.5, 6.5, 8)
    gids = [a.get_gid() for a in copy.axes[0].get_children()]
    assert pf.CURSOR_GID not in gids and pf.CURSOR_GID + '_pinned' in gids
    assert copy.axes[0].get_title() == 'sp001'


def test_printing_fit_to_page_grey_caption_and_preview(tmp_path):
    from PyQt5.QtPrintSupport import QPrinter
    from src.modules.visualization import publication_figure as pf
    from src.views.dialogs.visualization.publication_dialog import PublicationDialog
    # A4 printable part at 100 dots per cm: 8.5 x 6.5 cm fitted / actual / top left
    x, y, w, h = pf.print_place(1800, 2670, 850, 650, fit=True, centre=True)
    assert w == pytest.approx(1800) and h == pytest.approx(650 * 1800 / 850)
    assert y == pytest.approx((2670 - h) / 2)
    assert pf.print_place(1800, 2670, 850, 650, fit=False, centre=False) == (0, 0, 850, 650)
    assert pf.print_place(1800, 2670, 850, 650, fit=False)[2] == 850
    assert pf.print_place(1800, 2670, 3000, 650, fit=False)[2] == pytest.approx(1800)
    dlg = PublicationDialog(_figure())
    dlg.grey_check.setChecked(True)
    dlg.caption_edit.setText('Sample A, 6 Nov 2026')
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(tmp_path / 'fit.pdf'))
    assert dlg.paint_page(printer)
    assert os.path.getsize(tmp_path / 'fit.pdf') > 1000
    from PyQt5.QtGui import QPageLayout
    assert dlg._new_printer().pageLayout().orientation() == QPageLayout.Landscape   # wide
    preview = dlg.print_preview(run=False)
    assert preview.windowFlags() & Qt.WindowMaximizeButtonHint
    preview.deleteLater()


def test_print_preview_opens_and_closes():
    """Print preview: opened (exec), drawn, closed - without a crash (the
    printer was deleted while the preview used it)."""
    import gc
    from PyQt5.QtCore import QTimer
    from src.views.dialogs.visualization.publication_dialog import PublicationDialog
    dlg = PublicationDialog(_figure())
    drawn = []
    original = dlg.paint_page
    dlg.paint_page = lambda printer: drawn.append(original(printer))

    def close():
        gc.collect()
        app.activeModalWidget().reject()
    QTimer.singleShot(800, close)
    gc.collect()
    dlg.print_preview()
    assert drawn and drawn[0]
