"""Save plot for publication: a copy in a journal's column width, one text
size, lines at least so thick, at the chosen dpi - the plot on the screen
unchanged; the window remembers the choices."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _fresh_session():
    """Each test starts as the program does: the window's choices not kept."""
    from src.views.dialogs.visualization import publication_dialog
    publication_dialog._SESSION.clear()
    publication_dialog._SESSION_PANEL.clear()
    yield
    publication_dialog._SESSION.clear()
    publication_dialog._SESSION_PANEL.clear()


class _Pd:
    @property
    def _SESSION(self):
        from src.views.dialogs.visualization import publication_dialog
        return publication_dialog._SESSION


pd = _Pd()


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
    assert path and os.path.exists(path) and pd._SESSION['dpi'] == 300
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
    assert pd._SESSION['height_cm'] == 7.5 and pd._SESSION['legend'] == 'bottom'
    assert pd._SESSION['legend_place'] == 'outside'
    from src.modules.utils.app_logger import crash_watch_paused
    with crash_watch_paused():        # Windows: no harmless printer errors in the log
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
    assert pd._SESSION['width_cm'] == 8.5 and dlg.column_combo.currentIndex() == 0


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
    from src.modules.utils.app_logger import crash_watch_paused
    with crash_watch_paused():        # Windows: no harmless printer errors in the log
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


# ---------------------------------------------------------------- the look (publication_style)
def test_style_axes_titles_ranges_ticks_frame():
    from matplotlib.ticker import AutoMinorLocator, MultipleLocator
    from src.modules.visualization import publication_figure as pf
    fig = _figure()
    style = dict(x_title='Raman shift', y_title='Counts', x_min=1.5, x_max=2.5, x_step=0.25,
                 minor_ticks='on', tick_dir='in', mirror_ticks='on', frame='open', frame_pt=1.5,
                 x_dir='decreasing', title_mode='hide', font_family='DejaVu Serif')
    copy = pf.copy_for_publication(fig, 8.5, 6.5, 8, 1.0, style=style)
    ax = copy.axes[0]
    assert ax.get_xlabel() == 'Raman shift' and ax.get_ylabel() == 'Counts'
    assert ax.get_title() == '' and ax.xaxis_inverted()
    assert sorted(ax.get_xlim()) == [1.5, 2.5]
    assert isinstance(ax.xaxis.get_major_locator(), MultipleLocator)
    assert isinstance(ax.xaxis.get_minor_locator(), AutoMinorLocator)
    assert not ax.spines['top'].get_visible() and ax.spines['left'].get_linewidth() == 1.5
    assert ax.xaxis.label.get_fontfamily()[0] == 'DejaVu Serif'
    assert fig.axes[0].get_xlabel() == 'Wavenumber' and fig.axes[0].get_title() == 'Spectra'


def test_style_lines_colours_points_and_each_spectrum():
    from matplotlib.colors import to_hex
    from src.modules.visualization import publication_figure as pf
    from src.modules.visualization import publication_style as pst
    fig = _figure()
    assert [s['label'] for s in pst.series(fig)] == ['file : sp001', 'file : sp002']
    copy = pf.copy_for_publication(fig, 8.5, 6.5, 8, 1.0, style=dict(
        palette='okabe_ito', plot_as='points', marker='s', marker_every=5,
        series=[{'name': 'first', 'width': 3.0}, {'show': False}]))
    a, b = copy.axes[0].get_lines()[:2]
    assert to_hex(a.get_color()) == pst.OKABE_ITO[0] and a.get_linestyle() == 'None'
    assert a.get_marker() == 's' and a.get_markevery() == 5 and a.get_linewidth() == 3.0
    assert not b.get_visible()
    assert [t.get_text() for t in copy.axes[0].get_legend().get_texts()] == ['first']
    black = pf.copy_for_publication(fig, 8.5, 6.5, style=dict(palette='black_styles'))
    lines = black.axes[0].get_lines()[:2]
    assert [to_hex(l.get_color()) for l in lines] == ['#000000', '#000000']
    assert [l.get_linestyle() for l in lines] == ['-', '--']
    leg = black.axes[0].get_legend()
    assert to_hex(leg.legend_handles[0].get_color()) == '#000000'    # the legend follows


