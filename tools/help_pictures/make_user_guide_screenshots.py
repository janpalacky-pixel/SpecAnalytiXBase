"""Makes the User Guide pictures of the main window from the real program
(run from the repo root, on Windows so they have the Windows look):
    python tools/help_pictures/make_user_guide_screenshots.py
(make_all_help_pictures.bat runs it with the others).
Writes into resources/images/help_screenshots/user_guide/ (the old ones are
in git) and a log into tools/logs/pictures_user_guide.txt. Uses a
temporary settings folder, so your preferences, recent files and automatic
saves are not touched. Do not use the mouse while it runs (~30 s)."""
import os
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)                     # the repository: paths below are relative to it
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools', 'help_pictures'))
import steady                      # the same picture every run (see steady.py)
steady.start()
os.environ['SPECANALYTIXBASE_DATA_DIR'] = tempfile.mkdtemp(prefix='sax_shots_')
OUT = os.environ.get('SAX_SHOTS_OUT') or os.path.join('resources', 'images', 'help_screenshots', 'user_guide')
LOG = os.path.join('tools', 'logs', 'pictures_user_guide.txt')
os.makedirs(os.path.dirname(LOG), exist_ok=True)
_log = open(LOG, 'w', encoding='utf-8')


def log(*parts):
    text = ' '.join(str(p) for p in parts)
    print(text)
    _log.write(text + '\n')
    _log.flush()


from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QMenu, QMessageBox

app = QApplication(sys.argv)
app.setWindowIcon(QIcon(os.path.join('resources', 'icons', 'app_icon.ico')))
from src.views.theme import apply_saved_theme
apply_saved_theme(app)
from src.views import button_icons
button_icons.install(app)          # icons on the dialog buttons, as in the program

for name in ('information', 'warning', 'critical'):
    setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
from src.views.dialogs.misc import import_dialog
import_dialog.ImportDialog.run = staticmethod(
    lambda view, settings, file_paths=None: (True, list(file_paths),
                                             [{'jws_selected_channels': [0]} for _ in file_paths]))

from src.controllers.core.main_controller import MainController
steady.fixed_clock()
steady.park_mouse()

REAL = os.path.join('resources', 'test_data', 'real')
RAMAN = os.path.join(REAL, 'Raman_DNA_conc_dep.txt')
TBA = os.path.join(REAL, 'CD_spectra_TBA.txt')
import glob
JWB = sorted(glob.glob(os.path.join(REAL, 'CD melting', '*.jwb')))[0]


def settle(n=6):
    for _ in range(n):
        app.processEvents()


def save(pixmap, name):
    path = os.path.join(OUT, name)
    ok = pixmap.save(path, 'PNG')
    log(('saved ' if ok else 'FAILED ') + path, pixmap.width(), 'x', pixmap.height())


def load(mc, path):
    mc.import_controller._run_import(clear_first=True, file_paths=[path])
    mc.spectrum_selector.select_all_items()
    settle()


def plot_type(mc, text):
    mc.view.comboBox_plot_type_choice.setCurrentText(text)
    settle()
    mc.plot_spectra()
    settle()


def in_window(view, widget):
    """The widget's rectangle in window coordinates."""
    return QRect(widget.mapTo(view, QPoint(0, 0)), widget.size())


def plot_and_panel_rect(view):
    """The plot with the panel below it (no spectra list), in window coordinates."""
    r = in_window(view, view.graphicsView)
    for box in (view.groupBox_basic_plot_options, view.groupBox_link_axes,
                view.groupBox_spectra_visualization, view.groupBox_operations):
        if box.isVisible():
            r = r.united(in_window(view, box))
    return r.adjusted(-4, -4, 4, 4)


menus = []


def capture_exec(self, *args, **kwargs):
    """QMenu.exec_ that shows the menu, keeps a picture of it and closes it."""
    self.popup(QPoint(200, 200))
    settle()
    menus.append(self.grab())
    self.hide()
    return None


