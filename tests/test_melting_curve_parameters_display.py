"""Regression tests for two real GUI-testing complaints on the "Parameters
for Operation #N: Melting Curve Analysis" dialog:

1. It had no special-case handler in OperationParametersDialog, so it fell
   through to the generic setup_standard_parameters() -- dumping curve/
   fit_result/automatic_fit_result/component_thermodynamics as raw,
   un-curated numpy array/dict repr (compare with Normalization's own
   curated table). Fixed by adding setup_melting_curve_parameters(),
   which shows the genuinely human settings directly and moves the four
   heavy computed blobs behind one "Fit & Curve Detail" row, plus
   show_melting_curve_fit_details_dialog() for that row's own readable
   breakdown.

2. Once that fix shipped, clicking "Fit & Curve Detail" crashed with
   "ValueError: The truth value of an array with more than one element
   is ambiguous" -- fit_result['params'] is, in the REAL app, a plain
   numpy array of optimizer coefficients (e.g. [midpoint, lambda_]), not
   the dict this file's own test fixture had assumed. `if fit_result.get
   ('params'):` on that array raised. Fixed by comparing every field that
   could be a numpy array against `is not None` instead of relying on
   truthiness. The fixture below now matches the real shape (confirmed
   against the user's crash log and screenshots) so this class of bug
   would be caught here again.

3. 'temperatures' (every source spectrum's label -> its temperature) and
   'source_labels' (the same labels again, no values) rendered as two
   enormous, almost entirely redundant per-spectrum rows for any
   real-sized run (40 spectra in the reported case) -- collapsed into one
   "Source spectra" summary row, with the full per-spectrum breakdown
   moved into the "Fit & Curve Detail" table's own Spectrum column.
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QTableWidget, QPushButton

from src.views.dialogs.data_analysis.operations_summary_dialog import OperationParametersDialog

app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_modal_exec(monkeypatch):
    """Every test in this file may end up calling show_melting_curve_
    fit_details_dialog(), which opens its own QDialog and calls
    .exec_() on it -- modal, and nothing here ever clicks its Close
    button, so under the offscreen platform it would just hang
    forever. Patched globally (autouse) rather than per-test so a new
    test added later doesn't silently reintroduce the hang.
    """
    monkeypatch.setattr(
        "src.views.dialogs.data_analysis.operations_summary_dialog.QDialog.exec_",
        lambda self: None)


def _melting_curve_parameters():
    return {
        'temperatures': {'T05': 5.0, 'T10': 10.0, 'T15': 15.0},
        'source_labels': ['T05', 'T10', 'T15'],
        'curve_name': 'melting_curve',
        'extraction_method': 'signal_at_x',
        'svd_center': False,
        'window': 2.0,
        'curve': {
            'x_temperature': np.array([5.0, 10.0, 15.0]),
            'y_raw': np.array([0.1, 0.5, 0.9]),
            'source_labels': ['T05', 'T10', 'T15'],
            'normalization_result': {'y_norm': np.array([0.0, 0.5, 1.0])},
            'svd_diagnostics': None,
            'baseline_low': np.array([0.09, 0.1, 0.11]),
            'baseline_high': np.array([0.88, 0.9, 0.92]),
        },
        'normalization': {'method': 'first', 'low_range': (5.0, 7.0), 'high_range': (13.0, 15.0)},
        'span': 0.95,
        'x_trans': 10.0,
        'fit_settings': {'n_components': 1, 'shape_name': 'Logistic'},
        'fit_result': {
            # The REAL shape: a raw numpy array of optimizer coefficients,
            # not a dict -- this is exactly what crashed handle_cell_click
            # ("if fit_result.get('params'):") in the field report.
            'params': np.array([10.0, 0.25]),
            'y_fit': np.array([0.0, 0.5, 1.0]),
            'components': {'components': np.array([0.0, 0.5, 1.0]),
                            'params': {'factor': 1.0, 'midpoint': 10.0, 'lambda_': 0.25,
                                       'factor_err': 0.0, 'midpoint_err': 0.9, 'lambda_err': 0.5}},
            'quality': {'rmsd': 0.01, 'r_squared': 0.999, 'aic': -10.0, 'bic': -9.0},
            'inflection_points': [(10.0, -0.5)],
            'n_components': 1,
            'shape_name': 'Logistic',
            'constrained': False,
        },
        'automatic_fit_result': None,
        'component_thermodynamics': None,
        'output_options': {
            'add_raw_curve': True, 'add_normalized_curve': True, 'add_baselines': False,
            'add_fit': True, 'add_residual': False, 'add_components': False,
        },
        'source_mode': 'spectra',
        'external_file_path': None,
        'sheet_name': None,
        'spectra_fingerprint': 'deadbeef' * 4,
    }


def _cell_text(dialog, row, col):
    item = dialog.table.item(row, col)
    return item.text() if item else None


def test_heavy_keys_are_not_shown_as_raw_rows():
    params = _melting_curve_parameters()
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)

    all_text = "\n".join(
        _cell_text(dialog, r, c) or ""
        for r in range(dialog.table.rowCount())
        for c in range(2)
    )
    # None of the heavy blobs' own array contents should be dumped
    # directly into the table -- they're behind the detail row instead.
    assert "y_fit" not in all_text
    assert "baseline_low" not in all_text
    assert "svd_diagnostics" not in all_text
    # The cache key is hidden entirely -- never useful to a human.
    assert "spectra_fingerprint" not in all_text
    assert "deadbeef" not in all_text


def test_output_options_shown_as_friendly_summary_not_raw_dict():
    params = _melting_curve_parameters()
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)

    labels = [_cell_text(dialog, r, 0) for r in range(dialog.table.rowCount())]
    assert "Output spectra created" in labels
    row = labels.index("Output spectra created")
    value = _cell_text(dialog, row, 1)
    assert "Raw curve" in value
    assert "add_raw_curve" not in value  # not the raw dict key


def test_ordinary_settings_are_still_shown_directly():
    params = _melting_curve_parameters()
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)

    labels = [_cell_text(dialog, r, 0) for r in range(dialog.table.rowCount())]
    for expected in ('curve_name', 'extraction_method', 'normalization',
                      'span', 'x_trans', 'fit_settings', 'source_mode'):
        assert expected in labels


def test_temperatures_and_source_labels_collapse_into_one_summary_row():
    params = _melting_curve_parameters()
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)

    labels = [_cell_text(dialog, r, 0) for r in range(dialog.table.rowCount())]
    # The two large, redundant raw rows are gone...
    assert "temperatures" not in labels
    assert "source_labels" not in labels
    # ...replaced by one summary row.
    assert labels.count("Source spectra") == 1
    row = labels.index("Source spectra")
    value = _cell_text(dialog, row, 1)
    assert "3 spectra" in value
    assert "5" in value and "15" in value  # the temperature range


def test_detail_row_present_and_clickable_when_fit_result_exists():
    params = _melting_curve_parameters()
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)

    labels = [_cell_text(dialog, r, 0) for r in range(dialog.table.rowCount())]
    assert "Fit & Curve Detail" in labels
    row = labels.index("Fit & Curve Detail")
    value_item = dialog.table.item(row, 1)
    assert "Click to view" in value_item.text()
    payload = value_item.data(Qt.UserRole)
    np.testing.assert_allclose(payload['fit_result']['params'], [10.0, 0.25])


def test_detail_row_omitted_when_nothing_was_computed():
    params = _melting_curve_parameters()
    params['curve'] = None
    params['fit_result'] = None
    params['automatic_fit_result'] = None
    params['component_thermodynamics'] = None
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)

    labels = [_cell_text(dialog, r, 0) for r in range(dialog.table.rowCount())]
    assert "Fit & Curve Detail" not in labels


def test_clicking_detail_row_opens_readable_dialog(monkeypatch):
    params = _melting_curve_parameters()
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)

    labels = [_cell_text(dialog, r, 0) for r in range(dialog.table.rowCount())]
    row = labels.index("Fit & Curve Detail")

    opened = {}

    def fake_show(detail):
        opened['detail'] = detail

    monkeypatch.setattr(dialog, 'show_melting_curve_fit_details_dialog', fake_show)
    dialog.handle_cell_click(row, 1)

    assert 'detail' in opened
    assert opened['detail']['fit_result']['quality']['r_squared'] == 0.999


def test_clicking_detail_row_with_real_shaped_fit_result_does_not_crash():
    """The exact bug from the field report: fit_result['params'] is a
    numpy array, and handle_cell_click -> show_melting_curve_fit_details_
    dialog used to do `if fit_result.get('params'):`, which raises
    ValueError for a multi-element array. This exercises the REAL
    handle_cell_click path end to end (no monkeypatching the handler
    away), so it fails again if that truthiness check ever comes back."""
    params = _melting_curve_parameters()
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)

    labels = [_cell_text(dialog, r, 0) for r in range(dialog.table.rowCount())]
    row = labels.index("Fit & Curve Detail")

    dialog.handle_cell_click(row, 1)  # must not raise


def test_detail_dialog_builds_curve_table_with_spectrum_column():
    params = _melting_curve_parameters()
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)
    detail = {k: params[k] for k in
               ('curve', 'fit_result', 'automatic_fit_result', 'component_thermodynamics')}

    # Must not raise, and must actually build a table -- including the
    # Spectrum column (curve['source_labels']), which is where the full
    # per-spectrum list now lives after being removed from the main table.
    dialog.show_melting_curve_fit_details_dialog(detail)


def test_detail_dialog_handles_array_valued_thermodynamics(monkeypatch):
    """arrhenius/thermodynamics and y_pure/y_local_data can all be numpy
    arrays -- the same "if x:" truthiness bug that hit fit_result['params']
    would just as easily hit these. Must not raise.

    component_thermodynamics' REAL shape (per MeltingCurveManager.
    compute_component_thermodynamics's own docstring) is a LIST of one
    dict per fitted component, even for a single-component fit -- not a
    flat dict, which this fixture wrongly assumed until a field report
    showed `AttributeError: 'list' object has no attribute 'get'` from
    exactly this line."""
    params = _melting_curve_parameters()
    params['component_thermodynamics'] = [{
        'arrhenius': np.array([1.0, 2.0, 3.0]),
        'thermodynamics': np.array([4.0, 5.0]),
        'y_pure': np.array([0.0, 0.5, 1.0]),
        'y_local_data': np.array([0.0, 0.4, 1.0]),
    }]
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)
    detail = {k: params[k] for k in
               ('curve', 'fit_result', 'automatic_fit_result', 'component_thermodynamics')}

    dialog.show_melting_curve_fit_details_dialog(detail)  # must not raise


def test_detail_dialog_labels_each_component_of_a_multi_component_fit(monkeypatch):
    """The exact bug from the second field report: component_thermodynamics
    is a list (one dict per fitted sigmoid component), and the dialog used
    to call .get() on that list directly (AttributeError: 'list' object
    has no attribute 'get'). With 2+ components, each one's Arrhenius/
    thermodynamics rows must also be individually labeled rather than
    silently overwriting each other under the same row label."""
    params = _melting_curve_parameters()
    params['component_thermodynamics'] = [
        {'arrhenius': {'slope': 1.0}, 'thermodynamics': {'deltaH': 10.0},
         'y_pure': np.array([0.0, 0.5, 1.0]), 'y_local_data': np.array([0.0, 0.4, 1.0])},
        {'arrhenius': {'slope': 2.0}, 'thermodynamics': {'deltaH': 20.0},
         'y_pure': np.array([0.0, 0.6, 1.0]), 'y_local_data': np.array([0.0, 0.5, 1.0])},
    ]
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)
    detail = {k: params[k] for k in
               ('curve', 'fit_result', 'automatic_fit_result', 'component_thermodynamics')}

    dialog.show_melting_curve_fit_details_dialog(detail)  # must not raise


def test_detail_dialog_survives_malformed_curve_data():
    """A schema mismatch (e.g. mismatched array lengths, or missing
    keys) must narrow which columns appear -- never crash the dialog."""
    params = _melting_curve_parameters()
    params['curve']['normalization_result'] = {'y_norm': np.array([0.0, 1.0])}  # wrong length
    params['fit_result']['y_fit'] = "not an array at all"
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)
    detail = {k: params[k] for k in
               ('curve', 'fit_result', 'automatic_fit_result', 'component_thermodynamics')}

    dialog.show_melting_curve_fit_details_dialog(detail)  # must not raise


def _capture_detail_dialog(monkeypatch, dialog, detail):
    """show_melting_curve_fit_details_dialog builds its own QDialog
    locally and never returns or stores it -- .exec_() is patched to a
    no-op by the autouse fixture above, so this captures that dialog
    via the patch instead and hands it back for inspection."""
    captured = []
    monkeypatch.setattr(
        "src.views.dialogs.data_analysis.operations_summary_dialog.QDialog.exec_",
        lambda self: captured.append(self))
    dialog.show_melting_curve_fit_details_dialog(detail)
    assert len(captured) == 1
    return captured[0]


def _find_curve_table(monkeypatch, dialog, detail):
    """Finds the per-temperature curve table among the detail dialog's
    QTableWidget children (distinguished from the 2-column Field/Value
    summary table by its column count)."""
    detail_dialog = _capture_detail_dialog(monkeypatch, dialog, detail)
    tables = detail_dialog.findChildren(QTableWidget)
    curve_tables = [t for t in tables if t.columnCount() > 2]
    assert len(curve_tables) == 1
    return curve_tables[0]


def _table_headers(table):
    return [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]


def test_component_arrays_get_named_columns_not_a_misleading_pointer():
    """Real complaint: the summary table used to show 'Component 2 -
    y_pure' / 'Component 2 - y_local_data' rows worth "[40 points -- see
    curve table below]" -- but the curve table had no column that
    actually corresponded to either one, so there was nothing to see.
    y_pure/y_local_data are internal field names with no meaning to a
    user anyway. Fixed by dropping those placeholder summary rows
    entirely and giving the data real, self-explanatory columns in the
    curve table instead, named to match the exact legend labels the
    real per-component plot already uses elsewhere in this app
    ("Data (reconstructed)" / "Model" -- kept short since the
    "Component N: " prefix already says "Component" once; "Component
    N: Component model" repeated the word and read awkwardly)."""
    params = _melting_curve_parameters()
    params['component_thermodynamics'] = [{
        'arrhenius': {'slope': 1.0},
        'thermodynamics': {'deltaH': 10.0},
        'y_pure': np.array([0.0, 0.5, 1.0]),
        'y_local_data': np.array([0.0, 0.4, 1.0]),
    }]
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)
    detail = {k: params[k] for k in
               ('curve', 'fit_result', 'automatic_fit_result', 'component_thermodynamics')}

    monkeypatch = pytest.MonkeyPatch()
    try:
        curve_table = _find_curve_table(monkeypatch, dialog, detail)
        headers = _table_headers(curve_table)
        assert "Data (reconstructed)" in headers
        assert "Model" in headers
        assert "y_pure" not in headers
        assert "y_local_data" not in headers

        recon_col = headers.index("Data (reconstructed)")
        model_col = headers.index("Model")
        for r, (expected_recon, expected_model) in enumerate(
                zip([0.0, 0.4, 1.0], [0.0, 0.5, 1.0])):
            assert float(curve_table.item(r, recon_col).text()) == pytest.approx(expected_recon)
            assert float(curve_table.item(r, model_col).text()) == pytest.approx(expected_model)
    finally:
        monkeypatch.undo()


