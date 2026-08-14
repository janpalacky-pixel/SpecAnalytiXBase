"""
generate_pls_test_datasets.py

Generates 2 synthetic spectral workbooks for testing / demonstrating the
PLS / PLS-DA tool: one regression example (predict a continuous
concentration from a spectrum) and one classification example (predict
which of two sample types a spectrum belongs to). Matches the existing
SYNTHETIC_TEST_DATASETS convention in src/views/main_window.py -- first
sheet is always 'Spectra' (what gets imported), followed by sheets that
hold the known ground truth for calibration + a held-out "unknown" set
the user can predict and then check.

Both datasets are deliberately NOT solvable by "just read the peak
height at one wavelength" -- each has a second, off-target, un-correlated
source of spectral variation overlapping the informative signal, so a
naive univariate read gives a visibly worse answer than PLS actually
using the whole spectral shape. That's the point of using PLS at all.
"""
import numpy as np
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill

SEED = 42
HEADER_FILL = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
WARN_FILL = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
BOLD = Font(bold=True)


def gaussian(x, center, width, amp):
    return amp * np.exp(-((x - center) ** 2) / (2 * width ** 2))


# ======================================================================
# Dataset 1 -- Regression: protein concentration from UV absorbance
# ======================================================================
def build_regression_dataset(path):
    rng = np.random.default_rng(SEED)
    wl = np.arange(240, 321, 2.0)  # nm, 41 points

    def spectrum(conc, interferent_amp, noise_scale, rng):
        # Protein band near 280 nm (aromatic residues, Beer-Lambert: height
        # scales linearly with concentration) -- this is the signal PLS
        # should learn to read.
        protein = gaussian(wl, 280, 8.0, 0.42 * conc)
        # Off-target, concentration-INDEPENDENT nucleic-acid-like shoulder
        # near 260 nm, amplitude drawn independently per sample -- this is
        # what makes reading a single wavelength unreliable, and why PLS
        # (using the whole shape) out-performs a one-point calibration.
        interferent = gaussian(wl, 260, 10.0, interferent_amp)
        # Smooth scattering-type baseline, unrelated to protein content.
        baseline = 0.05 + 0.10 * np.exp(-(wl - 240) / 60.0)
        noise = rng.normal(0, noise_scale, size=wl.shape)
        return protein + interferent + baseline + noise

    # --- Calibration set: 15 known concentrations, spread 0.1-2.0 mg/mL ---
    cal_conc = np.round(np.linspace(0.10, 2.00, 15), 3)
    cal_labels = [f"cal_{i+1:02d}" for i in range(len(cal_conc))]
    cal_spectra = []
    for c in cal_conc:
        interferent_amp = rng.uniform(0.02, 0.12)
        cal_spectra.append(spectrum(c, interferent_amp, 0.006, rng))

    # --- Unknown set: 5 held-out spectra, true value only in the answer
    #     key sheet, for the user to predict and then self-check ---
    unk_conc_true = np.array([0.35, 1.62, 0.88, 1.15, 0.55])
    unk_labels = ["unknown_A", "unknown_B", "unknown_C", "unknown_D", "unknown_E"]
    unk_spectra = []
    for c in unk_conc_true:
        interferent_amp = rng.uniform(0.02, 0.12)
        unk_spectra.append(spectrum(c, interferent_amp, 0.006, rng))

    all_labels = cal_labels + unk_labels
    all_spectra = cal_spectra + unk_spectra

    wb = openpyxl.Workbook()

    # --- Sheet 1: Spectra (this is the only sheet imported into the app) ---
    ws = wb.active
    ws.title = "Spectra"
    header = ["Wavelength_nm"] + all_labels
    ws.append(header)
    for cell in ws[1]:
        cell.font = BOLD
        cell.fill = HEADER_FILL
    for i, w in enumerate(wl):
        row = [float(w)] + [float(s[i]) for s in all_spectra]
        ws.append(row)
    ws.column_dimensions["A"].width = 14

    # --- Sheet 2: calibration values to type into the PLS table ---
    ws2 = wb.create_sheet("Calibration_values")
    ws2.append(["Spectrum", "Concentration_mg_per_mL"])
    for cell in ws2[1]:
        cell.font = BOLD
        cell.fill = HEADER_FILL
    for lbl, c in zip(cal_labels, cal_conc):
        ws2.append([lbl, float(c)])
    ws2.column_dimensions["A"].width = 14
    ws2.column_dimensions["B"].width = 24

    # --- Sheet 3: answer key for the 5 unknowns (don't peek first!) ---
    ws3 = wb.create_sheet("Answer_key")
    ws3.append(["Do not look at this sheet until after you've run PLS and predicted the unknowns!"])
    ws3["A1"].font = BOLD
    ws3["A1"].fill = WARN_FILL
    ws3.merge_cells("A1:B1")
    ws3.append([])
    ws3.append(["Spectrum", "True_concentration_mg_per_mL"])
    for cell in ws3[3]:
        cell.font = BOLD
        cell.fill = HEADER_FILL
    for lbl, c in zip(unk_labels, unk_conc_true):
        ws3.append([lbl, float(c)])
    ws3.column_dimensions["A"].width = 14
    ws3.column_dimensions["B"].width = 34

    # --- Sheet 4: Info / walkthrough ---
    ws4 = wb.create_sheet("Info")
    lines = [
        ("Story", None),
        ("A lab measures UV absorbance spectra (240-320 nm) of 15 samples with",
         None),
        ("known protein concentration (a calibration series), plus 5 unknown",
         None),
        ("samples whose concentration needs to be PREDICTED from the spectrum",
         None),
        ("alone -- the classic use case for PLS regression.", None),
        ("", None),
        ("Why not just read the peak height at 280 nm directly?", None),
        ("Each spectrum also has a second, unrelated absorbance feature near", None),
        ("260 nm (simulating a nucleic-acid contaminant) whose size varies", None),
        ("randomly and independently of protein concentration. Reading only", None),
        ("one wavelength is thrown off by that; PLS uses the whole spectral", None),
        ("shape and is far more robust to this kind of unrelated interference.", None),
        ("", None),
        ("How to use this file", None),
        ("1. File -> Import data -> select this workbook (Spectra sheet).", None),
        ("2. Select all 20 imported spectra, open Visualization & Analysis ->", None),
        ("   PLS / PLS-DA.", None),
        ("3. Choose 'Regression'. In the calibration table, type in the 15", None),
        ("   Concentration_mg_per_mL values from the Calibration_values sheet", None),
        ("   next to cal_01 .. cal_15. Leave unknown_A .. unknown_E blank.", None),
        ("4. Click Run. The Results table will show predicted concentrations", None),
        ("   for unknown_A .. unknown_E.", None),
        ("5. Compare your predictions against the Answer_key sheet.", None),
        ("", None),
        ("Ground truth (for reference)", None),
    ]
    for text, _ in lines:
        ws4.append([text])
    ws4["A1"].font = BOLD
    ws4.column_dimensions["A"].width = 90
    ws4.append(["Calibration concentrations (mg/mL):", ", ".join(str(c) for c in cal_conc)])
    ws4.append(["True unknown concentrations (mg/mL):", ", ".join(f"{l}={c}" for l, c in zip(unk_labels, unk_conc_true))])
    ws4.append(["Expected PLS result:", "Auto-selection typically picks around 4-5 components (the extra components are needed to partially correct for the unrelated interferent, not because the real signal is complex); RMSECV should land around 0.03 mg/mL; predictions should track the true unknown values closely, though not exactly, due to the added noise/interferent."])

    wb.save(path)
    return cal_labels, cal_conc, unk_labels, unk_conc_true


