# src/controllers/visualization/band_marker_controller.py
"""
Controller for the Band Markers feature.

Fully confirmed against the real app (main_controller.py, band_marker_manager.py,
and band_marker_dialog.py have all been checked directly, not inferred):
- main_controller creates self.band_marker_manager = BandMarkerManager() at
  startup and reuses that same instance across every plot mode (overlay,
  grid, waterfall, etc.) plus this dialog.
- main_controller._show_band_marker_dialog previously constructed
  BandMarkerDialog directly; it now routes through this controller instead,
  the same lazy-controller pattern used for every other refactored operation
  (Cosmic Ray Removal, Resolution Enhancement, Peak Fitting).
- BandMarkerManager's own module path and full API (add/remove/update/clear,
  apply_to_axes, to_dict/from_dict) match exactly what this controller uses.
"""

from src.views.plot_only_mode import run_beside_plot  # windows beside the main plot
from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)


class BandMarkerController:
    """
    Controller for the Band Markers dialog.

    Deliberately does NOT create its own BandMarkerManager the way most
    controllers in this app create their own manager — band markers
    persist for the whole session and are drawn on every plot (overlay,
    grid, waterfall, mean +/- SD, difference, heatmap, and external
    figure windows), so the plotting code elsewhere in the app and this
    dialog need to share the exact same manager instance, not two
    independent ones that would silently drift apart. This controller
    reuses main_controller.band_marker_manager if it already exists, and
    only creates one (storing it back on main_controller so everything
    else keeps sharing it) if it genuinely doesn't exist yet.
    """

    def __init__(self, main_controller):
        self.controller = main_controller
        self.dialog = None
        self.manager = getattr(main_controller, 'band_marker_manager', None)
        if self.manager is None:
            from src.modules.visualization.band_marker_manager import BandMarkerManager
            self.manager = BandMarkerManager()
            if main_controller is not None:
                main_controller.band_marker_manager = self.manager

    def show_dialog(self, on_change=None):
        """Open the Band Markers dialog.

        *on_change*, if given, is called whenever a marker is added,
        edited, removed, or its visibility toggled — normally the main
        window's replot function, so changes appear immediately. Defaults
        to the main controller's plot_spectra() if available.
        """
        from src.views.dialogs.visualization_analysis.band_marker_dialog import (
            BandMarkerDialog)

        if on_change is None and self.controller is not None:
            on_change = getattr(self.controller, 'plot_spectra', None)

        dialog = BandMarkerDialog(
            parent=self.controller.view if self.controller else None,
            band_marker_manager=self.manager,
            on_change=on_change,
        )
        self.dialog = dialog                   # its table follows clicks on the plot
        run_beside_plot(dialog)
        return dialog

    # ------------------------------------------------------------------ #
    # Markers made with the mouse (since 1.7.0 the former "pinned        #
    # cursors" are band markers like any other)                           #
    # ------------------------------------------------------------------ #

    def _canvas(self):
        return getattr(self.controller, 'static_canvas', None)

    def changed(self):
        """A marker added / removed with the mouse: drawn on the plot shown
        now (without plotting the spectra again, the zoom stays) and listed
        in the Band markers window if it is open."""
        canvas = self._canvas()
        main = self.controller
        at = getattr(main, 'scale_each_at', None)
        if at is not None and canvas is not None and not any(
                abs(float(x) - at) <= 1e-9 * max(1.0, abs(at)) for _, x in self.manager.x_markers()):
            # "scale each" was 1 at the marker just removed: drawn again 0-1
            main.plot_spectra()
            canvas = None
        if canvas is not None:
            try:
                self.manager.redraw(canvas.figure)
                canvas.draw_idle()
            except Exception:
                logger.exception("Band markers: drawing them again failed")
        dialog = getattr(self, 'dialog', None)
        try:
            if dialog is not None and dialog.isVisible():
                dialog._populate_table()
        except RuntimeError:                   # the window is gone
            self.dialog = None

    def add_at(self, x):
        """A click with the Cursor ticked: a marker at x (its x as label)."""
        index = self.manager.add_at_click(x)
        self.changed()
        return index

    def marker_near(self, event, px=6):
        """The index of the X marker under the mouse (right-click), or None."""
        ax = getattr(event, 'inaxes', None)
        if ax is None or getattr(event, 'x', None) is None:
            return None
        try:
            dpr = float(self._canvas().device_pixel_ratio)
        except Exception:
            dpr = 1.0
        return self.manager.nearest_x_marker(ax, event.x, px * dpr)

    def remove(self, index):
        self.manager.remove(index)
        self.changed()

    def remove_all(self):
        self.manager.clear()
        self.changed()

    def copy_values(self, curves):
        """The spectra's values at the X markers as a tab-separated table on
        the clipboard (for Excel). Returns (spectra, markers) copied."""
        from src.modules.visualization import cursor_values as cv
        markers = self.manager.x_markers()
        if not curves or not markers:
            return 0, 0
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(cv.table_text(
            curves, [x for _, x in markers], names=[n for n, _ in markers]))
        return len(curves), len(markers)

    def pair_around(self, x):
        """The two neighbouring X markers with x between them, or None
        (band_between.pair_around)."""
        from src.modules.visualization import band_between
        return band_between.pair_around(self.manager.x_markers(), float(x))

    def copy_between(self, curves, pair):
        """The spectra's values between the two markers `pair` (maximum,
        minimum, area, the band above the line joining its ends ... -
        band_between.py) as a table on the clipboard. Returns the number of
        spectra copied."""
        from src.modules.visualization import band_between
        if not curves or not pair:
            return 0
        (la, a), (lb, b) = pair
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(band_between.table_text(curves, a, b, (la, lb)))
        return len(curves)

    # ------------------------------------------------------------------ #
    # Session persistence                                                  #
    # ------------------------------------------------------------------ #

    def save_state(self) -> dict:
        """Return the manager's current state as a plain dict, suitable
        for embedding in a larger app session/project save file.
        Thin wrapper around BandMarkerManager.to_dict() — exposed at the
        controller level so whatever handles the app's overall session
        save doesn't need to reach into self.manager directly, matching
        how every other controller in this app is used."""
        return self.manager.to_dict()

    def load_state(self, state: dict):
        """Restore manager state from a dict previously produced by
        save_state(). Thin wrapper around BandMarkerManager.from_dict()."""
        self.manager.from_dict(state or {})
