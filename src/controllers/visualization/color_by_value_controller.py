# src/controllers/visualization/color_by_value_controller.py
"""Line colours > Colours by value: the setting, the colours handed to the
Overlay, Waterfall and Grid plots, and the colour bar (see
src/modules/visualization/color_by_value.py). It is chosen in the Line
colours window (line_colours_controller.py). The setting belongs to the
session and is saved in snapshots, like the other plot settings."""

from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key
from src.modules.visualization import color_by_value as cbv

logger = get_logger(__name__)


class ColorByValueController:

    def __init__(self, main):
        self.main = main
        self.settings = cbv.normalized()
        self.last_values = None            # values of the spectra in the last plot

    # -- the plot
    def active_for(self, plot_type):
        return cbv.is_active(self.settings) and plot_type in cbv.PLOT_TYPES

    def colours_for(self, drawn, plot_type):
        """Line colours for the spectra drawn (or None). The colour scale
        spans all selected spectra, also when only a preview is drawn; 'order'
        is the place in the whole spectra list."""
        if not self.active_for(plot_type):
            self.last_values = None
            return None
        selected = list(getattr(self.main, 'selected_spectra', None) or [])
        place = {spectrum_key(s): i for i, s in enumerate(getattr(self.main, 'original_spectra', []))}
        vals = [cbv.value_of(s, place.get(spectrum_key(s), i), self.settings)
                for i, s in enumerate(selected)]
        colour_of = dict(zip((spectrum_key(s) for s in selected), cbv.colours(vals, self.settings)))
        self.last_values = vals
        return [colour_of.get(spectrum_key(s), cbv.NO_VALUE_COLOR) for s in drawn]

    def decorate(self, figure):
        """Add the colour bar to the plot just drawn (when one is wanted)."""
        if self.last_values is None or figure is None:
            return None
        try:
            return cbv.add_colorbar(figure, self.last_values, self.settings)
        except Exception:
            logger.exception("The colour bar could not be added")
            return None

    def missing(self):
        """How many selected spectra have no value (drawn grey)."""
        return sum(v is None for v in (self.last_values or []))

    # -- the setting
    def set_settings(self, settings, replot=True):
        self.settings = cbv.normalized(settings)
        line_colours = getattr(self.main, 'line_colours_controller', None)
        if line_colours is not None:
            line_colours.sync()            # the line colours list shows the choice
        if replot and getattr(self.main, 'selected_spectra', None):
            self.main.plot_spectra()
            n = self.missing()
            if n:
                self.main._status(f"{n} of the selected spectra have no value and are drawn grey.",
                                  6000)

    def show_dialog(self):
        """The Line colours window (where colours by value is chosen)."""
        return self.main.line_colours_controller.show_dialog()
