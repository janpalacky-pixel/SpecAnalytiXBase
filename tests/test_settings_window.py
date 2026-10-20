"""File -> Settings and saved items...: every remembered setting with its current
and default value, reset selected / all (never touching saved items); the saved
items (normalization presets, import profiles, batch pipelines, Open recent,
automatic saves of earlier sessions) deleted only on purpose."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from src.modules.misc import user_settings as us
from src.modules.misc.session_files import AutosaveManager, Preferences, RecentFiles

app = QApplication.instance() or QApplication([])


@pytest.fixture
def home(tmp_path, monkeypatch):
    """All per-user files in tmp_path -- the real ones are never touched."""
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    from src.modules.data_analysis import normalization_manager as nm
    from src.modules.misc import import_profile_manager as ipm, pipeline_manager as pm
    monkeypatch.setattr(nm, '_PRESETS_FILE', str(tmp_path / 'norm' / 'normalization_region_presets.json'))
    monkeypatch.setattr(ipm, '_profiles_file', lambda: str(tmp_path / 'appdata' / 'import_profiles.json'))
    monkeypatch.setattr(pm, '_pipelines_file', lambda: str(tmp_path / 'appdata' / 'batch_pipelines.json'))
    for n in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    return tmp_path


def _saved_items():
    from src.modules.data_analysis.normalization_manager import NormalizationManager
    from src.modules.misc.import_profile_manager import ImportProfileManager
    from src.modules.misc.pipeline_manager import PipelineManager
    NormalizationManager.save_region_preset('amide I', [(1600, 1700)])
    NormalizationManager.save_region_preset('CH stretch', [(2800, 3000)])
    ImportProfileManager().save_profile('Specord CSV', {'delimiter': ';'})
    PipelineManager().save_pipeline('clean up', [{'operation': 'SG-smoothing', 'params': {}}])
    RecentFiles().add('C:/data/a.txt', 'data')
    RecentFiles().add('C:/data/b.snapx', 'snapshot')


def test_settings_have_their_defaults_until_changed(home):
    prefs = Preferences()
    assert not any(s.changed(prefs) for s in us.SETTINGS)
    by_id = {s.id: s for s in us.SETTINGS}
    assert by_id['autosave'].default_text == 'every 10 minutes'
    assert by_id['cd_ht'].default_text == '700 V' and by_id['theme'].default_text == 'light'
    assert [g for g, _ in us.groups()][:3] == [
        'Automatic saving (File \u203a Automatic saving)',
        'Plotting many spectra (View \u203a Plotting many spectra\u2026)',
        'CD data quality (View \u203a CD data quality)']
    prefs.set('autosave_minutes', 5)
    prefs.set('cd_ht_limit_V', 650.0)
    prefs.set('large_plot_dialog_count', 300)
    prefs.set('whats_new_hidden_for', __import__('src.version', fromlist=['x']).__version__)
    prefs.set('last_version_seen', '1.5.0')                     # from another version
    changed = {s.id for s in us.SETTINGS if s.changed(prefs)}
    assert changed == {'autosave', 'cd_ht', 'large_dialog_count', 'whats_new'}
    assert by_id['large_dialog_count'].current_text(prefs) == '300 spectra'
    assert us.other_keys(prefs) == ['last_version_seen']


def test_setting_a_value_stores_it_where_the_program_reads_it(home):
    """Each row writes exactly what its own menu or dialog would write."""
    from src.controllers.visualization.large_plot_controller import dialog_draw_limit
    from src.modules.visualization_analysis.peak_fit_map import normalized_settings
    prefs = Preferences()
    by_id = {s.id: s for s in us.SETTINGS}
    by_id['large_dialog_count'].set(prefs, 250)
    assert dialog_draw_limit() == 250
    by_id['pf_shape'].set(prefs, 'Lorentzian')
    by_id['pf_min_band_points'].set(prefs, 3.0)
    assert normalized_settings(prefs.get('peak_fit_map_settings'))['shape'] == 'Lorentzian'
    assert prefs.cd_quality_limits() == (700.0, 3.0)
    by_id['cd_abs'].set(prefs, 2.5)
    assert prefs.cd_quality_limits() == (700.0, 2.5)
    by_id['whats_new'].set(prefs, False)
    assert by_id['whats_new'].current_text(prefs) == 'off'
    for sid in ('large_dialog_count', 'pf_shape', 'pf_min_band_points', 'cd_abs', 'whats_new'):
        by_id[sid].set(prefs, by_id[sid].default)
    assert prefs.all() == {}                                      # defaults are not stored


def test_reset_selected_and_all_never_touch_saved_items(home):
    _saved_items()
    prefs = Preferences()
    prefs.set('autosave_minutes', 5)
    prefs.set('theme', 'dark')
    prefs.set('last_version_seen', '1.5.0')
    assert us.reset(prefs, ['autosave']) == ['autosave']
    assert prefs.all() == {'theme': 'dark', 'last_version_seen': '1.5.0'}
    assert us.reset(prefs) == ['theme', 'last_version_seen'] and prefs.all() == {}
    assert us.effects(['autosave', 'theme', 'pf_shape']) == {'autosave', 'theme'}
    counts = {k.id: len(k.names()) for k in us.saved_kinds()}
    assert counts == {'normalization': 2, 'import_profiles': 1, 'pipelines': 1, 'recent': 2,
                      'autosaves': 0}


def test_window_edits_in_the_table_and_resets(home):
    from src.views.dialogs.misc.settings_dialog import SettingsDialog
    prefs = Preferences()
    prefs.set('autosave_minutes', 20)
    prefs.set('last_version_seen', '1.5.0')
    calls = []

    class Main:
        def settings_changed(self, ids):
            calls.append(set(ids))
    dlg = SettingsDialog(None, Main(), prefs)
    assert dlg.tabs.tabText(0) == 'Settings' and dlg.tabs.tabText(1) == 'Your saved items'
    assert 'min-width' in dlg.tabs.styleSheet()                  # titles never cut
    combo = dlg.editors['autosave']
    assert combo.currentText() == 'every 20 minutes' and combo.font().bold()
    assert dlg.changed_label.text() == '2 settings differ from the default.'
    # changed in the table: stored at once, the program follows
    dlg.editors['cd_ht'].setValue(600)
    assert prefs.cd_quality_limits()[0] == 600.0 and calls[-1] == {'cd_quality'}
    dlg.editors['theme'].setCurrentIndex(dlg.editors['theme'].findData('dark'))
    assert prefs.get('theme') == 'dark' and calls[-1] == {'theme'}
    dlg.editors['mr_table'].setChecked(False)
    assert prefs.get('methods_report_include_table') is False
    assert dlg.changed_label.text() == '5 settings differ from the default.'
    # the row of a value from another version
    r = dlg._row_of['other:last_version_seen']
    assert dlg.table.item(r, 1).text() == 'last_version_seen'
    assert 'another version' in dlg.table.item(r, 1).toolTip()
    # reset selected
    dlg.table.item(dlg._row_of['autosave'], 0).setCheckState(Qt.Checked)
    dlg.table.item(r, 0).setCheckState(Qt.Checked)
    assert dlg.reset_selected() == ['autosave', 'last_version_seen']
    assert dlg.editors['autosave'].currentText() == 'every 10 minutes'
    assert not dlg.editors['autosave'].font().bold()
    assert 'other:last_version_seen' not in dlg._row_of           # its row is gone
    # reset all
    dlg.reset_all()
    assert prefs.all() == {} and dlg.changed_label.text() == 'All settings are at their defaults.'
    assert dlg.editors['cd_ht'].value() == 700 and dlg.editors['mr_table'].isChecked()
    assert not dlg.reset_all_button.isEnabled()


def test_saved_items_are_deleted_only_as_chosen(home, monkeypatch):
    from src.views.dialogs.misc import settings_dialog as sd
    _saved_items()
    folder = str(home / 'appdata' / 'autosave')
    old = AutosaveManager(folder=folder, session_id='old', is_alive=lambda sid: False)
    old.start_session('1.4.2')
    old.write_snapshot(b'snapshot')
    own = AutosaveManager(folder=folder, session_id='own', is_alive=lambda sid: sid == 'own')
    own.start_session('1.5.0')
    own.write_snapshot(b'my unsaved work')
    dlg = sd.SettingsDialog(None, None, Preferences(), own)
    counts = {k: dlg.count_labels[k].text() for k in dlg.count_labels}
    assert counts == {'normalization': '2', 'import_profiles': '1', 'pipelines': '1',
                      'recent': '2', 'autosaves': '1'}           # the running session not offered
    kinds = {k.id: k for k in dlg.kinds}

    def pick(names):
        def run(self):
            for i in range(self.list.count()):
                if self.list.item(i).text() in names:
                    self.list.item(i).setCheckState(Qt.Checked)
            return QDialog.Accepted
        return run
    monkeypatch.setattr(sd._PickDialog, 'exec_', pick(['amide I']))
    assert dlg.delete_items(kinds['normalization']) == ['amide I']
    assert kinds['normalization'].names() == ['CH stretch']
    monkeypatch.setattr(sd._PickDialog, 'exec_', lambda self: QDialog.Rejected)
    assert dlg.delete_items(kinds['import_profiles']) == []            # cancelled: kept
    assert kinds['import_profiles'].names() == ['Specord CSV']
    assert len(dlg.delete_items(kinds['recent'])) == 2 and RecentFiles().items() == []
    monkeypatch.setattr(sd._PickDialog, 'exec_', lambda self: (self._set_all(Qt.Checked), QDialog.Accepted)[1])
    dlg.delete_items(kinds['autosaves'])
    assert kinds['autosaves'].names() == []
    assert os.path.exists(own.autosave_path())                      # own work never deleted
    assert dlg.count_labels['normalization'].text() == '1'
    assert not dlg.delete_buttons['recent'].isEnabled()


def test_folders_and_menu_entry(home, monkeypatch):
    folders = us.folders()
    assert folders[0][0].startswith('Settings, Open recent, automatic saves')
    assert any('Normalization presets' in what for what, _ in folders)
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import settings_dialog as sd
    shown = []
    monkeypatch.setattr(sd.SettingsDialog, 'exec_', lambda self: shown.append(self) or 0)
    mc = MainController()
    try:
        texts = [a.text() for a in mc.view.menuFile.actions()]
        assert 'Settings and saved items\u2026' in texts
        mc.settings_action.trigger()
        assert shown and shown[0].main is mc
        # a reset follows in the open program at once
        prefs = mc.autosave_controller.preferences
        prefs.set('autosave_minutes', 20)
        mc.autosave_controller._apply_interval(20)
        prefs.remove('autosave_minutes')
        mc.settings_changed({'autosave'})
        checked = [a.data() for a in mc.autosave_controller._interval_actions if a.isChecked()]
        assert checked == [10]
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()


def test_groups_open_and_close_and_a_heading_ticks_its_group(home):
    from src.views.dialogs.misc.settings_dialog import SettingsDialog
    prefs = Preferences()
    prefs.set('cd_ht_limit_V', 650.0)                           # one changed value in CD
    dlg = SettingsDialog(None, None, prefs)
    cd = 'CD data quality (View › CD data quality)'
    many = 'Plotting many spectra (View › Plotting many spectra…)'
    assert not dlg.is_collapsed(cd) and dlg.is_collapsed(many)  # changed groups open
    head = dlg._groups[cd]['row']
    assert dlg.table.item(head, 1).text().startswith('▾  CD data quality')
    assert '(1 of 3 changed)' in dlg.table.item(head, 1).text()
    assert all(dlg.table.isRowHidden(r) for r in dlg._groups[many]['rows'])
    dlg._cell_clicked(dlg._groups[many]['row'], 1)               # click the heading
    assert not any(dlg.table.isRowHidden(r) for r in dlg._groups[many]['rows'])
    dlg.set_all_collapsed(True)
    assert all(dlg.table.isRowHidden(r) for g in dlg._groups.values() for r in g['rows'])
    assert not dlg.table.isRowHidden(dlg._row_of['autosave'])    # a single setting: no group
    dlg.table.item(head, 0).setCheckState(Qt.Checked)            # the heading's box
    assert set(dlg.ticked()) == {'cd_shading', 'cd_ht', 'cd_abs'}


def test_every_setting_is_explained_with_a_working_link(home, monkeypatch):
    import re
    from src.help import help_window
    from src.views.dialogs.misc.settings_dialog import SettingsDialog
    assert set(us.HELP) == {s.id for s in us.SETTINGS}
    for sid, (text, link) in us.HELP.items():
        assert len(text) > 30, sid
        key, _, anchor = link[len('help://'):].partition('#')
        module, _, fn = help_window._REGISTRY[key]
        content = getattr(__import__(module, fromlist=[fn]), fn)()
        assert not anchor or f'id="{anchor}"' in content, link
    guide = __import__('src.help.user_guide_help', fromlist=['x']).get_user_guide_help_content()
    assert 'id="settings"' in guide and '$SETTINGS_TABLE' not in guide
    assert us.HELP['mr_table'][0].split('.')[0] in guide           # the table is in the guide
    dlg = SettingsDialog(None, None, Preferences())
    assert 'parameter table' in dlg.editors['mr_table'].toolTip()
    assert 'Default: on' in dlg.editors['mr_table'].toolTip()
    opened = []
    monkeypatch.setattr(help_window, 'open_help_topic',
                        lambda parent, key, anchor=None: opened.append((key, anchor)))
    dlg.help_button.click()                     # '?': a window with every explanation
    text = dlg.help_window.text.toPlainText()
    assert dlg.help_window.isVisible() and opened == []
    assert all(st.label in text for st in us.SETTINGS)
    assert us.HELP['parallel_mode'][0][:40] in text
    from PyQt5.QtCore import QUrl
    dlg.help_window.text.anchorClicked.emit(QUrl('help://user_guide#parallel-workers'))
    dlg.help_window.text.anchorClicked.emit(QUrl('help://methods_report'))
    assert opened == [('user_guide', 'parallel-workers'), ('methods_report', None)]
    dlg.help_window.close()


def test_parallel_processing_is_shared_by_the_tools(home, monkeypatch):
    """One computer-wide setting: Automated Baseline and X-axis alignment start
    from it, the peak-fit maps use it, bootstrap uses at most that many workers
    (none with 'serial'); its defaults keep today's behaviour."""
    from src.modules.utils import parallel_bootstrap as pb
    from src.modules.utils.parallel_utils import default_parallel_settings
    from src.views.dialogs.visualization_analysis import peak_fit_settings_dialog as pfs
    prefs = Preferences()
    assert default_parallel_settings() == {'processing_mode': 'auto', 'max_workers': 0}
    by_id = {s.id: s for s in us.SETTINGS}
    by_id['parallel_mode'].set(prefs, 'parallel')
    by_id['parallel_workers'].set(prefs, 3)
    assert default_parallel_settings() == {'processing_mode': 'parallel', 'max_workers': 3}
    s = pfs.load_settings()
    assert s['processing_mode'] == 'parallel' and s['max_workers'] == 3
    s['processing_mode'] = 'serial'                               # changed in Fit settings...
    pfs.save_settings(s)
    assert prefs.get('parallel_processing_mode') == 'serial'
    assert 'processing_mode' not in prefs.get('peak_fit_map_settings')
    # bootstrap: serial -> no workers; otherwise at most the setting
    used = []
    monkeypatch.setattr(pb, '_run_parallel', lambda fn, common, rows, rest, workers, *a: used.append(workers))
    monkeypatch.setattr(pb, 'bootstrap_worker_count', lambda table_bytes: 8)
    monkeypatch.setattr(pb, 'MIN_PARALLEL_SECONDS', 0.0)
    rep = lambda common, b, rows: (True, b, None)
    pb.run_replicates(rep, None, [[0]] * 10)
    assert used == []                                             # serial
    by_id['parallel_mode'].set(prefs, 'auto')
    pb.run_replicates(rep, None, [[0]] * 10)
    assert used == [3]
    by_id['parallel_workers'].set(prefs, 0)
    pb.run_replicates(rep, None, [[0]] * 10)
    assert used == [3, 8]


