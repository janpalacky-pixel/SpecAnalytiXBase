# src/controllers/visualization_analysis/mcr_als_controller.py

from src.modules.visualization_analysis.mcr_als_manager import MCRALSManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import validate_common_x_axis
from src.modules.utils.correction_history import append_correction_history
logger = get_logger(__name__)




class MCRALSController:
    """Controller for the MCR-ALS (Multivariate Curve Resolution -
    Alternating Least Squares) dialog. Mirrors NMFController's shape,
    including the same trial/adopt pattern for "Run N times, keep best"
    with random initialization."""

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = MCRALSManager()
        self.dialog = None

    def compute(self, spectra, n_components, init='svd', max_iterations=100,
                tol=0.01, c_nonneg=True, st_nonneg=True, normalize_spectra=True,
                closure=False, random_state=42, references=None,
                fix_references=False):
        """Run MCR-ALS on self.manager — the main "Run MCR-ALS" computation.
        Pure computation, safe to call from the dialog's background QThread.

        Returns:
            bool: True if the computation succeeded.
        """
        try:
            return self.manager.compute(
                spectra, n_components=n_components, init=init,
                max_iterations=max_iterations, tol=tol,
                c_nonneg=c_nonneg, st_nonneg=st_nonneg,
                normalize_spectra=normalize_spectra, closure=closure,
                random_state=random_state, references=references,
                fix_references=fix_references)
        except Exception as e:
            logger.error(f"ERROR: Exception in MCR-ALS computation: {e}")
            logger.exception("Traceback:")
            return False

    def compute_trial(self, spectra, n_components, init, max_iterations, tol,
                       c_nonneg, st_nonneg, normalize_spectra, random_state,
                       closure=False, references=None, fix_references=False):
        """Run MCR-ALS on a fresh, independent MCRALSManager rather than
        self.manager — used by "Run N times, keep best" (random init) and
        the Elbow tab, mirroring NMFController.compute_trial exactly.

        Returns:
            (MCRALSManager, bool): the trial's manager, and whether it
                succeeded.
        """
        mgr = MCRALSManager()
        try:
            ok = mgr.compute(
                spectra, n_components=n_components, init=init,
                max_iterations=max_iterations, tol=tol,
                c_nonneg=c_nonneg, st_nonneg=st_nonneg,
                normalize_spectra=normalize_spectra, closure=closure,
                random_state=random_state, references=references,
                fix_references=fix_references)
        except Exception as e:
            logger.error(f"ERROR: Exception in MCR-ALS trial computation: {e}")
            logger.exception("Traceback:")
            mgr.last_error = mgr.last_error or str(e)
            ok = False
        return mgr, ok

    def adopt(self, manager):
        """Make an externally-computed MCRALSManager (e.g. the winner from
        "Run N times, keep best") the controller's current one."""
        self.manager = manager

    def export_components_to_main_list(self, base_label, source_spectra, which=None):
        """Add each resolved pure-component spectrum as a new spectrum in
        the main spectrum list — the same idea as Peak Fitting's "Add new
        spectra from individual peaks" — and register it in Operations
        History via register_copy_operation(), the same method
        main_controller._copy_selected_spectra uses for "Copy spectra".
        That gives an entry like "MCR-ALS (add as new)" you can jump back
        from/to, consistent with every other spectra-adding action in the
        app.

        Args:
            base_label: prefix for each new spectrum's label
            source_spectra: the spectra MCR-ALS was actually run on —
                recorded as this operation's "affected/source" spectra in
                history (register_copy_operation's copied_spectra).
            which: optional list of 0-based component indices to export
                (default: all components)

        Returns:
            int: number of spectra actually added
        """
        import uuid
        mgr = self.manager
        if mgr.ST is None:
            return 0
        indices = which if which is not None else range(mgr.n_components)
        existing_labels = {s['label'] for s in self.controller.original_spectra}
        source_labels = [s['label'] for s in source_spectra]
        new_spectra = []
        # One shared identifier for every component exported in THIS call —
        # the concrete answer to "how do I know MCR-ALS_2_2 and
        # MCR-ALS_1_2 came from the same decomposition run": every
        # component sharing this same run_id came from one call to this
        # method, i.e. one MCR-ALS run's set of resolved components.
        # component_index/n_components alone don't establish this — two
        # SEPARATE runs can each produce a "component_index: 1 of 2", so
        # without a run-level id there's no way to tell whether two
        # exported components are siblings or just coincidentally share
        # an index.
        run_id = str(uuid.uuid4())
        for k in indices:
            # Previously '{base_label}_MCR{k+1}', which duplicated "MCR"
            # whenever base_label was itself "MCR-ALS" (the dialog's own
            # default) — e.g. "MCR-ALS_MCR1". Dropping the redundant
            # middle abbreviation: just the base label, an underscore,
            # and the 1-based component number.
            base_name = f'{base_label}_{k + 1}'
            name = base_name
            counter = 2
            while name in existing_labels or name in {s['label'] for s in new_spectra}:
                name = f'{base_name}_{counter}'
                counter += 1
            new_spectrum = {
                'label': name,
                'x_scale': mgr.x_axis.copy(),
                'y_scale': mgr.ST[k].copy(),
                'metadata': {'label': name, 'spectrum_name': name,
                             'unique_id': str(uuid.uuid4())},
            }
            # Shared, chronologically-ordered history mechanism (see
            # correction_history.py) — same reasoning as NMFController's
            # own export_components_to_main_list: fresh history for a
            # brand-new spectrum, 'source_spectra' matching this
            # operation's actual sources exactly so
            # OperationParametersDialog._get_created_results_data
            # (operations_summary_dialog.py) can find it.
            new_spectrum['metadata']['correction_history'] = append_correction_history(
                None, 'MCR-ALS',
                {
                    'run_id': run_id,
                    'component_index': k + 1,
                    'n_components': mgr.n_components,
                    'lof': getattr(mgr, 'lof', None),
                    'iterations_used': getattr(mgr, 'iterations_used', None),
                    'converged': getattr(mgr, 'converged', None),
                    'explained_variance': (
                        float(mgr.explained_variance[k])
                        if mgr.explained_variance is not None else None
                    ),
                    'references_fixed': mgr.references_fixed,
                    'source_spectra': source_labels,
                }
            )
            new_spectra.append(new_spectrum)
        self.controller.operations_controller.register_copy_operation(
            copied_spectra=source_spectra, new_spectra=new_spectra,
            operation_name='MCR-ALS')
        self.controller.add_new_spectra(new_spectra)
        return len(new_spectra)

    def save_results_excel(self, filepath, include_spectra=True,
                            include_concentrations=True, include_info=True):
        """
        Save MCR-ALS results to an Excel file.

        Returns:
            bool: True if save was successful
        """
        try:
            return self.manager.save_results_excel(
                filepath, include_spectra, include_concentrations, include_info)
        except Exception as e:
            logger.error(f"ERROR: Excel save failed: {e}")
            return False

    def save_results_text(self, save_config):
        """
        Save MCR-ALS results to text/CSV file(s).

        Returns:
            bool: True if save was successful
        """
        try:
            return self.manager.save_results_text(save_config)
        except Exception as e:
            logger.error(f"ERROR: Text save failed: {e}")
            return False

    def show_dialog(self, selected_spectra):
        """Show the MCR-ALS dialog — same shape as NMFController.show_dialog():
        takes spectra as a parameter (matching the original NMF call site
        convention this mirrors) rather than self-fetching them."""
        # Refuse BEFORE building the dialog — an empty window with a warning
        # in it is worse than no window (see validate_common_x_axis).
        if not validate_common_x_axis(selected_spectra,
                                      getattr(self.controller, 'view', None),
                                      'MCR-ALS'):
            return
        self.manager.reset()
        last = self.controller.operations_controller.last_op_settings.get("MCR-ALS", {})

        from src.views.dialogs.visualization_analysis.mcr_als_dialog import MCRALSDialog
        self.dialog = MCRALSDialog(
            parent=self.controller.view,
            controller=self,
            spectra=selected_spectra,
            current_settings=last,
        )
        self.dialog.exec_()
        # Remember the settings the user left the dialog with, so the next
        # time it's opened they're restored (read back via current_settings
        # in show_dialog above, applied by the dialog's _apply_saved_settings).
        # Nothing else writes last_op_settings['MCR-ALS'], so without this the
        # restore would always find an empty dict and fall back to defaults.
        try:
            self.controller.operations_controller.last_op_settings["MCR-ALS"] = \
                self.dialog._persist_settings()
        except Exception as e:
            logger.error(f"Could not persist MCR-ALS settings: {e}")
        self.dialog = None
