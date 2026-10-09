"""Automatic bug hunt ("smoke test") over the whole application.

1. Every shipped test dataset imports through the real importer.
2. Every batch-pipeline operation (with several settings each, all 13
   baseline methods, all normalization modes) runs on real data and keeps
   every spectrum complete and finite.
3. The real application is started without a window; for each dataset
   below, every Spectra Processing operation and every Analysis &
   Visualization tool is opened and its action buttons (Run, Fit, Apply,
   Update Map, Bootstrap, ...) are pressed automatically.

A test fails on anything that is a bug rather than the app correctly
asking for input: an unhandled exception, an error ("critical") message
box, an ERROR written to the log, or a computation that never finishes.
Message boxes that only warn ("define a range first", "select more
spectra") are expected and allowed.

Nothing here measures speed (see the Developer Guide, "No timing
assertions"). It writes no files: file dialogs are answered with
"cancel", and the app keeps its settings in memory.

When a test here fails, the message lists every problem with where it
happened, e.g.
    EXCEPTION | CD_spectra_TBA.txt > analysis: SOM > ... > [Run SOM] | ...
"""
import glob
import logging
import os
import re
import sys
import time
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import (QApplication, QDialog, QFileDialog, QInputDialog, QMessageBox,
                             QPushButton)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'resources', 'test_data')
app = QApplication.instance() or QApplication([])


def _all_datasets():
    pats = ['synthetic/*.xlsx', 'real/*.txt', 'real/2D map/*.mat', 'real/CD melting/*.jwb']
    return sorted(p for pat in pats for p in glob.glob(os.path.join(DATA, pat)))


def _load(path, **kw):
    from src.modules.core.spectrum_manager import SpectrumManager
    if path.endswith('.xlsx'):
        kw.setdefault('sheet_name', 'Spectra')
    if path.endswith(('.jws', '.jwb')):
        kw.setdefault('jws_selected_channels', [0])
    m = SpectrumManager()
    m.load_spectrum_from_file(path, **kw)
    return [{'label': k, 'x_scale': np.asarray(s.x_scale, float),
             'y_scale': np.asarray(s.y_scale, float), 'metadata': dict(s.metadata)}
            for k, s in m.get_all_spectra().items()]


# ---------------------------------------------------------------------------
# 1. every shipped dataset imports
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('path', _all_datasets(), ids=lambda p: os.path.relpath(p, DATA))
def test_every_shipped_dataset_imports(path):
    spectra = _load(path)
    assert spectra, 'nothing imported'
    assert len({s['label'] for s in spectra}) == len(spectra), 'duplicate labels'
    for s in spectra:
        assert len(s['x_scale']) == len(s['y_scale']) > 0
        assert np.isfinite(s['y_scale']).all() and np.isfinite(s['x_scale']).all()
        assert np.all(np.diff(s['x_scale']) >= 0), 'x axis not ascending'


def test_dataset_list_is_not_empty():
    assert len(_all_datasets()) >= 40


# ---------------------------------------------------------------------------
# 2. every pipeline operation on real data
# ---------------------------------------------------------------------------

_ALGOS = ['als', 'airpls', 'arpls', 'iarpls', 'aspls', 'drpls', 'psalsa', 'imodpoly',
          'morphological', 'mpls', 'mollification', 'mpspline', 'jbcd']
_NORM = ['vector', 'unit_area', 'max_peak', 'quantile', 'top_mean', 'reference', 'min_max',
         'snv', 'msc', 'svd', 'z_score', 'robust_scaling', 'range_scaling',
         'offset_correction', 'baseline_correction', 'mean_center', 'custom']
