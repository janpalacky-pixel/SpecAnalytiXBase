"""Group Statistics: the order of the groups (a group table's own order,
not the main list's alphabetical order) and the sideways spread of the dots
(Automatic / Random jitter / Beeswarm / Density-scaled, all deterministic).

The demos are also opened the way a user does it -- File -> Import into the
main window, select all -- because the main spectra list is sorted by name
("high_dose" before "low_dose", "after" before "before"); opening the
window directly with the file's order hid exactly that."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.visualization_analysis import dot_spread as ds
from src.modules.visualization_analysis import group_statistics as gs
from src.modules.visualization_analysis import group_spectra as gsp

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SYNTH = os.path.join(ROOT, 'resources', 'test_data', 'synthetic')


# --- order of the groups (Qt-free) ------------------------------------------------------

def test_ordered_names_puts_the_preferred_order_first():
    assert gs.ordered_names(['control', 'high dose', 'low dose'],
                            ['control', 'low dose', 'high dose']) == \
        ['control', 'low dose', 'high dose']
    # names not in the order follow in their own order; unknown ones are ignored
    assert gs.ordered_names(['b', 'x', 'a'], ['a', 'zz', 'b']) == ['a', 'b', 'x']
    assert gs.ordered_names(['b', 'a', 'b'], None) == ['b', 'a']


def test_table_group_order_and_collect():
    mapping = {'c1': 'control', 'l1': 'low dose', 'h1': 'high dose', 'c2': 'control', 'x': ''}
    order = gs.table_group_order(mapping)
    assert order == ['control', 'low dose', 'high dose']
    data = gs.collect(['control', 'high dose', 'low dose', 'high dose'], [1, 2, 3, np.nan],
                      order)
    assert list(data) == ['control', 'low dose', 'high dose']
    assert list(data['high dose']) == [2.0]                    # NaN still left out
    assert list(gs.collect(['b', 'a'], [1, 2])) == ['b', 'a']  # no order: first appearance


def test_compare_spectra_uses_the_order():
    x = np.linspace(0, 10, 30)
    rng = np.random.default_rng(3)
    spectra = [{'label': f's{i}', 'x_scale': x, 'y_scale': rng.normal(size=30) + (i % 2)}
               for i in range(8)]
    groups = ['b', 'a'] * 4
    assert gsp.compare_spectra(spectra, groups)['names'] == ['b', 'a']
    assert gsp.compare_spectra(spectra, groups, order=['a', 'b'])['names'] == ['a', 'b']


# --- dots (Qt-free) ----------------------------------------------------------------------

def test_jitter_is_fixed_per_spectrum():
    v = np.arange(5.0)
    a = ds.jitter(v, ['s1', 's2', 's3', 's4', 's5'], 0.12)
    b = ds.jitter(v[::-1], ['s5', 's4', 's3', 's2', 's1'], 0.12)
    assert np.allclose(a, b[::-1])                    # the same spectrum, the same shift
    assert np.all(np.abs(a) <= 0.12) and len(set(np.round(a, 6))) == 5
    assert np.allclose(ds.jitter(v[:2], ['s1', 's2'], 0.12), a[:2])   # others don't matter


def test_beeswarm_never_overlaps_and_is_deterministic():
    rng = np.random.default_rng(0)
    v = np.round(rng.normal(50, 5, 60), 1)
    dx, dy = 0.03, 0.8
    off = ds.swarm(v, dx, dy)
    assert np.allclose(off, ds.swarm(v, dx, dy))
    X, Y = off / dx, v / dy                            # in dot diameters
    d2 = (X[:, None] - X[None, :]) ** 2 + (Y[:, None] - Y[None, :]) ** 2
    np.fill_diagonal(d2, 9.0)
    assert d2.min() >= 1.0 - 1e-6                      # no dot covers another
    # well separated values stay on the centre line
    assert np.allclose(ds.swarm([1.0, 5.0, 9.0], 0.03, 0.8), 0.0)
    # equal values spread symmetrically: 0, -1, +1, -2, +2 diameters
    assert sorted(np.round(ds.swarm([3.0] * 5, 0.1, 1.0) / 0.1, 6)) == [-2, -1, 0, 1, 2]


def test_density_scaled_spread():
    rng = np.random.default_rng(1)
    v = rng.normal(0, 1, 500)
    off = ds.density(v, 0.3)
    assert np.allclose(off, ds.density(v, 0.3))
    assert np.max(np.abs(off)) <= 0.3 + 1e-12
    centre = np.abs(v) < 0.5                           # crowded middle: wider
    tail = np.abs(v) > 2.0
    assert np.mean(np.abs(off[centre])) > 2 * np.mean(np.abs(off[tail]))
    assert np.allclose(ds.density([2.0], 0.3), 0.0)
    assert len(ds.density([], 0.3)) == 0


def test_automatic_chooses_beeswarm_or_density():
    small = np.linspace(0, 10, 12)
    off, how = ds.automatic(small, 0.03, 0.2, 0.3)
    assert how == 'swarm' and np.max(np.abs(off)) <= 0.3
    many = np.random.default_rng(2).normal(size=3000)
    off, how = ds.automatic(many, 0.03, 0.01, 0.3)
    assert how == 'density' and np.max(np.abs(off)) <= 0.3
    assert ds.offsets('jitter', small, [str(i) for i in range(12)], 0.03, 0.2, 0.12)[1] == 'jitter'
    assert set(ds.MODES) == set(ds.MODE_NAMES) and ds.MODES[0] == 'auto'


# --- the demos opened as a user does it ------------------------------------------------

@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, 'exec_', lambda self: QMessageBox.Yes)
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths),
                                                 [{} for _ in file_paths])))
    from src.controllers.core.main_controller import MainController
    controller = MainController()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def _open_as_user(mc, name):
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    mc.import_controller._run_import(clear_first=True,
                                     file_paths=[os.path.join(SYNTH, name)])
    app.processEvents()
    mc.spectra_list_widget.selectAll()
    app.processEvents()
    spectra = mc.spectrum_selector.get_selected_spectra()
    return GroupStatisticsDialog(spectra, None, {}, {}), spectra


def _area(d, lo, hi):
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('area'))
    d.a_from.setValue(lo)
    d.a_to.setValue(hi)


@pytest.mark.parametrize('name, order', [
    ('group_stats_treatment_demo.xlsx', ['control', 'low dose', 'high dose']),
    ('group_stats_cells_samples_demo.xlsx', ['wild type', 'mutant']),
    ('group_stats_paired_demo.xlsx', ['before', 'after']),
    ('group_stats_skewed_demo.xlsx', ['control', 'nitrogen starved']),
])
def test_demo_groups_keep_the_order_of_their_table(mc, name, order):
    d, spectra = _open_as_user(mc, name)
    first_seen = list(dict.fromkeys(g for g in d.groups() if g))
    if name != 'group_stats_skewed_demo.xlsx':
        assert first_seen != order          # the main list is sorted by name ...
    assert d.group_order() == order         # ... the table's order is kept
    assert list(d.group_colours()) == order
    assert d._group_names() == order
    _area(d, 1620, 1690)
    d.compute()
    assert list(d.data) == order
    assert [d.summary_table.item(i, 0).text() for i in range(d.summary_table.rowCount())][:len(order)] == order
    d.deleteLater()


def test_treatment_demo_pairs_in_dose_order(mc):
    d, _ = _open_as_user(mc, 'group_stats_treatment_demo.xlsx')
    _area(d, 1620, 1690)
    d.compute()
    pairs = [(p['a'], p['b']) for p in d.comparison['pairs']]
    assert pairs == [('control', 'low dose'), ('control', 'high dose'),
                     ('low dose', 'high dose')]
    assert round(d.comparison['p'], 4) == 0.0308          # as in the tutorial
    d.deleteLater()


def test_paired_demo_difference_is_before_minus_after(mc):
    d, _ = _open_as_user(mc, 'group_stats_paired_demo.xlsx')
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('max'))
    d.a_from.setValue(1630)
    d.a_to.setValue(1680)
    d.test_combo.setCurrentIndex(d.test_combo.findData('paired_t'))
    d.compute()
    m, lo, hi = d.comparison['ci']
    assert round(m, 3) == 0.048 and lo > 0                # the tutorial: before - after = 0.048
    d.deleteLater()


def test_groups_from_names_use_the_list_order(mc, monkeypatch):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    d, _ = _open_as_user(mc, 'group_stats_treatment_demo.xlsx')
    groups = list(d.groups())

    class FakeNames:
        def __init__(self, *a, **k):
            pass

        def exec_(self):
            return gsd.QDialog.Accepted

        def groups(self):
            return groups

    monkeypatch.setattr(gsd, 'NamesToGroupsDialog', FakeNames)
    d.groups_from_names()
    assert d.group_order() == []
    assert d._group_names() == ['control', 'high dose', 'low dose']
    d.deleteLater()


# --- dots in the window ------------------------------------------------------------------

def _dot_x(d):
    """{(group, dot index): x position} of the drawn dots."""
    ax, layers, _ = d._dot_layers
    out = {}
    for p, v, keys, dots, ring, idx in layers:
        for k, (x, y) in zip(keys, dots.get_offsets()):
            out[k] = (x - p, y)
    return out


def test_dots_combo_default_remembered_and_every_mode_draws(mc):
    d, _ = _open_as_user(mc, 'group_stats_treatment_demo.xlsx')
    d.resize(1200, 900)
    d.show()
    app.processEvents()
    assert d.dots_combo.currentData() == 'auto'
    _area(d, 1620, 1690)
    d.compute()
    app.processEvents()
    assert d.dots_used == {'swarm'}                      # 12 dots per group fit
    for mode, used in (('jitter', 'jitter'), ('swarm', 'swarm'), ('density', 'density')):
        d.dots_combo.setCurrentIndex(d.dots_combo.findData(mode))
        app.processEvents()
        assert d.dots_used == {used}
        xs = _dot_x(d)
        assert len(xs) == 36 and all(abs(x) <= 0.3 + 1e-9 for x, _ in xs.values())
    assert d.remembered_settings['dots'] == 'density'
    d.close()
    d.deleteLater()


def test_a_dot_keeps_its_place_when_the_group_order_changes(mc):
    """The complaint: the dots of a group looked different in the tutorial
    because the random shifts were drawn group by group."""
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    d, spectra = _open_as_user(mc, 'group_stats_treatment_demo.xlsx')
    positions = {}
    for order in (['control', 'low dose', 'high dose'], ['high dose', 'control', 'low dose']):
        for mode in ('jitter', 'swarm', 'density'):
            w = GroupStatisticsDialog(spectra, None, {}, {'dots': mode})
            w.remembered_settings['group_order'] = order     # as if from another table
            w.resize(1200, 900)
            w.show()
            app.processEvents()
            _area(w, 1620, 1690)
            w.compute()
            app.processEvents()
            assert list(w.data) == order
            positions.setdefault(mode, []).append(_dot_x(w))
            w.close()
            w.deleteLater()
    for mode, (first, second) in positions.items():
        assert set(first) == set(second)
        for k in first:
            assert first[k] == pytest.approx(second[k], abs=1e-9), (mode, k)
    d.deleteLater()


def test_dots_do_not_depend_on_the_window_size(mc):
    """The same data give the same picture in a small or a maximized window
    (and in the help's screenshots): the beeswarm is laid out for a fixed
    reference plot size."""
    d, _ = _open_as_user(mc, 'group_stats_treatment_demo.xlsx')
    _area(d, 1620, 1690)
    seen = []
    for size in ((1000, 700), (1900, 1000)):
        d.resize(*size)
        d.show()
        app.processEvents()
        d.compute()
        app.processEvents()
        seen.append(_dot_x(d))
    assert set(seen[0]) == set(seen[1])
    for k in seen[0]:
        assert seen[0][k] == pytest.approx(seen[1][k], abs=1e-9)
    d.close()
    d.deleteLater()
