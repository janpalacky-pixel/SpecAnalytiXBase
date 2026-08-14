# src/modules/visualization_analysis/two_d_correlation_manager.py
"""
Two-Dimensional Correlation Spectroscopy (2D-COS) manager.

Implements Noda's generalized 2D correlation method (Noda, I. (1993),
Appl. Spectrosc. 47, 1329): a stacked set of 1D spectra, each recorded
under a different value of some external perturbation (time, temperature,
concentration, pH, pressure, ...), is transformed into two square
(n_wavelengths x n_wavelengths) correlation spectra:

    Synchronous  Phi(v1, v2)  — in-phase (simultaneous) intensity changes
    Asynchronous Psi(v1, v2)  — out-of-phase (sequential) intensity changes

Both are computed from the "dynamic spectra" — each spectrum with a
reference (usually the mean) subtracted — via:

    Phi = Y^T Y / (m - 1)
    Psi = Y^T N Y / (m - 1)

where Y is the (m spectra x n wavelengths) dynamic-spectra matrix and N is
the m x m Hilbert-Noda transformation matrix:

    N[j, k] = 0                  if j == k
            = 1 / (pi * (k - j)) otherwise

N implements the discrete Hilbert transform along the spectra (dynamic)
order, assuming the spectra are evenly spaced in the perturbation
variable — the standard assumption for this method (see the module help
for the caveat when they aren't).
"""

import os
import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import axes_match, describe_axis_mismatch
logger = get_logger(__name__)


