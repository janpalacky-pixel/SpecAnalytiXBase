"""Help > Quick reference: one printable page with the mouse, the keys and
the right-click menus. It names shortcuts and menu items of the program, so
these tests make sure they are the program's own: a key combination is in
keyboard_shortcuts.SHORTCUTS, a menu item is in the right-click menus (made
by the program here, not read from its source), an option is in Basic plot
options - when one of them changes, the page has to change too."""
import os
import re
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QCheckBox, QMenu, QMessageBox

from src.help import quick_reference_help as qr
from src.modules.misc import keyboard_shortcuts as ks

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')

PLOT_MENU = ["Copy plot to clipboard", "Save plot for publication…", "Copy the data in view",
             "Label the band here", "Add text here…", "Add an arrow here…",
             "Labels on the plot…", "Open in New Window", "Data table…", "Peak list…",
             "Detect Peaks", "Show all spectra", "Add a band marker here",
             "Copy the values at the band markers", "Copy the values between the band markers",
             "Zoom to the band markers", "Scale each spectrum to 1 at the band marker",
             "Remove the band marker", "Band markers…"]
LIST_MENU = ["Rename", "Spectrum properties…", "Plot Properties…", "Line colours…",
             "Order", "Select spectra"]
OPTIONS = ["Cursor", "keep zoom", "scale each", "reverse x"]
PLOT_TYPES = ["Overlay", "Grid", "Waterfall", "Mean ± SD", "Difference", "Heatmap"]


def _pump(seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


def _page_text():
    html = qr.get_quick_reference_help_content()
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).replace('&#42;', '*')


def test_the_page_is_in_the_help_and_the_help_menu():
    from src.help import help_window
    assert 'quick_reference' in help_window._REGISTRY
    html = qr.get_quick_reference_help_content()
    from src.version import __version__
    assert __version__ in html and '@media print' in html and 'size: A4 landscape' in html
    for link in re.findall(r'href="help://([a-z_]+)(?:#([^"]+))?"', html):
        assert link[0] in help_window._REGISTRY


def test_every_key_combination_is_a_shortcut_of_the_program():
    known = {k.strip() for _w, keys, _t in ks.SHORTCUTS for k in keys.split('/')}
    written = qr.key_combinations()
    assert written, "the page names no shortcuts?"
    assert written - known == set(), "on the Quick reference but not in keyboard_shortcuts.py"


def test_the_names_used_by_these_tests_are_on_the_page():
    text = _page_text()
    for name in PLOT_MENU + LIST_MENU + OPTIONS + PLOT_TYPES:
        assert name in text, name


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for n in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, [DATA], [{}])))
    from src.controllers.core.main_controller import MainController
    ctrl = MainController()
    ctrl.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    ctrl.spectrum_selector.select_all_items()
    _pump()
    yield ctrl
    ctrl.autosave_controller.shutdown()
    ctrl.view.deleteLater()


def _menu(monkeypatch, run):
    """The texts of a menu (and its submenus) that run() opens."""
    texts = []

    def fake_exec(menu, *a, **k):
        def walk(m):
            for act in m.actions():
                texts.append(act.text().split('\t')[0])
                if act.menu() is not None:
                    walk(act.menu())
        walk(menu)
        return None
    monkeypatch.setattr(QMenu, 'exec_', fake_exec)
    monkeypatch.setattr(QMenu, 'exec', fake_exec)
    run()
    return texts


def _right_click(mc, x):
    from matplotlib.backend_bases import MouseEvent
    canvas = mc.static_canvas
    ax = canvas.figure.axes[0]
    canvas.draw()
    px, py = ax.transData.transform((x, np.mean(ax.get_ylim())))
    mc.handle_mouse_click(MouseEvent('button_press_event', canvas, px, py, button=3))


def test_every_menu_item_and_option_is_in_the_program(mc, monkeypatch):
    markers = mc.band_markers()
    markers.add_at(1480.0)
    markers.add_at(1500.0)
    first = mc.selected_spectra[0]['label']
    mc.plot_mouse_controller.toggle(first)              # hidden: "Show all spectra" offered
    _pump()
    shown = (_menu(monkeypatch, lambda: _right_click(mc, 1490.0))      # between two markers
             + _menu(monkeypatch, lambda: _right_click(mc, 1500.0)))   # on a marker
    missing = [n for n in PLOT_MENU if not any(t.startswith(n) for t in shown)]
    assert missing == [], f"not in the plot's right-click menu: {missing}"

    from PyQt5.QtCore import QPoint
    listed = _menu(monkeypatch, lambda: mc.show_spectra_list_context_menu(QPoint(5, 5)))
    missing = [n for n in LIST_MENU if not any(t.startswith(n) for t in listed)]
    assert missing == [], f"not in the spectra list's right-click menu: {missing}"

    boxes = {b.text() for b in mc.view.findChildren(QCheckBox)}
    assert [o for o in OPTIONS if o not in boxes] == []
    combo = mc.view.comboBox_plot_type_choice
    types = [combo.itemText(i) for i in range(combo.count())]
    assert [t for t in PLOT_TYPES if not any(i.startswith(t) for i in types)] == []
