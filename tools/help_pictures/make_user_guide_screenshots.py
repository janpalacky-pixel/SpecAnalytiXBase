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


def _composed(view, region, popups):
    """A picture of `region` of the window with the open menus drawn over it."""
    from PyQt5.QtGui import QPixmap
    for menu in popups:
        top_left = view.mapFromGlobal(menu.mapToGlobal(QPoint(0, 0)))
        region = region.united(QRect(top_left, menu.size()))
    region = region.adjusted(-4, -4, 4, 4)
    picture = view.grab(region)
    painter = QPainter(picture)
    for menu in popups:
        top_left = view.mapFromGlobal(menu.mapToGlobal(QPoint(0, 0)))
        painter.drawPixmap(top_left - region.topLeft(), menu.grab())
    painter.end()
    return picture


def moving_pictures(mc, view):
    from PyQt5.QtCore import QEvent, QPointF
    from PyQt5.QtGui import QKeyEvent, QMouseEvent
    lw = mc.spectra_list_widget
    lw.clearSelection()
    for row in (2, 5):
        lw.item(row).setSelected(True)
    settle()

    def mouse(kind, pos, buttons):
        event = QMouseEvent(kind, QPointF(pos), Qt.LeftButton, buttons, Qt.NoModifier)
        (lw.mousePressEvent if kind == QEvent.MouseButtonPress else lw.mouseMoveEvent)(event)
    start = QPoint(8, lw.visualItemRect(lw.item(2)).center().y())
    end = QPoint(70, lw.visualItemRect(lw.item(8)).center().y() + 3)
    mouse(QEvent.MouseButtonPress, start, Qt.LeftButton)
    mouse(QEvent.MouseMove, start + QPoint(0, 12), Qt.LeftButton)
    mouse(QEvent.MouseMove, end, Qt.LeftButton)
    settle()
    top = in_window(view, mc.sort_button)
    rows = in_window(view, lw)
    last = lw.visualItemRect(lw.item(min(lw.count() - 1, 11)))
    region = QRect(0, top.y() - 6, rows.right() + 8,
                   rows.y() + last.bottom() + 10 - (top.y() - 6))
    save(view.grab(region), 'moving_spectra.png')
    lw.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))   # nothing moves
    settle()

    # right-click > Order (the submenu open)
    def with_order(self, *args, **kwargs):
        self.popup(view.mapToGlobal(in_window(view, lw).topLeft() + QPoint(60, 40)))
        settle()
        action = next(a for a in self.actions() if a.text() == 'Order')
        self.setActiveAction(action)
        sub = action.menu()
        geo = self.actionGeometry(action)
        sub.popup(self.mapToGlobal(QPoint(self.width() - 4, geo.top())))
        settle()
        top = view.mapFromGlobal(self.mapToGlobal(QPoint(0, 0))).y()
        strip = QRect(in_window(view, lw).x(), top - 6, 30, 20)     # a little of the list
        menus.append(_composed(view, strip, [self, sub]))
        sub.hide()
        self.hide()
        return None
    old = QMenu.exec_
    QMenu.exec_ = with_order
    QMenu.exec = with_order
    try:
        mc.show_spectra_list_context_menu(QPoint(20, 20))
    finally:
        QMenu.exec_ = old
        QMenu.exec = old
    if menus:
        picture = menus.pop()
        # only the menus (and a little of the list around them)
        save(picture, 'order_menu.png')
    lw.clearSelection()
    settle()


def sort_menu_picture(mc, view):
    mc._fill_sort_menu()
    menu = mc.sort_menu
    menu.popup(mc.sort_button.mapToGlobal(QPoint(0, mc.sort_button.height())))
    settle()
    props = next(a for a in menu.actions() if a.text().startswith('By a property'))
    menu.setActiveAction(props)
    sub = props.menu()
    geo = menu.actionGeometry(props)
    sub.popup(menu.mapToGlobal(QPoint(menu.width() - 4, geo.top())))
    settle()
    row = in_window(view, mc.sort_button).united(in_window(view, mc.checkBox_reverse_order))
    row = QRect(0, row.y() - 1, row.right() + 40, row.height() + 2)
    save(_composed(view, row, [menu, sub]), 'sort_menu.png')
    sub.hide()
    menu.hide()
    settle()


def wait(seconds):
    """Let timers run (e.g. the publication window's preview, 250 ms)."""
    import time
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


class _At:
    """A right-click on the plot at (x, y), as the labels' menu gets it."""
    button = 3

    def __init__(self, ax, x, y):
        self.inaxes, self.xdata, self.ydata = ax, float(x), float(y)