class TwoDCorrelationManager:
    """Business logic for 2D correlation analysis on a set of spectra."""

    def __init__(self):
        self.x_axis = None
        self.synchronous = None      # (n x n)
        self.asynchronous = None     # (n x n)
        self.reference_spectrum = None
        self.dynamic_spectra = None  # (m x n) — each spectrum minus the reference
        self.spectrum_labels = None
        self.reference_mode = None   # 'mean', 'first', or 'index'
        self.reference_label = None  # which spectrum was used, when mode != 'mean'
        self.perturbation_values = None       # as given, in original spectra order
        self.perturbation_label = None
        self.sorted_perturbation_values = None   # original values, sorted, matching spectrum_labels order
        self.uniform_perturbation_values = None  # the (possibly resampled) evenly-spaced grid actually used
        self.was_resampled = False    # True if perturbation values were uneven and had to be resampled
        self.last_error = None

        # Hetero (cross-dataset) 2D correlation — see compute_hetero().
        # Kept as separate attributes rather than reusing synchronous/
        # asynchronous/etc. above, since a dialog may want to show both a
        # standard (homo) result and a hetero result without one
        # overwriting the other.
        self.hetero_x_axis = None
        self.hetero_y_axis = None
        self.hetero_synchronous = None    # (n_x, n_y) — not necessarily square
        self.hetero_asynchronous = None
        self.hetero_dynamic_x = None
        self.hetero_dynamic_y = None
        self.hetero_labels_x = None
        self.hetero_labels_y = None

    def reset(self):
        """Clear all previous results — same purpose as the reset() method
        on every other visualization-analysis manager: without this, a
        controller's manager reused across dialog sessions could still
        hold a previous, unrelated selection's correlation spectra when a
        fresh dialog opens, before the first computation for the new
        selection finishes."""
        self.__init__()

    def compute(self, spectra, reference='mean', reference_index=None,
                perturbation_values=None, perturbation_label=None):
        """
        Compute the synchronous and asynchronous 2D correlation spectra.

        Args:
            spectra: list of spectrum dicts with 'x_scale', 'y_scale', 'label',
                in the order they should be treated along the perturbation
                variable (time, temperature, ...).
            reference: 'mean' (dynamic spectra = spectrum - average spectrum,
                the standard choice), 'first' (spectrum - first spectrum,
                useful when the first spectrum is a genuine baseline/blank),
                or 'index' (spectrum - the spectrum at reference_index, for
                when any other single spectrum in the selection is the
                appropriate reference state).
            reference_index: required when reference='index' — the 0-based
                position, within `spectra` (in the order given, before any
                perturbation-based reordering below), of the spectrum to use.
            perturbation_values: optional, one real value per spectrum (e.g.
                actual temperatures or times), in the same order as `spectra`.
                If given: spectra are re-sorted into increasing perturbation
                order, and — since the asynchronous (Hilbert-Noda) transform
                assumes evenly-spaced samples — if the values turn out to be
                unevenly spaced, the dynamic spectra are automatically
                resampled (via linear interpolation) onto a synthetic,
                evenly-spaced perturbation grid spanning the same range
                before computing either correlation spectrum. If omitted,
                spectra are assumed to already be in evenly-spaced order as
                given (the previous, order-only behavior).
            perturbation_label: optional axis label for the perturbation
                variable (e.g. "Temperature (\u00b0C)"), stored for display only.

        Returns:
            bool: True on success.
        """
        self.last_error = None

        if not spectra or len(spectra) < 3:
            self.last_error = (
                "2D correlation requires at least 3 spectra — the "
                "asynchronous (Hilbert-Noda) transform needs enough points "
                "to distinguish a real out-of-phase signal from noise."
            )
            return False

        if reference == 'index' and (reference_index is None
                                      or not (0 <= reference_index < len(spectra))):
            self.last_error = "Invalid reference spectrum index."
            return False

        pv = None
        if perturbation_values is not None:
            pv = np.asarray(perturbation_values, dtype=float)
            if len(pv) != len(spectra):
                self.last_error = (
                    "Number of perturbation values must match the number of "
                    f"spectra ({len(pv)} given, {len(spectra)} spectra)."
                )
                return False
            if len(np.unique(pv)) != len(pv):
                self.last_error = "Perturbation values must all be distinct."
                return False

        # Identical x-axis requirement — same check, same reasoning, as
        # SVD Analysis / PCA Scores & Loadings. Uses the shared
        # spectra_validation.axes_match rather than a private
        # np.allclose(rtol=1e-7, atol=1e-9): that combination looks
        # tighter than np.allclose's usual default, but np.allclose scales
        # its tolerance to each VALUE's own magnitude (rtol * |b|), not to
        # the axis's step size the way axes_match does — for a
        # large-absolute-value axis (e.g. 10000-10010 cm-1 with a step of
        # 0.1), that tolerance works out to ~0.001, ten thousand times
        # looser than axes_match's own (step * 1e-6 = 1e-7) for the same
        # axis. Verified directly: a genuine ~0.5-millistep discrepancy
        # (a real difference, not float round-off) was silently accepted
        # as "matching" by the private check and correctly rejected by
        # axes_match — meaning two spectra sampled on meaningfully
        # different grids could have been silently correlated point-by-
        # point as if they were the same wavelength axis.
        first_x = np.asarray(spectra[0]['x_scale'], dtype=float)
        for s in spectra[1:]:
            x = np.asarray(s['x_scale'], dtype=float)
            if not axes_match(first_x, x):
                self.last_error = describe_axis_mismatch(
                    spectra[0], s, '2D correlation')
                return False

        try:
            Y = np.array([np.asarray(s['y_scale'], dtype=float) for s in spectra])  # (m, n)
            m, n = Y.shape
            base_labels = [s.get('label', f'Spectrum {i+1}') for i, s in enumerate(spectra)]

            # Reference is resolved against the ORIGINAL order/index given —
            # reference_index means "the spectrum at this position as shown
            # to the user", regardless of whether perturbation-based
            # reordering happens afterward.
            reference_label = None
            if reference == 'first':
                ref = Y[0].copy()
                reference_label = base_labels[0]
            elif reference == 'index':
                ref = Y[reference_index].copy()
                reference_label = base_labels[reference_index]
            else:
                ref = Y.mean(axis=0)

            dynamic = Y - ref[None, :]   # (m, n)

            ordered_labels = base_labels
            pv_sorted = None
            uniform_pv = None
            resampled = False

            if pv is not None:
                order = np.argsort(pv)
                pv_sorted = pv[order]
                dynamic = dynamic[order]
                ordered_labels = [base_labels[i] for i in order]

                diffs = np.diff(pv_sorted)
                # "Evenly spaced" within a 2% relative tolerance of the mean
                # spacing — real perturbation values (e.g. logged
                # temperatures) rarely land on machine-exact intervals even
                # when the intent was uniform steps.
                is_uniform = True if len(diffs) == 0 else np.allclose(
                    diffs, diffs.mean(), rtol=0.02, atol=1e-9)

                if is_uniform:
                    uniform_pv = pv_sorted
                else:
                    uniform_pv = np.linspace(pv_sorted[0], pv_sorted[-1], len(pv_sorted))
                    dyn_resampled = np.empty_like(dynamic)
                    for j in range(dynamic.shape[1]):
                        dyn_resampled[:, j] = np.interp(uniform_pv, pv_sorted, dynamic[:, j])
                    dynamic = dyn_resampled
                    resampled = True
                    logger.info(
                        "TwoDCorrelationManager: perturbation values were "
                        "unevenly spaced — resampled onto a uniform grid "
                        "from %.6g to %.6g before computing correlation spectra.",
                        uniform_pv[0], uniform_pv[-1])

            # Synchronous correlation spectrum.
            sync = (dynamic.T @ dynamic) / (m - 1)

            # Asynchronous correlation spectrum via the Hilbert-Noda matrix.
            idx = np.arange(m)
            with np.errstate(divide='ignore'):
                N = 1.0 / (np.pi * (idx[None, :] - idx[:, None]))
            np.fill_diagonal(N, 0.0)
            asynchronous = (dynamic.T @ N @ dynamic) / (m - 1)

            self.x_axis = first_x
            self.synchronous = sync
            self.asynchronous = asynchronous
            self.reference_spectrum = ref
            self.dynamic_spectra = dynamic
            self.spectrum_labels = ordered_labels
            self.reference_mode = reference
            self.reference_label = reference_label
            self.perturbation_values = pv
            self.perturbation_label = perturbation_label
            self.sorted_perturbation_values = pv_sorted
            self.uniform_perturbation_values = uniform_pv
            self.was_resampled = resampled

            logger.info("TwoDCorrelationManager: computed %dx%d correlation "
                        "spectra from %d spectra", n, n, m)
            return True

        except Exception as e:
            logger.error(f"ERROR: 2D correlation computation failed: {e}")
            logger.exception("Traceback:")
            self.last_error = str(e)
            return False


    def get_n_points(self):
        return 0 if self.x_axis is None else len(self.x_axis)

    def get_n_spectra(self):
        return 0 if self.dynamic_spectra is None else self.dynamic_spectra.shape[0]

    # ------------------------------------------------------------------ #
    # Hetero (cross-dataset) 2D correlation                                #
    # ------------------------------------------------------------------ #

    def compute_hetero(self, spectra_x, spectra_y, reference_x='mean', reference_y='mean'):
        """
        Compute hetero (cross-dataset) 2D correlation between two datasets
        X and Y — a genuine extension of Noda's method (also due to Noda),
        directly correlating the dynamic spectra of two different datasets
        against each other, rather than a dataset against itself:

            Phi_XY = X_dyn^T Y_dyn / (m - 1)
            Psi_XY = X_dyn^T N Y_dyn / (m - 1)

        Unlike the standard (homo) method above, X and Y do NOT need to
        share a wavenumber axis (that's the point — e.g. correlating IR
        band positions directly against Raman band positions). They DO
        need the same number of spectra (m), each pair (X[i], Y[i])
        representing the SAME perturbation step (e.g. the same time point
        measured by two different techniques) — this pairing is assumed
        from the order given, not verified in any other way, since there's
        no shared axis to check it against.

        Args:
            spectra_x, spectra_y: lists of spectrum dicts, same length.
            reference_x, reference_y: 'mean' or 'first', applied
                independently to each dataset. (No 'index'/specific-spectrum
                or perturbation-value/resampling support in hetero mode —
                a deliberate scope simplification; ask if you need either.)

        Returns:
            bool: True on success.
        """
        self.last_error = None

        if not spectra_x or not spectra_y:
            self.last_error = "Both Dataset X and Dataset Y need at least one spectrum."
            return False
        if len(spectra_x) != len(spectra_y):
            self.last_error = (
                "Dataset X and Dataset Y must have the same number of spectra "
                f"(one pair per perturbation step) \u2014 got {len(spectra_x)} and "
                f"{len(spectra_y)}."
            )
            return False
        if len(spectra_x) < 3:
            self.last_error = (
                "Hetero 2D correlation requires at least 3 paired spectra in "
                "each dataset."
            )
            return False

        for name, spectra in (('Dataset X', spectra_x), ('Dataset Y', spectra_y)):
            first_x = np.asarray(spectra[0]['x_scale'], dtype=float)
            for s in spectra[1:]:
                x = np.asarray(s['x_scale'], dtype=float)
                if not axes_match(first_x, x):
                    self.last_error = (
                        f"{name}: spectra have different x-axes from each other "
                        "(X and Y don't need to match each other, but every "
                        "spectrum within the same dataset does)."
                    )
                    return False

        try:
            X = np.array([np.asarray(s['y_scale'], dtype=float) for s in spectra_x])
            Y = np.array([np.asarray(s['y_scale'], dtype=float) for s in spectra_y])
            m = X.shape[0]

            ref_x = X[0].copy() if reference_x == 'first' else X.mean(axis=0)
            ref_y = Y[0].copy() if reference_y == 'first' else Y.mean(axis=0)
            dyn_x = X - ref_x[None, :]
            dyn_y = Y - ref_y[None, :]

            sync = (dyn_x.T @ dyn_y) / (m - 1)   # (n_x, n_y)

            idx = np.arange(m)
            with np.errstate(divide='ignore'):
                N = 1.0 / (np.pi * (idx[None, :] - idx[:, None]))
            np.fill_diagonal(N, 0.0)
            asynchronous = (dyn_x.T @ N @ dyn_y) / (m - 1)

            self.hetero_x_axis = np.asarray(spectra_x[0]['x_scale'], dtype=float)
            self.hetero_y_axis = np.asarray(spectra_y[0]['x_scale'], dtype=float)
            self.hetero_synchronous = sync
            self.hetero_asynchronous = asynchronous
            self.hetero_dynamic_x = dyn_x
            self.hetero_dynamic_y = dyn_y
            self.hetero_labels_x = [s.get('label', f'X{i+1}') for i, s in enumerate(spectra_x)]
            self.hetero_labels_y = [s.get('label', f'Y{i+1}') for i, s in enumerate(spectra_y)]

            logger.info("TwoDCorrelationManager: computed %dx%d hetero correlation "
                        "spectra from %d paired spectra", sync.shape[0], sync.shape[1], m)
            return True

        except Exception as e:
            logger.error(f"ERROR: Hetero 2D correlation computation failed: {e}")
            logger.exception("Traceback:")
            self.last_error = str(e)
            return False

    # ------------------------------------------------------------------ #
    # Snapshot save/load (for Compare runs / Difference tab)               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def save_snapshot_file(filepath, x_axis, synchronous, asynchronous, desc=''):
        """Save an A/B comparison snapshot (see the dialog's Store as A/B)
        to a .npz file, so it can be compared later — including in a
        different dialog session, e.g. one run on heating-phase spectra
        and another on cooling-phase spectra, each selected and run
        separately since a single dialog only ever holds one spectra
        selection."""
        np.savez_compressed(
            filepath, x_axis=x_axis, synchronous=synchronous,
            asynchronous=asynchronous, desc=np.array(desc))

    @staticmethod
    def load_snapshot_file(filepath):
        """Load a snapshot saved by save_snapshot_file().

        Returns:
            dict: {'x_axis', 'synchronous', 'asynchronous', 'desc'}

        Raises on malformed/unreadable files — the caller is expected to
        catch and show a message, same convention as save_results_excel/text.
        """
        data = np.load(filepath, allow_pickle=False)
        required = {'x_axis', 'synchronous', 'asynchronous', 'desc'}
        if not required.issubset(data.files):
            raise ValueError(
                f"Not a valid 2D correlation snapshot file (missing: "
                f"{required - set(data.files)}).")
        return {
            'x_axis': data['x_axis'],
            'synchronous': data['synchronous'],
            'asynchronous': data['asynchronous'],
            'desc': str(data['desc']),
        }

    # ------------------------------------------------------------------ #
    # Export                                                               #
    # ------------------------------------------------------------------ #

    def _autofit_excel_columns(self, writer, sheet_name, n_cols):
        """Widen the first (label) column enough to show wavenumber
        headers on first open — same fix applied everywhere else in this
        codebase's Excel export. Correlation matrix sheets are otherwise
        all-numeric, wide grids, so only the leading label column needs it."""
        from openpyxl.utils import get_column_letter
        worksheet = writer.sheets[sheet_name]
        worksheet.column_dimensions[get_column_letter(1)].width = 14

    def _matrix_to_dataframe(self, matrix):
        import pandas as pd
        df = pd.DataFrame(matrix, index=self.x_axis, columns=self.x_axis)
        df.index.name = 'x'
        return df

    def save_results_excel(self, filepath, include_synchronous=True,
                            include_asynchronous=True, include_dynamic=True):
        """Save the correlation matrices (and optionally the dynamic
        spectra) to one Excel workbook with separate worksheets."""
        import pandas as pd
        if self.synchronous is None:
            raise ValueError("No 2D correlation data available to save")

        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            if include_synchronous:
                df = self._matrix_to_dataframe(self.synchronous)
                df.to_excel(writer, sheet_name='Synchronous')
                self._autofit_excel_columns(writer, 'Synchronous', len(self.x_axis))
            if include_asynchronous:
                df = self._matrix_to_dataframe(self.asynchronous)
                df.to_excel(writer, sheet_name='Asynchronous')
                self._autofit_excel_columns(writer, 'Asynchronous', len(self.x_axis))
            if include_dynamic:
                dyn_dict = {'x': self.x_axis}
                for i, label in enumerate(self.spectrum_labels):
                    dyn_dict[label] = self.dynamic_spectra[i]
                dyn_df = pd.DataFrame(dyn_dict)
                dyn_df.to_excel(writer, sheet_name='Dynamic_Spectra', index=False)
        return True

    def save_results_text(self, save_config):
        """Save the correlation matrices (and optionally the dynamic
        spectra) to text/CSV file(s)."""
        if self.synchronous is None:
            raise ValueError("No 2D correlation data available to save")

        file_path = save_config['file_path']
        delimiter = save_config.get('delimiter', '\t')
        precision = save_config.get('precision', 6)
        float_format = f'%.{precision}f'
        include_synchronous = save_config.get('include_synchronous', True)
        include_asynchronous = save_config.get('include_asynchronous', True)
        include_dynamic = save_config.get('include_dynamic', True)
        save_separate = save_config.get('save_separate', False)

        sync_df = self._matrix_to_dataframe(self.synchronous) if include_synchronous else None
        async_df = self._matrix_to_dataframe(self.asynchronous) if include_asynchronous else None
        dyn_df = None
        if include_dynamic:
            import pandas as pd
            dyn_dict = {'x': self.x_axis}
            for i, label in enumerate(self.spectrum_labels):
                dyn_dict[label] = self.dynamic_spectra[i]
            dyn_df = pd.DataFrame(dyn_dict)

        if save_separate:
            base = os.path.splitext(file_path)[0]
            if sync_df is not None:
                sync_df.to_csv(f'{base}_synchronous.txt', sep=delimiter, float_format=float_format)
            if async_df is not None:
                async_df.to_csv(f'{base}_asynchronous.txt', sep=delimiter, float_format=float_format)
            if dyn_df is not None:
                dyn_df.to_csv(f'{base}_dynamic_spectra.txt', sep=delimiter, index=False, float_format=float_format)
        else:
            with open(file_path, 'w', newline='') as f:
                if sync_df is not None:
                    f.write('# Synchronous\n')
                    sync_df.to_csv(f, sep=delimiter, float_format=float_format)
                    f.write('\n')
                if async_df is not None:
                    f.write('# Asynchronous\n')
                    async_df.to_csv(f, sep=delimiter, float_format=float_format)
                    f.write('\n')
                if dyn_df is not None:
                    f.write('# Dynamic_Spectra\n')
                    dyn_df.to_csv(f, sep=delimiter, index=False, float_format=float_format)
        return True
