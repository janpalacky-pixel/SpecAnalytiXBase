# src/views/theme.py
"""Light (default) or dark theme: View -> Theme. Used from the next start.

The windows of the program set many of their own colours (about 370 style
sheets in 50 files, coloured texts in labels, tinted table cells). Instead
of editing every one of them, the dark theme converts colours as they are
set: every colour keeps its hue and saturation but gets the opposite
lightness (white backgrounds -> dark grey, dark text -> light grey, the
orange "?" buttons stay orange). This applies to style sheets
(QWidget.setStyleSheet), rich text in labels and text views, and the
background / text colours of table and list cells. Plots stay white (as
they would be printed or put in a paper); the help opens in the web
browser, as before.

apply_saved_theme() must run before the first window is created.
"""
import colorsys
import re

from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)

THEMES = ('light', 'dark')
PREFERENCES_KEY = 'theme'

_HEX = re.compile(r'#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b')
_RGB = re.compile(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(,\s*[\d.]+\s*)?\)')
_NAMED_HEX = {
    'white': '#ffffff', 'black': '#000000', 'red': '#ff0000', 'green': '#008000',
    'blue': '#0000ff', 'gray': '#808080', 'grey': '#808080', 'lightgray': '#d3d3d3',
    'lightgrey': '#d3d3d3', 'darkgray': '#a9a9a9', 'darkgrey': '#a9a9a9',
    'yellow': '#ffff00', 'orange': '#ffa500', 'navy': '#000080', 'darkred': '#8b0000',
    'darkgreen': '#006400', 'darkblue': '#00008b', 'purple': '#800080',
}
_NAMED = re.compile(r'(?<![-\w#])(' + '|'.join(sorted(_NAMED_HEX, key=len, reverse=True))
                    + r')(?![-\w])', re.IGNORECASE)
# CSS text-colour properties and HTML colour attributes: "color: ...",
# "selection-color: ...", color="..."
_TEXT_PROP = re.compile(r'((?<![-\w])(?:selection-)?color\s*[:=]\s*["\']?)([^;}"\'<>\s]+)',
                        re.IGNORECASE)
_installed = False


# --------------------------------------------------------------- preference
def saved_theme():
    try:
        from src.modules.misc.session_files import Preferences
        name = Preferences().get(PREFERENCES_KEY, 'light')
    except Exception:
        return 'light'
    return name if name in THEMES else 'light'


def save_theme(name):
    from src.modules.misc.session_files import Preferences
    Preferences().set(PREFERENCES_KEY, name if name in THEMES else 'light')


# --------------------------------------------------------------- colours
def dark_rgb(r, g, b):
    """The dark-theme version of a colour: same hue and saturation, opposite
    lightness (kept between 0.12 and 0.92 so nothing is pure black/white)."""
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    l2 = 0.12 + 0.80 * (1.0 - l)
    rr, gg, bb = colorsys.hls_to_rgb(h, l2, s)
    return int(round(rr * 255)), int(round(gg * 255)), int(round(bb * 255))


def _hex_to_rgb(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def dark_hex(hex_colour):
    return '#%02x%02x%02x' % dark_rgb(*_hex_to_rgb(hex_colour))


def _convert_colours(value, text=False):
    """Every colour in `value` -> its dark version. text=True: a text colour;
    very light text (white on a coloured button) stays light."""
    def one_hex(h):
        r, g, b = _hex_to_rgb(h)
        if text and colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)[1] > 0.85:
            return '#%02x%02x%02x' % (r, g, b)
        return '#%02x%02x%02x' % dark_rgb(r, g, b)
    value = _NAMED.sub(lambda m: _NAMED_HEX[m.group(1).lower()], value)
    value = _HEX.sub(lambda m: one_hex(m.group(0)), value)

    def rgb(m):
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (text and colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)[1] > 0.85):
            r, g, b = dark_rgb(r, g, b)
        alpha = m.group(4)
        return f"rgba({r}, {g}, {b}{alpha})" if alpha else f"rgb({r}, {g}, {b})"
    return _RGB.sub(rgb, value)


def convert_css(text):
    """Every colour in a style sheet / HTML text -> its dark version (see
    the module docstring)."""
    if not text or not isinstance(text, str):
        return text
    marker = '\x00'
    # text colours first (kept light when they are light), protected from
    # the general conversion by a marker
    pieces = []

    def keep(m):
        pieces.append(m.group(1) + _convert_colours(m.group(2), text=True))
        return f"{marker}{len(pieces) - 1}{marker}"
    out = _TEXT_PROP.sub(keep, text)
    out = _convert_colours(out)
    return re.sub(marker + r'(\d+)' + marker, lambda m: pieces[int(m.group(1))], out)


