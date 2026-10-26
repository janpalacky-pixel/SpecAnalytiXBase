"""Runs every step of the Group Statistics tutorial on the demo datasets,
prints the results (to check the numbers quoted in the tutorial) and saves
the window screenshots used by the tutorial help page.

Run from the repository root:
    python tools/help_pictures/make_group_statistics_tutorial_figures.py [--no-images]
"""
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)                     # the repository: paths below are relative to it
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools', 'help_pictures'))
import steady                      # the same picture every run (see steady.py)
steady.start()

from PyQt5.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])
from src.views import button_icons as _bi   # icons on the dialog buttons, as in the program
_bi.install(app)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

from src.modules.core.spectrum_manager import SpectrumManager
# as on a Full HD screen: a window opens as wide as its two sides need
# (splitter_utils.fit_panel), as for a user; the offscreen screen is smaller
from src.views.dialogs.misc import splitter_utils as _su
_su._available_width = lambda window: 1920
from src.views.dialogs.visualization_analysis.group_statistics_dialog import GroupStatisticsDialog
steady.park_mouse()

SYNTH = os.path.join('resources', 'test_data', 'synthetic')
OUT = os.path.join('resources', 'images', 'help_screenshots', 'group_statistics_tutorial')
IMAGES = '--no-images' not in sys.argv
os.makedirs(OUT, exist_ok=True)


_MAIN = []


def _main_controller():
    """One hidden main window: the demos are imported the way a user does it
    (File -> Import), so the spectra arrive in the order of the main spectra
    list (sorted by name) -- the pictures then show exactly what a user sees."""
    if not _MAIN:
        import tempfile
        os.environ.setdefault('SPECANALYTIXBASE_DATA_DIR', tempfile.mkdtemp())
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        QMessageBox.exec_ = lambda self: QMessageBox.Yes
        from src.views.dialogs.misc import import_dialog
        import_dialog.ImportDialog.run = staticmethod(
            lambda view, settings, file_paths=None: (True, list(file_paths),
                                                     [{} for _ in file_paths]))
        from src.controllers.core.main_controller import MainController
        _MAIN.append(MainController())
        steady.fixed_clock()
    return _MAIN[0]


def open_demo(name):
    mc = _main_controller()
    mc.import_controller._run_import(
        clear_first=True, file_paths=[os.path.abspath(os.path.join(SYNTH, name))])
    app.processEvents()
    mc.spectra_list_widget.selectAll()
    app.processEvents()
    spectra = mc.spectrum_selector.get_selected_spectra()
    d = GroupStatisticsDialog(spectra, None, {}, {})
    d.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    d.show()
    app.processEvents()
    fixed_layout(d)
    return d


# The same window size and the same room for the right side (value, test,
# results) in every run, whatever the fonts: the left side gets exactly what
# it needs, the right side RIGHT_WIDTH - so the pictures keep their size
# and an unchanged window gives the same picture.
WINDOW_WIDTH, WINDOW_HEIGHT, RIGHT_WIDTH = 1600, 940, 860   # the Help shows pictures up to 760 px wide


def fixed_layout(d):
    from PyQt5.QtWidgets import QSplitter
    from src.views.dialogs.misc import splitter_utils as su
    splitters = [s for s in d.findChildren(QSplitter) if s.count() == 2 and s.parentWidget() is not None]
    if not splitters:
        return
    spl = splitters[0]
    left = su.needed_width(spl.widget(0))
    d.resize(left + RIGHT_WIDTH + spl.handleWidth() + 30, d.height())
    app.processEvents()
    spl.setSizes([left, RIGHT_WIDTH])
    app.processEvents()


def shot(d, name, tab=None, whole=False, find=None, width=1000):
    """Screenshot of the right half of the window (value, test, results) or,
    with whole=True, of the whole window; find= scrolls the Test tab to a text."""
    from PyQt5.QtCore import Qt
    if tab is not None:
        d.tabs.setCurrentIndex(tab)
    app.processEvents()
    if find:
        d.tests_view.moveCursor(d.tests_view.textCursor().End)
        d.tests_view.find(find)
        d.tests_view.ensureCursorVisible()
        d.tests_view.textCursor().clearSelection()
        app.processEvents()
    if IMAGES:
        widget = d if whole else d.tabs.parentWidget()
        img = widget.grab().toImage()
        if img.width() > width:
            img = img.scaledToWidth(width, Qt.SmoothTransformation)
        img.save(os.path.join(OUT, name))


