# src/views/dialogs/misc/rich_text.py
"""Text with superscript, subscript, Greek letters and special signs - for
the texts drawn in a plot (axis titles, the plot title, the legend's title
and names, labels on the plot ...).

  * RichTextEditor - the editor: you see the text as it will look (x² as a
    small raised 2), with buttons for superscript / subscript, Greek letters
    and signs (°, ±, ×, →, Å, cm⁻¹ ...), and a preview drawn as in the plot;
  * RichTextDialog - the editor in a small window (OK / Cancel);
  * RichTextButton - a button showing the text (cut short, all of it in its
    tooltip); a click opens the editor.

The text is kept as matplotlib draws it: superscript as $\\mathregular{^{-1}}$,
subscript as $\\mathregular{_{2}}$ (\\mathregular: in the plot's own font)."""

import html
import re

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMenu,
                             QPushButton, QSizePolicy, QTextEdit, QToolButton, QVBoxLayout,
                             QWidget)

GREEK = 'αβγδεζηθικλμνξοπρστυφχψω' + 'ΓΔΘΛΞΠΣΦΨΩ'
SIGNS = (('°', "degree"), ('±', "plus-minus"), ('×', "times"), ('·', "middle dot"),
         ('−', "minus"), ('→', "arrow right"), ('←', "arrow left"), ('↑', "arrow up"),
         ('↓', "arrow down"), ('↔', "arrow both ways"), ('≈', "about"), ('≠', "not equal"),
         ('≤', "at most"), ('≥', "at least"), ('∞', "infinity"), ('‰', "per mille"),
         ('Å', "ångström"), ('µ', "micro"), ('′', "prime"), ('″', "double prime"),
         ('∆', "increment"), ('√', "square root"), ('∑', "sum"), ('∫', "integral"))
# superscript / subscript as matplotlib's math text: $\mathregular{^{..}}$ or $^{..}$
_MATH = re.compile(r'\$\\mathregular\{([\^_])\{(.*?)\}\}\$|\$([\^_])\{(.*?)\}\$')
_SUP = str.maketrans('0123456789+-−=()ni', '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾ⁿⁱ')
_SUB = str.maketrans('0123456789+-−=()', '₀₁₂₃₄₅₆₇₈₉₊₋₋₌₍₎')


def _parts(text):
    """[(kind, text)] of a stored text: kind '', '^' (superscript) or '_'."""
    out, at = [], 0
    for m in _MATH.finditer(text or ''):
        if m.start() > at:
            out.append(('', text[at:m.start()]))
        kind = m.group(1) or m.group(3)
        inner = m.group(2) if m.group(1) else m.group(4)
        out.append((kind, inner.replace('\\ ', ' ')))
        at = m.end()
    if at < len(text or ''):
        out.append(('', text[at:]))
    return out


def plain(text):
    """The text for a button or a list: x² for x$\\mathregular{^{2}}$ (Unicode where
    there is a sign for it, else x^(...))."""
    out = []
    for kind, part in _parts(text):
        if kind == '^':
            t = part.translate(_SUP)
            out.append(t if all(c in '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ' for c in t) else f"^({part})")
        elif kind == '_':
            t = part.translate(_SUB)
            out.append(t if all(c in '₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎' for c in t) else f"_({part})")
        else:
            out.append(part.replace('\\$', '$'))
    return ''.join(out)


def to_html(text):
    """The stored text as HTML for the editor (<sup>, <sub>)."""
    out = []
    for kind, part in _parts(text):
        part = html.escape(part.replace('\\$', '$')).replace('\n', '<br>')
        out.append(f"<sup>{part}</sup>" if kind == '^' else
                   f"<sub>{part}</sub>" if kind == '_' else part)
    return ''.join(out)


def from_document(document):
    """The editor's text in the stored form (superscript, subscript as math
    text; a $ written as \\$ so it is not taken as math)."""
    out = []
    block = document.begin()
    first = True
    while block.isValid():
        if not first:
            out.append('\n')
        first = False
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                text = frag.text()
                align = frag.charFormat().verticalAlignment()
                if align == QTextCharFormat.AlignSuperScript and text.strip():
                    out.append("$\\mathregular{^{%s}}$" % _math_escape(text))
                elif align == QTextCharFormat.AlignSubScript and text.strip():
                    out.append("$\\mathregular{_{%s}}$" % _math_escape(text))
                else:
                    out.append(text.replace('$', '\\$'))
            it += 1
        block = block.next()
    return ''.join(out)