def test_style_grid_legend_extras_and_heatmap():
    import numpy as np
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    from src.modules.visualization import publication_figure as pf
    copy = pf.copy_for_publication(_figure(), 8.5, 6.5, 8, style=dict(
        grid='off', legend_ncol=2, legend_frame='off', legend_title='Samples'))
    ax = copy.axes[0]
    assert not any(g.get_visible() for g in ax.get_xgridlines())
    leg = ax.get_legend()
    assert leg._ncols == 2 and not leg.get_frame_on() and leg.get_title().get_text() == 'Samples'
    fig = Figure(figsize=(8, 5))
    FigureCanvasQTAgg(fig)
    hax = fig.add_subplot()
    im = hax.imshow(np.arange(20.0).reshape(4, 5), aspect='auto')
    fig.colorbar(im, ax=hax, label='I')
    heat = pf.copy_for_publication(fig, 8.5, 6.5, 8, style=dict(
        cmap='magma', c_min=5, c_max=15, cbar_label='Counts'))
    image = heat.axes[0].images[0]
    assert image.get_cmap().name == 'magma' and image.get_clim() == (5, 15)
    bar = next(a for a in heat.axes if hasattr(a, '_colorbar'))
    assert bar.get_ylabel() == 'Counts' and bar._colorbar.cmap.name == 'magma'


def test_style_several_plots():
    """Grid plot: the x title where the plots have one, one title above all."""
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    from src.modules.visualization import publication_figure as pf
    fig = Figure(figsize=(10, 6))
    FigureCanvasQTAgg(fig)
    axs = fig.subplots(2, 2, sharex=True)
    for k, ax in enumerate(axs.flat):
        ax.plot([1, 2, 3], [k, k + 1, k], label=f'f : s{k}')
        ax.set_title(f'f : s{k}')
        if k >= 2:
            ax.set_xlabel('x')
    copy = pf.copy_for_publication(fig, 17.5, 10, 8, style=dict(
        x_title='Shift', title_mode='own', title_text='Four'))
    assert [a.get_xlabel() for a in copy.axes] == ['', '', 'Shift', 'Shift']
    assert copy._suptitle.get_text() == 'Four' and copy.axes[0].get_title() == 's0'


def _prefs():
    class Prefs(dict):
        def set(self, k, v):
            self[k] = v

        def remove(self, *keys):
            for k in keys:
                self.pop(k, None)
    return Prefs()


def test_the_window_profiles_and_what_is_kept():
    """A profile keeps everything (also titles and the spectra's colours) and
    brings it back; without a profile only the general look is kept."""
    from src.views.dialogs.visualization.publication_dialog import (PREF_KEY, PROFILES_KEY,
                                                                    PublicationDialog)
    prefs = _prefs()
    dlg = PublicationDialog(_figure(), preferences=prefs)
    dlg.x_title_edit.setText('Shift')
    dlg.palette_combo.setCurrentIndex(dlg.palette_combo.findData('greys'))
    dlg._row_widgets[1]['color'].set_colour('#ff0000', quiet=False)
    dlg._row_widgets[0]['show'].setChecked(False)
    assert dlg.series_rows == [{'show': False}, {'color': '#ff0000'}]
    assert dlg._choices()['style']['series'][1]['color'] == '#ff0000'
    assert dlg.save_profile('Journal X') == 'Journal X'
    assert prefs[PROFILES_KEY]['Journal X']['x_title'] == 'Shift'
    assert 'x_title' not in pd._SESSION and pd._SESSION['palette'] == 'greys'
    assert set(prefs.get(PREF_KEY, {})) <= {'panel_width'}    # nothing else kept for good
    dlg.restore_defaults()
    assert dlg.x_title_edit.text() == '' and dlg.series_rows == []
    assert dlg.palette_combo.currentData() == 'keep'
    again = PublicationDialog(_figure(), preferences=prefs)
    assert again.palette_combo.currentData() == 'keep'        # defaults were kept last
    assert again.apply_profile('Journal X')
    assert again.x_title_edit.text() == 'Shift' and again.palette_combo.currentData() == 'greys'
    assert again._row_widgets[1]['color'].colour() == '#ff0000'
    assert not again._row_widgets[0]['show'].isChecked()
    assert again.delete_profile('Journal X') and PROFILES_KEY in prefs
    assert prefs[PROFILES_KEY] == {}


def test_page_orientation_and_the_quiet_crash_watcher():
    import faulthandler
    from PyQt5.QtGui import QPageLayout
    from src.modules.utils.app_logger import crash_watch_paused
    from src.views.dialogs.visualization.publication_dialog import PublicationDialog
    dlg = PublicationDialog(_figure())
    assert dlg._new_printer().pageLayout().orientation() == QPageLayout.Landscape  # wide: auto
    dlg.orientation_combo.setCurrentIndex(dlg.orientation_combo.findData('portrait'))
    assert dlg._new_printer().pageLayout().orientation() == QPageLayout.Portrait
    was = faulthandler.is_enabled()
    faulthandler.enable()
    try:
        with crash_watch_paused():
            assert not faulthandler.is_enabled()
        assert faulthandler.is_enabled()
    finally:
        if not was:
            faulthandler.disable()


