# src/controllers/visualization_analysis/group_statistics_controller.py
"""Opens Group Statistics for the selected spectra and remembers the group
of every spectrum (by its unique_id, not its name) for the rest of the
session, so reopening the window keeps the groups -- and the chosen value,
ranges and options. Spectra imported again are new spectra (new unique_id)
and start without the old groups."""


class GroupStatisticsController:

    def __init__(self, main_controller):
        self.controller = main_controller
        self.saved_groups = {}          # spectrum unique_id -> group, for this session
        self.saved_settings = {}        # the value / range choices, for this session
        self.dialog = None

    def show_dialog(self, selected_spectra=None):
        from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
            GroupStatisticsDialog)
        spectra = selected_spectra or self.controller.spectrum_selector.get_selected_spectra()
        if not spectra:
            return
        self.dialog = GroupStatisticsDialog(spectra, self.controller.view, self.saved_groups,
                                            self.saved_settings)
        self.dialog.exec_()