def two_bands(d, a, b, metric='Integral', op='A / B'):
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('ratio'))
    d.a_from.setValue(a[0]); d.a_to.setValue(a[1])
    d.b_from.setValue(b[0]); d.b_to.setValue(b[1])
    d.metric_a_combo.setCurrentText(metric); d.metric_b_combo.setCurrentText(metric)
    d.operation_combo.setCurrentText(op)


def one_band(d, kind, lo, hi):
    d.kind_combo.setCurrentIndex(d.kind_combo.findData(kind))
    d.a_from.setValue(lo); d.a_to.setValue(hi)


def test(d, method):
    d.test_combo.setCurrentIndex(d.test_combo.findData(method))


def report(title, d):
    r = d.comparison
    print(f"\n=== {title}\n  {r['test']}: p = {r['p']:.3g}  ({r.get('effect_name')} = {r.get('effect')})")
    for p in r.get('pairs') or []:
        print(f"    pair {p.get('a')} vs {p.get('b')}: p = {p.get('p_holm', p.get('p')):.3g}")
    if r.get('checks'):
        print('  normality', [(g, round(p, 4)) for g, n, p in r['checks']['normality']],
              'spread p', round(r['checks']['equal_spread_p'], 4))
        print('  advice', r['checks']['advice'])
    print('  outliers', r.get('outliers'))
    print('  sentence:', r.get('sentence'))
    print('  note:', d.note.text())
    print('  means:', {g: round(float(sum(v) / len(v)), 4) for g, v in d.data.items()})


def why_normalize_figure(path):
    """Lesson 1 picture: raw spectra hide the dose effect, the same spectra
    divided by their 1450 band show it (also the group means and the 1585 shift)."""
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    df = pd.read_excel(os.path.join(SYNTH, 'group_stats_treatment_demo.xlsx'), sheet_name='Spectra')
    x = df.iloc[:, 0].to_numpy(float)
    ref = (x >= 1420) & (x <= 1480)
    colors = {'control': '#1f77b4', 'low_dose': '#2ca02c', 'high_dose': '#d62728'}
    raw, norm, groups = {}, {}, {}
    for col in df.columns[1:]:
        y = df[col].to_numpy(float)
        g = col.rsplit('_', 1)[0]
        groups.setdefault(g, []).append(y / y[ref].max())
        if col.endswith('_01'):
            raw[col], norm[col] = y, y / y[ref].max()
    fig, ax = plt.subplots(2, 2, figsize=(13, 8.5))
    w = (x >= 1400) & (x <= 1720)
    for k in raw:
        c = colors[k.rsplit('_', 1)[0]]
        ax[0, 0].plot(x[w], raw[k][w], color=c, label=k)
        ax[0, 1].plot(x[w], norm[k][w], color=c, label=k)
    ax[0, 0].set_title('1) Raw spectra (as plotted in the main window)\n'
                       'high_dose_01 looks lowest - it was simply measured ~40 % weaker',
                       fontsize=10)
    ax[0, 1].set_title('2) The same 3 spectra divided by their 1450 band\n'
                       'now the 1655 band grows with the dose', fontsize=10)
    for a in ax[0]:
        a.axvline(1655, color='grey', ls=':')
        a.axvline(1450, color='grey', ls=':')
    w2 = (x >= 1600) & (x <= 1720)
    w3 = (x >= 1565) & (x <= 1605)
    for g, ys in groups.items():
        m = np.mean(ys, axis=0)
        ax[1, 0].plot(x[w2], m[w2], color=colors[g], lw=2,
                      label=f"{g.replace('_', ' ')} (mean of {len(ys)})")
        ax[1, 1].plot(x[w3], m[w3], color=colors[g], lw=2, label=g.replace('_', ' '))
    ax[1, 0].set_title('3) Mean of each group, divided by the 1450 band\n'
                       '1655 band: control < low dose < high dose', fontsize=10)
    ax[1, 1].set_title('4) Zoom on the 1585 band (group means)\nshifted to the right with '
                       'the dose: fitted 1584.9 -> 1585.6 -> 1586.4 cm-1', fontsize=10)
    for a in ax.flat:
        a.legend(fontsize=8)
        a.set_xlabel('Raman shift (cm-1)')
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)


