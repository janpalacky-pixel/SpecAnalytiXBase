"""The search field next to the drop-down lists of Spectra Processing and
Spectra Analysis & Visualization: a part of a tool's name or a word for what
it does gives the closest tools; choosing one selects it in the list."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from src.modules.misc import tool_search as ts

app = QApplication.instance() or QApplication([])


def _lists():
    from src.views.main_window import AnalysisTreeComboBox, OperationTreeComboBox
    return OperationTreeComboBox.CATEGORIES, AnalysisTreeComboBox.CATEGORIES


def test_every_tool_has_words_for_what_it_does():
    ops, analyses = _lists()
    tools = [t for _, items in ops + analyses for t in items]
    assert not [t for t in tools if t not in ts.KEYWORDS]


def test_a_part_of_the_name_a_word_for_what_it_does_or_a_small_typo():
    ops, analyses = _lists()
    assert ts.search('base', ops)[:3] == ['Manual baseline', 'Automated Baseline',
                                         'SNIP Baseline']
    assert ts.search('smooth', ops)[0] == 'SG-smoothing'
    assert ts.search('smoting', ops)[0] == 'SG-smoothing'             # a typo
    assert ts.search('normalise', ops) == ['Normalization']
    assert ts.search('snv', ops) == ['Normalization']
    assert ts.search('raman shift', ops) == ['X-axis Unit Conversion']  # every word must fit
    assert ts.search('pca', analyses) == ['PCA Scores & Loadings']
    assert ts.search('unmixing', analyses) == ['MCR-ALS']
    assert ts.search('fit', analyses)[:2] == ['Peak Fitting', 'Kinetics Fitting']
    assert ts.search('peak', ops) == [] and ts.search('', analyses) == []
    assert ts.search('xyzqw', analyses) == []


def test_the_field_selects_the_tool_also_in_the_other_list():
    from src.views.main_window import AnalysisTreeComboBox, OperationTreeComboBox
    ops, analyses = OperationTreeComboBox(), AnalysisTreeComboBox()
    ops.set_search_partner(analyses, "Spectra Analysis & Visualization")
    analyses.set_search_partner(ops, "Spectra Processing")
    chosen = []
    ops.currentTextChanged.connect(chosen.append)
    ops.search_field.setText('smooth')
    ops._search_typed('smooth')
    assert ops._search_model.stringList()[0] == 'SG-smoothing'
    ops._search_chosen('SG-smoothing')
    assert ops.currentText() == 'SG-smoothing' and chosen == ['SG-smoothing']
    assert ops.search_field.text() == ''
    # nothing in this list: the other list's tools, with where they are
    ops._search_typed('peak fit')
    shown = ops._search_model.stringList()
    assert shown == ['Peak Fitting  (in Spectra Analysis & Visualization)']
    ops._search_chosen(shown[0])
    assert analyses.currentText() == 'Peak Fitting' and ops.currentText() == 'SG-smoothing'
    # Enter: the first one
    analyses.search_field.setText('melt')
    analyses._search_enter()
    assert analyses.currentText() == 'Melting Curve Analysis'
    ops._search_typed('xyzqw')
    assert ops._search_model.stringList() == ['(no tool found)']
    ops._search_chosen('(no tool found)')                              # nothing happens
    assert ops.currentText() == 'SG-smoothing'
