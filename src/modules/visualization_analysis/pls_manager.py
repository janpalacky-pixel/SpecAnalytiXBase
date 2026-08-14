# src/modules/visualization_analysis/pls_manager.py
"""
PLS (Partial Least Squares) regression and PLS-DA (classification)
manager — pure computation, no Qt.

Two modes, one underlying algorithm:
  * 'regression'      — y is a continuous quantity (concentration, %
                         purity, temperature, ...) entered per spectrum;
                         a standard sklearn.cross_decomposition.
                         PLSRegression fit against that single column.
  * 'classification'  — y is a class label (text) entered per spectrum;
                         the classic PLS-DA trick is used: one-hot
                         ("dummy") encode the class labels into an
                         indicator matrix (one column per class, 1.0 for
                         the sample's own class, 0.0 otherwise) and fit
                         the SAME PLSRegression against that matrix. A
                         new sample is classified by which class's
                         predicted indicator column is highest.

WORKFLOW: some of the spectra handed in have a known y-value (the
CALIBRATION set — used to fit and cross-validate the model); any spectra
with no y-value provided are PREDICTION-only (the model is applied to
them, but they never influence the fit). This mirrors how a real
chemometrics workflow is structured: build a model from known standards,
then use it to read off unknowns.

CROSS-VALIDATION picks the number of latent variables (components): too
few underfits, too many overfits and starts modelling noise. For each
candidate component count from 1 up to a safe maximum, an out-of-fold
prediction is computed for every calibration sample (leave-one-out for
small calibration sets, k-fold otherwise) and scored — RMSECV
(regression) or cross-validated classification accuracy (PLS-DA). The
component count with the best score is selected automatically (ties
broken toward FEWER components — the simpler model is preferred,
standard chemometrics practice), though the caller may override this
with an explicit value.

VIP (Variable Importance in Projection) scores use the standard
formula (Wold et al.) — a per-wavelength importance metric, conventionally
interpreted as "above 1.0 is more influential than an average variable."
Computed from the fitted model's x_scores_/x_weights_/y_loadings_;
wrapped defensively since it depends on exact array shapes that can vary
slightly across scikit-learn versions — if it can't be computed for any
reason, it's simply omitted rather than the whole analysis failing.
"""

import numpy as np
from sklearn.cross_decomposition import PLSRegression
from sklearn.model_selection import KFold, LeaveOneOut
from sklearn.metrics import mean_squared_error, r2_score, confusion_matrix

from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import axes_match
from src.modules.utils.spectrum_identity import spectrum_key

logger = get_logger(__name__)

MODE_REGRESSION = 'regression'
MODE_CLASSIFICATION = 'classification'

DEFAULT_MAX_COMPONENTS = 15
DEFAULT_CV_FOLDS = 10
LOO_THRESHOLD = 20  # calibration sets at or below this size use leave-one-out


