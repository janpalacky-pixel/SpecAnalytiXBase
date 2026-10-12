# src/modules/data_io/import_settings.py
"""One place that turns the import dialog's per-file settings dict into a
SpectrumManager.load_spectrum_from_file call.

Used by the real import (ImportController._run_import) AND by the import
dialog's plot preview, so the preview always shows exactly what Import
would produce with the current settings -- the two cannot drift apart.
"""


def sheets_to_read(settings: dict) -> list:
    """The worksheet(s) one file's settings ask for: several when "Import
    several sheets" is ticked, otherwise one (None = auto-select / not an
    Excel file)."""
    return list(settings.get('sheet_names') or [settings.get('sheet_name')])


def settings_for_sheet(settings: dict, sheet) -> dict:
    """Each sheet of a multi-sheet import carries its own settings."""
    return (settings.get('sheet_settings') or {}).get(sheet, settings)


def load_file_with_settings(manager, file_path: str, cfg: dict, sheet=None,
                            duplicate_block_resolver=None,
                            unknown_extension_resolver=None) -> None:
    """Read *file_path* into *manager* using the dialog settings *cfg*."""
    manager.load_spectrum_from_file(
        file_path,
        delimiter         = cfg.get('delimiter'),
        decimal_separator = cfg.get('decimal_separator'),
        header            = cfg.get('header'),
        zero_padding      = cfg.get('zero_padding', 4),
        analyze_rows      = cfg.get('analyze_rows', 20),
        interlaced_format = cfg.get('interlaced_format', False),
        row_oriented      = cfg.get('row_oriented', False),
        header_threshold  = cfg.get('header_threshold', 0.5),
        label_column      = cfg.get('label_column'),
        x_scale_column    = cfg.get('x_scale_column'),
        exclude_columns   = cfg.get('exclude_columns'),
        sheet_name        = sheet,
        header_row        = cfg.get('header_row'),
        index_x           = cfg.get('index_x', False),
        spe_use_calibration = cfg.get('spe_use_calibration', False),
        jws_selected_channels = cfg.get('jws_selected_channels'),
        jws_channel_type_overrides = cfg.get('jws_channel_type_overrides'),
        specord_csv_format = cfg.get('specord_csv_format', False),
        duplicate_block_resolver = duplicate_block_resolver,
        unknown_extension_resolver = unknown_extension_resolver,
    )
