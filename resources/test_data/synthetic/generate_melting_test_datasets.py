"""
generate_melting_test_datasets.py

Generates 6 synthetic spectral workbooks for testing the Melting Curve
Analysis tool: 1, 2, and 3 thermal transitions, each in a "clean" and
"noisy" variant. Matches the existing SYNTHETIC_TEST_DATASETS convention
in src/views/main_window.py -- a 'Spectra' sheet (imported by default)
plus an 'Info' sheet holding the known ground truth.

Physical model
--------------
Each dataset simulates a genuinely wavelength-dependent spectral series
(absorption- or CD-like -- bands can be positive or negative), NOT a
single fixed band that just scales up and down with temperature. This
matters: a real multi-chromophore melting experiment has some
wavelengths where the signal changes a lot with the transition, and
others -- isosbestic points -- where it barely changes at all, because
different parts of the molecule (or different transitions) contribute
oppositely-signed changes that happen to cancel there. The previous
version of this generator built every spectrum as ONE fixed Gaussian
band multiplied by a single scalar amplitude A(T) -- mathematically
rank-1 (confirmed by SVD), meaning literally any extraction wavelength
reproduced the identical normalized melting curve. That is not
representative of real data, where the choice of extraction wavelength
genuinely matters.

Here, each transition i gets its own characteristic wavelength-dependent
DIFFERENCE spectrum dS_i(lambda) -- shaped like the derivative of a
Gaussian (a positive lobe and a negative lobe flanking a zero-crossing
at the transition's own "center" wavelength), the same qualitative shape
a real red/blue-shifting absorption or CD band produces. That zero
crossing is an exact isosbestic point for that transition: extracting
right there, the transition contributes nothing to the extracted curve
at all, regardless of how far along it is. The overall simulated
spectrum is:

    Signal(lambda, T) = Baseline(lambda) + drift*(T - T_ref)
                         + sum_i [ f_i(T) * dS_i(lambda) ]

where f_i(T) is the same two-state van't Hoff fraction (0 at low T, 1 at
high T) the previous generator used for each transition -- unchanged --
and Baseline(lambda) is a smooth, always-present background shape.
Because each transition contributes its own independent rank-1 term
(baseline is another rank-1 term), the overall spectral matrix has rank
1 + N_transitions -- SVD of a 2-transition dataset should show 3
significant components, not 1 -- which is a much more realistic
structure to test signal decomposition against.

A correct baseline correction + Arrhenius analysis in the actual tool
should still recover deltaH/deltaS/Tm close to (not pixel-identical to,
for the same reasons as before -- the tool's own sigmoid fit uses a
T-linear logistic/erf approximation, while the true model here and the
tool's separate Arrhenius transform are both the rigorous 1/T-linearized
van't Hoff form) the true values recorded in the Info sheet -- but ONLY
once you extract at a wavelength where that transition actually has
signal (not at, or very near, its own isosbestic point).
"""
import numpy as np
import pandas as pd

R = 8.31446261815324  # J/(mol*K)

WAVELENGTHS = np.arange(200, 401, 2.0)   # nm
TEMPERATURES = np.round(np.linspace(5, 95, 40), 2)  # degrees C

# Smooth, always-present background shape (present regardless of T) --
# roughly UV-like: higher near short wavelengths, decaying with a couple
# of gentle broad humps further out. Deliberately not perfectly smooth/
# monotonic, so it looks like a real background rather than a bare
# exponential.
def baseline_spectrum(wl):
    return (0.22
           + 0.55 * np.exp(-(wl - 205) / 35.0).clip(0, None)
           + 0.05 * np.exp(-((wl - 320) ** 2) / (2 * 45.0 ** 2)))


# Small uniform linear-in-temperature drift, independent of wavelength --
# representative of e.g. general instrument/solvent drift, and keeps the
# tool's own linear baseline-region fitting meaningfully exercised.
DRIFT_PER_DEGREE = 0.0009
T_REF = 50.0


def vant_hoff_fraction(temps_c, tm_c, dH):
    """f_i(T): 0 at low T, 1 at high T, two-state van't Hoff, dS chosen
    so K=1 (f=0.5) exactly at Tm."""
    T_K = np.asarray(temps_c, dtype=float) + 273.15
    Tm_K = tm_c + 273.15
    dS = dH / Tm_K
    lnK = -dH / R * (1.0 / T_K) + dS / R
    K = np.exp(lnK)
    return K / (1 + K)


def difference_spectrum(wl, center, width, amplitude):
    """A derivative-of-Gaussian shaped difference spectrum: an exact
    zero-crossing (isosbestic point) at `center`, with a positive lobe
    on one side and a negative lobe on the other -- the same
    qualitative shape a real red/blue-shifted absorption or CD band's
    difference spectrum has. `amplitude` can be negative to flip which
    side is positive."""
    z = (np.asarray(wl, dtype=float) - center) / width
    return amplitude * z * np.exp(-z ** 2 / 2.0)


