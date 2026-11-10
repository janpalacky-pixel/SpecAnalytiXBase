"""Save plot for publication / Print plot from a tool window (2D Map first):
the window of File > Save plot for publication opened with a copy of the
tool's plot; the tool's marks (the clicked pixel, the regions, the
reference pixels, a spectrum's shaded range) can each be left out; the plot
on the screen is never changed."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib
matplotlib.use('Agg')
import numpy as np
import pytest
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from PyQt5.QtWidgets import QApplication, QDialog, QMenu, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MAP = os.path.join(ROOT, 'resources', 'test_data', 'synthetic', 'group_stats_cell_map_demo.mat')

from src.modules.visualization import publication_figure as pf
from src.modules.visualization import publication_style as pst
from src.views import publication_actions as pa


def _visible(copy, gid):
    return [a.get_visible() for ax in copy.axes for a in ax.get_children()
            if getattr(a, 'get_gid', lambda: None)() == gid]


def test_marks_are_found_and_each_kind_can_be_left_out():
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.imshow(np.arange(12.0).reshape(3, 4))
    plus, = ax.plot(1, 1, 'w+')
    roi = ax.add_patch(Rectangle((0, 0), 2, 1, fill=False))
    copy = pa.figure_copy(fig, marks=[(plus, pst.MAP_PIXEL_GID), (roi, pst.MAP_ROI_GID)])
    assert plus.get_gid() is None and roi.get_gid() is None       # the screen: unchanged
    info = pst.current(copy)
    assert info['marks'] == [pst.MAP_PIXEL_GID, pst.MAP_ROI_GID]
    assert not info['has_lines']                                   # the + is not a spectrum
    style = dict(pst.STYLE_DEFAULTS, map_rois='off')
    out = pf.copy_for_publication(copy, 8.5, 7, font_pt=7, style=style)
    assert _visible(out, pst.MAP_PIXEL_GID) == [True]
    assert _visible(out, pst.MAP_ROI_GID) == [False]
    out = pf.copy_for_publication(copy, 8.5, 7, font_pt=7,
                                  style=dict(style, map_pixel='off'))
    assert _visible(out, pst.MAP_PIXEL_GID) == [False]


def test_figure_copy_names_lines_and_leaves_out_the_tooltip():
    fig = Figure()
    ax = fig.add_subplot(111)
    line, = ax.plot([1, 2, 3], [1, 3, 2])
    tip = ax.annotate("x = 1", (1, 1))
    copy = pa.figure_copy(fig, names=[(line, 'raman_01')], hide=[tip])
    assert line.get_label().startswith('_') and tip.get_gid() is None   # screen as it was
    assert [s['label'] for s in pst.series(copy)] == ['raman_01']
    out = pf.copy_for_publication(copy, 8.5, 7)
    assert not any(t.get_text() == "x = 1" for t in out.axes[0].texts)


def test_the_window_shows_the_marks_and_opens_on_printing():
    from src.views.dialogs.visualization.publication_dialog import PublicationDialog
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.imshow(np.ones((3, 3)))
    plus, = ax.plot(1, 1, 'w+')
    copy = pa.figure_copy(fig, marks=[(plus, pst.MAP_PIXEL_GID)])
    dlg = PublicationDialog(copy, None, title="Save plot for publication – 2D map",
                            tab="Printing")
    tabs = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert 'Labels' in tabs and 'Heatmap' in tabs and 'Lines' not in tabs
    assert dlg.tabs.tabText(dlg.tabs.currentIndex()) == 'Printing'
    assert list(dlg.mark_combos) == ['map_pixel']
    dlg.mark_combos['map_pixel'].setCurrentIndex(1)                 # left out
    assert dlg._choices()['style']['map_pixel'] == 'off'
    assert dlg.windowTitle().endswith('2D map')
    dlg.deleteLater()


# ------------------------------------------------------------------ 2D Map
@pytest.fixture
def map_dialog(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.modules.core.spectrum_manager import SpectrumManager
    from src.controllers.visualization_analysis.map2d_controller import Map2DController
    from src.views.dialogs.visualization_analysis.map2d_dialog import Map2DDialog
    m = SpectrumManager()
    m.load_spectrum_from_file(MAP)
    spectra = [{'label': l, 'x_scale': s.x_scale, 'y_scale': s.y_scale, 'metadata': s.metadata}
               for l, s in m.spectra.items()]

    class _Main:
        view = None
    dlg = Map2DDialog(None, Map2DController(_Main()), spectra)
    dlg.resize(1200, 800)
    dlg.show()
    app.processEvents()
    yield dlg
    dlg.close()
    dlg.deleteLater()


def _map_with_marks(dlg):
    dlg._radio_intensity.setChecked(True)
    dlg._compute_map()
    app.processEvents()

    class Click:
        button, dblclick = 1, False
    Click.inaxes = dlg._map_canvas.ax
    Click.xdata, Click.ydata = 5.0, 4.0
    dlg._on_map_click(Click())
    app.processEvents()
    rect = Rectangle((2, 2), 4, 3, fill=False, edgecolor='white', linestyle='--')
    dlg._map_canvas.ax.add_patch(rect)
    dlg._roi_regions.append({'type': 'rect', 'bounds': (2, 5, 2, 6), 'labels': [],
                             'spectra': [], 'patch': rect})
    return rect


def test_2d_map_toolbar_buttons(map_dialog):
    for tb in (map_dialog._map_toolbar, map_dialog._spectrum_toolbar):
        names = [a.objectName() for a in tb.actions()]
        assert 'publicationButton' in names


def test_2d_map_copies(map_dialog):
    rect = _map_with_marks(map_dialog)
    copy = map_dialog.map_figure_copy()
    assert pst.current(copy)['marks'] == [pst.MAP_PIXEL_GID, pst.MAP_ROI_GID]
    assert pst.current(copy)['has_colours']
    assert rect.get_gid() is None and map_dialog._map_canvas._crosshair.get_gid() is None
    spec = map_dialog.spectrum_figure_copy()
    info = pst.current(spec)
    assert info['has_lines'] and info['marks'] == [pst.RANGE_GID]
    assert pst.series(spec)[0]['label']                              # named for the Lines tab
    from matplotlib.colors import to_hex
    assert to_hex(spec.axes[0].get_facecolor()) == '#ffffff'
    # both can be made into pictures
    for c in (copy, spec):
        assert pf.render(c, 8.5, 7, 60, font_pt=7) is not None


def test_2d_map_opens_the_window(map_dialog, monkeypatch):
    from src.views.dialogs.visualization.publication_dialog import PublicationDialog
    opened = []
    monkeypatch.setattr(PublicationDialog, 'exec_',
                        lambda self: opened.append((self.windowTitle(),
                                                    self.tabs.tabText(self.tabs.currentIndex())))
                        or QDialog.Rejected)
    shown = []
    monkeypatch.setattr(QMessageBox, 'information',
                        staticmethod(lambda *a, **k: shown.append(a[1]) or QMessageBox.Ok))
    map_dialog._map_canvas._draw_stale()        # "Settings changed - click Update Map"
    assert map_dialog.save_map_for_publication() is None             # no map: a message
    assert shown == ["No map"]
    _map_with_marks(map_dialog)
    assert map_dialog.save_map_for_publication() is not None
    assert map_dialog.save_spectrum_for_publication(print_first=True) is not None
    assert opened[0][0].endswith('2D map') and opened[0][1] == 'Page'
    assert opened[1][0].startswith('Print plot') and opened[1][1] == 'Printing'


def test_2d_map_right_click_menu(map_dialog, monkeypatch):
    _map_with_marks(map_dialog)
    monkeypatch.setattr(QMenu, 'exec_', lambda self, *a: None)
    for canvas, what in ((map_dialog._map_canvas, 'map'),
                         (map_dialog._spectrum_canvas, 'spectrum')):
        monkeypatch.setattr(QApplication, 'widgetAt', staticmethod(lambda *a: canvas))
        map_dialog._show_right_panel_menu(canvas.rect().center())
        texts = [a.text() for a in map_dialog._last_context_menu.actions()]
        assert pa.SAVE_TEXT in texts and pa.PRINT_TEXT in texts, what
        assert any('controls panel' in t for t in texts)
    monkeypatch.setattr(QApplication, 'widgetAt', staticmethod(lambda *a: None))
    map_dialog._show_right_panel_menu(map_dialog.rect().center())
    texts = [a.text() for a in map_dialog._last_context_menu.actions()]
    assert pa.SAVE_TEXT not in texts                                 # on the controls: only that


def test_2d_map_drawing_tools_are_never_in_the_picture(map_dialog):
    """The rectangle / ellipse being drawn (with its handles) and the lasso
    are left out - also after the tool is switched off (they can stay on
    the axes); the dashed outlines of the regions are what can be kept."""
    _map_with_marks(map_dialog)
    map_dialog._activate_roi()
    sel = map_dialog._roi_selector
    sel.extents = (2.0, 6.0, 2.0, 5.0)                   # a rectangle being drawn
    sel.set_visible(True)
    tool = set(map(id, sel.artists))
    assert tool and all(id(a) in map(id, map_dialog._selector_artists) for a in sel.artists)
    map_dialog._deactivate_roi()                          # switched off: may stay drawn
    copy = map_dialog.map_figure_copy()
    out = pf.copy_for_publication(copy, 8.5, 7, font_pt=7, style=dict(pst.STYLE_DEFAULTS))
    ax = out.axes[0]
    # in the picture: the map, the + and the dashed region - nothing of the tool
    kinds = sorted(type(a).__name__ for a in ax.patches if a.get_visible())
    assert kinds == ['Rectangle'], kinds                  # only the region's outline
    assert [g for g in (a.get_gid() for a in ax.patches)] == [pst.MAP_ROI_GID]
    handles = [l for l in ax.get_lines() if l.get_visible() and l.get_gid() != pst.MAP_PIXEL_GID]
    assert handles == []
    assert all(a.get_gid() is None for a in sel.artists)  # the screen's artists untouched
