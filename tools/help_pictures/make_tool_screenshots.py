"""Retakes the help pictures of the dialogs (with the icons on their
buttons), from the real program. Run on Windows from the repo root:
    python tools/help_pictures/make_tool_screenshots.py [part ...]
(make_all_help_pictures.bat runs it with the others). Parts: see PARTS at
the end; none = all. Uses a temporary settings folder. A log goes to
tools/logs/pictures_tool_windows.txt. SAX_SHOTS_OUT=<folder>
writes the pictures there instead (for trying it out)."""
import os
import sys
import tempfile
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)                     # the repository: paths below are relative to it
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools', 'help_pictures'))
import steady                      # the same picture every run (see steady.py)
steady.start()
os.environ['SPECANALYTIXBASE_DATA_DIR'] = tempfile.mkdtemp(prefix='sax_tool_shots_')
SHOTS = os.environ.get('SAX_SHOTS_OUT') or os.path.join('resources', 'images', 'help_screenshots')
LOG = os.path.join('tools', 'logs', 'pictures_tool_windows.txt')
os.makedirs(os.path.dirname(LOG), exist_ok=True)
_log = open(LOG, 'w', encoding='utf-8')


def log(*parts):
    text = ' '.join(str(p) for p in parts)
    print(text, flush=True)
    _log.write(text + '\n')
    _log.flush()


from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (QAbstractButton, QApplication, QDialog, QGroupBox, QMessageBox,
                             QPushButton, QTabWidget, QWidget)

app = QApplication(sys.argv)
app.setWindowIcon(QIcon(os.path.join('resources', 'icons', 'app_icon.ico')))
from src.views.theme import apply_saved_theme
apply_saved_theme(app)
from src.views import button_icons
button_icons.install(app)

from src.views.dialogs.misc import import_dialog
ORIGINAL_IMPORT_RUN = import_dialog.ImportDialog.run
import_dialog.ImportDialog.run = staticmethod(
    lambda view, settings, file_paths=None: (True, list(file_paths),
                                             [{'jws_selected_channels': [0], 'sheet_name': 'Spectra'
                                               if str(p).endswith('.xlsx') else None}
                                              for p in file_paths]))
def _box(icon, default):
    """QMessageBox.information(...) and the like through the picture taker:
    a message box asked for is pictured, any other is answered."""
    def show(parent, title, text, *args, **kwargs):
        box = QMessageBox(icon, title, text, QMessageBox.Ok, parent)
        box.setProperty('_default_answer', int(default))
        result = _fake_exec(box)
        return default if result in (None, QMessageBox.Cancel) else result
    return staticmethod(show)


QMessageBox.information = _box(QMessageBox.Information, QMessageBox.Ok)
QMessageBox.warning = _box(QMessageBox.Warning, QMessageBox.Ok)
QMessageBox.critical = _box(QMessageBox.Critical, QMessageBox.Ok)
QMessageBox.question = _box(QMessageBox.Question, QMessageBox.Yes)

REAL = os.path.join('resources', 'test_data', 'real')
SYN = os.path.join('resources', 'test_data', 'synthetic')
RAMAN = os.path.join(REAL, 'Raman_DNA_conc_dep.txt')
TBA = os.path.join(REAL, 'CD_spectra_TBA.txt')
CHLORELLA = os.path.join(REAL, '2D map', 'Chlorella.mat')


# --------------------------------------------------------------------------- helpers
def settle(seconds=0.15):
    end = time.time() + seconds
    while True:
        app.processEvents()
        if time.time() >= end:
            break
        time.sleep(0.01)


def wait_until(condition, limit=120):
    end = time.time() + limit
    while time.time() < end:
        app.processEvents()
        try:
            if condition():
                settle(0.3)
                return True
        except Exception:
            pass
        time.sleep(0.05)
    log('   (timed out waiting)')
    return False


def save(pixmap, folder, name):
    path = os.path.join(SHOTS, folder, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ok = pixmap.save(path, 'PNG')
    log(('saved ' if ok else 'FAILED ') + path, pixmap.width(), 'x', pixmap.height())


def rect_in(window, widget):
    return QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())


def union(window, widgets, margin=6):
    widgets = [w for w in widgets if w is not None]
    r = rect_in(window, widgets[0])
    for w in widgets[1:]:
        r = r.united(rect_in(window, w))
    return r.adjusted(-margin, -margin, margin, margin).intersected(window.rect())


def common_parent(widgets):
    chains = []
    for w in widgets:
        chain = []
        while w is not None:
            chain.append(w)
            w = w.parentWidget()
        chains.append(chain)
    for candidate in chains[0][1:]:
        if all(candidate in c for c in chains[1:]):
            return candidate
    return chains[0][-1]


def shot(window, folder, name, widgets=None, margin=6):
    """The whole window, or the area of `widgets` (grabbed from their nearest
    common parent, so also when it is scrolled out of view)."""
    steady.fixed_clock()
    steady.park_mouse()
    settle(0.2)
    widgets = [w for w in (widgets or []) if w is not None]
    if not widgets:
        if widgets is not None and name and window is None:
            return
        save(window.grab(), folder, name)
        return
    if len(widgets) == 1:
        w = widgets[0]
        if margin <= 0 or w.parentWidget() is None:
            save(w.grab(), folder, name)
            return
        parent = w.parentWidget()
        r = rect_in(parent, w).adjusted(-margin, -margin, margin, margin).intersected(parent.rect())
        save(parent.grab(r), folder, name)
        return
    parent = common_parent(widgets)
    save(parent.grab(union(parent, widgets, margin)), folder, name)


def shot_list_without_empty_space(panel, lst, folder, name, below=8):
    """A panel with a list and buttons under it, without the empty part of the
    list: the list down to its last item, its bottom edge, then the buttons."""
    steady.fixed_clock()
    steady.park_mouse()
    settle(0.2)
    whole = panel.grab()
    dpr = whole.devicePixelRatio() or 1
    top = rect_in(panel, lst).top()
    last = lst.visualItemRect(lst.item(lst.count() - 1))
    cut = top + lst.viewport().mapTo(lst, last.bottomLeft()).y() + below
    list_bottom = rect_in(panel, lst).bottom() + 1
    edge = 2                                   # the list's bottom frame line
    if cut >= list_bottom - edge:
        save(whole, folder, name)
        return
    w = panel.width()
    rest = panel.height() - list_bottom
    dev = lambda x, y, ww, hh: QRect(int(x * dpr), int(y * dpr), int(ww * dpr), int(hh * dpr))
    picture = QPixmap(int(w * dpr), int((cut + edge + rest) * dpr))
    picture.setDevicePixelRatio(dpr)
    picture.fill(Qt.white)
    painter = QPainter(picture)
    painter.drawPixmap(QPoint(0, 0), whole.copy(dev(0, 0, w, cut)))
    painter.drawPixmap(QPoint(0, cut), whole.copy(dev(0, list_bottom - edge, w, edge)))
    painter.drawPixmap(QPoint(0, cut + edge), whole.copy(dev(0, list_bottom, w, rest)))
    painter.end()
    save(picture, folder, name)


