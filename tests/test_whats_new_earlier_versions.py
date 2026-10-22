"""The What's New window at the start of a new version shows the "in brief"
list of that version and, below it, the lists of all earlier versions,
newest first (e.g. 1.6.0, 1.5.1, 1.5.0 under 1.7.0) - the same for
everyone, also for someone who skipped versions."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from src.help import whats_new_help as wn

app = QApplication.instance() or QApplication([])


def _notes(folder, versions):
    for v in versions:
        (folder / f'{v}.md').write_text(f"## What's new in {v}\n\n### {v} in brief\n"
                                        f"- **Feature of {v}**\n", encoding='utf-8')
    return str(folder)


def test_earlier_versions(tmp_path):
    folder = _notes(tmp_path, ['1.5.0', '1.5.1', '1.6.0', '1.10.0'])
    assert wn.earlier_versions('1.5.1', folder) == ['1.5.0']
    assert wn.earlier_versions('1.10.0', folder) == ['1.6.0', '1.5.1', '1.5.0']    # 10 > 6
    assert wn.earlier_versions('1.5.0', folder) == []
    assert wn.earlier_versions('1.7.0', folder) == ['1.6.0', '1.5.1', '1.5.0']


def test_the_window_shows_all_earlier_versions_below(tmp_path, monkeypatch):
    folder = _notes(tmp_path, ['1.5.0', '1.5.1', '1.6.0', '1.7.0'])
    monkeypatch.setattr(wn, 'resource_path', lambda rel: folder if rel == wn._DIR
                        else os.path.join(folder, os.path.basename(rel)))
    from src.views.dialogs.misc.whats_new_dialog import WhatsNewDialog
    dlg = WhatsNewDialog(None, '1.7.0')
    text = dlg.text.toPlainText()
    order = [text.index(f'Feature of {v}') for v in ('1.7.0', '1.6.0', '1.5.1', '1.5.0')]
    assert order == sorted(order)                                    # newest first
    assert 'what was new in 1.6.0' in text and 'what was new in 1.5.0' in text
    assert dlg.windowTitle() == "What's new in SpecAnalytiXBase 1.7.0"
    first = WhatsNewDialog(None, '1.5.0')                            # nothing before it
    assert 'Earlier' not in first.text.toPlainText()
