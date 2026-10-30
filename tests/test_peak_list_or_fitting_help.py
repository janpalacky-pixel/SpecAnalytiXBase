"""The section "Peak list or Peak Fitting?" is in both helps, each linking to
the other; its example numbers are those the Peak list really gives for two
overlapping bands (1640 and 1660, FWHM 23.5 each)."""
import numpy as np


def test_the_section_is_in_both_helps():
    from src.help.peak_detection_help import get_peak_detection_help_content
    from src.help.peak_fitting_help import get_peak_fitting_help_content
    peaks, fitting = get_peak_detection_help_content(), get_peak_fitting_help_content()
    for page, other in ((peaks, 'help://peak_fitting#list-or-fitting'),
                        (fitting, 'help://peak_detection#list-or-fitting')):
        assert page.count('id="list-or-fitting"') == 1 and other in page
        assert '@@' not in page and 'Peak list or Peak Fitting?' in page
    assert 'href="#list-or-fitting"' in fitting                    # in its Contents


def test_the_example_numbers():
    from src.modules.data_analysis import peak_list as pl
    x = np.arange(1550, 1751, 1.0)
    s = 10.0                                                       # FWHM 23.5
    y = np.exp(-(x - 1640) ** 2 / (2 * s * s)) + 0.8 * np.exp(-(x - 1660) ** 2 / (2 * s * s))
    peaks = pl.spectrum_peaks(x, y)
    assert len(peaks) == 1                                         # one peak ...
    assert round(peaks[0]['x']) == 1644 and round(peaks[0]['fwhm']) == 39
    sp = [{'label': 'a', 'x_scale': x, 'y_scale': y}]
    rows, index = pl.peak_table_with_index(sp)
    out, _ = pl.refine_by_fitting(rows, index, sp)
    centre, fwhm, _, _, r2 = out[0][-5:]
    assert round(centre) == 1648 and round(fwhm) == 37 and r2 > 0.98   # ... also refined