def build_curve(temps_c, transitions):
    """transitions: list of dicts with 'tm_c', 'dH', 'factor' (unused
    here beyond bookkeeping -- 'factor' only matters for the OLD
    single-wavelength rank-1 model; here each transition's own spectral
    weight is entirely carried by its difference_spectrum amplitude, so
    this returns the simple unweighted sum of individual two-state
    fractions, useful only as an "all transitions equally" ground-truth
    reference curve in the Ground_truth sheet, not anything the tool
    itself sees directly.). Returns average of each transition's own
    0-1 fraction, for the Ground_truth sheet reference only."""
    fs = [vant_hoff_fraction(temps_c, t['tm_c'], t['dH']) for t in transitions]
    return np.mean(fs, axis=0)


def build_spectra_matrix(temps_c, wl, transitions, noise_sigma=0.0, seed=None):
    """Returns (n_temps, n_wl) matrix of simulated signal."""
    base = baseline_spectrum(wl)[None, :]                                    # (1, n_wl)
    drift = (DRIFT_PER_DEGREE * (np.asarray(temps_c) - T_REF))[:, None]      # (n_temps, 1)
    signal = np.tile(base, (len(temps_c), 1)) + drift

    for t in transitions:
        f_i = vant_hoff_fraction(temps_c, t['tm_c'], t['dH'])[:, None]       # (n_temps, 1)
        dS_i = difference_spectrum(wl, t['center'], t['width'], t['amplitude'])[None, :]  # (1, n_wl)
        signal = signal + f_i * dS_i

    if noise_sigma > 0:
        rng = np.random.default_rng(seed)
        signal = signal + rng.normal(0, noise_sigma, size=signal.shape)
    return signal


def find_isosbestic_and_best_wavelengths(wl, transitions):
    """For each transition, its own difference-spectrum zero-crossing
    (an exact isosbestic point for THAT transition, though other
    transitions may still contribute signal there) is just its 'center'.
    The wavelength with the single strongest total |signal change|
    across the full T range is a good default extraction point -- found
    numerically by evaluating the combined curve's peak-to-trough span
    at every wavelength, capturing constructive/destructive overlap
    between transitions' difference spectra rather than assuming either."""
    span_per_wl = np.zeros_like(wl)
    total_signal = build_spectra_matrix(TEMPERATURES, wl, transitions, noise_sigma=0.0)
    span_per_wl = total_signal.max(axis=0) - total_signal.min(axis=0)
    best_idx = int(np.argmax(span_per_wl))
    isosbestic_points = [round(t['center'], 1) for t in transitions]
    return round(float(wl[best_idx]), 1), isosbestic_points


def build_workbook(path, transitions, noise_sigma, seed, description):
    signal = build_spectra_matrix(TEMPERATURES, WAVELENGTHS, transitions,
                                  noise_sigma=noise_sigma, seed=seed)
    best_x, isosbestic = find_isosbestic_and_best_wavelengths(WAVELENGTHS, transitions)

    spectra_data = {"Wavelength_nm": WAVELENGTHS}
    for i, t in enumerate(TEMPERATURES):
        col = f"T_{t:05.2f}"
        spectra_data[col] = signal[i, :]
    spectra_df = pd.DataFrame(spectra_data)

    info_rows = [
        {"Field": "Description", "Value": description},
        {"Field": "Recommended extraction X (nm)", "Value": best_x},
        {"Field": "Isosbestic point(s) to avoid (nm)", "Value": ", ".join(str(v) for v in isosbestic)},
        {"Field": "Temperature range (C)", "Value": f"{TEMPERATURES.min()}-{TEMPERATURES.max()}"},
        {"Field": "N temperature points", "Value": len(TEMPERATURES)},
        {"Field": "Noise sigma (signal units)", "Value": noise_sigma},
        {"Field": "N transitions", "Value": len(transitions)},
    ]
    for i, t in enumerate(transitions, start=1):
        dS = t['dH'] / (t['tm_c'] + 273.15)
        info_rows.append({"Field": f"Transition {i}: Tm (C)", "Value": round(t['tm_c'], 2)})
        info_rows.append({"Field": f"Transition {i}: deltaH (kJ/mol)", "Value": round(t['dH'] / 1000, 2)})
        info_rows.append({"Field": f"Transition {i}: deltaS (J/mol/K)", "Value": round(dS, 2)})
        info_rows.append({"Field": f"Transition {i}: factor", "Value": round(1.0 / len(transitions), 3)})
        info_rows.append({"Field": f"Transition {i}: difference-spectrum center (nm)", "Value": t['center']})
        info_rows.append({"Field": f"Transition {i}: difference-spectrum amplitude", "Value": t['amplitude']})
    info_df = pd.DataFrame(info_rows)

    ground_truth_df = pd.DataFrame({
        "Temperature_C": TEMPERATURES,
        "True_average_fraction_0to1": build_curve(TEMPERATURES, transitions),
        "True_signal_at_recommended_X": signal[:, int(np.argmin(np.abs(WAVELENGTHS - best_x)))],
    })

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        spectra_df.to_excel(writer, sheet_name="Spectra", index=False)
        info_df.to_excel(writer, sheet_name="Info", index=False)
        ground_truth_df.to_excel(writer, sheet_name="Ground_truth", index=False)