_CASES = ([('Automated Baseline', {'algorithm': a, 'processing_mode': 'serial'}) for a in _ALGOS]
          + [('Normalization', {'normalization_mode': m}) for m in _NORM]
          + [('SNIP Baseline', {'n_iter': 100, 'decreasing': True, 'smooth_window': 0, 'transform': True}),
             ('SNIP Baseline', {'n_iter': 40, 'decreasing': False, 'smooth_window': 3, 'transform': False}),
             ('SG-smoothing', {'window_length': 11, 'polyorder': 3, 'deriv_order': 0, 'delta': 1.0, 'mode': 'interp'}),
             ('SG-smoothing', {'window_length': 15, 'polyorder': 2, 'deriv_order': 1, 'delta': 1.0, 'mode': 'nearest'}),
             ('FFT Denoising', {'high_cutoff': 0.3, 'window': 'none'}),
             ('FFT Denoising', {'low_cutoff': 0.01, 'high_cutoff': 0.5, 'window': 'hann'}),
             ('FFT Denoising', {'stop_bands': [(0.2, 0.3)], 'window': 'hann'}),
             ('Cosmic ray removal', {}),
             ('Spike removal', {}),
             ('Resolution enhancement', {'irf_sigma': 3.0, 'snr': 100.0}),
             ('Data range', {})])

_PIPELINE_DATA = {}


def _pipeline_data():
    if not _PIPELINE_DATA:
        _PIPELINE_DATA['CD TBA'] = _load(os.path.join(DATA, 'real', 'CD_spectra_TBA.txt'))[:10]
        _PIPELINE_DATA['Raman DNA'] = _load(os.path.join(DATA, 'real', 'Raman_DNA_conc_dep.txt'))[:6]
        _PIPELINE_DATA['CD melt'] = _load(os.path.join(DATA, 'real', 'CD melting',
                                                       'CD_melt_sample_3_cooling.jwb'))[:6]
    return _PIPELINE_DATA


@pytest.mark.parametrize('operation, settings', _CASES,
                         ids=[f"{o}-{list(s.values())[0] if s else 'defaults'}" for o, s in _CASES])
def test_every_pipeline_operation_on_real_data(operation, settings):
    from src.modules.data_analysis.batch_pipeline_manager import ELIGIBLE_OPERATIONS
    for name, spectra in _pipeline_data().items():
        inp = [dict(s, x_scale=s['x_scale'].copy(), y_scale=s['y_scale'].copy(),
                    metadata=dict(s['metadata'])) for s in spectra]
        out = ELIGIBLE_OPERATIONS[operation]['run'](inp, dict(settings), None)
        assert out is not None and len(out) == len(spectra), name
        for s in out:
            assert len(s['x_scale']) == len(s['y_scale']) > 0, f"{name}: {s['label']}"
            assert np.isfinite(s['y_scale']).all(), f"{name}: non-finite values in {s['label']}"


# ---------------------------------------------------------------------------
# 3. the real application: open every dialog and press its buttons
# ---------------------------------------------------------------------------

_ACTION = re.compile(r'^(run|compute|recompute|calculate|fit|detect|match|train|analy[sz]e|auto|'
                     r'find|estimate|apply|update|bootstrap|show|diagnostics|multi-map|suggest|'
                     r'next|store as|configure|ok)\b', re.I)
_SKIP = re.compile(r'close|cancel|help|export|save|load|import|browse|remove|delete|clear|reset|'
                   r'copy|\?|add as new|what does|enter manually|revert', re.I)
_CLEAN = lambda t: re.sub(r'^[^A-Za-z]+', '', t.replace('&', ''))
# Validation messages logged at ERROR level on purpose (e.g. "spectra have
# different x-axes") -- the user also gets a clear warning box for these.
_ALLOWED_LOGGERS = ('src.modules.utils.spectra_validation',)


