"""Text with superscript, subscript, Greek letters and signs for the texts in
a plot (src/views/dialogs/misc/rich_text.py): kept as matplotlib's math text,
edited as it will look, shown short on a button."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtGui import QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


def test_stored_text_and_what_is_shown():
    from src.views.dialogs.misc.rich_text import plain, to_html
    stored = 'Raman shift (cm$\\mathregular{^{-1}}$), H$\\mathregular{_{2}}$O'
    assert plain(stored) == 'Raman shift (cm⁻¹), H₂O'
    assert plain('cm$^{-1}$') == 'cm⁻¹'                          # the older short form too
    assert plain('x$\\mathregular{^{abc}}$') == 'x^(abc)'
    assert '<sup>-1</sup>' in to_html(stored) and '<sub>2</sub>' in to_html(stored)


def test_the_editor_round_trip_and_buttons():
    from src.views.dialogs.misc.rich_text import RichTextEditor, plain
    ed = RichTextEditor('cm$^{-1}$')
    assert ed.text() == 'cm$\\mathregular{^{-1}}$'                # kept in the plot's font
    ed.set_text('')
    ed.edit.insertPlainText('H2O')
    cur = ed.edit.textCursor()                                     # "2" chosen, x₂ clicked
    cur.setPosition(1)
    cur.setPosition(2, QTextCursor.KeepAnchor)
    ed.edit.setTextCursor(cur)
    ed.sub_button.click()
    assert ed.text() == 'H$\\mathregular{_{2}}$O' and plain(ed.text()) == 'H₂O'
    ed.set_text('')
    ed.insert('λ = 785 nm, 25 °C, 10 $')
    assert ed.text() == 'λ = 785 nm, 25 °C, 10 \\$'               # a $ is not taken as math
    assert ed.preview.pixmap() is not None and not ed.preview.pixmap().isNull()


def test_the_button(monkeypatch):
    from src.views.dialogs.misc import rich_text
    b = rich_text.RichTextButton('', "X title")
    b.setPlaceholderText('Raman shift (cm$^{-1}$)')
    b.resize(300, 26)
    assert 'Raman shift (cm⁻¹)' in b.toolTip() and b.text() == ''
    seen = []
    b.textChanged.connect(seen.append)
    monkeypatch.setattr(rich_text.RichTextDialog, 'ask',
                        staticmethod(lambda text='', *a, **k: ('Shift (cm$^{-1}$)', True)))
    b.click()
    assert b.text() == 'Shift (cm$^{-1}$)' and seen == ['Shift (cm$^{-1}$)']
    assert QPushButtonText(b) == 'Shift (cm⁻¹)'


def QPushButtonText(b):
    from PyQt5.QtWidgets import QPushButton
    return QPushButton.text(b)
