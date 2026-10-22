# src/controllers/misc/spectrum_properties_controller.py
"""Right-click on the spectra list -> Spectrum properties...: the window and
storing its values. Apply is one step "Spectrum properties" in the
Operations History (Undo takes it back), built like Rename: the current
state gets the new metadata and becomes the next state.
src/modules/misc/spectrum_properties.py."""

from src.modules.misc import spectrum_properties as sp
from src.modules.utils.spectrum_identity import spectrum_key


class SpectrumPropertiesController:

    def __init__(self, main_controller):
        self.controller = main_controller
        self.dialog = None

    def show_dialog(self):
        from src.views.dialogs.misc.spectrum_properties_dialog import SpectrumPropertiesDialog
        main = self.controller
        spectra = list(getattr(main, 'selected_spectra', None) or []) or \
            list(getattr(main, 'original_spectra', None) or [])
        if not spectra:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(main.view, "Spectrum properties", "Import spectra first.")
            return None
        self.dialog = SpectrumPropertiesDialog(main.view, spectra, apply_callback=self.commit)
        self.dialog.exec_()
        return self.dialog

    def commit(self, spectra, values):
        """Store values (one {key: value or None} per spectrum of `spectra`,
        matched by identity). Returns (ok, message)."""
        diff = sp.changes(spectra, values)
        if not diff:
            return False, "Nothing changed."
        new_by_key = {}
        for i, key, _old, new in diff:
            new_by_key.setdefault(spectrum_key(spectra[i]), {})[key] = new
        main = self.controller
        om = main.operations_controller.operations_manager
        current = om.get_current_spectra()
        affected = [s for s in current if spectrum_key(s) in new_by_key]
        if not affected:
            return False, "These spectra are no longer in the list."
        for s in affected:
            sp.apply_to(s, new_by_key[spectrum_key(s)])
        by_label = {s['label']: new_by_key[spectrum_key(s)] for s in affected}
        om.apply_operation('Spectrum properties', {'properties': by_label}, affected,
                           new_state_spectra=current)

        oc = main.operations_controller
        selected_ids = {spectrum_key(s) for s in (main.selected_spectra or [])}
        main.original_spectra = main.order_spectra(om.get_current_spectra())
        oc._rebuild_spectra_list_with_selection(selected_ids)
        main.selected_spectra = [s for s in main.original_spectra if spectrum_key(s) in selected_ids]
        oc._redraw_after_operation(None, "spectrum properties")
        n = len(affected)
        return True, (f"Stored {sp.describe(by_label)} "
                      f"({n} spectr{'um' if n == 1 else 'a'}; Undo takes it back).")
