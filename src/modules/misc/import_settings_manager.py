# src/modules/misc/import_settings_manager.py

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)

class ImportSettingsManager:
    """
    Manages import settings with a single source of truth.

    All keys that the import pipeline may read must be present in
    `default_settings` so that a reset never leaves the caller with a
    KeyError or an unintended None.
    """

    default_settings = {
        'delimiter':         None,   # None → auto-detect
        'decimal_separator': None,   # None → auto-detect
        'header':            None,   # None → auto-detect
        'zero_padding':      4,
        'analyze_rows':      20,
        'interlaced_format': False,
        'row_oriented':      False,
        'header_threshold':  0.5,    # fraction of non-numeric tokens required
                                      # to auto-detect a header (0.0-1.0)
        'label_column':      None,   # row-oriented only; None → column 0
        'x_scale_column':    None,   # standard only; None → column 0
        'exclude_columns':   None,   # standard only; None → nothing excluded
        'sheet_name':        None,   # Excel only; None → spectra / first sheet
        'sheet_names':       None,   # Excel only; list → import several sheets
        'header_row':        None,   # None → auto (header is row 0 / no header)
        'index_x':           False,  # use row number (1,2,3,…) as the X axis
    }

    # Settings that must reset to their default after every import.
    # interlaced_format, row_oriented, label_column, x_scale_column,
    # exclude_columns and sheet_name are per-file layout flags, not
    # persistent preferences — leaving any of them set would corrupt
    # every subsequent standard import. header_threshold is a genuine
    # session preference (like delimiter/decimal) and persists.
    _non_persistent = {'interlaced_format', 'row_oriented', 'label_column',
                        'x_scale_column', 'exclude_columns', 'sheet_name',
                        'sheet_names', 'header_row', 'index_x'}

    def __init__(self):
        self.current_settings = dict(self.default_settings)

    # ------------------------------------------------------------------

    def get_current_settings(self) -> dict:
        """Return a copy of the current settings."""
        return dict(self.current_settings)

    def update_settings(self, new_settings: dict) -> dict:
        """Merge *new_settings* into the current settings and return a copy."""
        logger.debug("Updating settings with: %s", new_settings)
        self.current_settings.update(new_settings)
        logger.debug("Settings now: %s", self.current_settings)
        return dict(self.current_settings)

    def reset_non_persistent(self) -> None:
        """Reset per-file flags to their defaults after each import.
        
        Call this after every import completes so that interlaced_format
        does not carry over and corrupt the next standard import.
        """
        for key in self._non_persistent:
            self.current_settings[key] = self.default_settings[key]

    def reset_to_defaults(self) -> dict:
        """Reset to factory defaults and return a copy."""
        self.current_settings = dict(self.default_settings)
        return dict(self.current_settings)