if IMAGES:
    why_normalize_figure(os.path.join(OUT, 'l1_why_normalize.png'))

# --- Lesson 1: three treatment groups ------------------------------------------------
d = open_demo('group_stats_treatment_demo.xlsx')
print('L1 source:', d.table_source.text())
shot(d, 'l1_opened.png', whole=True, width=1100)
one_band(d, 'area', 1620, 1690); d.compute(); report('L1 area 1620-1690', d)
shot(d, 'l1_area.png', 0)
two_bands(d, (1620, 1690), (1420, 1480)); d.compute(); report('L1 ratio', d)
shot(d, 'l1_ratio.png', 0)
shot(d, 'l1_ratio_test.png', 2)
shot(d, 'l1_checks.png', 2, find='Checks of the test')
test(d, 'welch_gh'); d.compute(); report('L1 ratio, Welch + Games-Howell', d)
d.outliers_check.setChecked(True)
shot(d, 'l1_outliers.png', 0)
d.outliers_check.setChecked(False)
test(d, 'parametric')
one_band(d, 'fit_center', 1560, 1610); d.compute(); report('L1 fitted peak position', d)
d.kind_combo.setCurrentIndex(d.kind_combo.findData('pca')); d.component_spin.setValue(1)
d.whole_range_check.setChecked(False); d.compute(); report('L1 PCA score PC1', d)
d.component_spin.setValue(2); d.compute(); report('L1 PCA score PC2', d)
shot(d, 'l1_pc2.png', 0)
d.deleteLater()

# --- Lesson 2: skewed values ----------------------------------------------------------
d = open_demo('group_stats_skewed_demo.xlsx')
print('\nL2 source:', d.table_source.text())
two_bands(d, (1715, 1775), (1420, 1480), metric='Baseline-corrected integral')
d.compute(); report('L2 ratio, parametric', d)
d.plot_combo.setCurrentIndex(d.plot_combo.findData('violin'))
shot(d, 'l2_violin.png', 0)
shot(d, 'l2_checks.png', 2, find='Checks of the test')
d.plot_combo.setCurrentIndex(d.plot_combo.findData('box'))
test(d, 'nonparametric'); d.compute(); report('L2 ratio, Mann-Whitney', d)
test(d, 'parametric'); d.operation_combo.setCurrentText('log₂(A / B)'); d.compute()
report('L2 log2 ratio, parametric', d)
shot(d, 'l2_log.png', 0)
d.deleteLater()

# --- Lesson 3: cells with several pixels ---------------------------------------------
d = open_demo('group_stats_cells_samples_demo.xlsx')
print('\nL3 source:', d.table_source.text())
two_bands(d, (1620, 1690), (1420, 1480)); d.compute(); report('L3 per spectrum', d)
shot(d, 'l3_warning.png', 0)
d.per_sample_check.setChecked(True); d.compute(); report('L3 one value per sample', d)
shot(d, 'l3_per_sample.png', 0)
d.deleteLater()

# --- Lesson 4: paired ------------------------------------------------------------------
d = open_demo('group_stats_paired_demo.xlsx')
print('\nL4 source:', d.table_source.text())
one_band(d, 'max', 1630, 1680); d.compute(); report('L4 unpaired', d)
shot(d, 'l4_unpaired.png', 0)
test(d, 'paired_t'); d.compute(); report('L4 paired t', d)
shot(d, 'l4_paired_test.png', 2)
test(d, 'wilcoxon'); d.compute(); report('L4 Wilcoxon', d)
d.deleteLater()
MAIN = os.path.join('resources', 'images', 'help_screenshots', 'group_statistics')
os.makedirs(MAIN, exist_ok=True)