def test_the_splitter_between_the_settings_and_the_preview():
    """The bar's place is kept while the program runs; a new start: its first place;
    nothing stored for good."""
    from src.views.dialogs.visualization import publication_dialog as module
    prefs = _prefs()
    prefs['publication_figure'] = {'panel_width': 900}           # stored by an older version
    dlg = module.PublicationDialog(_figure(), preferences=prefs)
    assert 'publication_figure' not in prefs                     # cleaned away
    dlg.resize(1300, 780)
    dlg.show()
    app.processEvents()
    assert dlg.splitter.count() == 2 and not dlg.splitter.childrenCollapsible()
    dlg.splitter.setSizes([800, 480])
    dlg._splitter_moved()
    again = module.PublicationDialog(_figure(), preferences=prefs)
    again.resize(1300, 780)
    again.show()
    app.processEvents()
    assert abs(again.splitter.sizes()[0] - 800) <= 40
    module._SESSION_PANEL.clear()                                # the program started again
    fresh = module.PublicationDialog(_figure(), preferences=prefs)
    fresh.resize(1300, 780)
    fresh.show()
    app.processEvents()
    assert abs(fresh.splitter.sizes()[0] - 660) <= 40 and prefs == {}
    for w in (dlg, again, fresh):
        w.close()


def _figure_with_labels():
    """The test plot with two band markers and a pinned cursor."""
    from src.modules.visualization.band_marker_manager import BandMarkerManager
    fig = _figure()
    ax = fig.axes[0]
    bm = BandMarkerManager()
    bm.add(1.5, 'band A')
    bm.add(2.5, 'band B', orientation='horizontal')
    bm.apply_to_axes(ax)
    ax.axvline(2.0, gid='sax_cursor_pinned')
    ax.text(2.0, 1.0, '2', transform=ax.get_xaxis_transform(), gid='sax_cursor_pinned')
    return fig


def test_text_sizes_numbers_and_band_markers():
    from src.modules.visualization import publication_figure as pf
    from src.modules.visualization import publication_style as pst
    fig = _figure_with_labels()
    info = pst.current(fig)
    assert info['has_bands'] and info['has_cursors'] and info['has_legend']
    copy = pf.copy_for_publication(fig, 8.5, 6.5, 8, style=dict(
        axis_title_pt=11, tick_pt=6, legend_pt=5, title_pt=14, band_pt=4.5, cursor_pt=5.5,
        y_numbers='off', band_rotation='horizontal', band_lines='off', cursors='off'))
    ax = copy.axes[0]
    assert ax.xaxis.label.get_fontsize() == 11 and ax.title.get_fontsize() == 14
    assert ax.get_xticklabels()[0].get_fontsize() == 6
    assert ax.get_legend().get_texts()[0].get_fontsize() == 5
    assert not ax.yaxis.get_tick_params()['labelleft']
    bands = [t for t in ax.texts if t.get_gid() == 'sax_band']
    assert len(bands) == 2 and all(t.get_rotation() == 0 and t.get_fontsize() == 4.5
                                   for t in bands)
    assert not any(l.get_visible() for l in ax.get_lines() if l.get_gid() == 'sax_band')
    assert not any(a.get_visible() for a in ax.texts + ax.get_lines()
                   if a.get_gid() == 'sax_cursor_pinned')
    plain = pf.copy_for_publication(fig, 8.5, 6.5, 8)                 # as in the plot
    assert plain.axes[0].title.get_fontsize() == 9                   # Text size + 1


def test_dragging_a_title_or_label_in_the_preview():
    from src.modules.visualization import publication_figure as pf
    fig = _figure_with_labels()
    _, boxes = pf.render(fig, 8.5, 6.5, 100, font_pt=8)
    keys = [b[0] for b in boxes]
    assert 0 in keys and 'title:0' in keys and 'band:0:0' in keys and 'pinned:0:0' in keys
    box = dict((b[0], b[1]) for b in boxes)
    _, after = pf.render(fig, 8.5, 6.5, 100, font_pt=8,
                         moved={'title:0': (36.0, -18.0), 'band:0:1': (-72.0, 0.0)})
    moved = dict((b[0], b[1]) for b in after)
    assert moved['title:0'][0] == pytest.approx(box['title:0'][0] + 50, abs=2)   # 36 pt
    assert moved['title:0'][1] == pytest.approx(box['title:0'][1] + 25, abs=2)   # y down
    assert moved['band:0:1'][0] == pytest.approx(box['band:0:1'][0] - 100, abs=2)


