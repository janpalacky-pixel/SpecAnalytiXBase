# src/controllers/data_analysis/data_table_controller.py
"""Analysis & Visualization -> Data Analysis -> Data table: opens the window
for the selected spectra and adds its formula columns to the spectra list as
new spectra - one step "Data table (add as new)" in the Operations History,
like every other tool that adds spectra (Undo removes them; snapshots and the
Methods report include the formulas)."""

import uuid

from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)


def unique_label(name, taken):
    """name, or name (2), name (3), ... - the program's usual way of keeping
    spectrum names unique."""
    name = (name or 'Data table').strip() or 'Data table'
    if name not in taken:
        return name
    k = 2
    while f"{name} ({k})" in taken:
        k += 1
    return f"{name} ({k})"


class DataTableController:

    def __init__(self, main_controller):
        self.main = main_controller
        self.dialog = None

    def show_dialog(self, selected_spectra):
        from src.views.dialogs.data_analysis.data_table_dialog import DataTableDialog
        self.dialog = DataTableDialog(self.main.view, selected_spectra,
                                      commit_callback=self.add_spectra)
        self.dialog.exec_()

    def add_spectra(self, table, new_spectra):
        """Add the formula columns (already turned into spectrum dicts by the
        table) to the spectra list. Returns (ok, message)."""
        if not new_spectra:
            return False, "There is no formula column to add."
        oc = self.main.operations_controller
        try:
            pre_state = oc.operations_manager.get_current_spectra()
            taken = {s['label'] for s in pre_state} | {s['label'] for s in self.main.original_spectra}
            for sp in new_spectra:
                sp['label'] = unique_label(sp['label'], taken)
                taken.add(sp['label'])
                meta = sp.setdefault('metadata', {})
                meta.update({'label': sp['label'], 'spectrum_name': sp['label'],
                             'unique_id': str(uuid.uuid4())})
            used = {}
            for sp in new_spectra:
                used.update(sp['metadata'].get('formula_columns') or {})
            by_name = {c.name: c.source for c in table.spectrum_columns()}
            sources = [by_name[n] for n in used if by_name.get(n) is not None]
            oc.register_copy_operation(sources, new_spectra, operation_name='Data table',
                                       pre_state=pre_state)
            record = oc.operations_manager.operations_chain[-1]
            record['parameters']['formulas'] = [
                {'name': sp['label'], 'formula': sp['metadata']['formula'],
                 'columns': dict(sp['metadata'].get('formula_columns') or {})}
                for sp in new_spectra]
            self.main.add_new_spectra(new_spectra)
            # add_new_spectra selects the new spectra with the list's signals
            # blocked: tell the selection (and the plot) about it, so the next
            # tool - e.g. the Data table opened again - works on them.
            selector = getattr(self.main, 'spectrum_selector', None)
            if selector is not None:
                selector.on_item_selection_changed()
        except Exception as exc:
            logger.exception("Adding the data table's columns as spectra failed")
            return False, f"The new spectra could not be added: {exc}"
        names = ', '.join(sp['label'] for sp in new_spectra)
        return True, f"Added {len(new_spectra)} new spectr{'um' if len(new_spectra) == 1 else 'a'}: {names}"
