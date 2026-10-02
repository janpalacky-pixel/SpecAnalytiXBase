"""Regression test for a real crash reported against both v1.3.0 and the
current dependency set, in Peak Fitting:

    TypeError: arguments did not match any overloaded call:
      QColor(color: Qt.GlobalColor):
      QColor(rgb: int): too many arguments
      QColor(rgba64: QRgba64): argument 1 has unexpected type 'tuple'
      ...
    File "peak_fitting_dialog.py", line 570, in update_peaks_table
        color_item.setBackground(QColor(color_hex))

Root cause: matplotlib's default color cycle (plt.rcParams['axes.
prop_cycle']) is a list of hex strings like '#1f77b4' on matplotlib 3.10
and earlier, but a list of (r, g, b) float tuples on matplotlib 3.11+.
PeakFittingDialog stored whichever one the installed matplotlib handed
back directly as a peak's 'color', then passed it straight to QColor(),
which accepts a hex string but rejects a bare 3-tuple. Confirmed this
reproduces with matplotlib==3.11.2 specifically (pinned in requirements.txt
as of this release) and not with 3.10.9 -- i.e. a user on an older cached
matplotlib would never have seen it, exactly matching the report.

Fixed by routing every peak color through matplotlib.colors.to_hex()
both when it's first assigned (so new peaks always get a hex string
going forward, regardless of matplotlib version) and again right before
each QColor() construction (so a project file saved by an older/different
matplotlib version with a raw tuple already baked into it still displays
correctly instead of crashing).
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog


def _spectrum():
    return {
        'label': 'test_spectrum',
        'x_scale': np.linspace(0.0, 10.0, 50),
        'y_scale': np.exp(-((np.linspace(0.0, 10.0, 50) - 5.0) ** 2)),
    }


class TestPeakColorSwatchSurvivesTupleColors:
    """The exact crash scenario: a peak whose stored 'color' is a raw RGB
    float tuple, the shape matplotlib 3.11+'s color cycle actually
    produces (and the shape any project saved under it would persist).
    """

    def test_dialog_opens_with_a_tuple_colored_peak(self):
        tuple_color = (0.12156862745098039, 0.4666666666666667, 0.7058823529411765)  # mpl 3.11's '#1f77b4'
        current_settings = {
            'initial_peaks': [
                {
                    'model': 'Gaussian',
                    'center': 5.0,
                    'amplitude': 1.0,
                    'width': 1.0,
                    'extra': 1.0,
                    'color': tuple_color,
                }
            ]
        }

        # Before the fix, this raised TypeError inside update_peaks_table()
        # the moment the dialog tried to build QColor(tuple_color).
        dialog = PeakFittingDialog(parent=None, spectrum=_spectrum(), current_settings=current_settings)

        swatch = dialog.peaks_table.item(0, 0)
        assert swatch is not None
        # The swatch should actually show the right color, not just avoid crashing.
        assert swatch.background().color().name() == '#1f77b4'

    def test_dialog_opens_with_a_hex_string_colored_peak(self):
        """Same path with the older matplotlib (<=3.10) hex-string format,
        to make sure the fix didn't break the common/previous case.
        """
        current_settings = {
            'initial_peaks': [
                {
                    'model': 'Gaussian',
                    'center': 5.0,
                    'amplitude': 1.0,
                    'width': 1.0,
                    'extra': 1.0,
                    'color': '#ff7f0e',
                }
            ]
        }

        dialog = PeakFittingDialog(parent=None, spectrum=_spectrum(), current_settings=current_settings)

        swatch = dialog.peaks_table.item(0, 0)
        assert swatch.background().color().name() == '#ff7f0e'


class TestNewPeakColorCycleIsAlwaysHex:
    """A brand-new peak (no saved settings at all) gets its color straight
    from self.colors, which is built from plt.rcParams['axes.prop_cycle'].
    Regardless of which matplotlib is installed, that list must come out
    as hex strings -- this is what let the bug slip through 5 other
    places in the codebase that already guarded against matplotlib API
    removals, but not this one, which guards against a return-type change
    instead.
    """

    def test_default_color_cycle_is_hex_strings(self):
        dialog = PeakFittingDialog(parent=None, spectrum=_spectrum(), current_settings=None)
        assert len(dialog.colors) > 0
        for color in dialog.colors:
            assert isinstance(color, str)
            assert color.startswith('#')
