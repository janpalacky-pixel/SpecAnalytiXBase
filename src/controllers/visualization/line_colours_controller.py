# src/controllers/visualization/line_colours_controller.py
"""Line colours: the three ways the lines get their colour, in one place.

- automatic: the standard sequence of colours (main.use_automatic_line_colors)
- own: the colour of every spectrum from Plot Properties
- value: along a colour scale (color_by_value_controller.py)

The choice is not stored separately: it follows from
main.use_automatic_line_colors and the "colour by value" settings, which
snapshots have always kept, so old snapshots open with the same colours.
Where it is chosen: the line colours list in Basic plot options and its
"…" button, View > Line colours…, the "Line colours" submenu of the plot's
right-click menu, and the spectra list's right-click menu. The window is
src/views/dialogs/visualization/line_colours_dialog.py."""

from PyQt5.QtWidgets import QAction

from src.modules.visualization import color_by_value as cbv
from src.views.dialogs.visualization.line_colours_dialog import CHOICE_TEXT, MODES

COMBO_TEXT = {'automatic': "automatic colours", 'own': "own colours",
              'value': "colours by value"}


class LineColoursController:

    def __init__(self, main):
        self.main = main
        self.last_by_value = None          # the colour-by-value settings to come back to
        self.dialog = None
        view = main.view
        self.combo = getattr(view, 'line_colours_comboBox', None)
        if self.combo is not None:
            for m in MODES:
                self.combo.addItem(COMBO_TEXT[m], m)
            self.combo.currentIndexChanged.connect(self._combo_changed)
        button = getattr(view, 'line_colours_button', None)
        if button is not None:
            button.clicked.connect(self.show_dialog)
        self.action = None
        view_menu = getattr(view, 'menuView', None)
        if view_menu is not None:
            self.action = QAction("Line colours…", view_menu)
            self.action.setObjectName("actionLineColours")
            self.action.setStatusTip("Automatic colours, own colours (Plot Properties) or colours "
                                     "by value along a colour scale")
            self.action.triggered.connect(self.show_dialog)
            view_menu.addAction(self.action)
        self.sync()

    # -- the choice
    def _by_value(self):
        return self.main.color_by_value_controller

    def mode(self):
        if cbv.is_active(self._by_value().settings):
            return 'value'
        return 'automatic' if getattr(self.main, 'use_automatic_line_colors', True) else 'own'

    def set_mode(self, mode, by_value=None, replot=True):
        """Switch to `mode`; for 'value' with `by_value` settings (or the
        last ones used)."""
        cbc = self._by_value()
        if mode == 'value':
            s = cbv.normalized(by_value or self.last_by_value or cbc.settings)
            if s['mode'] == 'off':
                s['mode'] = 'order'
            self.last_by_value = dict(s)
            cbc.set_settings(s, replot=replot)          # draws, says how many have no value
            return
        if cbv.is_active(cbc.settings):
            self.last_by_value = dict(cbc.settings)
        self.main.use_automatic_line_colors = (mode == 'automatic')
        cbc.set_settings(dict(cbc.settings, mode='off'), replot=False)
        if replot and getattr(self.main, 'selected_spectra', None):
            self.main.plot_spectra()

    def sync(self):
        """Show the current choice in the list (after snapshots, menus, ...)."""
        if self.combo is None:
            return
        self.combo.blockSignals(True)
        self.combo.setCurrentIndex(MODES.index(self.mode()))
        self.combo.blockSignals(False)

    def _combo_changed(self, index):
        mode = self.combo.itemData(index)
        if mode and mode != self.mode():
            self.set_mode(mode)

    # -- Plot Properties set a colour
    def own_colour_set(self):
        """A colour was set in Plot Properties: show it (switch to own colours)."""
        if self.mode() == 'own':
            return False
        self.set_mode('own', replot=False)
        self.main._status("Line colours switched to “own colours” to show the colour "
                          "set in Plot Properties.", 6000)
        return True

    # -- menus and the window
    def add_to_menu(self, menu):
        """The "Line colours" submenu of the plot's right-click menu."""
        sub = menu.addMenu("Line colours")
        current = self.mode()
        for m in MODES:
            act = sub.addAction(CHOICE_TEXT[m])
            act.setCheckable(True)
            act.setChecked(m == current)
            act.triggered.connect(lambda _=False, m=m: self.set_mode(m))
        sub.addSeparator()
        sub.addAction("Line colours…").triggered.connect(self.show_dialog)
        return sub

    def show_dialog(self):
        from src.views.dialogs.visualization.line_colours_dialog import LineColoursDialog
        spectra = list(getattr(self.main, 'selected_spectra', None) or []) or \
            list(getattr(self.main, 'original_spectra', []))
        cbc = self._by_value()
        settings = cbc.settings if cbv.is_active(cbc.settings) else (self.last_by_value or cbc.settings)
        dlg = LineColoursDialog(self.main.view, spectra, self.mode(), settings,
                                apply_callback=lambda mode, s: self.set_mode(mode, s),
                                set_own_colours=self.main.custom_plot_properties_controller.show_dialog)
        self.dialog = dlg
        dlg.exec_()
        return dlg