def buttons(window, *texts):
    """The visible push buttons with these texts (… and ... alike)."""
    norm = lambda t: t.replace('…', '...').replace('&', '').strip()
    wanted = [norm(t) for t in texts]
    found = []
    for t in wanted:
        cands = [b for b in window.findChildren(QAbstractButton)
                 if b.isVisible() and norm(b.text()) == t and b not in found]
        if not cands:
            continue
        if found:
            # prefer the button lying on the same row as the first one found
            y0 = found[0].mapToGlobal(found[0].rect().center()).y()
            cands.sort(key=lambda b: abs(b.mapToGlobal(b.rect().center()).y() - y0))
        found.append(cands[0])
    return found


def button(window, text):
    found = buttons(window, text)
    return found[0] if found else None


def group(window, title_start):
    for g in window.findChildren(QGroupBox):
        if g.isVisible() and g.title().replace('&', '').startswith(title_start):
            return g
    return None


def tab(window, text):
    """Select the tab `text`; returns its page."""
    for tw in window.findChildren(QTabWidget):
        for i in range(tw.count()):
            if tw.tabText(i).replace('&', '').strip() == text:
                tw.setCurrentIndex(i)
                settle(0.3)
                return tw.widget(i)
    return None


def tab_widget_of(page):
    w = page
    while w is not None and not isinstance(w, QTabWidget):
        w = w.parentWidget()
    return w


# --------------------------------------------------------------------------- dialogs
SHOOTERS = []          # (title start, function(dialog)) - the first that matches
_depth = [0]


def on(title_start):
    def register(function):
        SHOOTERS.append((title_start, function))
        return function
    return register


def _fake_exec(dialog, *args):
    _depth[0] += 1
    try:
        dialog.show()
        settle(0.4)
        title = dialog.windowTitle()
        for start, function in list(SHOOTERS):
            if title.startswith(start):
                SHOOTERS.remove((start, function))      # each one once
                log(f' [{title}]')
                try:
                    result = function(dialog)
                except Exception:
                    log(traceback.format_exc())
                    result = None
                if result is not None:
                    return result
                break
        else:
            log(f' (not pictured: {title!r})')
        return QMessageBox.Cancel if isinstance(dialog, QMessageBox) else QDialog.Rejected
    finally:
        try:
            if dialog.isVisible():
                dialog.hide()
        except RuntimeError:
            pass
        _depth[0] -= 1


QDialog.exec_ = _fake_exec
QDialog.exec = _fake_exec
QMessageBox.exec_ = _fake_exec
QMessageBox.exec = _fake_exec

from src.controllers.core.main_controller import MainController
steady.fixed_clock()
steady.park_mouse()
MC = []


def main_controller():
    if not MC:
        mc = MainController()
        mc.view.move(0, 0)
        mc.view.resize(1910, 1025)
        mc.show()
        settle(0.5)
        MC.append(mc)
    return MC[0]


def load(paths, select='all'):
    mc = main_controller()
    mc.import_controller._run_import(clear_first=True, file_paths=list(paths))
    settle(0.3)
    if select == 'all':
        mc.spectrum_selector.select_all_items()
    else:
        mc.spectra_list_widget.clearSelection()
        for i in select:
            mc.spectra_list_widget.item(i).setSelected(True)
    settle(0.5)
    return mc


# =========================================================================== parts
def part_user_guide():
    F = 'user_guide'
    mc = load([RAMAN])

    # Band markers: three markers, the third selected
    mc.band_marker_manager.clear()
    for x in (495, 683, 1483):
        mc.band_marker_manager.add(x, color='#E65100', linestyle='--')

    @on('Band Marker')
    def _(d):
        from PyQt5.QtWidgets import QTableWidget
        tables = d.findChildren(QTableWidget)
        if tables:
            tables[0].selectRow(2)
        d.resize(1023, 501)
        shot(d, F, 'band_marker_manager.png')
    mc.view.band_markers_btn.click()
    settle()
    mc.band_marker_manager.clear()

    @on('Legend Properties')
    def _(d):
        shot(d, F, 'legend_properties_dialog.png')
    mc.legend_properties_button.click()

    @on('Import Spectra')
    def _(d):
        d.resize(698, 744)
        settle(1.0)
        shot(d, F, 'import_spectra_dialog.png')
    ORIGINAL_IMPORT_RUN(mc.view, dict(mc.import_settings), [RAMAN])

    @on('Save Options')
    def _(d):
        shot(d, F, 'save_options_dialog.png')
    mc.save_controller.execute()

    @on('Load Snapshot')
    def _(d):
        shot(d, F, 'snapshot_confirmation_dialog.png')
    mc.save_controller.load_snapshot(os.path.join(tempfile.gettempdir(), 'none.snapx'))

    @on('Select Spectra')
    def _(d):
        shot(d, F, 'spectra_selection_dialog.png')
    mc.select_spectra_button.click()

    # Rename: 4 spectra
    load([RAMAN], select=[3, 4, 5, 6])

    @on('Rename Spectra')
    def _(d):
        d.resize(498, 430)
        shot(d, F, 'rename_spectra_dialog.png')
    mc.rename_spectra_button.click()

    @on('Spectrum Metadata Selection')
    def _(d):
        shot(d, F, 'spectrum_metadata_table_dialog.png')
    mc.metadata_button.click()

    load([RAMAN], select=[4])

    @on('Metadata:')
    def _(d):
        d.resize(772, 692)
        shot(d, F, 'spectrum_metadata_dialog.png')
    mc.metadata_button.click()

    # History: three steps
    load([RAMAN])
    om = mc.operations_controller.operations_manager
    for op, params in (('Automated Baseline', {'algorithm': 'arpls', 'lam': 1e5}),
                       ('Data range', {'ranges': [(400, 1800)], 'mode': 'include'}),
                       ('Normalization', {'method': 'peak_intensity'})):
        current = om.get_current_spectra()
        om.apply_operation(op, params, current, new_state_spectra=current)

    @on('Operations History')
    def _(d):
        d.resize(880, 594)
        shot(d, F, 'operations_history_dialog.png')
    mc.view.summary_operations_pushButton.click()