def save_img(widget, path, width=1000):
    from PyQt5.QtCore import Qt
    app.processEvents()
    if not IMAGES:
        return
    img = widget.grab().toImage()
    if img.width() > width:
        img = img.scaledToWidth(width, Qt.SmoothTransformation)
    img.save(path)


def spectra_tab(d, norm='none', band=(1420, 1480), rng=None):
    d.tabs.setCurrentIndex(4)
    d.sp_norm_combo.setCurrentIndex(d.sp_norm_combo.findData(norm))
    d.sp_band_from.setValue(band[0]); d.sp_band_to.setValue(band[1])
    if rng:
        d.sp_from.setValue(rng[0]); d.sp_to.setValue(rng[1])
    d.compute_spectra()
    print(f'  spectra [{norm}]:', d.sp_note.text())


# --- Lesson 5: along the whole spectrum -----------------------------------------------
print('\n=== L5 treatment along the spectrum')
d = open_demo('group_stats_treatment_demo.xlsx')
spectra_tab(d, 'none'); shot(d, 'l5_raw.png', 4)
spectra_tab(d, 'band'); shot(d, 'l5_band.png', 4)
save_img(d.tabs.parentWidget(), os.path.join(MAIN, 'spectra_tab.png'))
spectra_tab(d, 'area'); shot(d, 'l5_area.png', 4)
# main-help screenshots: the window, the Test tab, groups from names - in a freshly
# opened window (the Spectra tab, once used, needs more height and squeezes the top)
d.close()
d = open_demo('group_stats_treatment_demo.xlsx')
two_bands(d, (1620, 1690), (1420, 1480)); d.compute(); d.tabs.setCurrentIndex(0)
save_img(d, os.path.join(MAIN, 'group_statistics_dialog.png'), 1100)
d.tabs.setCurrentIndex(2)
save_img(d.tabs.parentWidget(), os.path.join(MAIN, 'test_tab.png'))
from src.views.dialogs.visualization_analysis.group_statistics_dialog import NamesToGroupsDialog
nd = NamesToGroupsDialog(d.labels, d)
nd.contains_radio.setChecked(True)
nd.rules_edit.setPlainText('control = control\nlow = low dose\nhigh = high dose')
nd.resize(620, 560); nd.show(); app.processEvents()
save_img(nd, os.path.join(MAIN, 'groups_from_names.png'), 700)
nd.close()
d.deleteLater()
d = open_demo('group_stats_cells_samples_demo.xlsx')
d.test_combo.setCurrentIndex(d.test_combo.findData('parametric'))
spectra_tab(d, 'band'); shot(d, 'l5_cells_warning.png', 4)
d.per_sample_check.setChecked(True)
spectra_tab(d, 'band')
d.deleteLater()

# --- Lesson 6: ROI regions of a map as groups -----------------------------------------
print('\n=== L6 map regions')
from matplotlib.patches import Ellipse, Rectangle
from PyQt5.QtWidgets import QDialog
from src.controllers.visualization_analysis.map2d_controller import Map2DController
from src.views.dialogs.visualization_analysis.map2d_dialog import Map2DDialog
from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
m = SpectrumManager()
m.load_spectrum_from_file(os.path.abspath(os.path.join(SYNTH, 'group_stats_cell_map_demo.mat')))
mspectra = [{'label': l, 'x_scale': s.x_scale, 'y_scale': s.y_scale, 'metadata': s.metadata}
            for l, s in m.spectra.items()]


class _Main:
    view = None


md = Map2DDialog(None, Map2DController(_Main()), mspectra)
md.resize(1300, 820); md.show(); app.processEvents()
md._radio_intensity.setChecked(True)
md._metric_combo.setCurrentText('Baseline-corrected integral')
md._ranges = [[770, 800]]
md._is_exclude = False
md._update_ranges_summary()
md._compute_map(); app.processEvents()


class _Click:
    inaxes = md._map_canvas.ax
    xdata, ydata, button, dblclick = 17.0, 14.0, 1, False


