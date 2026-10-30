"""A tool window beside the main plot (src/views/plot_only_mode.py): while it
is open, only the plot of the main window can be used (zoom, pan, save);
everything else is greyed out and comes back as it was when it closes."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QAction, QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                             QSizePolicy,
                             QListWidget, QMainWindow, QMessageBox, QPushButton, QShortcut,
                             QVBoxLayout, QWidget)

from src.views import plot_only_mode as pom

app = QApplication.instance() or QApplication([])


def _main():
    main = QMainWindow()
    central = QWidget()
    layout = QVBoxLayout(central)
    main.spectra = QListWidget()
    main.button = QPushButton("Import")
    main.already_off = QPushButton("Off before")
    main.already_off.setEnabled(False)
    main.graphicsView = QWidget()
    inner = QVBoxLayout(main.graphicsView)
    main.zoom = QPushButton("Zoom")                     # stands for the plot's toolbar
    inner.addWidget(main.zoom)
    for w in (main.spectra, main.button, main.already_off, main.graphicsView):
        layout.addWidget(w)
    main.setCentralWidget(central)
    main.action = QAction("Open", main)
    main.action.setShortcut(QKeySequence("Ctrl+O"))
    main.menuBar().addMenu("File").addAction(main.action)
    main.shortcut = QShortcut(QKeySequence("Ctrl+K"), main)
    main.show()
    return main


def _run_and_look(main, dialog, look, name="Peaks"):
    seen = {}

    def during():
        seen.update(look())
        dialog.accept()
    QTimer.singleShot(0, during)
    result = pom.run_beside_plot(dialog, name)
    return result, seen


def test_only_the_plot_can_be_used_while_the_window_is_open():
    main = _main()
    dialog = QDialog(main)
    result, seen = _run_and_look(main, dialog, lambda: {
        'list': main.spectra.isEnabled(), 'button': main.button.isEnabled(),
        'menu': main.menuBar().isEnabled(), 'action': main.action.isEnabled(),
        'shortcut': main.shortcut.isEnabled(), 'zoom': main.zoom.isEnabled(),
        'dialog': dialog.isEnabled() and dialog.isVisible() and not dialog.isModal(),
        'banner': pom.plot_only(main).banner.label.text(),
        'closed': main.close()})
    assert result == QDialog.Accepted
    assert not (seen['list'] or seen['button'] or seen['menu'] or seen['action']
                or seen['shortcut'])
    assert seen['zoom'] and seen['dialog']
    assert 'Peaks window is open' in seen['banner'] and 'zoom' in seen['banner']
    assert 'Basic plot options' in seen['banner']
    assert seen['closed'] is False and main.isVisible()          # not closed under the window
    # everything back as it was
    assert main.spectra.isEnabled() and main.button.isEnabled() and main.action.isEnabled()
    assert main.shortcut.isEnabled() and main.menuBar().isEnabled()
    assert not main.already_off.isEnabled()                       # was off before: stays off
    assert pom.plot_only(main) is None
    app.processEvents()
    assert not [w for w in main.findChildren(QLabel) if w.text().startswith('The Peaks window')]
    main.close()


def test_a_window_driven_by_a_test_is_left_to_it():
    main = _main()
    dialog = QDialog(main)
    dialog.exec_ = lambda: 7
    assert pom.run_beside_plot(dialog, "x") == 7 and pom.plot_only(main) is None
    main.close()


def test_without_a_plot_the_window_is_simply_modal(monkeypatch):
    dialog = QDialog(None)
    monkeypatch.setattr(QDialog, 'exec_', lambda self: 3)
    assert pom.run_beside_plot(dialog, "x") == 3


def test_a_mouse_grab_left_by_the_opening_click_is_let_go():
    """On Windows the main window could keep the mouse captured after the
    click that opened the window - every click then went to the main window,
    the window's own Close and X did nothing."""
    main = _main()
    main.button.grabMouse()                             # stands for the stuck capture
    dialog = QDialog(main)
    seen = {}

    def during():
        seen['grabber'] = QWidget.mouseGrabber()
        dialog.reject()
    QTimer.singleShot(0, during)
    pom.run_beside_plot(dialog)
    assert seen['grabber'] is None
    main.close()


