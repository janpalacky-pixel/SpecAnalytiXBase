# src/views/dialogs/data_analysis/peak_detection_dialog.py
"""The default settings of the peaks marked on the plot. The window is the
Peaks window (peak_list_dialog.PeakListDialog): right-click on the plot ->
Detect Peaks opens it on its tab "Mark on the plot", Peak list... on its tab
"List" - one window, one set of settings."""

from src.modules.data_analysis import peak_list as pl

# Everything as when nothing was changed (Reset to defaults)
DEFAULTS = {
    'threshold': pl.DEFAULTS['threshold'],
    'prominence': pl.DEFAULTS['prominence'],
    'distance': pl.DEFAULTS['distance'],
    'peak_mode': pl.DEFAULTS['mode'],
    'snr': pl.DEFAULTS['snr'],
    'font_size': 10,
    'rotation': 0,
    'decimals': 2,
    'number_format': 'fixed',
    'format_type': 'x_only',
    'labels': 'band',
}
# Which peaks get their number written (see peak_settings_help.LABEL_HELP)
LABEL_MODES = [('band', "Once per band (above the highest peak)"), ('all', "On every peak"),
               ('current', "Only the current spectrum"), ('none', "None (dots only)")]
# Number format of the numbers on the plot, in the order of the window's list
FORMATS = ["fixed", "sci", "general", "mixed"]