def commit_row(d, *texts):
    return buttons(d, *(texts or ('Help', 'Apply', 'Add as New', 'Close')))


def part_data_range():
    F = 'data_range'
    mc = load([RAMAN])

    @on('Define Spectral Range')
    def _(d):
        d.resize(1910, 1000)
        d.spectra_list.clearSelection()
        d.spectra_list.item(0).setSelected(True)
        d.exclude_radio.setChecked(True)
        settle(0.5)
        shot(d, F, 'dialog_overview.png')
        shot(d, F, 'commit_buttons.png', commit_row(d), margin=4)
        shot(d, F, 'xaxis_limits.png', [group(d, 'X-Scale Range')], margin=2)
        for x0, x1 in ((632.8, 720.5), (1831, 1952), (1142.2655, 1280.5932)):
            d._append_range(x0, x1)
        d.range_from_edit.setText('1142.2655')
        d.range_to_edit.setText('1280.5932')
        settle(0.5)
        shot(d, F, 'interactive_range_selection.png')
        shot(d, F, 'defined_ranges.png', [group(d, 'Defined Ranges')], margin=2)
    mc.operations_controller.show_parameters_dialog_for('Data range')


def part_manual_baseline():
    F = 'manual_baseline'
    mc = load([RAMAN])

    @on('Manual Baseline Correction')
    def _(d):
        d.resize(1910, 1000)
        d.spectra_list.setCurrentRow(0)
        d.baseline_on_btn.setChecked(True)
        d.enable_baseline_mode()
        settle(0.3)
        import numpy as np
        sp = d.selected_spectra[0] if hasattr(d, 'selected_spectra') else mc.selected_spectra[0]
        x, y = np.asarray(sp['x_scale']), np.asarray(sp['y_scale'])
        for xv in np.linspace(x.min() + 20, x.max() - 20, 14):
            i = int(np.argmin(abs(x - xv)))
            lo, hi = max(0, i - 15), min(len(y), i + 15)
            d.on_point_added(float(x[i]), float(np.min(y[lo:hi])))
        settle(0.5)
        shot(d, F, 'dialog_overview.png')
        shot(d, F, 'commit_buttons.png', buttons(d, 'Apply', 'Add as New', 'Close', 'Help'),
             margin=4)

        @on('Baseline Correction Summary')
        def _(s):
            shot(s, F, 'correction_summary_table.png')
        d.summary_button.click()
    mc.operations_controller.show_parameters_dialog_for('Manual baseline')