def test_peak_fit_processing_stored_by_an_earlier_version_moves_to_the_shared_setting(home):
    from src.views.dialogs.visualization_analysis import peak_fit_settings_dialog as pfs
    prefs = Preferences()
    prefs.set('peak_fit_map_settings', {'shape': 'Lorentzian', 'processing_mode': 'serial',
                                        'max_workers': 4})
    s = pfs.load_settings()
    assert (s['shape'], s['processing_mode'], s['max_workers']) == ('Lorentzian', 'serial', 4)
    assert prefs.get('parallel_processing_mode') == 'serial' and prefs.get('parallel_max_workers') == 4
    assert prefs.get('peak_fit_map_settings') == {'shape': 'Lorentzian'}


def test_tool_windows_start_from_the_shared_setting(home):
    prefs = Preferences()
    prefs.set('parallel_processing_mode', 'serial')
    prefs.set('parallel_max_workers', 1)            # (the slider shows 0 when it is all cores)
    from src.views.dialogs.data_analysis.automated_baseline_dialog import AutomatedBaselineDialog
    import numpy as np
    x = np.linspace(400, 1800, 100)
    spectra = [{'label': f's{i}', 'x_scale': x, 'y_scale': np.sin(x / 100) + i, 'metadata': {}}
               for i in range(3)]
    dlg = AutomatedBaselineDialog(None, selected_spectra=spectra, current_settings={})
    try:
        from src.modules.utils.parallel_utils import max_worker_count
        assert dlg.processing_mode_combo.currentData() == 'serial'
        assert dlg.max_workers_spin.value() == (1 if max_worker_count() > 1 else 0)
    finally:
        dlg.close()


