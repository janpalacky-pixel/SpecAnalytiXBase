# src/modules/visualization_analysis/som_manager.py

import numpy as np
import pandas as pd
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import axes_match, describe_axis_mismatch
from src.modules.visualization_analysis.band_ratio_manager import BandRatioManager

logger = get_logger(__name__)


class SOMManager:
    """
    Business logic for Self-Organizing Map (SOM) analysis on spectra.

    Shape mirrors ClusterAnalysisManager (src/modules/visualization_analysis/
    cluster_analysis_manager.py): pure computation, no Qt, no controller/
    dialog awareness. Input is the same general, ungrouped spectra list
    every other Visualization tool consumes (a plain list of {'x_scale',
    'y_scale', 'label'} dicts sharing one x-axis) — SOM is a peer of
    Cluster Analysis / PCA / NMF / MCR-ALS, not a variant of Melting Curve
    Analysis: it never modifies or commits spectra, it only visualizes/
    exports what it finds.

    The Kohonen training routine (_train) is deliberately implemented from
    scratch in plain numpy rather than pulling in a SOM library (e.g.
    minisom): the algorithm is short enough that a from-scratch version is
    easy to verify, and it keeps this tool's dependency footprint the same
    as every other Manager in this codebase (numpy/scipy/pandas/
    scikit-learn only) — matching the project's existing "genuinely
    standalone" design goal (see melting_curve_manager.py's own docstring
    for the same rule applied to sigmoid fitting). This is the same engine
    — rectangular grid, PCA-seeded init, geometric learning-rate/radius
    decay — already used and proven in the companion MeltAnalytiX
    application's own src/analysis/som_manager.py; ported here rather than
    reinvented.

    Training data (`train_mode`):
        'shape'   — (default) each spectrum's own y_scale is one training
                    vector, same as the original implementation. A trained
                    node's weight vector lives in wavelength space, so it
                    can be un-standardised back into a "prototype spectrum"
                    (see get_node_prototype_spectrum) and shown, exported,
                    or queried at any wavelength/x-value/range — this is
                    what makes the generalised Component Plane
                    (get_component_plane_by_settings) possible.
        'feature' — each spectrum is instead reduced to a short vector of
                    user-defined scalar features (peak position, band
                    integral, band ratio, intensity at x, ...) before
                    training, mirroring MeltAnalytiX's own SOM dialog
                    "Cluster by extracted features vs. Cluster by
                    melting-curve shape" toggle. Reuses BandRatioManager —
                    the exact engine behind this app's own standalone Band
                    Ratio / Peak Area Calculator tool — for every feature,
                    rather than a second, private implementation of the
                    same range/metric math.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        """Clear all previous results. Called by SOMController each time a
        fresh dialog is opened for a (possibly entirely different) set of
        spectra — without this, a stale map from a previous, unrelated
        selection could still be displayed before Run SOM is ever clicked
        for the current one. Same reasoning as ClusterAnalysisManager.reset."""
        self.x_axis = None
        self.spectrum_labels = None
        self.data_matrix = None
        self.scaled_data = None
        self._feature_mean = None
        self._feature_std = None

        self.train_mode = 'shape'      # 'shape' or 'feature'
        self.feature_defs = None       # list of BandRatioManager-style band_def dicts (feature mode)
        self.feature_labels = None     # display name per column of data_matrix (feature mode)
        self._band_ratio = BandRatioManager()

        self.grid_rows = None
        self.grid_cols = None
        self.n_iterations = None
        self.learning_rate_start = None
        self.learning_rate_end = None
        self.radius_end = None

        self.weights = None            # (rows, cols, n_features) — trained node weight vectors
        self.bmu_indices = None        # (n_spectra, 2) int array — (row, col) best-matching unit per spectrum
        self.per_sample_error = None   # (n_spectra,) — distance from each spectrum to its own BMU
        self.u_matrix = None           # (rows, cols) — mean distance to neighbouring nodes
        self.hit_map = None            # (rows, cols) int — spectra count per node
        self.quantization_error = None

    # ------------------------------------------------------------------ #
    # Training                                                            #
    # ------------------------------------------------------------------ #

    def compute_som(self, spectra, grid_rows=5, grid_cols=5, n_iterations=300,
                     learning_rate_start=0.5, learning_rate_end=0.02,
                     radius_end=0.5, random_seed=42, train_mode='shape',
                     feature_defs=None, progress_callback=None):
        """
        Train a Self-Organizing Map on the given spectra.

        Args:
            spectra: list of spectrum dicts with 'x_scale', 'y_scale', 'label'
            grid_rows, grid_cols: SOM grid dimensions
            n_iterations: number of full passes over the (shuffled) spectra
            learning_rate_start, learning_rate_end: learning rate decays
                geometrically from start to end over training
            radius_end: neighbourhood radius (grid units) at the end of
                training — it starts at max(grid_rows, grid_cols) / 2 and
                decays geometrically down to this value, same schedule as
                learning rate
            random_seed: fixed seed so a given parameter set reproduces the
                same map exactly
            train_mode: 'shape' (train on each spectrum's full y_scale, the
                original behaviour) or 'feature' (train on a short vector
                of user-defined scalar features instead — see class
                docstring). Anything other than 'feature' is treated as
                'shape'.
            feature_defs: required when train_mode == 'feature'. A list of
                BandRatioManager band_def dicts, each additionally carrying
                a 'name' key used as that feature's display label, e.g.
                {'name': 'Peak @1650', 'metric': 'Peak intensity',
                 'ranges': [[1600, 1700]], 'is_exclude': False}
                or {'name': 'I(1550)', 'metric': 'Intensity at x',
                    'x_pos': 1550.0}.
            progress_callback: optional callable(step, total_steps, label).
                Unlike a call into an opaque third-party fit function, this
                training loop is plain Python/numpy under our control, so
                the reported progress is the REAL fraction of iterations
                completed, not a handful of fixed stage boundaries standing
                in for one big opaque call — see ClusterAnalysisManager.
                compute_clustering's docstring for why that stage-boundary
                approach was the honest option THERE; here we can do better
                because the loop is actually observable.

        Returns:
            bool: True if training was successful.
        """
        if not spectra:
            logger.debug("DEBUG: No spectra provided for SOM analysis")
            return False

        train_mode = 'feature' if train_mode == 'feature' else 'shape'

        total_steps = n_iterations + 1  # 1 data-prep step + one per training pass

        def _report(step, label):
            if progress_callback is not None:
                progress_callback(step, total_steps, label)

        try:
            _report(0, 'Preparing data…')

            self.spectrum_labels = [s['label'] for s in spectra]

            if train_mode == 'feature':
                if not feature_defs:
                    logger.error("SOM (feature mode): no feature definitions supplied.")
                    return False

                columns = []
                labels = []
                for fdef in feature_defs:
                    values = []
                    for s in spectra:
                        x = np.asarray(s.get('x_scale', []), dtype=float)
                        y = np.asarray(s.get('y_scale', []), dtype=float)
                        if len(x) < 2:
                            values.append(np.nan)
                            continue
                        _, _, _, value = self._band_ratio._compute_band(x, y, fdef)
                        values.append(value if value is not None else np.nan)
                    columns.append(values)
                    labels.append(fdef.get('name') or fdef.get('metric', 'feature'))

                self.data_matrix = np.array(columns, dtype=float).T  # (n_samples, n_features)
                if not np.isfinite(self.data_matrix).all():
                    logger.error(
                        "SOM (feature mode): one or more features could not be computed "
                        "for every spectrum (missing/invalid value) — check that every "
                        "feature's range or x-position actually falls inside all selected "
                        "spectra."
                    )
                    return False

                self.feature_defs = feature_defs
                self.feature_labels = labels
                self.x_axis = None  # no single shared wavelength axis drives training here

            else:
                x_scales = [s['x_scale'] for s in spectra]
                y_scales = [s['y_scale'] for s in spectra]

                # Same tolerance-aware check every other "stack spectra into
                # one matrix" tool in this app uses (spectra_validation.
                # axes_match) — not a private exact-equality copy. The
                # controller already ran validate_common_x_axis before this
                # dialog was allowed to open; this is the same
                # belt-and-suspenders re-check ClusterAnalysisManager.
                # compute_clustering does for itself.
                first_x = x_scales[0]
                for i, x in enumerate(x_scales):
                    if not axes_match(first_x, x):
                        logger.error(
                            "SOM analysis: %s",
                            describe_axis_mismatch(spectra[0], spectra[i], 'SOM analysis')
                            .replace('\n', ' ')
                        )
                        return False

                self.x_axis = first_x
                self.data_matrix = np.row_stack(y_scales)
                self.feature_defs = None
                self.feature_labels = None

            # Standardise each column before training — SOM node distances
            # are Euclidean over the raw feature vector, so without this the
            # highest-magnitude wavelength/feature alone would decide which
            # node wins, exactly as PCA/Cluster Analysis already scale their
            # inputs before computing distances.
            mean = self.data_matrix.mean(axis=0)
            std = self.data_matrix.std(axis=0)
            std_safe = std.copy()
            std_safe[std_safe == 0] = 1.0
            self._feature_mean = mean
            self._feature_std = std_safe
            self.scaled_data = (self.data_matrix - mean) / std_safe

            self.train_mode = train_mode
            self.grid_rows = int(grid_rows)
            self.grid_cols = int(grid_cols)
            self.n_iterations = int(n_iterations)
            self.learning_rate_start = float(learning_rate_start)
            self.learning_rate_end = float(learning_rate_end)
            self.radius_end = float(radius_end)

            result = self._train(
                self.scaled_data, self.grid_rows, self.grid_cols,
                n_iterations=self.n_iterations, seed=random_seed,
                lr_start=self.learning_rate_start, lr_end=self.learning_rate_end,
                radius_end=self.radius_end, report=_report,
            )

            self.weights = result['weights']
            self.bmu_indices = result['bmu']
            self.per_sample_error = result['per_sample_error']
            self.quantization_error = result['quantization_error']
            self.u_matrix = result['u_matrix']

            self.hit_map = np.zeros((self.grid_rows, self.grid_cols), dtype=int)
            for r, c in self.bmu_indices:
                self.hit_map[r, c] += 1

            return True

        except Exception as e:
            logger.error(f"SOM computation failed: {e}")
            logger.exception("Traceback:")
            return False

    @staticmethod
    def _train(X, grid_rows, grid_cols, n_iterations, seed,
               lr_start, lr_end, radius_end, report=None):
        """Train a rectangular-grid Kohonen self-organizing map on X.

        Ported from MeltAnalytiX's src/analysis/som_manager.py::train_som
        (same algorithm, same defaults, same return-value shape), adapted
        here to report per-iteration progress via `report(step, label)`.
        See that module's own docstring for the full design rationale
        (PCA-seeded init converges faster/more reproducibly than random
        weights on the small, tens-to-low-hundreds-of-spectra datasets
        typical here; the geometric learning-rate/radius decay organizes
        overall topology early and refines local detail late).

        Args:
            X: (n_samples, n_features) already-scaled matrix.
            grid_rows, grid_cols: SOM grid size.
            n_iterations: number of full passes over the shuffled data.
            seed: RNG seed — training is otherwise fully deterministic.
            lr_start, lr_end: learning rate decays geometrically between these.
            radius_end: neighbourhood radius at the end of training; it
                starts at max(grid_rows, grid_cols) / 2.
            report: optional callable(step, label) called once per pass.

        Returns a dict: 'weights' (rows, cols, n_features), 'bmu'
        (n_samples, 2) int, 'quantization_error' (float, mean BMU
        distance), 'per_sample_error' (n_samples,), 'u_matrix'
        (rows, cols, mean distance to each node's grid neighbours).
        """
        X = np.asarray(X, dtype=float)
        n_samples, n_features = X.shape
        if n_samples == 0:
            raise ValueError("No samples to train on (empty input matrix).")
        rng = np.random.default_rng(seed)
        radius_start = max(grid_rows, grid_cols) / 2.0

        # PCA-based initialization: place nodes on a small grid spanning the
        # two directions of greatest variance in X, rather than pure random
        # weights.
        mean = X.mean(axis=0)
        Xc = X - mean
        if n_features >= 2 and n_samples >= 2:
            try:
                _, S, Vt = np.linalg.svd(Xc, full_matrices=False)
                pc1 = Vt[0]
                pc2 = Vt[1] if Vt.shape[0] > 1 else rng.normal(size=n_features)
                span1 = (S[0] / np.sqrt(n_samples)) if S.size > 0 and S[0] > 0 else 1.0
                span2 = (S[1] / np.sqrt(n_samples)) if S.size > 1 and S[1] > 0 else span1 * 0.1
            except np.linalg.LinAlgError:
                pc1, pc2 = rng.normal(size=n_features), rng.normal(size=n_features)
                span1 = span2 = 1.0
        else:
            pc1, pc2 = rng.normal(size=n_features), rng.normal(size=n_features)
            span1 = span2 = 1.0

        rows_lin = np.linspace(-1, 1, grid_rows)
        cols_lin = np.linspace(-1, 1, grid_cols)
        weights = np.empty((grid_rows, grid_cols, n_features))
        for r_i, rv in enumerate(rows_lin):
            for c_i, cv in enumerate(cols_lin):
                weights[r_i, c_i] = mean + rv * span1 * pc1 + cv * span2 * pc2

        grid_r, grid_c = np.meshgrid(np.arange(grid_rows), np.arange(grid_cols), indexing='ij')
        grid_r = grid_r.astype(float)
        grid_c = grid_c.astype(float)

        order = np.arange(n_samples)
        for it in range(n_iterations):
            t_frac = it / max(1, n_iterations - 1)
            lr = lr_start * (lr_end / lr_start) ** t_frac
            radius = radius_start * (radius_end / radius_start) ** t_frac
            rng.shuffle(order)
            for idx in order:
                x = X[idx]
                diffs = weights - x
                dists = np.einsum('rcf,rcf->rc', diffs, diffs)
                bmu_r, bmu_c = np.unravel_index(np.argmin(dists), dists.shape)
                grid_dist2 = (grid_r - bmu_r) ** 2 + (grid_c - bmu_c) ** 2
                neighborhood = np.exp(-grid_dist2 / (2.0 * radius ** 2))
                weights -= (lr * neighborhood)[:, :, None] * diffs
            if report is not None:
                report(it + 1, f'Training SOM… pass {it + 1}/{n_iterations}')

        bmu = np.empty((n_samples, 2), dtype=int)
        per_sample_error = np.empty(n_samples)
        for i in range(n_samples):
            diffs = weights - X[i]
            dists = np.einsum('rcf,rcf->rc', diffs, diffs)
            r, c = np.unravel_index(np.argmin(dists), dists.shape)
            bmu[i] = (r, c)
            per_sample_error[i] = np.sqrt(dists[r, c])

        u_matrix = np.zeros((grid_rows, grid_cols))
        for r in range(grid_rows):
            for c in range(grid_cols):
                neigh_dists = []
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < grid_rows and 0 <= cc < grid_cols:
                        neigh_dists.append(float(np.linalg.norm(weights[r, c] - weights[rr, cc])))
                u_matrix[r, c] = np.mean(neigh_dists) if neigh_dists else 0.0

        return {
            'weights': weights,
            'bmu': bmu,
            'quantization_error': float(per_sample_error.mean()),
            'per_sample_error': per_sample_error,
            'u_matrix': u_matrix,
        }

    # ------------------------------------------------------------------ #
    # Result accessors                                                    #
    # ------------------------------------------------------------------ #

    def get_node_info(self):
        """Per-occupied-node summary: list of dicts with row, col, size,
        mean_qe (mean distance of that node's assigned spectra to its own
        weight vector, in standardised space)."""
        if self.hit_map is None:
            return []
        info = []
        for r in range(self.grid_rows):
            for c in range(self.grid_cols):
                size = int(self.hit_map[r, c])
                if size == 0:
                    continue
                mask = (self.bmu_indices[:, 0] == r) & (self.bmu_indices[:, 1] == c)
                mean_qe = float(np.mean(self.per_sample_error[mask])) if np.any(mask) else None
                info.append({'row': r, 'col': c, 'size': size, 'mean_qe': mean_qe})
        return info

    def get_node_members(self, row, col):
        """Spectrum labels whose best-matching unit is (row, col)."""
        if self.bmu_indices is None:
            return []
        mask = (self.bmu_indices[:, 0] == row) & (self.bmu_indices[:, 1] == col)
        return [label for label, m in zip(self.spectrum_labels, mask) if m]

    def get_component_plane(self, feature_index):
        """(rows, cols) weight plane for one training column — a raw
        wavelength index in 'shape' mode, or one custom feature in
        'feature' mode. Shows how strongly that single column drives the
        map's layout."""
        if self.weights is None:
            return None
        return self.weights[:, :, feature_index]

    def get_n_features(self):
        if self.train_mode == 'feature':
            return 0 if not self.feature_labels else len(self.feature_labels)
        return 0 if self.x_axis is None else len(self.x_axis)

    def get_feature_label(self, idx):
        """Human-readable label for training column `idx` — the feature's
        own name in 'feature' mode, or 'x = <value>' in 'shape' mode."""
        if self.train_mode == 'feature' and self.feature_labels:
            if 0 <= idx < len(self.feature_labels):
                return self.feature_labels[idx]
            return f"feature {idx}"
        if self.x_axis is not None and 0 <= idx < len(self.x_axis):
            return f"x = {self.x_axis[idx]:g}"
        return f"index {idx}"

    def get_node_prototype_spectrum(self, row, col):
        """Reconstruct the (x_axis, y) prototype spectrum for one trained
        node, by un-standardising its weight vector back to original
        y-scale units. 'shape' mode only — in 'feature' mode a node's
        weight vector lives in feature space (e.g. [peak position, band
        integral, ...]), not wavelength space, so there is no spectrum to
        reconstruct; returns (None, None) there.
        """
        if self.weights is None or self.train_mode != 'shape' or self.x_axis is None:
            return None, None
        if not (0 <= row < self.grid_rows and 0 <= col < self.grid_cols):
            return None, None
        y = self.weights[row, col] * self._feature_std + self._feature_mean
        return self.x_axis, y

    def get_component_plane_by_settings(self, settings):
        """Generalised 'component plane' for 'shape'-mode SOM: instead of a
        raw per-wavelength-index weight, computes any Band Ratio-style
        scalar feature (intensity at one x-value, mean/integral/variance/
        peak over an x-range, or the ratio/difference/sum of two such
        bands) from each node's reconstructed prototype spectrum. Reuses
        BandRatioManager — the exact same engine the standalone Band Ratio
        / Peak Area Calculator tool uses on real, measured spectra — just
        applied here to a SOM node's trained prototype spectrum instead.

        `settings` has the same shape BandRatioManager.compute_results
        expects: {'band_a': band_def, 'band_b': band_def or None,
        'operation': str}. 'shape' mode only; returns None otherwise.
        """
        if self.weights is None or self.train_mode != 'shape' or self.x_axis is None:
            return None

        band_a = settings.get('band_a', {})
        band_b = settings.get('band_b')
        operation = settings.get('operation', 'A only')

        grid = np.full((self.grid_rows, self.grid_cols), np.nan)
        for r in range(self.grid_rows):
            for c in range(self.grid_cols):
                x, y = self.get_node_prototype_spectrum(r, c)
                _, _, _, value_a = self._band_ratio._compute_band(x, y, band_a)
                value_b = None
                if band_b is not None:
                    _, _, _, value_b = self._band_ratio._compute_band(x, y, band_b)
                value = self._band_ratio._apply_operation(value_a, value_b, operation)
                if value is not None:
                    grid[r, c] = value
        return grid

    # ------------------------------------------------------------------ #
    # Export                                                              #
    # ------------------------------------------------------------------ #

    def _autofit_excel_columns(self, writer, sheet_name, df):
        """Widen each column enough to show its full header on first open —
        same fix ClusterAnalysisManager/PCA/SVD/NMF apply to their own
        Excel export."""
        from openpyxl.utils import get_column_letter
        worksheet = writer.sheets[sheet_name]
        for i, col in enumerate(df.columns):
            width = max(len(str(col)) + 2, 10)
            worksheet.column_dimensions[get_column_letter(i + 1)].width = width

    def save_results_excel(self, filepath):
        """Save SOM results (per-spectrum BMU assignments, per-node summary,
        training parameters, and — in 'feature' mode — the feature
        definitions used) to a multi-sheet Excel workbook. Same engine
        ('openpyxl') and autofit convention as every other Visualization
        tool's Excel export in this app."""
        if self.bmu_indices is None:
            return False
        try:
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                assignments_df = pd.DataFrame({
                    'Spectrum': self.spectrum_labels,
                    'Node_Row': self.bmu_indices[:, 0],
                    'Node_Col': self.bmu_indices[:, 1],
                    'Distance_To_BMU': self.per_sample_error,
                })
                assignments_df.to_excel(writer, sheet_name='BMU_Assignments', index=False)
                self._autofit_excel_columns(writer, 'BMU_Assignments', assignments_df)

                node_info = self.get_node_info()
                nodes_df = pd.DataFrame(node_info) if node_info else pd.DataFrame(
                    columns=['row', 'col', 'size', 'mean_qe'])
                nodes_df.to_excel(writer, sheet_name='Node_Summary', index=False)
                self._autofit_excel_columns(writer, 'Node_Summary', nodes_df)

                params_df = pd.DataFrame([{
                    'Grid_Rows': self.grid_rows,
                    'Grid_Cols': self.grid_cols,
                    'Iterations': self.n_iterations,
                    'Learning_Rate_Start': self.learning_rate_start,
                    'Learning_Rate_End': self.learning_rate_end,
                    'Neighborhood_Radius_End': self.radius_end,
                    'Quantization_Error': self.quantization_error,
                    'Train_Mode': self.train_mode,
                    'N_Spectra': len(self.spectrum_labels) if self.spectrum_labels else 0,
                }])
                params_df.to_excel(writer, sheet_name='Parameters', index=False)
                self._autofit_excel_columns(writer, 'Parameters', params_df)

                if self.train_mode == 'feature' and self.feature_defs:
                    feat_rows = []
                    for name, fdef in zip(self.feature_labels, self.feature_defs):
                        ranges = fdef.get('ranges', [])
                        feat_rows.append({
                            'Name': name,
                            'Metric': fdef.get('metric', ''),
                            'X1': (ranges[0][0] if ranges else fdef.get('x_pos', '')),
                            'X2': (ranges[0][1] if ranges else ''),
                        })
                    feat_df = pd.DataFrame(feat_rows)
                    feat_df.to_excel(writer, sheet_name='Feature_Definitions', index=False)
                    self._autofit_excel_columns(writer, 'Feature_Definitions', feat_df)

            return True
        except Exception as e:
            logger.error(f"Error saving SOM results: {e}")
            return False