class _Driver:
    """Runs the application without a window and presses dialog buttons."""

    def __init__(self, monkeypatch):
        self.problems, self.context, self.depth = [], [], 0
        self.monkeypatch = monkeypatch
        mp = monkeypatch
        mp.setattr(sys, 'excepthook', self._exception)

        def box(kind, ret):
            def f(parent, title, text, *a, **k):
                if kind == 'critical':
                    self._record('ERROR BOX', f'{title}: {text}')
                return ret
            return staticmethod(f)
        mp.setattr(QMessageBox, 'question', box('q', QMessageBox.Yes))
        mp.setattr(QMessageBox, 'information', box('i', QMessageBox.Ok))
        mp.setattr(QMessageBox, 'warning', box('w', QMessageBox.Ok))     # input prompts: fine
        mp.setattr(QMessageBox, 'critical', box('critical', QMessageBox.Ok))
        for name, ret in (('getOpenFileName', ('', '')), ('getOpenFileNames', ([], '')),
                          ('getSaveFileName', ('', '')), ('getExistingDirectory', '')):
            mp.setattr(QFileDialog, name, staticmethod(lambda *a, _r=ret, **k: _r))
        for name, ret in (('getText', ('', False)), ('getInt', (0, False)),
                          ('getDouble', (0.0, False)), ('getItem', ('', False))):
            mp.setattr(QInputDialog, name, staticmethod(lambda *a, _r=ret, **k: _r))
        mp.setattr(QDialog, 'exec_', lambda dlg: self._drive(dlg))
        mp.setattr(QDialog, 'exec', lambda dlg: self._drive(dlg))
        self._log_handler = _ErrorLogHandler(self)
        logging.getLogger().addHandler(self._log_handler)

    def close(self):
        logging.getLogger().removeHandler(self._log_handler)

    # -- recording
    def _record(self, kind, text):
        self.problems.append(f"{kind} | {' > '.join(self.context)} | {str(text)[:400]}")

    def _exception(self, etype, value, tb):
        src = [f for f in traceback.extract_tb(tb) if f'{os.sep}src{os.sep}' in f.filename
               or '/src/' in f.filename]
        where = f' [{os.path.basename(src[-1].filename)}:{src[-1].lineno}]' if src else ''
        self._record('EXCEPTION', f'{etype.__name__}: {value}{where}')

    # -- driving
    @staticmethod
    def _pump(seconds=0.05):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.005)

    def _wait_for_threads(self, widget, limit=600):
        # A hang detector, not a speed test: a computation that has not
        # finished after 10 minutes is stuck.
        t0 = time.time()
        while time.time() - t0 < limit:
            app.processEvents()
            if not [t for t in widget.findChildren(QThread) if t.isRunning()]:
                return
            time.sleep(0.01)
        self._record('HANG', f'still computing after {limit} s')

    def _drive(self, dlg):
        if isinstance(dlg, QMessageBox):
            if dlg.icon() == QMessageBox.Critical:
                self._record('ERROR BOX', f'{dlg.windowTitle()}: {dlg.text()}')
            return QMessageBox.Yes
        self.depth += 1
        try:
            dlg.show()
            self._pump()
            if self.depth > 2:                     # sub-dialog of a sub-dialog: just close
                return QDialog.Rejected
            buttons = [b for b in dlg.findChildren(QPushButton)
                       if b.isVisible() and b.isEnabled() and _ACTION.search(_CLEAN(b.text()))
                       and not _SKIP.search(b.text())]
            buttons.sort(key=lambda b: _CLEAN(b.text()).lower().startswith(('apply', 'ok')))
            self.context.append(dlg.windowTitle() or type(dlg).__name__)
            for b in buttons:
                try:
                    if not (dlg.isVisible() and b.isVisible() and b.isEnabled()):
                        continue
                except RuntimeError:               # widget already deleted
                    break
                self.context.append(f'[{_CLEAN(b.text())}]')
                b.click()
                self._pump()
                self._wait_for_threads(dlg)
                self.context.pop()
            self.context.pop()
            result = dlg.result()
            if dlg.isVisible():
                dlg.reject()
            return result
        finally:
            self.depth -= 1

    def run_everything(self, paths, operations, analyses):
        from src.controllers.core.main_controller import MainController
        from src.views.dialogs.misc import import_dialog

        def fake_import_dialog(view, settings, file_paths=None):
            return True, paths, [{'sheet_name': 'Spectra' if p.endswith('.xlsx') else None,
                                  'jws_selected_channels': [0] if p.endswith('.jwb') else None}
                                 for p in paths]
        self.monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(fake_import_dialog))
        mc = MainController()
        name = ' + '.join(os.path.basename(p) for p in paths)

        def fresh(what):
            self.context[:] = [name, what]
            mc.import_controller._run_import(clear_first=True, file_paths=list(paths))
            self._pump()
            mc.spectrum_selector.select_all_items()
            self._pump()

        fresh('import')
        assert mc.import_controller.spectrum_manager.spectra, f'{name}: nothing imported'
        for op in operations:
            fresh('operation: ' + op)
            try:
                mc.operations_controller.show_parameters_dialog_for(op)
            except Exception:
                self._exception(*sys.exc_info())
            self._pump()
        for analysis in analyses:
            fresh('analysis: ' + analysis)
            if analysis == 'Peak Fitting':        # works on exactly one spectrum
                mc.spectra_list_widget.clearSelection()
                mc.spectra_list_widget.item(0).setSelected(True)
                self._pump()
            try:
                mc.run_visualization_analysis(analysis)
            except Exception:
                self._exception(*sys.exc_info())
            self._pump()
        mc.view.close()