def test_apply_is_added_next_to_ok():
    applied = []
    plain = QDialog()
    row = QHBoxLayout(plain)
    for text in ("Reset to Default", "OK", "Cancel"):
        row.addWidget(QPushButton(text))
    b = pom.add_apply_button(plain, lambda: applied.append(1))
    texts = [row.itemAt(i).widget().text() for i in range(row.count())]
    assert texts == ["Reset to Default", "Apply", "OK", "Cancel"]
    b.click()
    boxed = QDialog()
    QVBoxLayout(boxed).addWidget(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
    pom.add_apply_button(boxed, lambda: applied.append(2)).click()
    assert applied == [1, 2] and boxed.apply_button.text() == "Apply"


# --- in the program -----------------------------------------------------------------------

def _program(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    mc = MainController()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mc.import_controller._run_import(
        clear_first=True, file_paths=[os.path.join(root, 'resources', 'test_data', 'real',
                                                   'CD_spectra_TBA.txt')])
    mc.spectrum_selector.select_all_items()
    mc.view.show()
    app.processEvents()
    return mc


def test_the_peaks_window_and_the_plot_settings_windows_run_beside_the_plot(tmp_path,
                                                                             monkeypatch):
    mc = _program(tmp_path, monkeypatch)
    view = mc.view
    seen = []

    def look_then_close():
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QDialog) and w.isVisible():
                menus = []
                monkeypatch.setattr(mc, 'show_context_menu', lambda e: menus.append(e))

                class Right:
                    button = 3
                mc.handle_mouse_click(Right())
                seen.append((w.windowTitle(), mc.spectra_list_widget.isEnabled(),
                             mc.static_toolbar.isEnabled(), mc.static_canvas.isEnabled(),
                             bool(menus), getattr(w, 'apply_button', None) is not None))
                w.reject()
                return
        QTimer.singleShot(20, look_then_close)

    for open_window in (mc.peak_detection_controller.show_dialog,
                        mc.axis_properties_controller.show_dialog,
                        mc.grid_properties_controller.show_dialog,
                        mc.legend_properties_controller.show_dialog,
                        mc.constrained_layout_controller.show_dialog):
        QTimer.singleShot(0, look_then_close)
        open_window()
        assert mc.spectra_list_widget.isEnabled()                 # back after closing
    assert len(seen) == 5
    for title, list_on, toolbar_on, canvas_on, menu, has_apply in seen:
        assert not list_on and toolbar_on and canvas_on and not menu, title
    assert [s[5] for s in seen] == [False, True, True, True, True]   # Apply in the 4
    mc.autosave_controller.shutdown()
    view.deleteLater()


def test_apply_in_axis_properties_shows_the_settings_at_once(tmp_path, monkeypatch):
    mc = _program(tmp_path, monkeypatch)
    applied = []
    monkeypatch.setattr(mc.axis_properties_controller, 'apply_settings',
                        lambda: applied.append(dict(mc.axis_manager.get_current_settings())))

    def apply_then_cancel():
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QDialog) and w.isVisible() and hasattr(w, 'apply_button'):
                w.apply_button.click()
                w.reject()
                return
        QTimer.singleShot(20, apply_then_cancel)
    QTimer.singleShot(0, apply_then_cancel)
    mc.axis_properties_controller.show_dialog()
    assert len(applied) == 1                                       # Apply, then Cancel
    mc.autosave_controller.shutdown()
    mc.view.deleteLater()