def _math_escape(text):
    return text.replace(' ', '\\ ').replace('{', '').replace('}', '').replace('$', '')


def render(text, font_family='', size=14, colour='#000000'):
    """The text drawn as matplotlib draws it in the plot (a QPixmap), or None."""
    if not text:
        return None
    try:
        import io
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        fig = Figure(figsize=(0.1, 0.1), dpi=100)
        FigureCanvasAgg(fig)
        kw = {'fontsize': size, 'color': colour}
        if font_family:
            kw['fontfamily'] = font_family
        fig.text(0, 0, text, **kw)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', pad_inches=0.05,
                    facecolor='white')
        pix = QPixmap()
        pix.loadFromData(buf.getvalue(), 'PNG')
        return pix
    except Exception:
        return None


class RichTextEditor(QWidget):
    """Type the text; x² / x₂ make the chosen letters (or what is typed next)
    raised or lowered; αβγ and ° ± … add a Greek letter or a sign."""
    changed = pyqtSignal()

    def __init__(self, text='', parent=None, multiline=True):
        super().__init__(parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.sup_button = self._tool("x²", "Superscript (raised, small): e.g. cm⁻¹, x².\n"
                                     "Choose letters first, or click and then type.",
                                     lambda: self._align(QTextCharFormat.AlignSuperScript))
        self.sub_button = self._tool("x₂", "Subscript (lowered, small): e.g. H₂O, λₘₐₓ.",
                                     lambda: self._align(QTextCharFormat.AlignSubScript))
        self.normal_button = self._tool("x", "Normal: neither raised nor lowered.",
                                        lambda: self._align(QTextCharFormat.AlignNormal))
        greek = QToolButton()
        greek.setText("αβγ")
        greek.setToolTip("Greek letters")
        greek.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(greek)
        for i, ch in enumerate(GREEK):
            menu.addAction(ch, lambda ch=ch: self.insert(ch))
        greek.setMenu(menu)
        signs = QToolButton()
        signs.setText("° ± …")
        signs.setToolTip("Signs: °, ±, ×, arrows, Å, µ ...")
        signs.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(signs)
        for ch, name in SIGNS:
            menu.addAction(f"{ch}   {name}", lambda ch=ch: self.insert(ch))
        signs.setMenu(menu)
        unit = self._tool("cm⁻¹", "cm⁻¹: the unit of a Raman shift or a wavenumber.",
                          lambda: self.insert_parts([('', 'cm'), ('^', '−1')]))
        for w in (self.sup_button, self.sub_button, self.normal_button, greek, signs, unit):
            bar.addWidget(w)
        bar.addStretch(1)
        box.addLayout(bar)
        self.edit = QTextEdit()
        self.edit.setAcceptRichText(False)
        font = QFont(self.edit.font())
        font.setPointSizeF(max(11.0, font.pointSizeF() * 1.25))
        self.edit.setFont(font)
        self.edit.setFixedHeight(80 if multiline else 46)
        self.edit.setToolTip("The text as it will look. Enter: a new line.")
        box.addWidget(self.edit)
        box.addWidget(QLabel("In the plot:"))
        self.preview = QLabel()
        self.preview.setMinimumHeight(36)
        self.preview.setStyleSheet("background: white; border: 1px solid #ccc; padding: 4px;")
        box.addWidget(self.preview)
        self.set_text(text)
        self.edit.textChanged.connect(self._changed)

    @staticmethod
    def _tool(text, tip, slot):
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.clicked.connect(slot)
        return b

    def set_text(self, text):
        self.edit.setHtml(to_html(text or ''))
        if not text:                    # an empty text starts neither raised nor lowered
            normal = QTextCharFormat()
            normal.setVerticalAlignment(QTextCharFormat.AlignNormal)
            self.edit.setCurrentCharFormat(normal)
        self._changed()

    def text(self):
        return from_document(self.edit.document())

    setText = set_text                  # like a QLineEdit

    def insert(self, chars):
        self.edit.insertPlainText(chars)
        self.edit.setFocus()

    def insert_parts(self, parts):
        cur = self.edit.textCursor()
        for kind, text in parts:
            fmt = QTextCharFormat()
            fmt.setVerticalAlignment({'^': QTextCharFormat.AlignSuperScript,
                                      '_': QTextCharFormat.AlignSubScript}.get(
                                          kind, QTextCharFormat.AlignNormal))
            cur.insertText(text, fmt)
        normal = QTextCharFormat()
        normal.setVerticalAlignment(QTextCharFormat.AlignNormal)
        self.edit.setCurrentCharFormat(normal)
        self.edit.setFocus()

    def _align(self, alignment):
        fmt = QTextCharFormat()
        fmt.setVerticalAlignment(alignment)
        cur = self.edit.textCursor()
        if cur.hasSelection():
            cur.mergeCharFormat(fmt)
        self.edit.mergeCurrentCharFormat(fmt)
        self.edit.setFocus()

    def _changed(self):
        pix = render(self.text())
        if pix is None:
            self.preview.setText("")
            self.preview.setPixmap(QPixmap())
        else:
            self.preview.setPixmap(pix)
        self.changed.emit()


class RichTextDialog(QDialog):
    """The editor in a small window."""

    def __init__(self, text='', parent=None, title="Text", hint=''):
        super().__init__(parent)
        self.setWindowTitle(title)
        box = QVBoxLayout(self)
        if hint:
            label = QLabel(hint)
            label.setWordWrap(True)
            box.addWidget(label)
        self.editor = RichTextEditor(text)
        box.addWidget(self.editor)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        clear = buttons.addButton("Clear", QDialogButtonBox.ResetRole)
        clear.setToolTip("Clear: no text (where it can be empty: as in the plot).")
        clear.clicked.connect(lambda: self.editor.set_text(''))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        self.resize(460, 260)
        self.editor.edit.setFocus()
        self.editor.edit.moveCursor(QTextCursor.End)

    def text(self):
        return self.editor.text()

    @staticmethod
    def ask(text='', parent=None, title="Text", hint=''):
        """(text, ok) - like QInputDialog.getText."""
        dlg = RichTextDialog(text, parent, title, hint)
        ok = dlg.exec_() == QDialog.Accepted
        return (dlg.text() if ok else text), ok


class RichTextButton(QPushButton):
    """Shows the text (cut short; all of it in the tooltip); a click opens the
    editor. Used like a QLineEdit: text(), setText(), textChanged,
    setPlaceholderText()."""
    textChanged = pyqtSignal(str)

    def __init__(self, text='', title="Text", parent=None):
        super().__init__(parent)
        self._text = text or ''
        self._placeholder = ''
        self._title = title
        self.setAutoDefault(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(40)
        self.clicked.connect(self.edit)
        self._show()

    def text(self):
        return self._text

    def setText(self, text):
        text = text or ''
        if text != self._text:
            self._text = text
            self._show()
            self.textChanged.emit(text)
        else:
            self._show()

    def setPlaceholderText(self, text):
        self._placeholder = text or ''
        self._show()

    def placeholderText(self):
        return self._placeholder

    def edit(self):
        text, ok = RichTextDialog.ask(self._text, self.window(), self._title)
        if ok:
            self.setText(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._show()

    def _show(self):
        shown = plain(self._text) if self._text else plain(self._placeholder)
        shown = shown.replace('\n', ' ')
        width = max(20, self.width() - 16)
        super().setText(self.fontMetrics().elidedText(shown, Qt.ElideRight, width))
        self.setStyleSheet("" if self._text else "QPushButton { color: #888; }")
        full = plain(self._text) if self._text else (
            f"empty: {plain(self._placeholder)}" if self._placeholder else "empty")
        self.setToolTip(f"{full}\nClick to change it (superscript, subscript, Greek letters, "
                        "signs).")
