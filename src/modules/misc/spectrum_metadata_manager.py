
# src/modules/misc/spectrum_metadata_manager.py

class SpectrumMetadataManager:
    """Manages spectrum metadata operations."""
    
    def __init__(self, main_controller):
        self.controller = main_controller
    
    def get_selected_spectra(self, selected_indices):
        """Get spectrum data for the given ROW indices (position in
        self.controller.original_spectra), not labels.

        Was previously matched by label containment
        (`spectrum['label'] in selected_labels`) — if two spectra shared
        a label (a real, reachable case elsewhere in this app: two
        separate import sessions producing the same filename-derived
        label), selecting just ONE of them in the list widget and asking
        for its metadata would silently return metadata for BOTH,
        merged into one table/dialog, with no way to tell they weren't
        really both selected. Matched by index instead, the same safe
        pattern already used (and explicitly documented) by
        SpectrumSelectorController.get_selected_spectra() elsewhere in
        this app.
        """
        return [
            self.controller.original_spectra[i]
            for i in selected_indices
            if 0 <= i < len(self.controller.original_spectra)
        ]