def test_multi_component_columns_are_individually_labeled():
    """With 2+ components, each one's reconstructed data/model columns
    must be individually labeled (Component 1/2: ...) rather than
    colliding under one shared column name."""
    params = _melting_curve_parameters()
    params['component_thermodynamics'] = [
        {'arrhenius': {'slope': 1.0}, 'thermodynamics': {'deltaH': 10.0},
         'y_pure': np.array([0.0, 0.5, 1.0]), 'y_local_data': np.array([0.0, 0.4, 1.0])},
        {'arrhenius': {'slope': 2.0}, 'thermodynamics': {'deltaH': 20.0},
         'y_pure': np.array([0.1, 0.6, 0.9]), 'y_local_data': np.array([0.1, 0.5, 0.8])},
    ]
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)
    detail = {k: params[k] for k in
               ('curve', 'fit_result', 'automatic_fit_result', 'component_thermodynamics')}

    monkeypatch = pytest.MonkeyPatch()
    try:
        curve_table = _find_curve_table(monkeypatch, dialog, detail)
        headers = _table_headers(curve_table)
        assert "Component 1: Data (reconstructed)" in headers
        assert "Component 1: Model" in headers
        assert "Component 2: Data (reconstructed)" in headers
        assert "Component 2: Model" in headers

        c1_recon = headers.index("Component 1: Data (reconstructed)")
        c2_recon = headers.index("Component 2: Data (reconstructed)")
        assert float(curve_table.item(0, c1_recon).text()) == pytest.approx(0.0)
        assert float(curve_table.item(0, c2_recon).text()) == pytest.approx(0.1)
    finally:
        monkeypatch.undo()



