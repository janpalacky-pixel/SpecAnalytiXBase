"""SOM: classic online training vs the faster batch training.

The online result must be EXACTLY what it was before batch training was
added (existing maps stay reproducible); batch is a different algorithm and
is checked for sensible behaviour instead.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

import src.modules.visualization_analysis.som_manager as som_module
from src.modules.visualization_analysis.som_manager import SOMManager, _eta_suffix

app = QApplication.instance() or QApplication([])


def _clusters(n_per=20, n_features=40, seed=0):
    """Three well separated groups of spectra."""
    rng = np.random.default_rng(seed)
    centres = rng.normal(size=(3, n_features)) * 4
    return np.vstack([c + rng.normal(scale=0.3, size=(n_per, n_features)) for c in centres])


def _spectra(n_per=20, n_features=40):
    x = np.linspace(0, 1, n_features)
    return [{'label': f's{i}', 'x_scale': x, 'y_scale': row}
            for i, row in enumerate(_clusters(n_per, n_features))]


# ---------------------------------------------------------------- online unchanged

def test_online_default_is_the_classic_algorithm_and_is_the_default():
    spectra = _spectra()
    a = SOMManager(); b = SOMManager()
    assert a.compute_som(spectra, grid_rows=4, grid_cols=4, n_iterations=8)
    assert b.compute_som(spectra, grid_rows=4, grid_cols=4, n_iterations=8, training_method='online')
    assert a.training_method == b.training_method == 'online'
    assert np.array_equal(a.weights, b.weights)


def test_unknown_method_is_treated_as_online():
    m = SOMManager()
    assert m.compute_som(_spectra(), grid_rows=3, grid_cols=3, n_iterations=5, training_method='turbo')
    assert m.training_method == 'online'


# ---------------------------------------------------------------- batch behaviour

def test_batch_returns_the_same_kind_of_result():
    m = SOMManager()
    assert m.compute_som(_spectra(), grid_rows=4, grid_cols=5, n_iterations=30, training_method='batch')
    assert m.training_method == 'batch'
    assert m.weights.shape == (4, 5, 40)
    assert m.bmu_indices.shape == (60, 2)
    assert m.hit_map.sum() == 60
    assert m.u_matrix.shape == (4, 5)
    assert np.isfinite(m.weights).all() and np.isfinite(m.quantization_error)


def test_batch_separates_obvious_groups_like_online_does():
    spectra = _spectra()
    for method in ('online', 'batch'):
        m = SOMManager()
        assert m.compute_som(spectra, grid_rows=5, grid_cols=5, n_iterations=60, training_method=method)
        nodes = [tuple(b) for b in m.bmu_indices]
        group_nodes = [set(nodes[g * 20:(g + 1) * 20]) for g in range(3)]
        # spectra of different groups never share a node
        assert not (group_nodes[0] & group_nodes[1])
        assert not (group_nodes[0] & group_nodes[2])
        assert not (group_nodes[1] & group_nodes[2])


def test_batch_quality_is_close_to_online():
    spectra = _spectra(n_per=40)
    online = SOMManager(); batch = SOMManager()
    online.compute_som(spectra, grid_rows=6, grid_cols=6, n_iterations=60)
    batch.compute_som(spectra, grid_rows=6, grid_cols=6, n_iterations=60, training_method='batch')
    assert batch.quantization_error < online.quantization_error * 1.3


def test_batch_is_deterministic():
    spectra = _spectra()
    a = SOMManager(); b = SOMManager()
    a.compute_som(spectra, grid_rows=4, grid_cols=4, n_iterations=20, training_method='batch')
    b.compute_som(spectra, grid_rows=4, grid_cols=4, n_iterations=20, training_method='batch')
    assert np.array_equal(a.weights, b.weights)


def test_batch_handles_tiny_and_degenerate_data():
    # fewer spectra than nodes, a single feature, identical spectra
    rng = np.random.default_rng(0)
    for X in (rng.normal(size=(3, 1)), np.ones((5, 4)), rng.normal(size=(2, 6))):
        result = SOMManager._train_batch(X, 3, 3, 10, 42, 0.5)
        assert np.isfinite(result['weights']).all()
        assert result['bmu'].shape == (X.shape[0], 2)


def test_batch_in_small_blocks_gives_the_same_result_as_in_one_block(monkeypatch):
    X = _clusters(n_per=30, n_features=20)             # 90 samples, 16 nodes
    whole = SOMManager._train_batch(X, 4, 4, 15, 42, 0.5)
    monkeypatch.setattr(som_module, '_BATCH_DISTANCE_BLOCK_ELEMENTS', 16 * 7)   # 7 samples per block
    blocked = SOMManager._train_batch(X, 4, 4, 15, 42, 0.5)
    assert np.array_equal(whole['weights'], blocked['weights'])
    assert np.array_equal(whole['bmu'], blocked['bmu'])


def test_batch_reports_progress_for_every_pass():
    seen = []
    m = SOMManager()
    m.compute_som(_spectra(), grid_rows=3, grid_cols=3, n_iterations=7, training_method='batch',
                  progress_callback=lambda step, total, label: seen.append((step, total, label)))
    assert [s for s, _, _ in seen] == list(range(0, 8))    # data preparation (0), then one report per pass
    assert all(total == 8 for _, total, _ in seen)
    assert 'batch' in seen[-1][2]


# (No wall-clock "batch is faster" test here on purpose: timing asserts fail
# at random on busy or shared machines -- such as the GitHub build that runs
# these tests before every nightly/release build -- and would block a build
# for no real reason. Measured speed: see the SOM help and dev notes.)


# ---------------------------------------------------------------- progress estimate

def test_eta_text_appears_only_when_reliable(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(som_module.time, 'perf_counter', lambda: now[0])
    assert _eta_suffix(1000.0, 1, 100) == ''                # first seconds: too early
    now[0] = 1010.0                                          # 10 s for 10 of 100 passes
    assert _eta_suffix(1000.0, 10, 100) == '  —  about 1 min 30 s left'
    now[0] = 1010.0
    assert _eta_suffix(1000.0, 99, 100) == ''                # almost done: no estimate


# ---------------------------------------------------------------- dialog

def _dialog(n=20):
    from src.views.dialogs.visualization_analysis.som_dialog import SOMDialog
    from src.controllers.visualization_analysis.som_controller import SOMController
    from types import SimpleNamespace
    controller = SOMController(SimpleNamespace(operations_controller=None))
    return SOMDialog(parent=None, controller=controller, spectra=_spectra(n_per=max(1, n // 3)))


def test_dialog_defaults_to_online_and_greys_out_learning_rates_for_batch():
    d = _dialog()
    assert d.training_method_combo.currentData() == 'online'
    assert d.lr_start_spin.isEnabled() and d.lr_end_spin.isEnabled()
    d.training_method_combo.setCurrentIndex(d.training_method_combo.findData('batch'))
    assert not d.lr_start_spin.isEnabled() and not d.lr_end_spin.isEnabled()
    d.training_method_combo.setCurrentIndex(d.training_method_combo.findData('online'))
    assert d.lr_start_spin.isEnabled()


def test_dialog_shows_the_speed_tip_only_for_bigger_datasets():
    assert _dialog(n=30)._method_tip_label.isHidden()
    assert not _dialog(n=300)._method_tip_label.isHidden()


# ---------------------------------------------------------------- cancel / all-or-nothing

from src.modules.utils.progress_utils import OperationCancelled


def _cancel_after(passes):
    def callback(step, total, label):
        if step >= passes:
            raise OperationCancelled()
    return callback


@pytest.mark.parametrize('method', ['online', 'batch'])
def test_cancel_keeps_the_previous_map_untouched(method):
    spectra = _spectra()
    m = SOMManager()
    assert m.compute_som(spectra, grid_rows=4, grid_cols=4, n_iterations=10)
    before = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in m.__dict__.items()}

    ok = m.compute_som(spectra[:30], grid_rows=6, grid_cols=7, n_iterations=50,
                       training_method=method, progress_callback=_cancel_after(3))
    assert ok is False
    assert m.cancelled is True and m.last_error is None
    assert (m.grid_rows, m.grid_cols) == (4, 4)                 # not the cancelled 6 x 7
    assert np.array_equal(m.weights, before['weights'])
    assert len(m.spectrum_labels) == 60                         # not the cancelled 30
    assert m.hit_map.shape == m.weights.shape[:2]               # still consistent


def test_cancel_before_any_previous_run_leaves_an_empty_manager():
    m = SOMManager()
    assert m.compute_som(_spectra(), grid_rows=4, grid_cols=4, n_iterations=10,
                         progress_callback=_cancel_after(1)) is False
    assert m.cancelled and m.weights is None and m.grid_rows is None


def test_a_successful_run_after_a_cancel_works_and_clears_the_flag():
    m = SOMManager()
    m.compute_som(_spectra(), grid_rows=4, grid_cols=4, n_iterations=10,
                  progress_callback=_cancel_after(1))
    assert m.compute_som(_spectra(), grid_rows=4, grid_cols=4, n_iterations=10)
    assert m.cancelled is False and m.weights.shape == (4, 4, 40)


def test_failed_run_keeps_the_previous_map_but_reports_the_error():
    spectra = _spectra()
    m = SOMManager()
    assert m.compute_som(spectra, grid_rows=4, grid_cols=4, n_iterations=10)
    weights = m.weights.copy()
    # feature mode without feature definitions -> fails after some state was touched
    assert m.compute_som(spectra, grid_rows=6, grid_cols=6, n_iterations=10,
                         train_mode='feature', feature_defs=None) is False
    assert m.last_error and 'feature' in m.last_error.lower()
    assert m.cancelled is False
    assert (m.grid_rows, m.grid_cols) == (4, 4) and np.array_equal(m.weights, weights)


def test_dialog_cancel_button_stops_training_and_keeps_the_dialog_usable():
    from PyQt5.QtCore import QTimer, QEventLoop
    d = _dialog(n=300)
    d.iterations_spin.setValue(5000)                   # long enough to be cancelled
    d.grid_rows_spin.setValue(10); d.grid_cols_spin.setValue(10)
    from PyQt5.QtWidgets import QPushButton

    def click_cancel():                                # exactly what the user does
        buttons = d._som_progress.findChildren(QPushButton)
        assert buttons, 'the progress dialog has no Cancel button'
        buttons[0].click()
    QTimer.singleShot(300, click_cancel)
    d.run_som()
    loop = QEventLoop()
    d._som_worker.done.connect(loop.quit)
    QTimer.singleShot(30000, loop.quit)                # safety net
    if d._som_worker.isRunning():
        loop.exec_()
    app.processEvents()
    assert d.controller.manager.cancelled is True
    assert d.run_btn.isEnabled() and d._som_running is False
    assert d.controller.manager.weights is None        # nothing half-trained left behind