# --------------------------------------------------------------- install
def _dark_palette():
    from PyQt5.QtGui import QColor, QPalette
    p = QPalette()
    c = {
        QPalette.Window: '#2b2d31', QPalette.WindowText: '#e6e6e6',
        QPalette.Base: '#1f2023', QPalette.AlternateBase: '#2a2c30',
        QPalette.ToolTipBase: '#3a3d42', QPalette.ToolTipText: '#eeeeee',
        QPalette.Text: '#e6e6e6', QPalette.Button: '#34363b',
        QPalette.ButtonText: '#e6e6e6', QPalette.BrightText: '#ff6b6b',
        QPalette.Highlight: '#4a7fc1', QPalette.HighlightedText: '#ffffff',
        QPalette.Link: '#8ab4f8', QPalette.LinkVisited: '#c58af9',
        QPalette.PlaceholderText: '#8a8d93',
    }
    for role, col in c.items():
        p.setColor(role, QColor(col))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor('#7d8087'))
    return p


def _patch_qt():
    """Convert colours as the program sets them (see the module docstring)."""
    global _installed
    if _installed:
        return
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QBrush, QColor
    from PyQt5.QtWidgets import (QLabel, QListWidgetItem, QTableWidgetItem, QTextEdit,
                                 QTreeWidgetItem, QWidget)

    orig_style = QWidget.setStyleSheet

    def set_style_sheet(self, css):
        return orig_style(self, convert_css(css))
    QWidget.setStyleSheet = set_style_sheet

    orig_label_text = QLabel.setText

    def label_set_text(self, text):
        if isinstance(text, str) and Qt.mightBeRichText(text):
            text = convert_css(text)
        return orig_label_text(self, text)
    QLabel.setText = label_set_text

    for name in ('setHtml', 'insertHtml'):
        orig = getattr(QTextEdit, name)

        def patched(self, html, _orig=orig):
            return _orig(self, convert_css(html))
        setattr(QTextEdit, name, patched)

    def dark_brush(value):
        try:
            if isinstance(value, QBrush):
                col = value.color()
                if value.style() == Qt.NoBrush:
                    return value
            else:
                col = QColor(value)
            if not col.isValid():
                return value
            r, g, b = dark_rgb(col.red(), col.green(), col.blue())
            out = QColor(r, g, b, col.alpha())
            return QBrush(out) if isinstance(value, QBrush) else out
        except Exception:
            return value

    for cls in (QTableWidgetItem, QListWidgetItem):
        for name in ('setBackground', 'setForeground'):
            orig = getattr(cls, name)

            def patched(self, value, _orig=orig):
                return _orig(self, dark_brush(value))
            setattr(cls, name, patched)
    for name in ('setBackground', 'setForeground'):
        orig = getattr(QTreeWidgetItem, name)

        def patched(self, column, value, _orig=orig):
            return _orig(self, column, dark_brush(value))
        setattr(QTreeWidgetItem, name, patched)
    _installed = True


def apply_theme(app, name):
    """Install the theme for this run (before the first window exists)."""
    if name != 'dark':
        return
    try:
        app.setStyle('Fusion')
        app.setPalette(_dark_palette())
        _patch_qt()
    except Exception:
        logger.exception("The dark theme could not be applied")


def apply_saved_theme(app):
    apply_theme(app, saved_theme())


# --------------------------------------------------------------- menu
def build_menu(main_controller):
    """View -> Theme -> Light / Dark (used from the next start)."""
    from PyQt5.QtWidgets import QAction, QActionGroup, QMenu, QMessageBox
    view = getattr(main_controller, 'view', None)
    view_menu = getattr(view, 'menuView', None)
    if view_menu is None:
        return None
    menu = QMenu("Theme", view_menu)
    menu.setObjectName("menuTheme")
    group = QActionGroup(menu)
    current = saved_theme()
    actions = {}
    for key, text in (('light', "Light"), ('dark', "Dark")):
        act = QAction(text, menu, checkable=True)
        act.setChecked(key == current)
        group.addAction(act)
        menu.addAction(act)
        actions[key] = act

        def chosen(_checked=False, k=key):
            if k == saved_theme():
                return
            save_theme(k)
            QMessageBox.information(
                view, "Theme",
                f"The {'dark' if k == 'dark' else 'light'} theme is used from the next start "
                "of SpecAnalytiXBase.\n\nPlots stay white (as they are printed or put into "
                "a paper).")
        act.triggered.connect(chosen)
    view_menu.addSeparator()
    view_menu.addMenu(menu)
    main_controller.theme_menu = menu
    main_controller.theme_actions = actions
    return menu
