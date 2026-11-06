"""The start page over the empty plot: shown while no spectra are loaded,
gone as soon as there are some, back when all are deleted. Its buttons do
what the menu commands do; the recent files are listed."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QAction, QApplication, QLabel, QMenu, QWidget

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CD = os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD_spectra_TBA.txt')


def test_the_page_alone():
    from src.views.start_page import StartPage
    host = QWidget()
    host.resize(800, 600)
    done, opened = [], []
    actions = {k: QAction(k, host) for k in ('import', 'snapshot', 'quick_start')}
    for k, a in actions.items():
        a.triggered.connect(lambda _c=False, k=k: done.append(k))
    recent = [{'path': os.path.join('C:', 'data', 'a.txt'), 'kind': 'file'},
              {'path': os.path.join('C:', 'work', 'b.sax'), 'kind': 'snapshot'}]
    page = StartPage(host, actions, test_menu=QMenu(), recent=lambda: recent,
                     open_recent=opened.append)
    host.show()
    page.show_if(True)
    app.processEvents()
    assert page.isVisible() and page.geometry() == host.rect()
    for k in ('import', 'snapshot', 'quick_start'):
        page.buttons[k].click()
    assert done == ['import', 'snapshot', 'quick_start']
    texts = [b.text() for b in page.recent_buttons]
    assert texts[0].startswith('a.txt') and '(snapshot)' in texts[1] and 'in work' in texts[1]
    page.recent_buttons[1].click()
    assert opened == [recent[1]]
    page.show_if(False)
    assert not page.isVisible()
    host.hide()


def test_in_the_main_window(tmp_path, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    mc = MainController()
    mc.view.show()
    try:
        app.processEvents()
        assert mc.start_page.isVisible()                      # nothing loaded
        mc.import_controller._run_import(clear_first=True, file_paths=[CD])
        app.processEvents()
        assert mc.spectra_list_widget.count() > 0 and not mc.start_page.isVisible()
        mc.spectra_list_widget.clear()                        # all gone: back
        app.processEvents()
        assert mc.start_page.isVisible()
    finally:
        mc.autosave_controller.shutdown()
        mc.view.hide()
        mc.view.deleteLater()