def test_the_line_above_the_plot_is_slim_and_can_hide_or_close_the_window():
    main = _main()
    options = QPushButton("Overlay plot")
    main.groupBox_basic_plot_options = QWidget()
    QVBoxLayout(main.groupBox_basic_plot_options).addWidget(options)
    main.centralWidget().layout().addWidget(main.groupBox_basic_plot_options)
    main.resize(1300, 700)                                  # as wide as the program's window
    app.processEvents()
    dialog = QDialog(main)
    seen = {}

    def during():
        lock = pom.plot_only(main)
        app.processEvents()
        seen['height'] = lock.banner.height()
        seen['button'] = lock.toggle_button.sizeHint().height()
        seen['fixed'] = lock.banner.sizePolicy().verticalPolicy() == QSizePolicy.Fixed
        seen['options'] = options.isEnabled()
        lock.toggle_button.click()                          # Hide the window
        seen['hidden'] = not dialog.isVisible() and lock.toggle_button.text() == "Show the window"
        lock.toggle_button.click()                          # Show the window
        seen['shown'] = dialog.isVisible() and lock.toggle_button.text() == "Hide the window"
        lock.close_button.click()                           # Close the window
    QTimer.singleShot(0, during)
    result = pom.run_beside_plot(dialog)
    assert result == QDialog.Rejected and seen['options'] and seen['hidden'] and seen['shown']
    # a slim line of fixed height (one or two lines of text beside its buttons),
    # not the big box it was (it took about a third of the plot)
    assert seen['fixed'] and seen['height'] <= 4 * seen['button']
    main.close()


def test_the_peaks_marks_come_back_when_the_plot_is_drawn_again(tmp_path, monkeypatch):
    mc = _program(tmp_path, monkeypatch)
    seen = {}

    def during():
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QDialog) and w.isVisible() and hasattr(w, 'mark_button'):
                w.mark_button.click()
                marks = lambda: sum(len(v) for v in mc.peak_detection_controller.peak_detector
                                    .peak_indices.values())
                seen['before'] = marks()
                seen['options'] = mc.view.groupBox_basic_plot_options.isEnabled()
                mc.view.comboBox_plot_type_choice.setCurrentText("Waterfall plot")  # redrawn
                app.processEvents()
                seen['after'] = marks()
                seen['banner'] = mc.view.plot_only_lock.banner.isVisible()
                w.reject()
                return
        QTimer.singleShot(20, during)
    QTimer.singleShot(0, during)
    mc.peak_detection_controller.show_dialog()
    assert seen['options'] and seen['before'] > 0 and seen['after'] > 0 and seen['banner']
    mc.autosave_controller.shutdown()
    mc.view.deleteLater()


def test_other_windows_open_beside_the_plot_too(tmp_path, monkeypatch):
    mc = _program(tmp_path, monkeypatch)
    seen = []

    def during():
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QDialog) and w.isVisible():
                seen.append((w.windowTitle(), mc.spectra_list_widget.isEnabled(),
                             mc.view.plot_only_lock is not None))
                w.reject()
                return
        QTimer.singleShot(20, during)
    QTimer.singleShot(0, during)
    mc.data_table_controller.show_dialog(mc.selected_spectra)
    QTimer.singleShot(0, during)
    mc.line_colours_controller.show_dialog()
    assert len(seen) == 2 and all(not on and locked for _, on, locked in seen)
    assert seen[0][0].startswith('Data table')
    mc.autosave_controller.shutdown()
    mc.view.deleteLater()


def test_the_help_explains_it_with_pictures_and_the_windows_link_to_it():
    import re
    from src.help import help_window as hw
    from src.help.user_guide_help import get_user_guide_help_content
    guide = get_user_guide_help_content()
    part = guide[guide.index('id="beside-the-plot"'):guide.index('id="legend-panel"')]
    assert 'beside_the_plot.png' in part and 'beside_the_plot_line.png' in part
    assert 'Hide the window' in part and '$BESIDE' not in part            # pictures resolved
    page = hw.with_beside_plot_note('data_range', '<html><h1>Data range</h1><p>x</p></html>')
    assert re.search(r'</h1><p[^>]*>While this window is open', page)
    assert 'help://user_guide#beside-the-plot' in page
    assert hw.with_beside_plot_note('user_guide', '<h1>U</h1>') == '<h1>U</h1>'
    assert hw.BESIDE_PLOT_TOPICS <= set(hw._REGISTRY)
