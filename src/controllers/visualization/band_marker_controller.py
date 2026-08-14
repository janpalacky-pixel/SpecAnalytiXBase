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
        dialog.exec_()
        return dialog

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