def test_x_axis_alignment_starts_from_the_shared_setting(home):
    import numpy as np
    from src.views.dialogs.data_analysis.xaxis_alignment_dialog import XAxisAlignmentDialog
    prefs = Preferences()
    prefs.set('parallel_processing_mode', 'parallel')
    prefs.set('parallel_max_workers', 1)
    x = np.linspace(400, 1800, 100)
    spectra = [{'label': f's{i}', 'x_scale': x + i, 'y_scale': np.exp(-((x - 900) / 30) ** 2),
                'metadata': {}} for i in range(3)]
    dlg = XAxisAlignmentDialog(None, selected_spectra=spectra)
    try:
        from src.modules.utils.parallel_utils import max_worker_count
        assert dlg.processing_mode_combo.currentData() == 'parallel'
        assert dlg.max_workers_spin.value() == (1 if max_worker_count() > 1 else 0)
    finally:
        dlg.close()


def test_more_links_open_the_help_page_at_its_section(home, monkeypatch, tmp_path):
    """Windows drops '#section' from a file link handed to the browser, so the
    page opened at its top: a small page next to it now sends the browser on
    to page.html#section (also used by the What's New window)."""
    import re
    from PyQt5.QtGui import QDesktopServices
    from src.help import help_window
    monkeypatch.setattr(help_window, '_help_pages_dir', lambda: str(tmp_path / 'pages'))
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', staticmethod(lambda url: opened.append(url)))
    for sid, (_text, link) in us.HELP.items():
        key, _, anchor = link[len('help://'):].partition('#')
        opened.clear()
        help_window.open_help_topic(None, key, anchor or None)
        url = opened[0].toString()
        assert '#' not in url, sid                       # nothing for Windows to drop
        path = opened[0].toLocalFile()
        if not anchor:
            assert path.endswith(f'{key}.html'), sid
            continue
        redirect = open(path, encoding='utf-8').read()
        assert f'url={key}.html#{anchor}"' in redirect, sid
        target = open(tmp_path / 'pages' / f'{key}.html', encoding='utf-8').read()
        assert re.search(rf'id="{re.escape(anchor)}"', target), sid