class PLSManager:
    """Business logic for PLS regression / PLS-DA. compute_pls() never
    mutates its inputs, never touches the UI, and never modifies the
    spectra list — read-only analysis, same as ClusterAnalysisManager /
    IsosbesticPointManager."""

    def compute_pls(self, spectra, y_by_key, mode=MODE_REGRESSION,
                     n_components=None, autoscale_x=True, cv_folds=None,
                     max_components=DEFAULT_MAX_COMPONENTS, progress_callback=None):
        """
        Parameters
        ----------
        spectra : list of spectrum dicts, all sharing one x-axis. Every
            spectrum in *spectra* gets a prediction; only the ones with
            an entry in *y_by_key* are used to fit/cross-validate.
        y_by_key : dict {spectrum_key(spectrum): value}. Regression:
            value is a float. Classification: value is a class label
            (any hashable, typically str). Spectra with no entry here
            (or an entry that is None/empty) are prediction-only.
        mode : MODE_REGRESSION or MODE_CLASSIFICATION.
        n_components : int or None — None means auto-select via
            cross-validation (see module docstring); an int forces that
            exact number of components (still cross-validated for the
            diagnostic curve, just not used to pick the final model).
        autoscale_x : bool — standardize each wavelength channel to unit
            variance before fitting (PLSRegression always mean-centers
            internally regardless of this flag; this additionally scales,
            which matters a lot when Raman/CD intensities span very
            different ranges across the spectral window).
        cv_folds : int or None — None means auto (leave-one-out for
            small calibration sets, DEFAULT_CV_FOLDS-fold otherwise).
        max_components : safety cap on how many components the
            cross-validation curve searches.

        Returns
        -------
        dict — see the large comment block near the return statement for
        every key, since there are a lot of them (this is the richest
        result dict of any analysis tool in the app, by necessity: a
        calibration model isn't just one number).

        Raises
        ------
        ValueError — fewer than the minimum usable calibration samples,
        spectra not sharing one x-axis, classification with fewer than 2
        distinct classes, etc.
        """
        if len(spectra) < 2:
            raise ValueError("Select at least 2 spectra.")

        x_ref = np.asarray(spectra[0]['x_scale'], dtype=float)
        for s in spectra[1:]:
            if not axes_match(x_ref, np.asarray(s.get('x_scale', []), dtype=float)):
                raise ValueError(
                    "All selected spectra must share the same x-axis. Use the "
                    "Data Range operation with linearisation first."
                )

        # Split into calibration (has a y-value) vs prediction-only.
        cal_idx, pred_only_idx = [], []
        for i, s in enumerate(spectra):
            key = spectrum_key(s)
            val = y_by_key.get(key)
            if val is None or (isinstance(val, str) and not val.strip()):
                pred_only_idx.append(i)
            else:
                cal_idx.append(i)

        min_cal = 4 if mode == MODE_REGRESSION else 4
        if len(cal_idx) < min_cal:
            raise ValueError(
                f"Need at least {min_cal} calibration spectra (with a value entered) — "
                f"only {len(cal_idx)} were provided. Prediction-only spectra (left blank) "
                "don't count toward this."
            )

        X_full = np.vstack([np.asarray(s['y_scale'], dtype=float) for s in spectra])
        X_cal = X_full[cal_idx]

        if mode == MODE_REGRESSION:
            try:
                y_cal = np.array([float(y_by_key[spectrum_key(spectra[i])]) for i in cal_idx])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"All calibration values must be numbers for PLS Regression: {exc}")
            class_labels = None
            Y_cal = y_cal.reshape(-1, 1)
        elif mode == MODE_CLASSIFICATION:
            y_cal = np.array([str(y_by_key[spectrum_key(spectra[i])]) for i in cal_idx])
            class_labels = sorted(set(y_cal))
            if len(class_labels) < 2:
                raise ValueError(
                    f"PLS-DA needs at least 2 distinct classes among the calibration "
                    f"values — found {len(class_labels)}."
                )
            class_index = {c: j for j, c in enumerate(class_labels)}
            Y_cal = np.zeros((len(y_cal), len(class_labels)))
            for i, label in enumerate(y_cal):
                Y_cal[i, class_index[label]] = 1.0
        else:
            raise ValueError(f"Unknown mode: {mode!r}")

        n_cal, n_features = X_cal.shape
        max_components = max(1, min(max_components, n_cal - 1, n_features))

        if progress_callback:
            progress_callback(0, 4, "Standardizing…")

        x_mean = X_cal.mean(axis=0)
        x_std = X_cal.std(axis=0)
        x_std_safe = np.where(x_std > 0, x_std, 1.0)

        def _scale(X):
            if not autoscale_x:
                return X
            return (X - x_mean) / x_std_safe

        X_cal_s = _scale(X_cal)

        # ------------------------------------------------------------------
        # Cross-validation curve: score at every candidate component count.
        # ------------------------------------------------------------------
        if progress_callback:
            progress_callback(1, 4, "Cross-validating components…")

        use_loo = cv_folds is None and n_cal <= LOO_THRESHOLD
        if use_loo:
            splitter = LeaveOneOut()
        else:
            k = cv_folds or DEFAULT_CV_FOLDS
            k = max(2, min(k, n_cal))
            splitter = KFold(n_splits=k, shuffle=True, random_state=42)

        cv_scores = []  # one entry per candidate n_components
        for n_comp in range(1, max_components + 1):
            y_true_all, y_pred_all = [], []
            for train_i, test_i in splitter.split(X_cal_s):
                if len(train_i) <= n_comp:
                    continue
                model = PLSRegression(n_components=n_comp)
                model.fit(X_cal_s[train_i], Y_cal[train_i])
                pred = model.predict(X_cal_s[test_i])
                y_true_all.append(Y_cal[test_i])
                y_pred_all.append(pred)
            if not y_true_all:
                cv_scores.append(np.nan)
                continue
            y_true_all = np.vstack(y_true_all)
            y_pred_all = np.vstack(y_pred_all)
            if mode == MODE_REGRESSION:
                score = float(np.sqrt(mean_squared_error(y_true_all, y_pred_all)))
            else:
                pred_class = np.argmax(y_pred_all, axis=1)
                true_class = np.argmax(y_true_all, axis=1)
                score = float(np.mean(pred_class == true_class))
            cv_scores.append(score)

        cv_scores = np.array(cv_scores)
        components_tried = np.arange(1, max_components + 1)

        if n_components is not None:
            chosen_n = int(max(1, min(n_components, max_components)))
        else:
            chosen_n = self._select_parsimonious_n(components_tried, cv_scores, mode)

        # ------------------------------------------------------------------
        # Final model, fit on the full calibration set.
        # ------------------------------------------------------------------
        if progress_callback:
            progress_callback(2, 4, f"Fitting final model ({chosen_n} components)…")

        final_model = PLSRegression(n_components=chosen_n)
        final_model.fit(X_cal_s, Y_cal)

        Y_cal_pred = final_model.predict(X_cal_s)

        if mode == MODE_REGRESSION:
            rmsec = float(np.sqrt(mean_squared_error(Y_cal, Y_cal_pred)))
            r2_cal = float(r2_score(Y_cal, Y_cal_pred))
            idx_at_chosen = int(np.where(components_tried == chosen_n)[0][0])
            rmsecv = float(cv_scores[idx_at_chosen]) if not np.isnan(cv_scores[idx_at_chosen]) else None
            cal_accuracy = cv_accuracy = None
            confusion = None
        else:
            cal_pred_class_idx = np.argmax(Y_cal_pred, axis=1)
            cal_true_class_idx = np.argmax(Y_cal, axis=1)
            cal_accuracy = float(np.mean(cal_pred_class_idx == cal_true_class_idx))
            idx_at_chosen = int(np.where(components_tried == chosen_n)[0][0])
            cv_accuracy = float(cv_scores[idx_at_chosen]) if not np.isnan(cv_scores[idx_at_chosen]) else None
            confusion = confusion_matrix(cal_true_class_idx, cal_pred_class_idx,
                                          labels=list(range(len(class_labels)))).tolist()
            rmsec = rmsecv = r2_cal = None

        # ------------------------------------------------------------------
        # VIP scores + regression coefficients (per-wavelength diagnostics).
        # ------------------------------------------------------------------
        if progress_callback:
            progress_callback(3, 4, "Computing diagnostics…")

        vip = self._compute_vip(final_model)
        # coef_ is in the SCALED-X space; report the effective per-wavelength
        # coefficient in ORIGINAL x_scale units so it's directly interpretable
        # against the spectrum's own axis (divide out the standardization).
        coef_raw = np.asarray(final_model.coef_)
        if coef_raw.ndim == 1:
            coef_raw = coef_raw.reshape(1, -1)
        elif coef_raw.shape[0] == n_features:
            coef_raw = coef_raw.T
        coef = coef_raw / x_std_safe if autoscale_x else coef_raw

        # ------------------------------------------------------------------
        # Predictions for EVERY spectrum handed in (calibration + prediction-only).
        # ------------------------------------------------------------------
        X_all_s = _scale(X_full)
        Y_all_pred = final_model.predict(X_all_s)

        predictions = []
        for i, s in enumerate(spectra):
            key = spectrum_key(s)
            is_calibration = i in cal_idx
            entry = {
                'label': s.get('label', '?'),
                'is_calibration': is_calibration,
            }
            if mode == MODE_REGRESSION:
                entry['predicted'] = float(Y_all_pred[i, 0])
                entry['actual'] = float(y_by_key[key]) if is_calibration else None
                entry['residual'] = (entry['actual'] - entry['predicted']) if is_calibration else None
            else:
                probs = Y_all_pred[i]
                best = int(np.argmax(probs))
                entry['predicted_class'] = class_labels[best]
                entry['class_scores'] = {class_labels[j]: float(probs[j]) for j in range(len(class_labels))}
                entry['actual_class'] = str(y_by_key[key]) if is_calibration else None
                entry['correct'] = (entry['actual_class'] == entry['predicted_class']) if is_calibration else None
            predictions.append(entry)

        if progress_callback:
            progress_callback(4, 4, "Done")

        return {
            'mode': mode,
            'x_scale': x_ref,
            'n_calibration': n_cal,
            'n_prediction_only': len(pred_only_idx),
            'n_features': n_features,
            'class_labels': class_labels,
            'max_components': max_components,
            'components_tried': components_tried.tolist(),
            'cv_scores': cv_scores.tolist(),
            'cv_method': 'leave-one-out' if use_loo else f'{splitter.get_n_splits()}-fold',
            'chosen_n_components': chosen_n,
            'autoscale_x': autoscale_x,
            'rmsec': rmsec,
            'rmsecv': rmsecv,
            'r2_calibration': r2_cal,
            'cal_accuracy': cal_accuracy,
            'cv_accuracy': cv_accuracy,
            'confusion_matrix': confusion,
            'vip': vip.tolist() if vip is not None else None,
            'coefficients': coef.tolist(),
            'x_scores': final_model.x_scores_.tolist(),
            'cal_indices': cal_idx,
            'predictions': predictions,
            'model': final_model,
        }

    @staticmethod
    def _select_parsimonious_n(components_tried, cv_scores, mode):
        """Pick the number of components automatically from the
        cross-validation curve — but the SIMPLEST model that's
        essentially as good as the best one, not necessarily the bare
        numerical minimum/maximum.

        With real (noisy) data the CV curve is very often almost flat
        past some point — component 3 might score 0.1807 and component
        9 might score 0.1799, a difference entirely within CV noise, not
        a real improvement. Blindly taking the exact minimum in that
        case picks an arbitrarily larger, harder-to-interpret model for
        no real accuracy gain (confirmed directly against synthetic
        data with a known single-component ground truth: greedy argmin
        picked 5 components when 1-2 were already essentially optimal).
        Standard chemometrics practice (the "one-standard-error"-style
        rule) is to prefer the smallest model within a small tolerance
        of the best score, which this implements with a fixed,
        conservative tolerance rather than requiring per-fold variance
        tracking: 2% relative for RMSECV (regression), 1 percentage
        point absolute for CV accuracy (classification, where relative
        tolerance is a poor fit since scores are bounded in [0, 1]).
        """
        valid = ~np.isnan(cv_scores)
        if not valid.any():
            return 1

        valid_components = components_tried[valid]
        valid_scores = cv_scores[valid]

        if mode == MODE_REGRESSION:
            best_score = float(np.min(valid_scores))
            tolerance = best_score * 1.02
            within_tolerance = valid_scores <= tolerance
        else:
            best_score = float(np.max(valid_scores))
            tolerance = best_score - 0.01
            within_tolerance = valid_scores >= tolerance

        return int(np.min(valid_components[within_tolerance]))

    @staticmethod
    def _compute_vip(model):
        """Standard VIP (Variable Importance in Projection) formula
        (Wold et al.) from a fitted sklearn PLSRegression. Returns None
        (rather than raising) if the model's internal array shapes don't
        line up as expected for any reason — this is a secondary
        diagnostic, not worth failing the whole analysis over."""
        try:
            t = np.asarray(model.x_scores_)     # (n_samples, h)
            w = np.asarray(model.x_weights_)    # (n_features, h)
            q = np.asarray(model.y_loadings_)   # (n_targets, h) — sklearn's documented shape
            if q.shape[1] != t.shape[1] and q.shape[0] == t.shape[1]:
                # Defensive: some scikit-learn versions have shipped this
                # transposed relative to the documented shape — detect and
                # correct rather than assume either layout blindly.
                q = q.T
            p, h = w.shape
            s = np.diag(t.T @ t @ q.T @ q).reshape(h, -1)
            total_s = np.sum(s)
            if total_s <= 0:
                return None
            vips = np.zeros(p)
            for j in range(p):
                weight = np.array([(w[j, a] / np.linalg.norm(w[:, a])) ** 2 for a in range(h)])
                vips[j] = np.sqrt(p * float(s.flatten() @ weight) / total_s)
            return vips
        except Exception as exc:
            logger.debug("VIP computation skipped (%s)", exc)
            return None