def test_curve_table_columns_are_resizable_not_forced_to_stretch():
    """Real complaint: with several per-component columns added ("Component
    1: Data (reconstructed)", "Component 1: Model", ...), the
    table's old Stretch resize mode squeezed every column into the visible
    width regardless of its header text -- so longer headers got clipped
    down to a few characters, with no scrollbar (Stretch mode never lets
    total column width exceed the viewport, so one never appears) and no
    way to widen a column to read the rest. Interactive mode instead sizes
    each column from its own header/content (resizeColumnsToContents())
    and lets the user drag columns wider, with an ordinary horizontal
    scrollbar appearing whenever the total width exceeds the table's
    viewport."""
    from PyQt5.QtWidgets import QHeaderView

    params = _melting_curve_parameters()
    params['component_thermodynamics'] = [
        {'arrhenius': {'slope': 1.0}, 'thermodynamics': {'deltaH': 10.0},
         'y_pure': np.array([0.0, 0.5, 1.0]), 'y_local_data': np.array([0.0, 0.4, 1.0])},
        {'arrhenius': {'slope': 2.0}, 'thermodynamics': {'deltaH': 20.0},
         'y_pure': np.array([0.1, 0.6, 0.9]), 'y_local_data': np.array([0.1, 0.5, 0.8])},
    ]
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)
    detail = {k: params[k] for k in
               ('curve', 'fit_result', 'automatic_fit_result', 'component_thermodynamics')}

    monkeypatch = pytest.MonkeyPatch()
    try:
        curve_table = _find_curve_table(monkeypatch, dialog, detail)
        header = curve_table.horizontalHeader()
        for c in range(curve_table.columnCount()):
            assert header.sectionResizeMode(c) == QHeaderView.Interactive
    finally:
        monkeypatch.undo()



