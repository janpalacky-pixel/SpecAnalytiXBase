# src/views/plot_toolbar.py
"""matplotlib's plot toolbar (home, back, forward, pan, zoom, ..., Save)
with one more button: Save plot for publication - the same window as for
the main plot (publication_dialog), with a copy of this toolbar's plot.

The tool windows whose plots are results in their own right import
NavigationToolbar from here instead of from matplotlib (one line), so every
plot toolbar they make - also one made later, e.g. on a new tab - has the
button. Not used by the processing windows (Baseline, Smoothing, ...: their
plots are previews; the result is saved from the main plot), and 2D Map adds
its own buttons (its marks can be left out, see map2d_dialog)."""

from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT

from src.views import publication_actions


class NavigationToolbar(NavigationToolbar2QT):
    def __init__(self, canvas, parent=None, *args, **kwargs):
        super().__init__(canvas, parent, *args, **kwargs)
        self.publication_action = publication_actions.add_toolbar_button(
            self, lambda: self.save_for_publication())

    def save_for_publication(self):
        """The window for this toolbar's plot, titled with the tool's name
        (e.g. "Save plot for publication - Peak Fitting")."""
        return publication_actions.save_plot_of(self.window(), self.canvas.figure)