# ======================================================================
# Dataset 2 -- Classification (PLS-DA): sample type A vs B
# ======================================================================
def build_classification_dataset(path):
    rng = np.random.default_rng(SEED + 1)
    x = np.arange(700, 1501, 10.0)  # cm-1 (Raman-like), 81 points

    def spectrum(cls, rng):
        # Both classes share a band near 1100 cm-1 (present regardless of
        # class) -- a distractor, so classification can't be done from
        # "is there a peak at 1100" alone.
        shared = gaussian(x, 1100, 25, rng.uniform(0.35, 0.45))
        if cls == "A":
            main = gaussian(x, 900, 20, rng.uniform(0.75, 0.95))
            minor = gaussian(x, 1300, 20, rng.uniform(0.10, 0.20))
        else:
            main = gaussian(x, 1300, 20, rng.uniform(0.75, 0.95))
            minor = gaussian(x, 900, 20, rng.uniform(0.10, 0.20))
        noise = rng.normal(0, 0.02, size=x.shape)
        baseline = 0.03
        return shared + main + minor + baseline + noise

    n_per_class = 10
    cal_labels, cal_classes, cal_spectra = [], [], []
    for cls in ("A", "B"):
        for i in range(n_per_class):
            cal_labels.append(f"class{cls}_{i+1:02d}")
            cal_classes.append(cls)
            cal_spectra.append(spectrum(cls, rng))

    unk_true = ["A", "B", "A", "B"]
    unk_labels = [f"unknown_{i+1}" for i in range(len(unk_true))]
    unk_spectra = [spectrum(cls, rng) for cls in unk_true]

    all_labels = cal_labels + unk_labels
    all_spectra = cal_spectra + unk_spectra

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Spectra"
    header = ["Raman_shift_cm-1"] + all_labels
    ws.append(header)
    for cell in ws[1]:
        cell.font = BOLD
        cell.fill = HEADER_FILL
    for i, xv in enumerate(x):
        row = [float(xv)] + [float(s[i]) for s in all_spectra]
        ws.append(row)
    ws.column_dimensions["A"].width = 16

    ws2 = wb.create_sheet("Calibration_values")
    ws2.append(["Spectrum", "Class"])
    for cell in ws2[1]:
        cell.font = BOLD
        cell.fill = HEADER_FILL
    for lbl, cls in zip(cal_labels, cal_classes):
        ws2.append([lbl, cls])
    ws2.column_dimensions["A"].width = 14
    ws2.column_dimensions["B"].width = 10

    ws3 = wb.create_sheet("Answer_key")
    ws3.append(["Do not look at this sheet until after you've run PLS-DA and predicted the unknowns!"])
    ws3["A1"].font = BOLD
    ws3["A1"].fill = WARN_FILL
    ws3.merge_cells("A1:B1")
    ws3.append([])
    ws3.append(["Spectrum", "True_class"])
    for cell in ws3[3]:
        cell.font = BOLD
        cell.fill = HEADER_FILL
    for lbl, cls in zip(unk_labels, unk_true):
        ws3.append([lbl, cls])
    ws3.column_dimensions["A"].width = 14
    ws3.column_dimensions["B"].width = 14

    ws4 = wb.create_sheet("Info")
    lines = [
        "Story",
        "A lab has two known sample types (A and B) that give visibly different",
        "spectra -- 10 reference spectra of each are provided as a calibration",
        "set, plus 4 unknown spectra whose type needs to be PREDICTED -- the",
        "classic use case for PLS-DA (PLS discriminant analysis).",
        "",
        "Why not just check which peak is taller?",
        "Both classes share an unrelated band near 1100 cm-1 that has nothing",
        "to do with class identity, and each class also has a smaller trace of",
        "the OTHER class's characteristic peak. PLS-DA uses the whole spectral",
        "shape rather than a single band, which is much more reliable.",
        "",
        "How to use this file",
        "1. File -> Import data -> select this workbook (Spectra sheet).",
        "2. Select all 24 imported spectra, open Visualization & Analysis ->",
        "   PLS / PLS-DA.",
        "3. Choose 'Classification'. In the calibration table, type 'A' or 'B'",
        "   next to classA_01 .. classA_10 / classB_01 .. classB_10 (see the",
        "   Calibration_values sheet). Leave unknown_1 .. unknown_4 blank.",
        "4. Click Run. The Results table will show the predicted class for",
        "   unknown_1 .. unknown_4.",
        "5. Compare your predictions against the Answer_key sheet.",
        "",
        "Ground truth (for reference)",
    ]
    for text in lines:
        ws4.append([text])
    ws4["A1"].font = BOLD
    ws4.column_dimensions["A"].width = 90
    ws4.append(["True unknown classes:", ", ".join(f"{l}={c}" for l, c in zip(unk_labels, unk_true))])
    ws4.append(["Expected PLS-DA result:", "1-2 components should already separate the classes cleanly; all 4 unknowns should be predicted correctly with high class-probability."])

    wb.save(path)
    return cal_labels, cal_classes, unk_labels, unk_true


if __name__ == "__main__":
    import os
    out_dir = os.path.dirname(os.path.abspath(__file__))
    p1 = os.path.join(out_dir, "pls_regression_protein_concentration_demo.xlsx")
    p2 = os.path.join(out_dir, "pls_da_sample_type_classification_demo.xlsx")
    r = build_regression_dataset(p1)
    c = build_classification_dataset(p2)
    print("Wrote:", p1)
    print("Wrote:", p2)
    print("Regression calibration:", list(zip(r[0], r[1])))
    print("Regression unknowns (true):", list(zip(r[2], r[3])))
    print("Classification calibration classes:", r  and None)
    print("Classification unknowns (true):", list(zip(c[2], c[3])))