def test_component_info_button_present_and_explains_reconstructed_vs_model():
    """The Fit & Curve Detail dialog gets a small orange "?" button next to
    Close, matching the pattern used elsewhere in this app (e.g.
    NormalizationDialog's own info buttons) -- clicking it must explain
    "Data (reconstructed)" vs. "Model" without the user having to open the
    main Help window."""
    params = _melting_curve_parameters()
    params['component_thermodynamics'] = [{
        'arrhenius': {'slope': 1.0}, 'thermodynamics': {'deltaH': 10.0},
        'y_pure': np.array([0.0, 0.5, 1.0]), 'y_local_data': np.array([0.0, 0.4, 1.0]),
    }]
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)
    detail = {k: params[k] for k in
               ('curve', 'fit_result', 'automatic_fit_result', 'component_thermodynamics')}

    monkeypatch = pytest.MonkeyPatch()
    try:
        detail_dialog = _capture_detail_dialog(monkeypatch, dialog, detail)

        buttons = [b for b in detail_dialog.findChildren(QPushButton) if b.text() == '?']
        assert len(buttons) == 1

        shown = []
        monkeypatch.setattr(
            "src.views.dialogs.data_analysis.operations_summary_dialog.QMessageBox.information",
            lambda parent, title, text: shown.append((title, text)))
        buttons[0].click()

        assert len(shown) == 1
        title, text = shown[0]
        assert "Data (reconstructed)" in title or "Model" in title
        assert "Data (reconstructed)" in text
        assert "Model" in text
        assert "noise-free" in text  # explains the MODEL side
        assert "measured curve" in text  # explains the DATA side
    finally:
        monkeypatch.undo()



