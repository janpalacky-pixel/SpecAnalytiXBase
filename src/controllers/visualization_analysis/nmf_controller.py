# src/controllers/visualization_analysis/nmf_controller.py

import numpy as np
from src.modules.visualization_analysis.nmf_manager import NMFManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import validate_common_x_axis
from src.modules.utils.correction_history import append_correction_history
logger = get_logger(__name__)




class NMFController:
    """Controller for the NMF (Non-negative Matrix Factorisation) dialog.
    Mirrors PcaScoresController/ClusterAnalysisController's shape, with one
    addition: the dialog also runs independent trial fits for "Run N
    times, keep best" and the Elbow tab, each of which needs its own
    throwaway NMFManager rather than mutating self.manager mid-trial —
    see compute_trial()/adopt() below.
    """

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = NMFManager()
        self.dialog = None

    def compute(self, spectra, n_components, init='nndsvda', max_iter=500, random_state=42,
                references=None, fix_references=False):
        """Run NMF on self.manager — the main "Run NMF" computation. Pure
        computation, safe to call from the dialog's background QThread.

        Returns:
            bool: True if the computation succeeded.
        """
        try:
            return self.manager.compute(spectra, n_components=n_components,
                                         init=init, max_iter=max_iter,
                                         random_state=random_state,
                                         references=references,
                                         fix_references=fix_references)
        except Exception as e:
            logger.error(f"ERROR: Exception in NMF computation: {e}")
            logger.exception("Traceback:")
            return False

    def compute_trial(self, spectra, n_components, init, max_iter, random_state,
                       references=None, fix_references=False, init_H=None):
        """Run NMF on a fresh, independent NMFManager rather than
        self.manager — used by "Run N times, keep best" and the Elbow tab
        (cold fits), AND compute_bootstrap_uncertainty() below (init_H,
        warm-started from the fit being bootstrapped) — mirroring
        MCRALSController.compute_trial's init_ST pass-through.

        Returns:
            (NMFManager, bool): the trial's manager, and whether it
                succeeded. The manager is always returned (never None) so
                callers can read .last_error off a failed trial.
        """
        mgr = NMFManager()
        try:
            ok = mgr.compute(spectra, n_components=n_components, init=init,
                              max_iter=max_iter, random_state=random_state,
                              references=references,
                              fix_references=fix_references, init_H=init_H)
        except Exception as e:
            logger.error(f"ERROR: Exception in NMF trial computation: {e}")
            logger.exception("Traceback:")
            mgr.last_error = mgr.last_error or str(e)
            ok = False
        return mgr, ok

    def compute_bootstrap_uncertainty(self, reference_manager, n_components,
                                       init, max_iter, n_resamples,
                                       confidence_level, random_state=None,
                                       references=None, fix_references=False,
                                       progress_callback=None, cancel_check=None):
        """Residual bootstrap with a warm-started refit — quantifies how
        sensitive reference_manager's ALREADY-FITTED W/H are to the actual
        noise in the data, as a complement to (not a replacement for) "Run
        N times, keep best": that explores rotational-ambiguity/local-optima
        risk via random restarts, this measures pure measurement-noise
        sensitivity of ONE specific, already-chosen fit. Mirrors
        MCRALSController.compute_bootstrap_uncertainty; see the Developer
        Guide's NMF Bootstrap Uncertainty section for the one thing that
        differs from MCR-ALS's version: every replicate here is refit
        through NMFManager._fit_with_references' hand-written
        multiplicative-update loop (via init_H), even when
        reference_manager's own original fit used sklearn's solver —
        justified because both algorithms converge to KKT-stationary
        points of the same Frobenius NMF objective, so warm-starting the
        MU loop from a genuinely-converged sklearn result reproduces it in
        a couple of iterations rather than drifting to a different point.

        reference_manager must already hold a successful fit (.W, .H,
        .X_nn, .x_axis, .labels all set — i.e. self.manager right after
        compute() returned True, or after adopt()-ing a "Run N times"
        winner). n_components, init, max_iter, references, fix_references:
        the SAME settings reference_manager was fitted with — every
        replicate is refit under identical constraints (init is passed
        through for signature symmetry with compute_trial, but is not
        actually consulted for a warm-started fit — see compute()'s
        init_H docstring). progress_callback(b, n_resamples) is called
        before each replicate, if given; cancel_check(), if given, is
        checked before each replicate and stops early (partial results
        from however many replicates completed are still used) when it
        returns True.

        Returns a dict with H_lower/H_upper/W_lower/W_upper (pointwise
        percentile bounds), H_samples/W_samples (the raw per-replicate
        arrays), n_resamples_requested/n_resamples_used/n_failed, and
        confidence_level — or None if reference_manager isn't fitted yet,
        or every replicate's refit failed. On success, also stored on
        reference_manager.bootstrap_result.
        """
        ref = reference_manager
        if ref.W is None or ref.H is None or ref.X_nn is None:
            ref.last_error = (
                "Run NMF successfully before requesting bootstrap "
                "uncertainty.")
            return None

        X, W0, H0 = ref.X_nn, ref.W, ref.H
        m = X.shape[0]
        residuals = X - W0 @ H0
        rng = np.random.RandomState(random_state)

        H_samples, W_samples = [], []
        n_failed = 0
        for b in range(n_resamples):
            if cancel_check is not None and cancel_check():
                break
            if progress_callback is not None:
                progress_callback(b, n_resamples)
            row_idx = rng.randint(0, m, size=m)
            X_b = W0 @ H0 + residuals[row_idx, :]
            synth_spectra = [
                {'label': ref.labels[i], 'x_scale': ref.x_axis,
                 'y_scale': X_b[i, :], 'metadata': {}}
                for i in range(m)
            ]
            trial_mgr, ok = self.compute_trial(
                synth_spectra, n_components=n_components, init=init,
                max_iter=max_iter, random_state=b, references=references,
                fix_references=fix_references, init_H=H0)
            if ok:
                H_samples.append(trial_mgr.H)
                W_samples.append(trial_mgr.W)
            else:
                n_failed += 1

        if not H_samples:
            ref.last_error = (
                f"All {n_resamples} bootstrap resamples failed to fit.")
            return None

        H_arr = np.array(H_samples)   # (B_ok, k, n_wl)
        W_arr = np.array(W_samples)   # (B_ok, m, k)
        alpha = 1.0 - confidence_level
        lo_pct, hi_pct = 100.0 * alpha / 2.0, 100.0 * (1.0 - alpha / 2.0)
        result = {
            'H_lower': np.percentile(H_arr, lo_pct, axis=0),
            'H_upper': np.percentile(H_arr, hi_pct, axis=0),
            'W_lower': np.percentile(W_arr, lo_pct, axis=0),
            'W_upper': np.percentile(W_arr, hi_pct, axis=0),
            'H_samples': H_arr,
            'W_samples': W_arr,
            'n_resamples_requested': n_resamples,
            'n_resamples_used': len(H_samples),
            'n_failed': n_failed,
            'confidence_level': confidence_level,
        }
        ref.bootstrap_result = result
        return result

    def adopt(self, manager):
        """Make an externally-computed NMFManager (e.g. the winner from
        "Run N times, keep best") the controller's current one, so
        self.manager always reflects whatever the dialog is currently
        showing — relevant since save/export methods below operate on
        self.manager."""
        self.manager = manager

    def export_components_to_main_list(self, base_label, source_spectra, which=None):
        """Add each resolved NMF component spectrum as a new spectrum in
        the main spectrum list — the same idea as Peak Fitting's "Add new
        spectra from individual peaks" — and register it in Operations
        History via register_copy_operation(), the same method
        main_controller._copy_selected_spectra uses for "Copy spectra".
        That gives an entry like "NMF (add as new)" you can jump back
        from/to, consistent with every other spectra-adding action in the
        app.

        Args:
            base_label: prefix for each new spectrum's label
            source_spectra: the spectra NMF was actually run on — recorded
                as this operation's "affected/source" spectra in history
                (register_copy_operation's copied_spectra).
            which: optional list of 0-based component indices to export
                (default: all components)

        Returns:
            int: number of spectra actually added
        """
        import uuid
        mgr = self.manager
        if mgr.H is None:
            return 0
        indices = which if which is not None else range(mgr.n_components)
        existing_labels = {s['label'] for s in self.controller.original_spectra}
        source_labels = [s['label'] for s in source_spectra]
        new_spectra = []
        # One shared identifier for every component exported in THIS call —
        # see MCRALSController.export_components_to_main_list for the full
        # reasoning: without a run-level id, two separate NMF runs each
        # producing a "component_index: 1" look identical from a single
        # component's own metadata, with no way to tell whether two
        # exported components are actually siblings from the same run.
        run_id = str(uuid.uuid4())
        for k in indices:
            # Previously '{base_label}_NMF{k+1}', which duplicated "NMF"
            # whenever base_label was itself "NMF" (the dialog's own
            # default) — e.g. "NMF_NMF1". Matches MCR-ALS's format
            # exactly (underscore + component number) per explicit
            # request for consistency between the two.
            base_name = f'{base_label}_{k + 1}'
            name = base_name
            counter = 2
            while name in existing_labels or name in {s['label'] for s in new_spectra}:
                name = f'{base_name}_{counter}'
                counter += 1
            new_spectrum = {
                'label': name,
                'x_scale': mgr.x_axis.copy(),
                'y_scale': mgr.H[k].copy(),
                'metadata': {'label': name, 'spectrum_name': name,
                             'unique_id': str(uuid.uuid4())},
            }
            # Shared, chronologically-ordered history mechanism (see
            # correction_history.py) — started fresh here since each
            # component is a brand-new spectrum with no prior history of
            # its own, same reasoning as Combine Spectra / Spectral
            # Calculator's own result entries. 'source_spectra' matches
            # this operation's actual sources exactly (source_labels,
            # computed above from the same source_spectra this method
            # already registers via register_copy_operation below) — the
            # same field OperationParametersDialog._get_created_results_data
            # (operations_summary_dialog.py) matches against to find which
            # created spectra belong to which historical operation.
            new_spectrum['metadata']['correction_history'] = append_correction_history(
                None, 'NMF',
                {
                    'run_id': run_id,
                    'component_index': k + 1,
                    'n_components': mgr.n_components,
                    'reconstruction_error': mgr.reconstruction_error,
                    'lof': getattr(mgr, 'lof', None),
                    'iterations_used': mgr.iterations_used,
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
            operation_name='NMF')
        self.controller.add_new_spectra(new_spectra)
        return len(new_spectra)

    def save_results_excel(self, filepath, include_components=True,
                            include_scores=True, include_info=True):
        """
        Save NMF results to an Excel file.

        Returns:
            bool: True if save was successful
        """
        try:
            return self.manager.save_results_excel(
                filepath, include_components, include_scores, include_info)
        except Exception as e:
            logger.error(f"ERROR: Excel save failed: {e}")
            return False

    def save_results_text(self, save_config):
        """
        Save NMF results to text/CSV file(s).

        Returns:
            bool: True if save was successful
        """
        try:
            return self.manager.save_results_text(save_config)
        except Exception as e:
            logger.error(f"ERROR: Text save failed: {e}")
            return False

    def show_dialog(self, selected_spectra):
        """Show the NMF dialog — ported from
        main_controller._show_nmf_dialog. Takes spectra as a parameter
        rather than self-fetching them (unlike SVDAnalysisController /
        ClusterAnalysisController / PcaScoresController) to match that
        original call site exactly: run_visualization_analysis already had
        the selection in hand and passed it straight through, with no
        NMF-specific validation beyond the generic "some spectra are
        selected" check made before dispatch."""
        # Refuse BEFORE building the dialog — an empty window with a warning
        # in it is worse than no window (see validate_common_x_axis).
        if not validate_common_x_axis(selected_spectra,
                                      getattr(self.controller, 'view', None),
                                      'NMF'):
            return
        self.manager.reset()
        last = self.controller.operations_controller.last_op_settings.get("NMF", {})

        from src.views.dialogs.visualization_analysis.nmf_dialog import NMFDialog
        self.dialog = NMFDialog(
            parent=self.controller.view,
            controller=self,
            spectra=selected_spectra,
            current_settings=last,
        )
        self.dialog.exec_()
        # Remember the settings the user left the dialog with, so the next
        # time it's opened they're restored (read back via current_settings
        # in show_dialog above, applied by the dialog's _apply_saved_settings).
        # Nothing else writes last_op_settings['NMF'], so without this the
        # restore would always find an empty dict and fall back to defaults.
        try:
            self.controller.operations_controller.last_op_settings["NMF"] = \
                self.dialog._persist_settings()
        except Exception as e:
            logger.error(f"Could not persist NMF settings: {e}")
        self.dialog = None