class _ErrorLogHandler(logging.Handler):
    def __init__(self, driver):
        super().__init__(level=logging.ERROR)
        self.driver = driver

    def emit(self, record):
        if record.name.startswith(_ALLOWED_LOGGERS):
            return
        msg = record.getMessage()
        if record.exc_info:
            msg += f' | {record.exc_info[0].__name__}: {record.exc_info[1]}'
        self.driver._record('LOG ERROR', f'{record.name}: {msg}')


def _all_tools():
    from src.views.main_window import AnalysisTreeComboBox, OperationTreeComboBox
    ops = [o for _, items in OperationTreeComboBox.CATEGORIES for o in items
           if o != 'Run Batch Pipeline']
    analyses = [a for _, items in AnalysisTreeComboBox.CATEGORIES for a in items]
    return ops, analyses


def _write_table(path, x, columns):
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('x\t' + '\t'.join(f's{i}' for i in range(len(columns))) + '\n')
        for j in range(len(x)):
            fh.write(f'{x[j]:.4f}\t' + '\t'.join(f'{c[j]:.6g}' for c in columns) + '\n')


def _edge_files(tmp_path):
    x = np.linspace(400, 1800, 200)
    peak = lambda c: 5 * np.exp(-((x - c) / 15) ** 2) + 0.002 * x
    two = tmp_path / 'two_spectra.txt'
    _write_table(two, x, [peak(800), peak(820)])
    six = tmp_path / 'six_spectra.txt'
    _write_table(six, x, [peak(800 + 15 * i) for i in range(6)])
    x2 = np.linspace(500, 1700, 150)
    other = tmp_path / 'other_axis.txt'
    _write_table(other, x2, [5 * np.exp(-((x2 - 800 - 10 * i) / 15) ** 2) for i in range(4)])
    return {'two spectra': [str(two)], 'mixed x-axes': [str(six), str(other)]}


@pytest.mark.parametrize('case', ['CD spectra (real)', 'two spectra', 'mixed x-axes'])
def test_every_dialog_runs_without_errors(case, monkeypatch, tmp_path):
    paths = ([os.path.join(DATA, 'real', 'CD_spectra_TBA.txt')] if case == 'CD spectra (real)'
             else _edge_files(tmp_path)[case])
    ops, analyses = _all_tools()
    driver = _Driver(monkeypatch)
    try:
        driver.run_everything(paths, ops, analyses)
    finally:
        driver.close()
    assert not driver.problems, '\n' + '\n'.join(driver.problems)
