"""Data table -> "Values per spectrum": one row per spectrum with its stored
values and the numbers in its name, value columns computed exactly as in
Group Statistics (Add value...), formula columns, copy / export, and a plot
of one column against another."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

from src.modules.data_analysis.value_table import ValueTable
from src.modules.visualization_analysis import group_values as gv

app = QApplication.instance() or QApplication([])


def _spectra():
    x = np.linspace(0, 100, 501)
    out = []
    for i, t in enumerate([20.0, 40.0, 60.0]):
        out.append({'label': f'TBA_{int(t)}C : 000{i + 1}', 'x_scale': x,
                    'y_scale': (3 - i) * np.exp(-((x - 50) / 5) ** 2),
                    'metadata': {'temperature_C': t, 'unique_id': 'u', 'valid_points': 501}})
    x2 = np.linspace(60, 100, 50)                      # does not cover 30-70
    out.append({'label': 'short', 'x_scale': x2, 'y_scale': np.ones_like(x2), 'metadata': {}})
    return out


def test_columns_from_the_spectra():
    t = ValueTable.from_spectra(_spectra())
    assert [(c.name, c.kind) for c in t.columns] == [
        ('name', 'name'), ('temperature_C', 'metadata'), ('n1', 'number'), ('n2', 'number')]
    assert list(t.column('n1').values[:3]) == [20, 40, 60]
    assert np.isnan(t.column('temperature_C').values[3])
    assert t.row_names() == ['sp1', 'sp2', 'sp3', 'sp4']


def test_values_as_in_group_statistics():
    sp = _spectra()
    t = ValueTable.from_spectra(sp)
    area = t.add_value({'kind': 'area', 'range_a': (30, 70)})
    expected, _ = gv.compute_values(sp, ['all'] * 4, {'kind': 'area', 'range_a': (30, 70)})
    assert area.name == 'v1' and area.title == 'Area over 30–70'
    assert np.allclose(area.values[:3], expected[:3]) and np.isnan(area.values[3])
    assert area.values[0] == pytest.approx(3 * 5 * np.sqrt(np.pi), rel=1e-3)
    pos = t.add_value({'kind': 'peak_position', 'range_a': (30, 70), 'max_mode': 'parabola'})
    assert np.allclose(pos.values[:3], 50, atol=0.05)
    ratio = t.add_value({'kind': 'ratio', 'range_a': (30, 70), 'range_b': (40, 60)})
    assert np.allclose(ratio.values[:3], ratio.values[0])          # same band shape
    at = t.add_value({'kind': 'intensity_at_x', 'x0': 50})
    assert np.allclose(at.values[:3], [3, 2, 1]) and np.isnan(at.values[3])  # 50 outside 60-100


def test_formulas_remove_and_plot_data():
    t = ValueTable.from_spectra(_spectra())
    t.add_value({'kind': 'max', 'range_a': (30, 70)})
    f = t.add_formulas('v1 / max_val(v1), v1 * temperature_C')
    assert np.allclose(f[0].values[:3], [1, 2 / 3, 1 / 3]) and f[1].values[1] == pytest.approx(80)
    assert np.isnan(f[0].values[3])                    # no value stays no value
    with pytest.raises(ValueError, match='use the column names'):
        t.add_formula('nonsense + 1')
    with pytest.raises(ValueError, match='f1'):
        t.remove_column('v1')
    x, y, labels = t.xy('temperature_C', 'v1')
    assert list(x) == [20, 40, 60] and len(labels) == 3            # 'short' has no temperature
    with pytest.raises(ValueError):
        t.xy('name', 'v1')


def test_copy_and_export(tmp_path):
    t = ValueTable.from_spectra(_spectra())
    t.add_value({'kind': 'area', 'range_a': (30, 70)})
    lines = t.rows_as_text().splitlines()
    assert lines[0].split('\t')[:3] == ['sp', 'Spectrum', 'temperature_C']
    assert lines[0].endswith('v1: Area over 30–70') and lines[4].split('\t')[-1] == ''
    import pandas as pd
    t.export(str(tmp_path / 'v.xlsx'))
    assert pd.read_excel(tmp_path / 'v.xlsx').shape == (4, 6)


def test_the_tab_in_the_data_table():
    from src.views.dialogs.data_analysis.data_table_dialog import DataTableDialog
    from src.views.dialogs.data_analysis.value_table_panel import ValueChoiceDialog
    sp = _spectra()[:3]
    dlg = DataTableDialog(None, sp)
    assert [dlg.tabs.tabText(i) for i in range(2)] == ['Points (one row per x)', 'Values per spectrum']
    p = dlg.values
    col = p.add_value({'kind': 'area', 'range_a': (30, 70)})
    assert p.model.columnCount() == 5 and p.y_combo.currentText() == col.name
    p.formula_edit.setText('v1 / 2')
    assert p.add_formula().name == 'f1'
    p.x_combo.setCurrentText('temperature_C')
    plot = p.plot()
    assert list(plot.points[0]) == [20, 40, 60]
    plot.close()
    choice = ValueChoiceDialog(None, sp)
    choice.kind.setCurrentIndex(choice.kind.findData('ratio'))
    assert choice._visible() >= {'range_a', 'range_b', 'operation'}
    choice.kind.setCurrentIndex(choice.kind.findData('intensity_at_x'))
    assert choice._visible() == {'x0', 'x_mode'}
    assert choice.settings()['kind'] == 'intensity_at_x'
    dlg.close()