def test_the_window_tabs_drag_grey_and_undo():
    from src.views.dialogs.visualization.publication_dialog import PublicationDialog
    dlg = PublicationDialog(_figure_with_labels())
    tabs = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert tabs == ['Page', 'Text', 'Axes', 'Lines', 'Legend', 'Labels', 'Printing']
    plain = PublicationDialog(_figure())
    assert 'Labels' not in [plain.tabs.tabText(i) for i in range(plain.tabs.count())]
    dlg._update_preview()
    dlg._render_dpi = 72.0
    dlg.preview.text_moved.emit('title:0', 10.0, 20.0)                # pixels, y down
    assert dlg.moved == {'title:0': (10.0, -20.0)}                    # points, y up
    dlg._record()
    dlg.size_spins['tick_pt'].setValue(5)
    dlg._record()
    assert dlg.undo() and dlg.size_spins['tick_pt'].value() == 0     # the size undone
    assert dlg.moved == {'title:0': (10.0, -20.0)}
    assert dlg.undo() and dlg.moved == {}                              # the drag undone
    assert dlg.redo() and dlg.moved == {'title:0': (10.0, -20.0)}
    assert dlg.redo() and dlg.size_spins['tick_pt'].value() == 5
    assert not dlg.redo()
    dlg.grey_check.setChecked(True)
    dlg._update_preview()
    image = dlg.preview.pixmap().toImage()
    assert image.isGrayscale()


def test_each_start_begins_as_in_the_plot():
    """The choices are kept while the program runs, not after a restart (a new
    start = an empty session); only the bar's place is stored for good."""
    from src.views.dialogs.visualization import publication_dialog as module
    prefs = _prefs()
    dlg = module.PublicationDialog(_figure(), preferences=prefs)
    dlg.palette_combo.setCurrentIndex(dlg.palette_combo.findData('greys'))
    again = module.PublicationDialog(_figure(), preferences=prefs)
    assert again.palette_combo.currentData() == 'greys'          # the same run: kept
    module._SESSION.clear()                                       # the program started again
    fresh = module.PublicationDialog(_figure(), preferences=prefs)
    assert fresh.palette_combo.currentData() == 'keep'
    assert set(prefs.get(module.PREF_KEY, {})) <= {'panel_width'}


def test_short_names_of_spectra_from_several_files():
    """raman_01 in two files: the files told apart by what differs in their names."""
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    from src.modules.visualization import publication_figure as pf
    fig = Figure()
    FigureCanvasQTAgg(fig)
    ax = fig.add_subplot()
    for f in ('raman_2comp_clean', 'raman_2comp_noisy'):
        for k in ('raman_01', 'raman_02'):
            ax.plot([1, 2], [1, 2], label=f'{f} : {k}')
    ax.legend()
    copy = pf.copy_for_publication(fig, 8.5, 6.5, 7)
    assert [t.get_text() for t in copy.axes[0].get_legend().get_texts()] == [
        'clean : raman_01', 'clean : raman_02', 'noisy : raman_01', 'noisy : raman_02']


def test_restore_defaults_puts_back_everything():
    """Every choice of every tab, the table of spectra, dragged legends /
    titles, the caption - all as at first; the window cannot be minimized."""
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit, QSpinBox
    from src.views.dialogs.visualization import publication_dialog as module
    dlg = module.PublicationDialog(_figure_with_labels())
    assert dlg.windowFlags() & Qt.WindowMaximizeButtonHint
    assert not dlg.windowFlags() & Qt.WindowMinimizeButtonHint
    first = dlg.settings()
    for key, (get, set_) in dlg._fields.items():         # change every single choice
        value = get()
        if isinstance(value, bool):
            set_(not value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            set_(value + 1)
        elif isinstance(value, str) and value.startswith('#'):
            set_('#123456')
        elif value is None or isinstance(value, str):
            set_(5.0 if key.endswith(('_min', '_max')) else 'x')
    for w in dlg.findChildren(QComboBox):                  # and every list: its last item
        if w.count() > 1 and w is not dlg.profile_combo:
            w.setCurrentIndex(w.count() - 1)
    dlg._row_widgets[0]['show'].setChecked(False)
    dlg.legend_xy = {0: (0.3, 0.3)}
    dlg.moved = {'title:0': (5.0, 5.0)}
    dlg.caption_edit.setText('caption')
    assert dlg.settings() != first
    dlg.restore_defaults()
    after = dlg.settings()
    defaults = module.all_defaults()
    for key, value in after.items():
        if key in defaults:
            assert value == defaults[key] or (key == 'legend' and value == 'best'), key
    assert after['series'] == [] and dlg.legend_xy == {} and dlg.moved == {}
    assert dlg.caption_edit.text() == ''