DATASETS = [
    # (filename, transitions, description)
    ("melting_1trans_clean.xlsx",
     [{'tm_c': 45.0, 'dH': 220_000, 'center': 275.0, 'width': 30.0, 'amplitude': 0.55}],
     "Single two-state thermal transition (Tm=45C, dH=+220 kJ/mol), clean (no noise). "
     "Wavelength-dependent spectrum with a genuine isosbestic point at 275 nm."),
    ("melting_1trans_noisy.xlsx",
     [{'tm_c': 45.0, 'dH': 220_000, 'center': 275.0, 'width': 30.0, 'amplitude': 0.55}],
     "Single two-state thermal transition (Tm=45C, dH=+220 kJ/mol), with added noise. "
     "Wavelength-dependent spectrum with a genuine isosbestic point at 275 nm."),
    ("melting_2trans_clean.xlsx",
     [{'tm_c': 35.0, 'dH': 180_000, 'center': 260.0, 'width': 35.0, 'amplitude': 0.50},
      {'tm_c': 65.0, 'dH': 260_000, 'center': 315.0, 'width': 35.0, 'amplitude': -0.45}],
     "Two independent thermal transitions (Tm=35C/65C), clean (no noise). "
     "Each transition has its own characteristic wavelength region and isosbestic point "
     "(260 nm and 315 nm) — extracting near one transition's isosbestic point shows "
     "mostly the OTHER transition, since the bands overlap enough for real cross-talk."),
    ("melting_2trans_noisy.xlsx",
     [{'tm_c': 35.0, 'dH': 180_000, 'center': 260.0, 'width': 35.0, 'amplitude': 0.50},
      {'tm_c': 65.0, 'dH': 260_000, 'center': 315.0, 'width': 35.0, 'amplitude': -0.45}],
     "Two independent thermal transitions (Tm=35C/65C), with added noise. "
     "Each transition has its own characteristic wavelength region and isosbestic point "
     "(260 nm and 315 nm) — extracting near one transition's isosbestic point shows "
     "mostly the OTHER transition, since the bands overlap enough for real cross-talk."),
    ("melting_3trans_clean.xlsx",
     [{'tm_c': 30.0, 'dH': 150_000, 'center': 235.0, 'width': 35.0, 'amplitude': 0.45},
      {'tm_c': 55.0, 'dH': 220_000, 'center': 290.0, 'width': 35.0, 'amplitude': -0.40},
      {'tm_c': 78.0, 'dH': 300_000, 'center': 345.0, 'width': 35.0, 'amplitude': 0.50}],
     "Three independent thermal transitions (Tm=30C/55C/78C), clean (no noise). "
     "Each transition has its own characteristic wavelength region and isosbestic point "
     "(235, 290, 345 nm), with meaningful overlap between neighbors."),
    ("melting_3trans_noisy.xlsx",
     [{'tm_c': 30.0, 'dH': 150_000, 'center': 235.0, 'width': 35.0, 'amplitude': 0.45},
      {'tm_c': 55.0, 'dH': 220_000, 'center': 290.0, 'width': 35.0, 'amplitude': -0.40},
      {'tm_c': 78.0, 'dH': 300_000, 'center': 345.0, 'width': 35.0, 'amplitude': 0.50}],
     "Three independent thermal transitions (Tm=30C/55C/78C), with added noise. "
     "Each transition has its own characteristic wavelength region and isosbestic point "
     "(235, 290, 345 nm), with meaningful overlap between neighbors."),
]

NOISE_SIGMA = 0.006  # signal units, comparable magnitude to the previous generator


def main(out_dir):
    import os
    os.makedirs(out_dir, exist_ok=True)
    for i, (fname, transitions, description) in enumerate(DATASETS):
        noise = NOISE_SIGMA if "noisy" in fname else 0.0
        path = os.path.join(out_dir, fname)
        build_workbook(path, transitions, noise_sigma=noise, seed=1000 + i, description=description)
        print(f"wrote {path}")


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    main(out)