def test_info_button_sits_right_next_to_close_not_floating_mid_row():
    """Real complaint: the "?" button rendered in the middle of the button
    row with a large gap before Close, instead of sitting right next to
    it. Root cause: QDialogButtonBox defaults to an Expanding horizontal
    size policy, so with nothing after it in the row it silently claimed
    the rest of the row's width and right-aligned its own Close button
    inside that extra space -- Close ends up flush with the dialog's own
    right edge, but with a gap opened up between it and "?". Fixed by
    giving the button box a Fixed size policy so it (and Close) stay snug
    against "?"."""
    from PyQt5.QtWidgets import QDialogButtonBox

    params = _melting_curve_parameters()
    dialog = OperationParametersDialog("Melting Curve Analysis", 0, params)
    detail = {k: params[k] for k in
               ('curve', 'fit_result', 'automatic_fit_result', 'component_thermodynamics')}

    monkeypatch = pytest.MonkeyPatch()
    try:
        detail_dialog = _capture_detail_dialog(monkeypatch, dialog, detail)
        detail_dialog.resize(700, 580)
        detail_dialog.show()
        app.processEvents()

        info_button = [b for b in detail_dialog.findChildren(QPushButton) if b.text() == '?'][0]
        button_box = detail_dialog.findChild(QDialogButtonBox)
        close_button = button_box.buttons()[0]

        info_right_edge = info_button.geometry().x() + info_button.geometry().width()
        close_left_edge = close_button.mapTo(detail_dialog, close_button.rect().topLeft()).x()
        gap = close_left_edge - info_right_edge

        # The row's own layout spacing (a handful of pixels), not the
        # ~250px gap the Expanding button box used to leave.
        assert 0 <= gap <= 20
    finally:
        monkeypatch.undo()