md._on_map_click(_Click()); app.processEvents()


def region(kind, inside, patch):
    labels = [mspectra[r * 40 + c]['label'] for r in range(30) for c in range(40) if inside(r, c)]
    md._map_canvas.ax.add_patch(patch)
    return {'type': kind, 'bounds': None, 'labels': labels, 'spectra': [], 'patch': patch}


md._roi_regions = [
    region('ellipse', lambda r, c: ((c - 17) / 4) ** 2 + ((r - 14) / 4) ** 2 <= 1,
           Ellipse((17, 14), 8, 8, lw=1.5, edgecolor='white', facecolor='none', ls='--', zorder=5)),
    region('rect', lambda r, c: 12 <= r <= 18 and 26 <= c <= 31,
           Rectangle((25.5, 11.5), 6, 7, lw=1.5, edgecolor='white', facecolor='none', ls='--',
                     zorder=5))]
md._update_roi_count(); md._map_canvas.draw(); app.processEvents()
save_img(md, os.path.join(OUT, 'l6_map.png'), 1000)
save_img(md, os.path.join(MAIN, 'map_roi_regions.png'), 1000)


def roi_menu_shot(path, scale=0.8):
    """The 2D Map's ROI menu, open above its button (help page of 2D Map)."""
    from PyQt5.QtWidgets import QToolButton
    from PyQt5.QtGui import QPainter
    from PyQt5.QtCore import QPoint, QRect, Qt
    btn = [b for b in md.findChildren(QToolButton) if b.text().startswith('ROI') and b.isVisible()][0]
    for _ in range(5):
        app.processEvents()
    md.repaint(); app.processEvents()
    bg = md.grab()
    pos = btn.mapTo(md, QPoint(0, 0))
    menu = btn.menu()
    menu.popup(btn.mapToGlobal(QPoint(0, 0))); app.processEvents()
    mp = menu.grab()
    menu.close()
    mx, my = pos.x(), pos.y() - mp.height()
    p = QPainter(bg); p.drawPixmap(mx, my, mp); p.end()
    x0, y0 = max(0, mx - 120), max(0, my - 20)
    crop = bg.copy(QRect(x0, y0, mp.width() + 200, pos.y() + btn.height() + 10 - y0))
    if IMAGES:
        crop.toImage().scaledToWidth(int(crop.width() * scale), Qt.SmoothTransformation).save(path)


roi_menu_shot(os.path.join('resources', 'images', 'help_screenshots', 'map2d', 'roi_menu.png'))
orig_exec = QDialog.exec_


def grab_names(self):
    edits = self.findChildren(gsd.QLineEdit) if hasattr(gsd, 'QLineEdit') else []
    from PyQt5.QtWidgets import QLineEdit
    e = self.findChildren(QLineEdit)
    e[0].setText('nucleus'); e[1].setText('cytoplasm')
    self.show(); app.processEvents()
    save_img(self, os.path.join(OUT, 'l6_names.png'), 700)
    return QDialog.Accepted


QDialog.exec_ = grab_names
gsd.GroupStatisticsDialog.exec_ = lambda self: 0
md._open_roi_group_statistics()
QDialog.exec_ = orig_exec
d = md._roi_group_dialog
d.resize(WINDOW_WIDTH, WINDOW_HEIGHT); d.show(); app.processEvents(); fixed_layout(d)
print('L6 source:', d.table_source.text(), sorted(set(d.groups())))
two_bands(d, (770, 800), (1420, 1480), metric='Baseline-corrected integral'); d.compute()
report('L6 DNA 770-800 / 1420-1480', d)
shot(d, 'l6_ratio.png', 0, whole=True, width=1100)
two_bands(d, (990, 1015), (1420, 1480), metric='Baseline-corrected integral'); d.compute()
report('L6 protein 990-1015 / 1420-1480', d)
spectra_tab(d, 'none'); shot(d, 'l6_spectra_raw.png', 4)
spectra_tab(d, 'band'); shot(d, 'l6_spectra_band.png', 4)
d.deleteLater(); md.deleteLater()
print('\nImages in', OUT if IMAGES else '(not written)')