def main():
    mc = MainController()
    view = mc.view
    view.move(0, 0)
    view.resize(1910, 1025)
    mc.show()
    settle()

    # 1. the main window
    load(mc, RAMAN)
    plot_type(mc, 'Overlay plot')
    save(view.grab(), 'main_window_overview.png')

    # 2. the plot types (plot + the panel below it), in a smaller window
    #    so the text stays readable when the help shows them 700 px wide
    view.resize(1500, 900)
    settle()
    load(mc, TBA)
    for text, name in (('Overlay plot', 'plot_type_overlay.png'),
                       ('Grid plot', 'plot_type_grid.png'),
                       ('Waterfall plot', 'plot_type_waterfall.png'),
                       ('Mean \u00b1 SD', 'plot_type_mean_sd.png'),
                       ('Difference', 'plot_type_difference.png'),
                       ('Heatmap', 'plot_type_heatmap.png')):
        if text == 'Grid plot':                  # 12 small panels, without legends
            view.show_legend_checkBox.setChecked(False)
            view.number_of_rows_spinBox.setValue(4)
            view.number_of_columns_spinBox.setValue(3)
        plot_type(mc, text)
        save(view.grab(plot_and_panel_rect(view)), name)
        if text == 'Grid plot':
            view.show_legend_checkBox.setChecked(True)
    plot_type(mc, 'Overlay plot')

    # 3. the right-click menus
    QMenu.exec_ = capture_exec
    QMenu.exec = capture_exec

    class Click:
        x, y, button, inaxes, xdata, ydata = 300, 300, 3, None, None, None
    mc.show_context_menu(Click())
    if menus:
        save(menus.pop(), 'plot_context_menu.png')
    mc.show_spectra_list_context_menu(QPoint(20, 20))
    if menus:
        save(menus.pop(), 'spectrum_list_context_menu.png')

    # 3b. the buttons below the spectra list
    from PyQt5.QtWidgets import QAbstractButton
    names = {'Select All', 'Unselect All', 'Select spectra', 'Rename', 'Show Metadata',
             'Plot Properties\u2026', 'Interactive Update', '\u2630 Legend'}
    parts = [w for w in view.findChildren(QAbstractButton)
             if w.isVisible() and w.text() in names and in_window(view, w).x() < view.width() // 4]
    if parts:
        r = in_window(view, parts[0])
        for w in parts[1:]:
            r = r.united(in_window(view, w))
        r = QRect(0, r.y(), r.right() + 1, r.height()).adjusted(4, -8, 50, 8)
        save(view.grab(r), 'spectrum_list_panel.png')

    # 4. the Spectra Processing panel with the list of operations open
    combo = view.available_operations_comboBox
    combo._open_popup()
    settle()
    popup = combo._popup
    box = in_window(view, view.groupBox_operations)
    popup_top_left = view.mapFromGlobal(popup.mapToGlobal(QPoint(0, 0)))
    region = box.united(QRect(popup_top_left, popup.size())).adjusted(-6, -6, 6, 6)
    picture = view.grab(region)
    painter = QPainter(picture)
    painter.drawPixmap(popup_top_left - region.topLeft(), popup.grab())
    painter.end()
    save(picture, 'spectra_processing_panel.png')
    combo._close_popup()
    settle()

    # 5. the Spectrum properties window (temperature_C from the file, pH typed in)
    load(mc, JWB)
    from src.views.dialogs.misc.spectrum_properties_dialog import SpectrumPropertiesDialog
    dlg = SpectrumPropertiesDialog(view, mc.selected_spectra)
    dlg.resize(760, 520)
    dlg.show()
    settle()
    dlg.add_property('pH')
    dlg.table.clearSelection()
    dlg.fill_series(start=7.4, step=0)
    dlg.table.setCurrentCell(-1, -1)
    settle()
    save(dlg.grab(), 'spectrum_properties_dialog.png')
    dlg.apply_button.setEnabled(False)
    dlg.close()

    mc.autosave_controller.shutdown()
    view.close()


try:
    main()
    log('done')
except Exception:
    log(traceback.format_exc())
finally:
    _log.close()