def part_normalization():
    F = 'normalization'
    mc = load([RAMAN])

    @on('Normalization')
    def _(d):
        d.resize(1900, 990)
        d.spectra_list.clearSelection()
        d.spectra_list.item(4).setSelected(True)
        settle(0.6)
        shot(d, F, 'dialog_overview.png')
        shot(d, F, 'commit_buttons.png', commit_row(d), margin=4)
        # a region, the preset row and the region controls
        d.x_min_spinbox.setText('1462.8245')
        d.x_max_spinbox.setText('1506.0211')
        d._add_region()
        settle(0.4)
        row = [d.preset_combo] + buttons(d, 'Load', 'Save as...', 'Delete')
        shot(d, F, 'region_presets.png', row, margin=4)
        section = d.regions_list
        while section is not None and type(section).__name__ != 'CollapsibleSection':
            section = section.parentWidget()
        shot(d, F, 'regions_controls.png', [section], margin=0)
        # preview tab with the factors

        page = tab(d, 'Preview (normalized)')
        settle(1.5)
        if page is not None:
            shot(d, F, 'preview_tab.png', [tab_widget_of(page)], margin=2)
            for b in page.findChildren(QPushButton):
                if 'Per-spectrum factors' in b.text() and not d.factor_table.isVisible():
                    b.click()
                    settle(0.5)
            shot(d, F, 'per_spectrum_factors.png',
                 [d.factor_table] + buttons(d, 'Save selected spectra...'), margin=8)

        @on('Peak intensity')
        def _(m):
            # the method info box over the method group
            g = group(d, 'Normalization method') or d.method_tabs
            pic = g.grab()
            box = m.grab()
            p = QPainter(pic)
            p.drawPixmap(max(0, (pic.width() - box.width()) // 2), 40, box)
            p.end()
            save(pic, F, 'method_tabs.png')
        tab(d, 'Intensity')
        d.method_info_button.click()
    mc.operations_controller.show_parameters_dialog_for('Normalization')


def part_x_axis_alignment():
    F = 'x_axis_alignment'
    mc = load([os.path.join(SYN, 'x_axis_alignment_demo_data.txt')])

    @on('X-Axis Alignment')
    def _(d):
        d.resize(1289, 871)
        d._run_preview()
        wait_until(lambda: not d.run_preview_btn.isEnabled() or d._progress.isVisible(), 5)
        wait_until(lambda: d.run_preview_btn.isEnabled() and not d._progress.isVisible(), 120)
        settle(1.0)
        shot(d, F, 'dialog_overview.png')
        shot(d, F, 'commit_buttons.png', commit_row(d), margin=4)
    mc.operations_controller.show_parameters_dialog_for('X-axis alignment')


def part_svd_interpolation():
    F = 'svd_interpolation'
    mc = load([TBA])

    @on('SVD Interpolation')
    def _(d):
        d.resize(1907, 1000)
        wait_until(lambda: d._component_list.count() > 0, 120)
        table = d._param_table
        from PyQt5.QtWidgets import QTableWidgetItem
        col = table.columnCount() - 1
        for r in range(table.rowCount()):
            table.setItem(r, col, QTableWidgetItem(f'{10 + 2 * r:g}'))
        d._on_apply_parameters()
        settle(0.5)
        d._component_list.setCurrentRow(0)
        item = d._component_list.item(0)
        if item.flags() & Qt.ItemIsUserCheckable:
            item.setCheckState(Qt.Checked)
        d._on_component_row_changed(0)
        settle(0.3)
        try:
            d._on_autofill_clicked()
        except Exception:
            log(traceback.format_exc())
        d._target_edit.setPlainText('21,31,37,62.5')
        d._on_compute_preview_clicked()
        wait_until(lambda: d._preview_gen_list.count() > 0, 120)
        page = tab(d, 'Preview')
        d._preview_gen_list.selectAll()
        d._preview_source_list.clearSelection()
        for i in range(min(7, d._preview_source_list.count())):
            d._preview_source_list.item(i).setSelected(True)
        settle(0.8)
        shot(d, F, 'dialog_overview.png')
        if page is not None:
            shot(d, F, 'preview_tab.png', [page], margin=0)
        shot(d, F, 'commit_buttons.png', buttons(d, 'Apply', 'Add as New', 'Close', 'Help'),
             margin=4)
        shot(d, F, 'parameter_values.png', [group(d, '1. Parameter values')], margin=0)
        shot(d, F, 'components_curve_fit.png', [group(d, '2. Components')], margin=0)

        @on('Guess # of Components')
        def _(g):
            shot(g, F, 'guess_components.png')
        d._guess_components_btn.click()
    mc.operations_controller.show_parameters_dialog_for('SVD Interpolation')


def part_peak_fitting():
    """Peak Fitting on a series of Raman spectra (raman_2comp_noisy): the
    peaks of one spectrum, the fit, the list of spectra, several shown
    together (Overlay, Waterfall, Grid), Series results, the output options,
    the orange "?" and a missing peak seen in the residual."""
    F = 'peak_fitting'
    mc = load([os.path.join(SYN, 'raman_2comp_noisy.xlsx')], select=list(range(10)))

    @on('Peak Fitting')
    def _(d):
        from PyQt5.QtCore import QItemSelectionModel
        d.resize(1900, 1000)
        settle(0.5)

        def select(rows):
            lst = d.spectra_list
            lst.clearSelection()
            for r in rows:
                lst.selectionModel().select(lst.model().index(r, 0), QItemSelectionModel.Select)
            settle(0.6)

        # one spectrum: the detected peaks, fitted
        d.peaks = []
        d.amplitude_combo.setCurrentIndex(1)                  # Positive Peaks Only
        d.auto_detect_peaks()
        d.fit_selected()                                      # Fit Peaks - 1 spectrum
        d.interactive_add_cb.setChecked(True)
        settle(0.6)
        shot(d, F, 'dialog_overview.png')
        shot(d, F, 'plot_area.png', [d.canvas], margin=0)
        shot(d, F, 'peaks_table.png', [d.peaks_group], margin=0)
        shot(d, F, 'peak_adding_controls.png',
             buttons(d, 'Auto-Detect Peaks', 'Remove Selected Peak(s)', 'Clear All Peaks')
             + [d.interactive_add_cb, d.quick_help_buttons['peaks']], margin=4)
        shot(d, F, 'plot_bar.png', [d.list_button.parentWidget(), d.click_hint], margin=4)

        # the whole series: all selected, Fit Peaks - 10 selected spectra; the
        # others start from the fit before them (a band shifting along the series)
        d.follow_check.setChecked(True)
        d.list_all_button.click()
        settle(0.5)
        shot(d, F, 'fitting_controls.png', [group(d, 'Fitting')], margin=0)
        d.fit_selected()
        settle(0.6)
        shot(d, F, 'series_results.png', [d.left_tabs], margin=0)
        # the Amplitude Constraint drop-down, open, over the Fitting group
        combo = d.amplitude_combo
        combo.showPopup()
        settle(0.6)
        popup = combo.view().window()
        box = rect_in(d, group(d, 'Fitting'))
        # drawn just under the drop-down (where the system puts it varies)
        top_left = combo.mapTo(d, QPoint(0, combo.height()))
        region = box.united(QRect(top_left, popup.size())).adjusted(-6, -6, 6, 6)
        region = region.intersected(d.rect())
        picture = d.grab(region)
        painter = QPainter(picture)
        painter.drawPixmap(top_left - region.topLeft(), popup.grab())
        painter.end()
        save(picture, F, 'constraint_dropdown.png')
        combo.hidePopup()
        settle(0.3)
        d.view_combo.setCurrentIndex(1)                       # Waterfall
        settle(0.6)
        shot(d, F, 'series_waterfall.png', [d.canvas], margin=0)
        d.view_combo.setCurrentIndex(2)                       # Grid
        settle(0.6)
        shot(d, F, 'series_grid.png', [d.canvas], margin=0)
        d.view_combo.setCurrentIndex(0)                       # Overlay of three
        select([0, 4, 9])
        d.output_for_combo.setCurrentIndex(1)
        d.add_fit_check.setChecked(True)
        settle(0.5)
        shot(d, F, 'series_overview.png')
        shot_list_without_empty_space(d.spectra_panel, d.spectra_list, F, 'spectra_list.png')
        shot(d, F, 'output_options.png', [group(d, 'Output Options')], margin=0)
        d.output_for_combo.setCurrentIndex(0)
        d.add_fit_check.setChecked(False)

        # the orange "?"
        @on('Quick help')
        def _(box):
            shot(box, F, 'quick_help.png')
        d.quick_help_buttons['fitting'].click()
        settle(0.3)

        # a band without a peak: the residual shows where
        select([0])
        missing = [k for k, p in enumerate(d.peaks) if abs(p['center'] - 1293) < 15]
        if missing:
            del d.peaks[missing[0]]
            d.update_peaks_table()
            d.fit_selected()
            settle(0.6)
            shot(d, F, 'missing_peak.png', [d.canvas], margin=0)

        from PyQt5.QtWidgets import QInputDialog
        q = QInputDialog(d)
        q.setWindowTitle('Initial Peak Parameters')
        q.setInputMode(QInputDialog.DoubleInput)
        q.setLabelText('Enter initial width (\u03c3/\u03b3) for new peaks:')
        q.setDoubleDecimals(4)
        q.setDoubleMinimum(1e-6)
        q.setDoubleMaximum(1e9)
        q.setDoubleValue(8.0)
        q.show()
        settle(0.4)
        shot(q, F, 'initial_width_dialog.png')
        q.close()
    mc.run_visualization_analysis('Peak Fitting')


def part_peak_fitting_own():
    """Peak Fitting with Raman and CD spectra together (CD: a band up and a
    band down): each spectrum its own peaks and its own Amplitude Constraint
    (Raman Positive Peaks Only, CD Unrestricted), shown in Grid; a CD fit,
    and the same CD spectrum wrongly fitted with Positive Peaks Only."""
    F = 'peak_fitting'
    mc = load([os.path.join(SYN, 'raman_2comp_noisy.xlsx'),
               os.path.join(SYN, 'cd_3comp_noisy.xlsx')],
              select=list(range(5)) + list(range(30, 35)))

    @on('Peak Fitting')
    def _(d):
        d.resize(1900, 1000)
        settle(0.5)
        d.peaks = []
        d.update_peaks_table()
        # the Amplitude Constraint of each kind: Raman positive, CD unrestricted
        d.own_constraint_check.setChecked(True)
        from PyQt5.QtCore import QItemSelectionModel

        def select(rows):
            lst = d.spectra_list
            lst.clearSelection()
            for r in rows:
                lst.selectionModel().select(lst.model().index(r, 0), QItemSelectionModel.Select)
            settle(0.3)
        raman = [k for k, sp in enumerate(d.series) if 'raman' in sp['label']]
        cd = [k for k, sp in enumerate(d.series) if 'cd_' in sp['label']]
        select(raman)
        d.amplitude_combo.setCurrentIndex(1)                  # Positive Peaks Only
        select(cd)
        d.amplitude_combo.setCurrentIndex(0)                  # Unrestricted
        d.list_all_button.click()
        settle(0.4)
        d.auto_detect_peaks()                                 # each spectrum its own
        d.fit_selected()
        settle(0.5)
        shot(d, F, 'constraint_each.png', [group(d, 'Fitting'), d.spectra_panel], margin=4)
        d.view_combo.setCurrentIndex(2)                       # Grid
        d.left_tabs.setCurrentIndex(0)
        settle(0.8)
        shot(d, F, 'peaks_each_own.png')
        # one CD spectrum: a band up and a band down (Unrestricted) ...
        select([cd[2]])
        settle(0.6)
        shot(d, F, 'cd_fit_unrestricted.png', [d.canvas], margin=0)
        # ... and the same spectrum with Positive Peaks Only: the band down is lost
        d.amplitude_combo.setCurrentIndex(1)
        d.fit_selected()
        settle(0.6)
        shot(d, F, 'cd_fit_positive.png', [d.canvas], margin=0)
        d.amplitude_combo.setCurrentIndex(0)
    mc.run_visualization_analysis('Peak Fitting')


def part_interactive_subtraction():
    F = 'interactive_subtraction'
    mc = load([RAMAN])

    def shoot(d):
        d.resize(1442, 923)
        if d.minuend_list.count() > 1:
            d.minuend_list.clearSelection()
            for i in (4, 6, 7):
                if i < d.minuend_list.count():
                    d.minuend_list.item(i).setSelected(True)
        if d.subtrahend_list.count() > 1:
            d.subtrahend_list.setCurrentRow(1)
        settle(0.6)
        d.on_update_clicked()
        settle(0.4)
        shot(d, F, 'dialog_overview.png')
        commit = group(d, 'Commit')
        shot(d, F, 'commit_and_apply_buttons.png', [commit] + buttons(d, 'Apply', 'Add as New'),
             margin=4)
        top = [d.minuend_list] + buttons(d, 'All', 'Clear')
        shot(d, F, 'batch_selection.png', top, margin=8)
        shot(d, F, 'minuend_subtrahend_lists.png',
             [d.minuend_list, d.subtrahend_list, d.import_subtrahend_button], margin=8)

        @on('Subtraction info')
        def _(s):
            shot(s, F, 'show_info_dialog.png')
        d.show_info_button.click()

        @on('X-Axis Mismatch')
        def _(m):
            shot(m, F, 'xaxis_mismatch_dialog.png')
        import numpy as np
        other = {'label': 'CD_spectra_TBA : 0003', 'x_scale': np.linspace(200, 330, 261),
                 'y_scale': np.zeros(261), 'metadata': {}}
        try:
            d._check_subtrahend_overlap(other)
        except Exception:
            log(traceback.format_exc())
    isc = mc.interactive_subtraction_controller
    d = isc.show_dialog(list(mc.selected_spectra), commit_callback=isc.commit_interactive_subtraction)
    settle(0.8)
    log(' [Spectra subtraction]')
    shoot(d)
    d.close()


def _factor_part(F, analysis, title, settings_group, save_title, export_title, first_tab,
                 settings_extra=None):
    mc = load([os.path.join(SYN, 'closed_dna_melting_3comp_noisy.xlsx')])

    @on(title)
    def _(d):
        d.resize(1276, 790)
        settle(0.5)
        d._n_spin.setValue(3)   # the demo data hold three components
        settle(0.2)
        d.run_btn.click()
        wait_until(lambda: 'lack of fit' in d._status_label.text(), 180)
        tab(d, first_tab)
        settle(0.8)
        shot(d, F, 'dialog_overview.png')
        widgets = [group(d, settings_group)]
        if settings_extra:
            widgets.append(group(d, settings_extra))
        shot(d, F, 'settings_panel.png', widgets, margin=4)

        @on(save_title)
        def _(s):
            shot(s, F, 'save_dialog.png')
        b = button(d, 'Save...')
        if b is not None:
            b.click()

        @on(export_title)
        def _(e):
            shot(e, F, 'export_components_dialog.png')
        b = button(d, 'Send to main list...')
        if b is not None:
            b.click()
    mc.run_visualization_analysis(analysis)


def part_nmf():
    _factor_part('NMF', 'NMF', 'Non-negative Matrix', 'NMF settings', 'Save NMF Results',
                 'Export Components', 'Components')


def part_mcr_als():
    _factor_part('MCR-ALS', 'MCR-ALS', 'MCR-ALS', 'MCR-ALS settings', 'Save MCR-ALS Results',
                 'Export Pure Spectra', 'Pure Spectra', settings_extra='Reference spectra')


def window_titled(start, limit=10):
    """A window that was opened with show() (not exec_)."""
    found = []

    def look():
        for w in QApplication.topLevelWidgets():
            if w.isVisible() and w.windowTitle().startswith(start):
                found.append(w)
                return True
        return False
    wait_until(look, limit)
    return found[0] if found else None


def part_svd_analysis():
    F = 'svd_analysis'
    mc = load([TBA])

    @on('SVD Analysis')
    def _(d):
        d.resize(1277, 800)
        wait_until(lambda: d.main_tabs.isEnabled() and len(d.findChildren(QAbstractButton)) > 10, 60)
        settle(2.0)
        tab(d, 'Components')
        settle(0.5)
        shot(d, F, 'dialog_overview.png')
        shot(d, F, 'commit_buttons.png', buttons(d, 'Close', 'Save...', 'Help'), margin=4)
        dp = d.diagnostics_panel
        d.resize(1870, 990)
        tab(d, 'Diagnostics')
        dp.mode_combo.setCurrentIndex(2)
        settle(0.8)
        shot(d, F, 'diagnostics_tab_overview.png', [d.main_tabs], margin=0)
        dp.mode_combo.setCurrentIndex(0)
        for i in range(dp.single_combo.count()):
            if dp.single_combo.itemText(i).startswith('Residual'):
                dp.single_combo.setCurrentIndex(i)
        dp.log_scale_cb.setChecked(True)
        settle(0.8)
        shot(d, F, 'diagnostics_single_metric.png', [d.main_tabs], margin=0)
        dp.mode_combo.setCurrentIndex(1)
        dp.x_combo.setCurrentIndex(0)
        dp.x_log_cb.setChecked(True)
        for i in range(dp.y_combo.count()):
            if 'IND' in dp.y_combo.itemText(i):
                dp.y_combo.setCurrentIndex(i)
        settle(0.8)
        shot(d, F, 'diagnostics_compare_metrics.png', [dp], margin=0)

        @on('All SVD Metrics')
        def _(m):
            shot(m, F, 'show_all_metrics_table.png')
        b = button(d, 'Show all metrics (table)...')
        if b is not None:
            b.click()
        if window_titled('All SVD Metrics', 2):
            w = window_titled('All SVD Metrics', 1)
            shot(w, F, 'show_all_metrics_table.png')
            w.close()

        @on('Save SVD Analysis Results')
        def _(s):
            shot(s, F, 'save_dialog.png')
        tab(d, 'Components')
        b = button(d, 'Save...')
        if b is not None:
            b.click()
    mc.run_visualization_analysis('SVD analysis')


def part_pca_scores():
    F = 'pca_scores'
    mc = load([CHLORELLA])

    @on('PCA / SVD')
    def _(d):
        d.resize(1275, 790)
        wait_until(lambda: d._tabs.isEnabled(), 120)
        settle(2.0)
        tab(d, 'Scores')
        settle(0.5)
        shot(d, F, 'dialog_overview.png')
        shot(d, F, 'left_panel_buttons.png', buttons(d, 'Save...', 'Help', 'Close'), margin=4)
        shot(d, F, 'svd_settings_group.png', [group(d, 'SVD settings')], margin=0)

        @on('Save PCA/SVD Results')
        def _(s):
            shot(s, F, 'save_dialog.png')
        b = button(d, 'Save...')
        if b is not None:
            b.click()
    mc.run_visualization_analysis('PCA Scores & Loadings')


def part_svd_baseline():
    F = 'svd_baseline'
    mc = load([RAMAN])

    @on('SVD Background Correction')
    def _(d):
        d.resize(1379, 912)
        wait_until(lambda: getattr(d, 'components_list', None) is not None
                   and d.components_list.count() > 0, 120)
        settle(1.0)
        shot(d, F, 'dialog_overview.png')
        shot(d, F, 'commit_buttons.png', buttons(d, 'Apply', 'Add as New', 'Close', 'Help'),
             margin=4)
        shot(d, F, 'subspectrum_navigation.png', [group(d, 'Subspectrum Navigation')], margin=0)
        b = button(d, 'Only corr.')
        if b is not None:
            b.click()
        shot(d, F, 'reconstruction_mode_buttons.png', [group(d, 'Reconstruction Mode')], margin=0)
        b = button(d, 'All')
        d._show_svd_plot('both')
        w = window_titled('SVD Singular Values', 5)
        if w is not None:
            w.resize(1017, 836)
            settle(0.8)
            shot(w, F, 'singular_values_window.png')
            w.close()

        d.preview_btn.click()                    # the preview opens as an ordinary window, not a dialog
        w = window_titled('SVD Reconstruction Preview', 3)
        if w is not None:
            w.resize(1700, 950)
            settle(1.0)
            shot(w, F, 'preview_reconstruction_window.png')
            w.close()
    mc.operations_controller.show_parameters_dialog_for('SVD background')


def add_ranges(r, pairs=None):
    """Type ranges into a Define Spectral Range window and press Add.
    With no pairs, the range it suggests by itself is added."""
    try:
        if pairs is None:
            r._on_add()
        for lo, hi in pairs or ():
            r._edit_from.setText(str(lo))
            r._edit_to.setText(str(hi))
            r._on_add()
    except Exception:
        log(traceback.format_exc())
    settle(0.3)


def part_band_ratio():
    F = 'band_ratio'
    mc = load([TBA])

    @on('Band Ratio')
    def _(d):
        d.resize(1900, 1000)
        settle(1.0)
        shot(d, F, 'dialog_overview.png')
    mc.run_visualization_analysis('Band Ratio')
    mc = load([RAMAN])

    @on('Band Ratio')
    def _(d):
        d.resize(1900, 1000)
        settle(0.5)

        @on('Define Spectral Range')
        def _(r):
            r.resize(780, 707)
            settle(0.5)
            add_ranges(r, [(1296.0, 1399.1), (1454.7, 1512.8)])
            settle(0.5)
            shot(r, F, 'define_spectral_range_dialog.png')
        load_raman = False
        b = button(d, 'Configure Band A...')
        if b is not None:
            b.click()
    mc.run_visualization_analysis('Band Ratio')


def part_melting_curve():
    F = 'melting_curve_analysis'
    from PyQt5.QtWidgets import QInputDialog
    names = iter(['seqA_1_comp', 'seqB_1_comp', 'seqC_1_comp', 'seqD_1_comp'])
    QInputDialog.getText = staticmethod(lambda *a, **k: (next(names, 'fit'), True))
    mc = load([os.path.join(SYN, 'melting_1trans_clean.xlsx')])

    @on('Melting Curve Analysis')
    def _(d):
        d.resize(1910, 1000)
        settle(0.8)
        d.x_value_spin.setValue(300.0)
        settle(0.5)
        d.fit_btn.click()
        settle(2.0)
        shot(d, F, 'dialog_overview.png')
        shot(d, F, 'curve_data_table.png', [group(d, 'Curve Data')], margin=0)
        shot(d, F, 'sigmoid_fit_group.png', [group(d, 'Sigmoid Fit')], margin=0)
        # saved fits: four of them
        if not d.saved_fits_list.isVisible():
            d.saved_fits_toggle_btn.click()
        for x in (300.0, 290.0, 280.0, 270.0):
            d.x_value_spin.setValue(x)
            settle(0.3)
            d.fit_btn.click()
            settle(1.0)
            d.save_current_fit()
            settle(0.3)
        shot(d, F, 'saved_fits_group.png', [group(d, 'Saved Fits')], margin=0)

        @on('Saved Fits Summary')
        def _(s):
            s.resize(1033, 815)
            settle(0.8)
            shot(s, F, 'show_summary_window.png')

        @on('Saved Fits Overlay')
        def _(o):
            o.resize(792, 625)
            settle(0.8)
            shot(o, F, 'show_overlay_plot_window.png')
        for text in ('Show Summary', 'Show Overlay Plot'):
            b = button(d, text)
            if b is not None:
                b.click()
                settle(0.5)
        for title, name in (('Saved Fits Summary', 'show_summary_window.png'),
                            ('Saved Fits Overlay', 'show_overlay_plot_window.png')):
            w = window_titled(title, 2)
            if w is not None and any(s[0] == title for s in SHOOTERS):
                settle(0.8)
                shot(w, F, name)
                w.close()

        @on('Unphysical Fit Result')
        def _(m):
            shot(m, F, 'unphysical_fit_warning.png')
        d.n_components_spin.setValue(3)
        d.fit_btn.click()
        settle(2.0)
    mc.run_visualization_analysis('Melting Curve Analysis')


def part_map2d():
    F = 'map2d'
    mc = load([CHLORELLA])

    @on('2D Spectral Map')
    def _(d):
        d.resize(1910, 1000)
        settle(1.0)

        class Click:
            button, dblclick = 1, False

        def click(row, col):
            Click.inaxes = d._map_canvas.ax
            Click.xdata, Click.ydata = float(col), float(row)
            try:
                d._on_map_click(Click())
            except Exception:
                log(traceback.format_exc())
            settle(0.6)

        def compute(radio, limit=240):
            radio.setChecked(True)
            settle(0.4)
            d._compute_map()
            settle(1.5)

        rows, cols = d._rows_spin.value(), d._cols_spin.value()
        r0, c0 = rows // 2, cols // 2
        panel = lambda: [d._spectrum_panel] + buttons(d, 'Update Map', 'Help', 'Close')

        compute(d._radio_intensity)
        click(r0, c0)
        shot(d, F, 'dialog_overview.png')
        shot(d, F, 'spectrum_panel.png', panel(), margin=4)

        @on('Valid map dimensions')
        def _(s):
            shot(s, F, 'suggest_dialog.png')
        d._btn_autofill.click()

        @on('Define Spectral Range')
        def _(r):
            r.resize(777, 702)
            settle(0.5)
            add_ranges(r, [(2820.0, 3020.0)])   # the C-H band
            settle(0.5)
            shot(r, F, 'configure_range_dialog.png')
        b = button(d, 'Configure Band...')
        if b is not None:
            b.click()

        @on('Peak-fit settings')
        def _(s):
            shot(s, F, 'peak_fit_settings.png')
        try:
            d._edit_peak_fit_settings()
        except Exception:
            log(traceback.format_exc())

        # SVD
        compute(d._radio_svd)
        click(r0, c0)
        shot(d, F, 'svd_spectrum_panel.png', panel(), margin=4)
        d._svd_full_range_cb.setChecked(True)
        settle(0.6)
        click(r0, c0)
        shot(d, F, 'svd_full_spectrum_range.png', panel(), margin=4)
        d._svd_full_range_cb.setChecked(False)

        @on('SVD Multi-Component Map')
        def _(m):
            m.resize(1700, 950)
            settle(1.0)
            shot(m, F, 'svd_multi_map_result.png')
        d._show_multi_map()
        w = window_titled('SVD Multi-Component Map', 2)
        if w is not None and any(s[0] == 'SVD Multi-Component Map' for s in SHOOTERS):
            w.resize(1700, 950)
            settle(1.0)
            shot(w, F, 'svd_multi_map_result.png')
            w.close()

        # PCA
        compute(d._radio_pca)
        click(r0, c0)
        d._show_reconstructed_cb.setChecked(True)
        settle(0.4)
        d._recon_n_spin.setValue(min(3, d._recon_n_spin.maximum()))
        settle(0.4)
        click(r0, c0)
        shot(d, F, 'pca_spectrum_panel.png', panel(), margin=4)
        d._show_reconstructed_cb.setChecked(False)

        # NMF and MCR-ALS, 3 components - on baseline-corrected spectra, as
        # the help says (the raw Chlorella map sits on a ~670 offset, which
        # makes NMF/MCR-ALS components jagged); the raw ones come back after
        # the RGB overlay, for the ROI pictures
        import numpy as np
        from src.modules.data_analysis.automated_baseline_manager import AutomatedBaselineManager
        bm = AutomatedBaselineManager()
        raw_y = [s['y_scale'] for s in d.spectra]
        for s in d.spectra:
            y = np.asarray(s['y_scale'], dtype=float)
            s['y_scale'] = y - bm.calculate_arpls_baseline(y, 1e5)
        d._decomp_n_spin.setValue(3)
        compute(d._radio_nmf)
        if d._component_combo.count() > 1:
            d._component_combo.setCurrentIndex(1)
        click(r0, c0)
        shot(d, F, 'map_type_nmf.png')
        d._decomp_n_spin.setValue(3)
        compute(d._radio_mcr)
        if d._component_combo.count() > 1:
            d._component_combo.setCurrentIndex(1)
        click(r0, c0)
        shot(d, F, 'map_type_mcr.png')
        d._show_reconstructed_cb.setChecked(True)
        settle(0.6)
        shot(d, F, 'nmf_mcr_spectrum_panel.png', panel(), margin=4)
        d._show_reconstructed_cb.setChecked(False)

        # RGB overlay from the components above
        try:
            d._radio_rgb.setChecked(True)
            settle(0.4)
            for ch, (kind, comp) in zip(d._rgb_channel_widgets,
                                        (('mcr', 0), ('nmf', 1), ('nmf', 2))):
                i = ch['kind'].findData(kind)
                if i >= 0:
                    ch['kind'].setCurrentIndex(i)
                settle(0.2)
                if ch['comp'].count() > comp:
                    ch['comp'].setCurrentIndex(comp)
                ch['enable'].setChecked(True)
            settle(0.4)
            d._compute_map()
            settle(1.5)
            click(r0, c0)
            shot(d, F, 'rgb_overlay_result.png')
        except Exception:
            log(traceback.format_exc())

        for s, y in zip(d.spectra, raw_y):
            s['y_scale'] = y

        # ROI: a rectangle, its statistics and its spectra
        compute(d._radio_intensity)

        class Corner:
            pass
        e1, e2 = Corner(), Corner()
        e1.xdata, e1.ydata = cols * 0.3, rows * 0.3
        e2.xdata, e2.ydata = cols * 0.6, rows * 0.6
        for e in (e1, e2):
            e.inaxes = d._map_canvas.ax
            e.button = 1
        try:
            d._activate_roi()
            d._on_roi_selected(e1, e2)
            d._deactivate_roi()
            settle(0.4)
            e3, e4 = Corner(), Corner()
            e3.xdata, e3.ydata = cols * 0.65, rows * 0.1
            e4.xdata, e4.ydata = cols * 0.9, rows * 0.3
            for e in (e3, e4):
                e.inaxes = d._map_canvas.ax
                e.button = 1
            d._activate_roi()
            d._on_roi_selected(e3, e4)
            d._deactivate_roi()
        except Exception:
            log(traceback.format_exc())
        settle(0.8)
        shot(d, F, 'roi_drawn_rectangle.png')

        @on('ROI comparison statistics')
        def _(s):
            shot(s, F, 'roi_comparison_stats.png')
        d._act_roi_stats.trigger()
        w = window_titled('ROI comparison statistics', 2)
        if w is not None and any(s[0] == 'ROI comparison statistics' for s in SHOOTERS):
            shot(w, F, 'roi_comparison_stats.png')
            w.close()

        @on('ROI [')
        def _(v):
            v.resize(1046, 631)
            settle(0.8)
            shot(v, F, 'roi_spectra_viewer.png')
        d._act_view_roi.trigger()
        w = window_titled('ROI [', 2)
        if w is not None and any(s[0] == 'ROI [' for s in SHOOTERS):
            w.resize(1046, 631)
            settle(0.8)
            shot(w, F, 'roi_spectra_viewer.png')
            w.close()
    mc.run_visualization_analysis('2D map')


def part_peak_detection():
    """The Peaks window: tab Mark on the plot (Detect Peaks) and tab Band table -
    help Peaks."""
    F = 'peak_detection'
    mc = load([os.path.join(SYN, 'raman_2comp_clean.xlsx')],
              select=[0, 4, 5, 6, 7, 8, 14, 15, 16, 17, 18])
    mc.plot_spectra()
    settle(0.5)

    @on('Peaks')
    def _(d):
        d.resize(980, 560)
        settle(0.3)
        d.mark_button.click()
        settle(0.8)
        shot(d, F, 'peaks_mark_tab.png')
        tab(d, 'Band table')
        d.refine_check.setChecked(True)
        settle(1.0)
        d.band_value_combo.setCurrentText('Fitted FWHM')
        settle(0.8)
        shot(d, F, 'peak_list_band_table.png')
    mc.peak_detection_controller.show_dialog()
    settle(0.3)
    beside_the_plot(mc)


def beside_the_plot(mc):
    """User Guide, Windows beside the plot: the main window while the Peaks
    window is open (the orange line, the rest greyed out, the plot zoomed in
    on the marked peaks) with the Peaks window floating at its lower right,
    as on the screen."""
    from src.views.plot_only_mode import PlotOnlyLock, banner_text
    mc.view.resize(1360, 860)
    settle(0.5)

    @on('Peaks')
    def _(d):
        d.resize(760, 470)
        lock = PlotOnlyLock(mc.view, banner_text(d, "Peaks"), d).engage()
        try:
            settle(0.4)
            d.mark_button.click()
            settle(0.6)
            ax = mc.static_canvas.figure.axes[0]
            ax.set_xlim(640, 1300)                            # zoomed in: the toolbar works
            if ax.get_legend() is not None:
                ax.get_legend().set_visible(False)            # the marked peaks clearly visible
            mc.static_canvas.draw()
            settle(0.6)
            steady.park_mouse()
            main, window = mc.view.grab(), d.grab()
            top_left = lock.banner.mapTo(mc.view, lock.banner.rect().topLeft())
            line = QRect(top_left.x() - 2, top_left.y() - 2, lock.banner.width() + 4,
                         lock.banner.height() + 4)
        finally:
            lock.release()
            d.remove_marks_button.click()
        # the window floats at the lower right, partly beyond the main window
        from PyQt5.QtGui import QColor
        out_w = main.width() + window.width() // 3
        out_h = main.height() + window.height() // 5
        picture = QPixmap(out_w, out_h)
        picture.fill(QColor('#FFFFFF'))
        painter = QPainter(picture)
        painter.drawPixmap(0, 0, main)
        x, y = out_w - window.width() - 4, out_h - window.height() - 4
        for k, alpha in ((10, 18), (6, 30), (3, 45)):           # a soft shadow
            painter.fillRect(x + k, y + k, window.width(), window.height(), QColor(0, 0, 0, alpha))
        painter.drawPixmap(x, y, window)
        painter.setPen(QColor('#7A869A'))
        painter.drawRect(x, y, window.width() - 1, window.height() - 1)
        painter.end()
        save(picture, 'user_guide', 'beside_the_plot.png')
        # the orange line alone, readable
        dpr = main.devicePixelRatio() or 1
        save(main.copy(QRect(int(line.x() * dpr), int(line.y() * dpr), int(line.width() * dpr),
                             int(line.height() * dpr))), 'user_guide', 'beside_the_plot_line.png')
    mc.peak_detection_controller.show_dialog()


PARTS = {'peak_detection': part_peak_detection, 'user_guide': part_user_guide, 'map2d': part_map2d, 'melting_curve': part_melting_curve, 'svd_analysis': part_svd_analysis,
         'pca_scores': part_pca_scores, 'svd_baseline': part_svd_baseline,
         'band_ratio': part_band_ratio, 'nmf': part_nmf, 'mcr_als': part_mcr_als, 'data_range': part_data_range,
         'manual_baseline': part_manual_baseline, 'normalization': part_normalization,
         'x_axis_alignment': part_x_axis_alignment, 'svd_interpolation': part_svd_interpolation,
         'peak_fitting': part_peak_fitting, 'peak_fitting_own': part_peak_fitting_own,
         'interactive_subtraction': part_interactive_subtraction}


def main(names):
    for name in names or list(PARTS):
        log(f'== {name}')
        SHOOTERS.clear()
        try:
            PARTS[name]()
        except Exception:
            log(traceback.format_exc())
        for start, _ in SHOOTERS:
            log(f'   NOT TAKEN: {start}')
    for mc in MC:
        mc.autosave_controller.shutdown()
        mc.view.close()


try:
    main(sys.argv[1:])
    log('done')
finally:
    _log.close()
    button_icons.uninstall()