def publication_pictures(mc, view):
    """Labels on the main plot (two band labels, a text, a chosen arrow with
    its two squares), the Save plot for publication window (Page tab with the
    preview; the Labels tab with the table) and the text editor."""
    from src.modules.visualization.plot_notes import peak_top
    load(mc, RAMAN)
    lw = mc.spectra_list_widget
    ids = [lw.item(i).data(Qt.UserRole) or lw.item(i).text() for i in range(4, 8)]
    mc.select_ids(ids)                       # sp005 - sp008: similar heights
    plot_type(mc, 'Overlay plot')
    notes = mc.plot_notes_controller
    notes.clear()
    ax = notes.target_axes(mc.static_canvas.figure)
    curves = mc.plot_cursor_controller._curves(ax)
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    notes.add_at('band', _At(ax, 785, 0), text='785')
    notes.add_at('band', _At(ax, 1092, 0),
                 text='1092 PO$\\mathregular{_{2}}$$\\mathregular{^{-}}$')
    notes.add_at('text', _At(ax, x0 + 0.78 * (x1 - x0), y0 + 0.72 * (y1 - y0)),
                 text='DNA, 4 concentrations')         # above the curves, right
    top = peak_top(curves, 1490, (x0, x1))
    arrow = notes.add_at('arrow', _At(ax, 1490, top if top is not None else y0),
                         text='G, A')
    notes.select(arrow)                      # chosen: its two ends as small squares
    settle()
    save(view.grab(in_window(view, view.graphicsView)), 'plot_labels.png')
    notes.select(None)
    settle()

    from src.views.dialogs.visualization.publication_dialog import PublicationDialog
    dlg = PublicationDialog(mc.static_canvas.figure, view,
                            preferences=mc.autosave_controller.preferences, notes=notes)
    dlg.resize(1500, 860)
    dlg.show()
    wait(1.5)
    save(dlg.grab(), 'publication_window.png')
    dlg.tabs.setCurrentWidget(dlg.tab_pages['Labels'])
    dlg.resize(1500, 600)                    # the table without much empty room
    dlg.splitter.setSizes([780, 720])        # wide enough for the table's columns
    wait(0.8)
    save(dlg.splitter.widget(0).grab(), 'publication_labels_tab.png')
    dlg.close()
    settle()

    from src.views.dialogs.misc.rich_text import RichTextDialog
    ed = RichTextDialog('PO$\\mathregular{_{2}}$$\\mathregular{^{-}}$ band, 1092 '
                        'cm$\\mathregular{^{-1}}$', view, "Label the band",
                        "Label (e.g. the band's position or a name):")
    ed.resize(460, 260)
    ed.show()
    wait(0.6)
    save(ed.grab(), 'rich_text_editor.png')
    ed.close()
    notes.clear()
    settle()


def plot_mouse_pictures(mc, view):
    """The mouse on the plot: a clicked line (thicker, its row of the list
    bold with a yellow frame) and a spectrum
    hidden with a click on its name in the legend (the name pale)."""
    from matplotlib.backend_bases import MouseEvent
    load(mc, RAMAN)
    lw = mc.spectra_list_widget
    ids = [lw.item(i).data(Qt.UserRole) or lw.item(i).text() for i in range(4, 8)]
    mc.select_ids(ids)                       # sp005 - sp008
    plot_type(mc, 'Overlay plot')
    canvas = mc.static_canvas
    canvas.draw()
    m = mc.plot_mouse_controller
    ax = canvas.figure.axes[0]
    line = next(l for l in m.data_lines(ax) if str(l.get_label()).endswith('sp006'))
    xs, ys = line.get_xdata(), line.get_ydata()
    k = int(len(xs) * 0.62)
    x, y = ax.transData.transform((xs[k], ys[k]))
    # the click on the line: a press and a release at the same place (a line
    # is marked on the release - a press that moves on drags the plot)
    for name in ('button_press_event', 'button_release_event'):
        canvas.callbacks.process(name, MouseEvent(name, canvas, x, y, button=1))
    settle()
    canvas.draw()
    settle()
    # (the name that appears when pointing at the line is a tooltip: Windows
    # fades it in, so it is not in a picture taken at once - the help says it)
    plot = in_window(view, view.graphicsView)
    lst = in_window(view, view.spectrum_selection_frame)
    region = QRect(QPoint(lst.left(), plot.top()), QPoint(plot.right(), plot.bottom()))
    save(view.grab(region.adjusted(-4, -4, 4, 4)), 'plot_mouse_line.png')
    m.mark(None)
    settle()
    # a click on a name in the legend: that spectrum hidden, its name pale
    m.toggle(str(next(l for l in m.data_lines(ax)
                      if str(l.get_label()).endswith('sp007')).get_label()))
    canvas.draw()
    settle()
    save(view.grab(in_window(view, view.graphicsView)), 'plot_mouse_legend.png')
    m.toggle(next(iter(m.hidden)))
    settle()


def main():
    mc = MainController()
    view = mc.view
    view.move(0, 0)
    view.resize(1910, 1025)
    mc.show()
    settle()

    # 0. the start page (no spectra yet), with two shipped files as recent ones
    for path in (TBA, RAMAN):
        mc.autosave_controller.recent.add(path, 'data')
    mc._update_start_page()
    settle()
    save(view.grab(), 'start_page.png')

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

    class Click:                      # on the plot: "Label the band here (1004)" active
        x, y, button = 300, 300, 3
        inaxes, xdata, ydata = mc.static_canvas.figure.axes[0], 1004.0, 0.0
    mc.show_context_menu(Click())
    if menus:
        save(menus.pop(), 'plot_context_menu.png')
    mc.show_spectra_list_context_menu(QPoint(20, 20))
    if menus:
        save(menus.pop(), 'spectrum_list_context_menu.png')

    # 3a. moving spectra: two selected ones dragged by the handle (the blue
    #     line), and right-click > Order
    moving_pictures(mc, view)

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

    # 5b. Sort: > By a property (temperature_C read from the file)
    sort_menu_picture(mc, view)

    # 6. labels on the plot, Save plot for publication, the text editor
    try:
        publication_pictures(mc, view)
    except Exception:
        log(traceback.format_exc())

    # 7. the mouse on the plot: a clicked line, a spectrum hidden in the legend
    try:
        plot_mouse_pictures(mc, view)
    except Exception:
        log(traceback.format_exc())

    mc.autosave_controller.shutdown()
    view.close()


try:
    main()
    log('done')
except Exception:
    log(traceback.format_exc())
finally:
    _log.close()
