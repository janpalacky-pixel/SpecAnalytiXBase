# src/controllers/visualization_analysis/map2d_controller.py

from src.modules.visualization_analysis.map2d_manager import Map2DManager
from PyQt5.QtWidgets import QMessageBox
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key

logger = get_logger(__name__)


class Map2DController:
    """
    Controller for the 2-D spectral map feature.

    Follows the same thin-controller pattern as SVDAnalysisController:
    it owns a Map2DManager, delegates all computation to it, and
    handles dialog creation / error display.
    """

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = Map2DManager()

    # ------------------------------------------------------------------ #
    # Public API used by the dialog                                        #
    # ------------------------------------------------------------------ #

    def validate_dimensions(self, n_spectra, n_rows, n_cols):
        return Map2DManager.validate_dimensions(n_spectra, n_rows, n_cols)

    def get_factor_pairs(self, n):
        return Map2DManager.factor_pairs(n)

    def compute_intensity_map(self, spectra, n_rows, n_cols,
                              metric="Integral",
                              x_min=None, x_max=None,
                              include_ranges=None, exclude_ranges=None,
                              x_val=None):
        """Delegate to manager; return map array or None."""
        return self.manager.compute_intensity_map(
            spectra, n_rows, n_cols,
            metric=metric,
            x_min=x_min, x_max=x_max,
            include_ranges=include_ranges,
            exclude_ranges=exclude_ranges,
            x_val=x_val,
        )

    def compute_arithmetic_map(self, spectra, n_rows, n_cols, **kwargs):
        """Delegate arithmetic map computation to manager."""
        return self.manager.compute_arithmetic_map(
            spectra, n_rows, n_cols, **kwargs)

    def compute_svd_map(self, spectra, n_rows, n_cols,
                        component_index=0,
                        x_min=None, x_max=None,
                        include_ranges=None, exclude_ranges=None):
        """Delegate to manager; return map array or None."""
        return self.manager.compute_svd_map(
            spectra, n_rows, n_cols,
            component_index=component_index,
            x_min=x_min, x_max=x_max,
            include_ranges=include_ranges,
            exclude_ranges=exclude_ranges,
        )

    def get_explained_variance(self):
        return self.manager.get_explained_variance()

    def get_n_svd_components(self):
        return self.manager.get_n_svd_components()

    def get_subspectrum(self, component_index):
        return self.manager.get_subspectrum(component_index)

    def get_coefficients(self, component_index):
        return self.manager.get_coefficients(component_index)

    # ------------------------------------------------------------------ #
    # Dialog launcher (called by VisualizationAnalysisController)         #
    # ------------------------------------------------------------------ #

    def send_spectra_to_main_list(self, spectra, label_prefix="ROI", source_spectra=None):
        """Add spectra to the main application spectrum list.

        Parameters
        ----------
        spectra        : list of spectrum dicts to add
        label_prefix   : prefix for auto-generated unique labels
        source_spectra : the ORIGINAL spectra this export was derived
            from (e.g. the spectra the 2D map/clustering was built
            from). Recorded as the operation's affected spectra via
            register_copy_operation(), the same way
            NMFController/MCRALSController record which spectra a
            component was derived from — this is what makes "Affected
            Spectra" in Operations History meaningful instead of empty.
            Falls back to *spectra* itself if not given.

        Returns
        -------
        int : number of spectra actually added

        This used to hand-roll its own operations_chain manipulation
        (truncate-forward-history, append a raw {'type': 'roi_export',
        ...} record) plus its own spectra_list_widget rebuild — entirely
        parallel to, and diverging from, the established
        register_copy_operation() / _rebuild_spectra_list_with_selection()
        helpers every other spectrum-creating operation in this app
        already uses. Two confirmed, real performance bugs came along
        with that duplication:
          - copy.deepcopy() used repeatedly to build the new state —
            confirmed elsewhere in this codebase (register_copy_operation
            itself) to be 10-18x slower than a targeted copy once a
            spectrum's correction_history has any entries, which is after
            literally any prior operation.
          - item.setSelected(True) called once per spectrum in a loop to
            rebuild the list widget — confirmed by direct profiling on a
            real session to cost 83 of a ~90-second operation at ~4675
            spectra; blockSignals() (already used here) does nothing
            about this, since it only suppresses signal emission, not the
            real per-call Qt cost.
        Routing through the shared helpers below fixes both for free, and
        also gives 'roi_export' entries the SAME "(add as new)"-style
        record shape (and the SAME correction_history convention) every
        other operation's export already uses, rather than a one-off
        custom record shape nothing else in Operations History expects.
        """
        from src.modules.utils.correction_history import append_correction_history
        import uuid

        mc = self.controller   # MainController
        existing_labels = {s['label'] for s in mc.original_spectra}

        new_spectra = []
        for sp in spectra:
            base  = sp.get('label', label_prefix)
            name  = base
            count = 2
            while name in existing_labels or name in {s['label'] for s in new_spectra}:
                name = f"{base}_{count}"
                count += 1

            # Targeted copy, not copy.deepcopy() — see docstring above.
            new_sp = {k: (v.copy() if hasattr(v, 'copy') else v)
                      for k, v in sp.items() if k != 'metadata'}
            new_sp['label'] = name
            source_metadata = dict(sp.get('metadata') or {})
            new_sp['metadata'] = source_metadata
            new_sp['metadata']['unique_id'] = str(uuid.uuid4())
            new_sp['metadata'].setdefault('source', 'ROI export from 2D Map')

            # A real correction_history entry, matching the convention
            # every other spectrum-creating operation in this app
            # follows (Combine Spectra, NMF, MCR-ALS) — describes how
            # this spectrum came to exist, using whatever descriptive
            # metadata the caller already attached (e.g. cluster index /
            # member count for a cluster average, or ROI region info for
            # an ROI export), rather than nothing at all.
            history_entry = {
                k: v for k, v in source_metadata.items()
                if k not in ('unique_id', 'correction_history')
            }
            new_sp['metadata']['correction_history'] = append_correction_history(
                None, '2D Map export', history_entry
            )

            new_spectra.append(new_sp)
            existing_labels.add(name)

        if not new_spectra:
            return 0

        mc = self.controller
        oc = getattr(mc, 'operations_controller', None)
        if oc is None:
            logger.error("No operations_controller available; cannot record 2D Map export in history.")
            return 0

        oc.register_copy_operation(
            source_spectra if source_spectra else new_spectra,
            new_spectra,
            operation_name="2D Map export",
        )

        mc.original_spectra = oc.operations_manager.get_current_spectra()
        # Sort before rebuilding — same order_spectra() + rebuild pattern
        # used by every Add-as-New / Copy spectra path. Without this, ROI
        # exports were just appended at the end regardless of the
        # selected sort order, same bug Copy spectra had.
        mc.original_spectra = mc.order_spectra(mc.original_spectra)

        new_ids = {spectrum_key(s) for s in new_spectra}
        # Batched selection via the already-fixed shared helper — see
        # docstring above for why the per-item setSelected() loop this
        # replaced was a real, confirmed bottleneck at scale.
        oc._rebuild_spectra_list_with_selection(new_ids)

        mc.selected_spectra = [s for s in mc.original_spectra if spectrum_key(s) in new_ids]

        mc.spectrum_selector.update_spectra_count_label()
        n = len(mc.original_spectra)
        mc.view.number_of_rows_spinBox.setMaximum(n)
        mc.view.number_of_columns_spinBox.setMaximum(n)

        return len(new_spectra)

    def show_dialog(self):
        """Show the 2-D map dialog."""
        selected_spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not selected_spectra:
            QMessageBox.warning(
                self.controller.view,
                "No Spectra Selected",
                "Please select spectra before opening the 2D Map tool.",
            )
            return

        from src.views.dialogs.visualization_analysis.map2d_dialog import Map2DDialog

        dialog = Map2DDialog(
            parent=self.controller.view,
            controller=self,
            spectra=selected_spectra,
        )
        dialog.exec_()
