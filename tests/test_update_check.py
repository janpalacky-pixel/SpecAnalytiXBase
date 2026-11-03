"""Is a newer version released? At the start (setting "Check for a new
version at the start", on by default) and Help > Check for a new version...
GitHub is never asked in the tests: the answer is given."""
import io
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.misc import update_check as uc

app = QApplication.instance() or QApplication([])


def test_versions_are_compared_as_numbers():
    assert uc.parse_version('v1.7.0') == (1, 7, 0) and uc.parse_version('1.10') == (1, 10, 0)
    assert uc.is_newer('v1.10.0', '1.9.3') and not uc.is_newer('1.7.0', '1.7.0')
    assert not uc.is_newer('1.6.0', '1.7.0') and not uc.is_newer('nonsense', '1.7.0')


class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_the_latest_release_from_the_github_answer():
    seen = []

    def opener(request, timeout):
        seen.append((request.full_url, request.get_header('User-agent'), timeout))
        return _Answer(json.dumps({'tag_name': 'v1.8.0', 'name': 'SpecAnalytiXBase 1.8.0',
                                   'html_url': 'https://example.org/r', 'body': 'notes'}).encode())
    release = uc.fetch_latest('1.7.0', opener=opener)
    assert release == {'version': '1.8.0', 'url': 'https://example.org/r',
                       'name': 'SpecAnalytiXBase 1.8.0', 'notes': 'notes'}
    assert seen[0][0] == uc.API_URL and seen[0][1] == 'SpecAnalytiXBase/1.7.0'

    def offline(request, timeout):
        raise OSError("no network")
    assert uc.fetch_latest('1.7.0', opener=offline) is None
    assert uc.fetch_latest('1.7.0', opener=lambda r, timeout: _Answer(b'not json')) is None
    draft = json.dumps({'tag_name': 'v2.0.0', 'draft': True}).encode()
    assert uc.fetch_latest('1.7.0', opener=lambda r, timeout: _Answer(draft)) is None


def test_newer_newest_or_unknown():
    new = {'version': '1.8.0', 'url': 'u', 'name': 'n', 'notes': ''}
    assert uc.newer_release('1.7.0', lambda v: new) == (new, None)
    assert uc.newer_release('1.8.0', lambda v: new) == (None, 'newest')
    assert uc.newer_release('1.7.0', lambda v: None) == (None, 'unknown')


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    from src.controllers.core.main_controller import MainController
    controller = MainController()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


NEW = {'version': '1.8.0', 'url': 'https://example.org/r', 'name': 'SpecAnalytiXBase 1.8.0',
       'notes': ''}


def test_at_the_start_a_newer_version_is_announced_and_can_be_skipped(mc, monkeypatch):
    shown = []

    def exec_(box):
        shown.append(box.text())
        skip = [b for b in box.buttons() if b.text() == 'Skip this version'][0]
        monkeypatch.setattr(box, 'clickedButton', lambda: skip)
        return 0
    monkeypatch.setattr(QMessageBox, 'exec_', exec_)
    mc.check_for_update('1.7.0', automatic=True, fetch=lambda v: NEW, wait=True)
    assert shown and '1.8.0' in shown[0] and 'you have 1.7.0' in shown[0]
    assert mc.autosave_controller.preferences.get('update_skipped') == '1.8.0'
    mc.check_for_update('1.7.0', automatic=True, fetch=lambda v: NEW, wait=True)
    assert len(shown) == 1                                         # skipped: not again
    # switched off in the Settings: no question at all
    mc.autosave_controller.preferences.set('update_check', False)
    assert mc.check_for_update('1.7.0', automatic=True, fetch=lambda v: NEW) is None


def test_at_the_start_nothing_when_there_is_no_answer_or_no_newer(mc, monkeypatch):
    calls = []
    monkeypatch.setattr(QMessageBox, 'exec_', lambda box: calls.append(box.text()))
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(
        lambda *a, **k: calls.append(a[2])))
    mc.check_for_update('1.7.0', automatic=True, fetch=lambda v: None, wait=True)
    mc.check_for_update('1.8.0', automatic=True, fetch=lambda v: NEW, wait=True)
    assert calls == []


def test_help_menu_always_says_the_result(mc, monkeypatch):
    said = []
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(
        lambda *a, **k: said.append(a[2])))
    monkeypatch.setattr(QMessageBox, 'exec_', lambda box: said.append(box.text()))
    mc.check_for_update('1.8.0', automatic=False, fetch=lambda v: NEW, wait=True)
    mc.check_for_update('1.7.0', automatic=False, fetch=lambda v: None, wait=True)
    mc.check_for_update('1.7.0', automatic=False, fetch=lambda v: NEW, wait=True)
    assert 'newest version (1.8.0)' in said[0]
    assert 'Could not find out' in said[1] and uc.RELEASES_URL in said[1]
    assert '1.8.0' in said[2]
    # (a version skipped at the start is still shown when asked)
    mc.autosave_controller.preferences.set('update_skipped', '1.8.0')
    mc.check_for_update('1.7.0', automatic=False, fetch=lambda v: NEW, wait=True)
    assert len(said) == 4


def test_menu_entry_with_icon_and_the_setting(mc):
    v = mc.view
    assert v.actionCheckUpdate in v.menuHelp.actions()
    assert not v.actionCheckUpdate.icon().isNull()
    from src.modules.misc import user_settings as us
    st = [s for s in us.SETTINGS if s.id == 'update_check'][0]
    assert st.default is True and 'update_check' in us.KNOWN_KEYS
    assert 'help://installation#updates' == us.HELP['update_check'][1]
