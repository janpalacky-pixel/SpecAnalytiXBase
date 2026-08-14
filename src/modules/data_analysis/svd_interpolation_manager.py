# src/modules/data_analysis/svd_interpolation_manager.py

import numpy as np
from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)


class SVDInterpolationManager:
    """
    Business logic for 'SVD Interpolation' (Data Manipulation): decompose a
    set of spectra measured at known parameter values (e.g. temperature,
    pH, time) via SVD, fit a simple curve (polynomial or spline) through
    each selected component's coefficients as a function of that
    parameter, then evaluate those curves at NEW, unmeasured parameter
    values to synthesize new spectra:

        y_new(v) = sum over selected components k of  U[:, k] * s[k] * coeff_k(v)

    using the SAME subspectra (U columns) and singular values (s) the fit was built from — this is
    standard truncated-SVD spectral reconstruction, just with the scores
    (Vt rows) replaced by a fitted curve evaluated at a new parameter
    value instead of an actually-measured one.

    Deliberately a separate class from SVDAnalysisManager
    (visualization_analysis/svd_analysis_manager.py), even though the SVD
    computation itself is the same idea — that one is a read-only
    exploration tool with no per-component curve fitting or spectrum
    synthesis; this one is a spectra-processing operation that produces
    new spectra. Kept fully independent (no shared state) so opening one
    never disturbs the other.
    """

    def __init__(self):
        # SVD results
        self.U = None
        self.s = None
        self.Vt = None
        self.x_axis = None
        self.explained_variance = None
        self.spectrum_labels = None

        # Parameter values, one per input spectrum, in the SAME order as
        # spectrum_labels / Vt's columns — e.g. the temperature each
        # spectrum was measured at. Required here (unlike
        # SVDAnalysisManager's optional parameter axis): there is no
        # "spectrum index" fallback, since new spectra are generated AT
        # specific values of this parameter, not at a position.
        self.parameter_values = None
        self.parameter_label = None

        # Per-component (by SVD component index) manual curve points, fit
        # type and settings — same shape/spirit as BaselineManager's
        # per-spectrum baseline_points/fit_types/poly_orders, but keyed by
        # component index instead of by spectrum, and fitting a
        # coefficient-vs-parameter curve instead of a baseline shape.
        self.curve_points = {}       # {component_idx: [(param_value, coeff_value), ...]}
        self.fit_types = {}          # {component_idx: 'polynomial' | 'spline'}
        self.poly_orders = {}        # {component_idx: int}
        self.spline_smoothing = {}   # {component_idx: float}, 0 = interpolating spline

        self.default_fit_type = 'spline'
        self.default_poly_order = 2
        self.default_spline_smoothing = 0.0

    # ------------------------------------------------------------------
    # SVD computation — same approach as SVDAnalysisManager.
    # ------------------------------------------------------------------
    def compute_svd_from_spectra(self, spectra):
        """Compute SVD from input spectra. All spectra must already share
        an identical x-axis (callers should check this with
        spectra_validation.validate_common_x_axis before opening the
        dialog, exactly like other combining methods)."""
        if not spectra:
            return False
        try:
            x_scales = [s['x_scale'] for s in spectra]
            y_scales = [s['y_scale'] for s in spectra]
            first_x = x_scales[0]
            for x in x_scales:
                if not np.array_equal(x, first_x):
                    logger.error("SVD Interpolation: spectra have mismatched x-axes")
                    return False

            self.x_axis = np.asarray(first_x, dtype=float)
            data_matrix = np.column_stack(y_scales)
            self.spectrum_labels = [s['label'] for s in spectra]

            self.U, self.s, self.Vt = np.linalg.svd(data_matrix, full_matrices=False)
            self.explained_variance = (self.s ** 2) / np.sum(self.s ** 2) * 100

            # A fresh computation invalidates anything tied to the OLD
            # component indices / spectrum count.
            self.parameter_values = None
            self.parameter_label = None
            self.curve_points = {}
            self.fit_types = {}
            self.poly_orders = {}
            self.spline_smoothing = {}
            return True
        except Exception as e:
            logger.error(f"SVD Interpolation: SVD computation failed: {e}")
            logger.exception("Traceback:")
            return False

    def get_n_components(self):
        return 0 if self.U is None else self.U.shape[1]

    def compute_residual_errors(self):
        """Malinowski's residual error RE(m): the RMS residual left after
        using the first m components, for m = 0..k-2 — same formula
        SVD Analysis's own Diagnostics tab uses for its RE(m) plot.
        Unlike IND (see compute_component_diagnostics above), plain RE
        doesn't try to pick a "best" number by itself — it's just shown
        here as one of a few raw diagnostic views the user can look at
        and judge for themselves. Returns None if there isn't enough
        data to compute it."""
        if self.s is None:
            return None
        n_sp = self.get_n_spectra()
        n_pts = 0 if self.x_axis is None else len(self.x_axis)
        if n_sp <= 1 or n_pts <= 0:
            return None
        eigenvalues = self.s ** 2
        k = len(self.s)
        re = np.zeros(k - 1)
        for m in range(k - 1):
            res_var = np.sum(eigenvalues[m + 1:])
            denom = n_pts * (n_sp - m)
            re[m] = np.sqrt(res_var / denom) if denom > 0 else 0
        return re

    def compute_component_diagnostics(self, threshold_pct=99.0):
        """
        A simple, robust hint for how many components carry real signal:
        the smallest number of components whose CUMULATIVE explained
        variance reaches threshold_pct.

        Deliberately NOT using Malinowski's IND function (an earlier
        version of this used it, same as SVD Analysis's own Diagnostics
        tab) — IND assumes fairly uniform noise across the "signal"
        components and a clean transition to a noise floor, an
        assumption that breaks down badly for datasets with many spectra
        and a very fast, clean singular-value drop-off (e.g. thousands of
        spectra where the first component alone already explains >90% of
        the variance and the tail is essentially zero) — in exactly that
        situation IND's minimum can land absurdly deep into the tail
        (hundreds or thousands of components) instead of reflecting the
        handful that actually matter. Cumulative variance threshold
        doesn't have that failure mode: it directly answers "how many
        components until we've captured (threshold)% of the
        variability", which is the practical question for this operation
        anyway — only components with real statistical weight are worth
        fitting a curve to.

        Returns None if there's no SVD yet, otherwise a dict with
        'cum_ev' (cumulative % variance array) and 'suggested_n' (the
        smallest component count reaching threshold_pct).
        """
        if self.explained_variance is None:
            return None
        cum_ev = np.cumsum(self.explained_variance)
        idx = int(np.searchsorted(cum_ev, threshold_pct))
        suggested_n = min(idx + 1, len(cum_ev))
        return {'cum_ev': cum_ev, 'suggested_n': suggested_n}

    def get_n_spectra(self):
        return 0 if self.Vt is None else self.Vt.shape[1]

    def get_coefficients(self, idx):
        """The TRUE (measured) coefficients for component idx — one per
        input spectrum. This is the data the manual curve points are
        placed against, not the fitted curve itself."""
        if self.Vt is None or idx >= self.Vt.shape[0]:
            return None
        return self.Vt[idx, :]

    def get_subspectrum(self, idx):
        if self.U is None or idx >= self.U.shape[1]:
            return None
        return self.U[:, idx]

    # ------------------------------------------------------------------
    # Parameter values
    # ------------------------------------------------------------------
    def set_parameter_values(self, values, label=None):
        """Set the per-spectrum parameter values (e.g. temperatures) that
        every coefficient curve gets fit against. Required before curve
        fitting or generation will do anything useful."""
        if self.Vt is None:
            return False
        n_expected = self.Vt.shape[1]
        try:
            arr = np.asarray(values, dtype=float)
        except (TypeError, ValueError):
            return False
        if arr.ndim != 1 or len(arr) != n_expected or n_expected == 0:
            return False
        self.parameter_values = arr
        self.parameter_label = label
        return True

    def get_parameter_values(self):
        return self.parameter_values

    # ------------------------------------------------------------------
    # Manual curve points, per component — same add/remove/clear shape as
    # BaselineManager, keyed by component index instead of by spectrum.
    # ------------------------------------------------------------------
    def _ensure_component(self, component_idx):
        if component_idx not in self.curve_points:
            self.curve_points[component_idx] = []
            self.fit_types[component_idx] = self.default_fit_type
            self.poly_orders[component_idx] = self.default_poly_order
            self.spline_smoothing[component_idx] = self.default_spline_smoothing

    def add_curve_point(self, component_idx, x, y):
        self._ensure_component(component_idx)
        self.curve_points[component_idx].append((float(x), float(y)))
        self.curve_points[component_idx].sort(key=lambda p: p[0])
        return self.curve_points[component_idx]

    def remove_curve_point(self, component_idx, x, y):
        """Remove whichever existing point is nearest to (x, y), in
        normalized units (so parameter units and coefficient units, which
        are usually very different scales, contribute comparably to
        'nearest')."""
        points = self.curve_points.get(component_idx)
        if not points:
            return points
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        x_span = (max(xs) - min(xs)) or 1.0
        y_span = (max(ys) - min(ys)) or 1.0
        best_i, best_d = None, None
        for i, (px, py) in enumerate(points):
            d = ((px - x) / x_span) ** 2 + ((py - y) / y_span) ** 2
            if best_d is None or d < best_d:
                best_i, best_d = i, d
        if best_i is not None:
            points.pop(best_i)
        return points

    def clear_curve_points(self, component_idx):
        if component_idx in self.curve_points:
            self.curve_points[component_idx] = []

    def get_curve_points(self, component_idx):
        return self.curve_points.get(component_idx, [])

    def set_fit_type(self, component_idx, fit_type):
        self._ensure_component(component_idx)
        self.fit_types[component_idx] = fit_type

    def get_fit_type(self, component_idx):
        return self.fit_types.get(component_idx, self.default_fit_type)

    def set_poly_order(self, component_idx, order):
        self._ensure_component(component_idx)
        self.poly_orders[component_idx] = order

    def get_poly_order(self, component_idx):
        return self.poly_orders.get(component_idx, self.default_poly_order)

    def set_spline_smoothing(self, component_idx, smoothing):
        self._ensure_component(component_idx)
        self.spline_smoothing[component_idx] = smoothing

    def get_spline_smoothing(self, component_idx):
        return self.spline_smoothing.get(component_idx, self.default_spline_smoothing)

    # ------------------------------------------------------------------
    # Curve evaluation
    # ------------------------------------------------------------------
    def evaluate_curve(self, component_idx, target_values):
        """Evaluate the fitted coefficient-vs-parameter curve for one
        component at target_values (a scalar or array). Returns None if
        there aren't enough manual points to fit (need >= 2)."""
        points = self.curve_points.get(component_idx, [])
        if len(points) < 2:
            return None

        x_points = np.array([p[0] for p in points], dtype=float)
        y_points = np.array([p[1] for p in points], dtype=float)

        # Collapse duplicate x-values by averaging their y's before
        # fitting. This matters in practice — e.g. a heating/cooling
        # ramp that revisits the same nominal temperature on the way
        # back down gives two DIFFERENT measured coefficients at the
        # SAME parameter value. An exact-fit spline (smoothing 0, what
        # Auto-fill uses) mathematically cannot pass through two
        # different y's at one x — that's not a function — so without
        # this it just failed silently (caught by the try/except below,
        # logged, curve simply never fit). Averaging treats repeated
        # measurements at the same parameter value as noisy replicates
        # of one true curve value there, which is the reasonable
        # assumption for what this tool is doing.
        order = np.argsort(x_points)
        x_points, y_points = x_points[order], y_points[order]
        unique_x, inverse = np.unique(x_points, return_inverse=True)
        if len(unique_x) < len(x_points):
            y_sum = np.zeros(len(unique_x))
            counts = np.zeros(len(unique_x))
            np.add.at(y_sum, inverse, y_points)
            np.add.at(counts, inverse, 1)
            y_points = y_sum / counts
            x_points = unique_x

        if len(x_points) < 2:
            return None

        targets = np.atleast_1d(np.asarray(target_values, dtype=float))

        fit_type = self.get_fit_type(component_idx)
        try:
            if fit_type == 'spline':
                from scipy.interpolate import UnivariateSpline
                # Spline order can't exceed (n_points - 1); cap at cubic.
                k = min(3, len(x_points) - 1)
                s = self.get_spline_smoothing(component_idx)
                spline = UnivariateSpline(x_points, y_points, k=k, s=s)
                return spline(targets)
            else:  # polynomial
                order_n = min(self.get_poly_order(component_idx), len(x_points) - 1)
                coeffs = np.polyfit(x_points, y_points, order_n)
                return np.polyval(coeffs, targets)
        except Exception as e:
            logger.error(f"SVD Interpolation: curve fit failed for component {component_idx}: {e}")
            return None

    def get_curve_for_plot(self, component_idx, n_points=200, x_min=None, x_max=None):
        """Convenience for drawing the fitted curve as a smooth line: a
        dense (x, y) pair spanning the component's own points (or an
        explicit range, e.g. to show extrapolation out to target values
        beyond the measured range). Returns (None, None) if not enough
        points to fit."""
        points = self.curve_points.get(component_idx, [])
        if len(points) < 2:
            return None, None
        xs = [p[0] for p in points]
        lo = x_min if x_min is not None else min(xs)
        hi = x_max if x_max is not None else max(xs)
        if lo == hi:
            lo, hi = lo - 1, hi + 1
        curve_x = np.linspace(lo, hi, n_points)
        curve_y = self.evaluate_curve(component_idx, curve_x)
        return (curve_x, curve_y) if curve_y is not None else (None, None)

    # ------------------------------------------------------------------
    # Spectrum synthesis
    # ------------------------------------------------------------------
    def generate_spectra(self, selected_components, target_values, target_labels=None):
        """Synthesize one new spectrum per target value:

            y = sum over selected_components of  U[:, k] * s[k] * evaluate_curve(k, target)

        The s[k] (singular value) factor matters: SVD decomposes the data
        as U @ diag(s) @ Vt, so a component's actual contribution to a
        spectrum is U[:,k] * s[k] * Vt[k,i] — U alone is just a unit-norm
        shape, and get_coefficients()/the curve points are fit against
        raw Vt values (unscaled by s[k], matching SVDAnalysisManager's
        convention, so the numbers on the coefficient plot stay in a
        sane, eyeball-able range). Without re-applying s[k] here, every
        selected component would be summed as if equally important,
        instead of weighted by how much it actually matters — which is
        exactly backwards, since Vt rows are all unit-norm regardless of
        a component's real significance.

        Returns (spectra, failed_components). failed_components is the
        subset of selected_components that didn't have enough curve
        points to fit — generation still proceeds using whatever DID fit;
        a failed component simply contributes nothing, same as if it had
        never been selected. Caller should warn the user about these.
        """
        if self.U is None or self.x_axis is None or not selected_components:
            return [], list(selected_components or [])

        target_values = np.atleast_1d(np.asarray(target_values, dtype=float))
        if target_labels is None:
            unit = f'_{self.parameter_label}' if self.parameter_label else ''
            target_labels = [f'SVD_interp_{v:g}{unit}' for v in target_values]

        coeff_by_component = {}
        failed = []
        for k in selected_components:
            vals = self.evaluate_curve(k, target_values)
            if vals is None:
                failed.append(k)
            else:
                coeff_by_component[k] = vals

        usable = [k for k in selected_components if k in coeff_by_component]
        spectra = []
        for i, target in enumerate(target_values):
            y = np.zeros_like(self.x_axis, dtype=float)
            for k in usable:
                y = y + self.U[:, k] * self.s[k] * coeff_by_component[k][i]
            spectra.append({
                'x_scale': self.x_axis.copy(),
                'y_scale': y,
                'label': target_labels[i],
                # Transient carrier for this ONE spectrum's own generation
                # specifics — which target value it was evaluated at,
                # which components actually contributed, and what curve
                # fit each of those components used. SVDInterpolationController
                # .commit_generated_spectra pops this key back out and folds
                # it into the spectrum's correction_history entry (same
                # "compute here, fold into history at commit time" pattern
                # SVDBackgroundManager/-Controller already use for their own
                # 'svd_correction' key) rather than leaving it as its own
                # separate metadata section — this is exactly the flat-key
                # vs. correction_history duplication that turned out to be
                # dead weight for Automated Baseline (see
                # automated_baseline_manager.py's apply_correction). Before
                # this, EVERY spectrum generated in one run got an
                # identical correction_history entry — just a shared run_id
                # and the list of source spectra — with no way to tell
                # which target value or components a given spectrum
                # actually came from.
                'metadata': {
                    'svd_interpolation_target': {
                        'parameter_label': self.parameter_label or None,
                        # Displayed to the user (metadata dialog, Operations
                        # History) as 1-based component numbers, matching
                        # the dialog's own component list ("Component 1",
                        # "Component 2", ... — see
                        # SVDInterpolationDialog._component_label) rather
                        # than the internal 0-based component_idx used
                        # everywhere else in this manager (self.U/self.Vt
                        # columns, curve_points/fit_types dict keys, etc).
                        # Converted only here, at the point this transient
                        # dict is built for display/history — nothing
                        # downstream re-indexes back into the manager with
                        # these values (SVDInterpolationController.
                        # commit_generated_spectra only folds them into
                        # correction_history), so this is purely cosmetic.
                        'components_used': [k + 1 for k in usable],
                        'fit_types': {int(k) + 1: self.get_fit_type(k) for k in usable},
                    }
                },
            })
        return spectra, failed
