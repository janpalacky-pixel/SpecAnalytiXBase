"""
generate_som_test_datasets.py

Generates 2 synthetic spectral workbooks for testing / demonstrating the
Self-Organizing Map (SOM) tool: a Raman-like dataset (sharp, all-positive
fingerprint bands) and a UV/Vis absorption-like dataset (broad, overlapping
electronic bands) -- two different "textures" a SOM has to organize.

Matches the existing SYNTHETIC_TEST_DATASETS convention in
src/views/main_window.py -- first sheet is always 'Spectra' (what gets
imported), followed by a 'Ground_truth' sheet (known class + a continuous
"purity" parameter per spectrum, for checking the trained map against) and
an 'Info' sheet with the story and a step-by-step walkthrough.

Design intent (why this shape, not just N random clusters):
  - Several (5-6) clearly distinct classes, each defined by its own
    characteristic band(s) -- so the SOM's Hit Map / U-Matrix should
    organize into that many separated regions.
  - Within each class, a continuous "purity" parameter (0.55-1.0) scales
    the class's defining bands and blends in a bit of a shared "Mixed/
    Reference" signature at low purity -- so each region isn't just a
    tight dot, it's a small gradient, and low-purity samples drift toward
    the Mixed/Reference region. This is the property a SOM shows off that
    plain clustering doesn't: topology -- neighbouring nodes correspond to
    genuinely similar spectra, not just "same bucket".
  - One extra "Mixed/Reference" class made of a random blend of every
    other class's bands at reduced amplitude -- with no fixed identity of
    its own, it should land in the middle of the map, touching several of
    the pure-class regions, which is a nice visible illustration of
    topology preservation.
  - A biologically real pair of bands is called out in each dataset's Info
    sheet for the SOM Component Plane's "Ratio of two ranges (A/B)" mode
    and for "Custom features" training, so those newer SOM dialog features
    have something concrete to try.
"""
import numpy as np
import openpyxl
from openpyxl.styles import Font, PatternFill

HEADER_FILL = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
BOLD = Font(bold=True)


def gaussian(x, center, width, amp):
    return amp * np.exp(-((x - center) ** 2) / (2 * width ** 2))


def _write_spectra_sheet(wb, x_label, x, all_labels, all_spectra):
    ws = wb.active
    ws.title = "Spectra"
    header = [x_label] + all_labels
    ws.append(header)
    for cell in ws[1]:
        cell.font = BOLD
        cell.fill = HEADER_FILL
    for i in range(len(x)):
        row = [float(x[i])] + [float(s[i]) for s in all_spectra]
        ws.append(row)
    ws.column_dimensions["A"].width = 16
    return ws


def _write_ground_truth_sheet(wb, rows):
    """rows: list of (label, class_name, purity_or_blend_note)."""
    ws = wb.create_sheet("Ground_truth")
    ws.append(["Spectrum", "True_class", "Purity_or_blend"])
    for cell in ws[1]:
        cell.font = BOLD
        cell.fill = HEADER_FILL
    for r in rows:
        ws.append(list(r))
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 40
    return ws


def _write_info_sheet(wb, lines, extra_rows):
    ws = wb.create_sheet("Info")
    for text in lines:
        ws.append([text])
    ws["A1"].font = BOLD
    ws.column_dimensions["A"].width = 96
    for row in extra_rows:
        ws.append(list(row))
    return ws


# ======================================================================
# Dataset 1 -- Raman-like: sharp, all-positive fingerprint bands
# ======================================================================

def build_raman_dataset(path, seed=101, n_per_class=40):
    rng = np.random.default_rng(seed)
    x = np.linspace(400, 1800, 400)  # cm-1

    # Each class's defining bands: list of (center, width, base_amp).
    CLASS_BANDS = {
        "protein":      [(1004, 6, 1.00), (1655, 25, 0.80), (1340, 12, 0.30)],
        "lipid":        [(1440, 12, 1.00), (1300, 15, 0.60), (1660, 20, 0.45)],
        "nucleicacid":  [(785, 8, 1.00), (1090, 10, 0.70), (1580, 12, 0.50)],
        "carbohydrate": [(850, 10, 0.90), (1125, 12, 0.80), (480, 10, 0.60)],
        "silica":       [(490, 15, 1.00), (800, 10, 0.40), (1080, 20, 0.25)],
    }
    CLASSES = list(CLASS_BANDS.keys())
    # Weak background band shared by every spectrum (matrix Raman).
    SHARED_BAND = (1450, 60, 0.15)

    def render(bands, amp_scale, rng):
        y = gaussian(x, *SHARED_BAND[:2], SHARED_BAND[2])
        for center, width, amp in bands:
            jitter_c = center + rng.uniform(-1.5, 1.5)
            jitter_a = amp * amp_scale * rng.uniform(0.95, 1.05)
            y = y + gaussian(x, jitter_c, width, jitter_a)
        return y

    def add_baseline_and_noise(y, rng):
        slope = rng.uniform(-0.00005, 0.00015)
        offset = rng.uniform(0.0, 0.03)
        baseline = offset + slope * (x - x[0])
        noise = rng.normal(0, 0.012, size=x.shape)
        return y + baseline + noise

    labels, spectra, truth_rows = [], [], []

    for cls in CLASSES:
        for i in range(n_per_class):
            purity = rng.uniform(0.55, 1.0)
            y = render(CLASS_BANDS[cls], purity, rng)
            if purity < 1.0:
                # Blend in a faint touch of every OTHER class's bands,
                # scaled by how impure this sample is -- so low-purity
                # samples visibly drift toward the shared "Mixed/
                # Reference" region of the map instead of just being a
                # noisier copy of their own class.
                contam_scale = (1.0 - purity) * 0.35
                for other_cls, other_bands in CLASS_BANDS.items():
                    if other_cls == cls:
                        continue
                    w = rng.uniform(0.3, 1.0)
                    y = y + render(other_bands, contam_scale * w / len(CLASSES), rng)
            y = add_baseline_and_noise(y, rng)
            label = f"{cls}_{i + 1:03d}_p{int(round(purity * 100)):03d}"
            labels.append(label)
            spectra.append(y)
            truth_rows.append((label, cls, f"purity={purity:.2f}"))

    # "Mixed/Reference" class: a random blend of every class's bands at
    # reduced amplitude, no single dominant identity -- should land near
    # the middle of the trained map, touching several pure-class regions.
    n_mixed = n_per_class
    for i in range(n_mixed):
        weights = rng.dirichlet(np.ones(len(CLASSES)))
        y = gaussian(x, *SHARED_BAND[:2], SHARED_BAND[2])
        for cls, w in zip(CLASSES, weights):
            y = y + render(CLASS_BANDS[cls], 0.55 * w * len(CLASSES) / len(CLASSES), rng)
        y = add_baseline_and_noise(y, rng)
        label = f"mixedref_{i + 1:03d}"
        labels.append(label)
        spectra.append(y)
        blend_desc = ", ".join(f"{c}={w:.2f}" for c, w in zip(CLASSES, weights))
        truth_rows.append((label, "mixedref", blend_desc))

    # Shuffle so the imported spectra list isn't trivially sorted by
    # class -- a more honest test of what SOM discovers on its own.
    order = rng.permutation(len(labels))
    labels = [labels[i] for i in order]
    spectra = [spectra[i] for i in order]
    truth_rows = [truth_rows[i] for i in order]

    wb = openpyxl.Workbook()
    _write_spectra_sheet(wb, "Raman_shift_cm-1", x, labels, spectra)
    _write_ground_truth_sheet(wb, truth_rows)

    lines = [
        "Story",
        f"{len(labels)} Raman-like spectra ({len(CLASSES)} biomolecule-signature",
        "classes x %d samples, plus %d 'Mixed/Reference' blend samples) --" % (n_per_class, n_mixed),
        "a fingerprint-region (400-1800 cm-1) illustration for the Self-",
        "Organizing Map (SOM) tool. Each class is defined by its own sharp",
        "characteristic band(s): protein (~1004, ~1655 cm-1), lipid (~1440,",
        "~1300 cm-1), nucleic acid (~785, ~1090, ~1580 cm-1), carbohydrate",
        "(~850, ~1125, ~480 cm-1), and silica/mineral (~490, ~800 cm-1).",
        "",
        "Within each class, a random 'purity' (55-100%) scales that class's",
        "bands and blends in a bit of every other class at low purity, so a",
        "class isn't a single tight dot -- it's a small gradient that drifts",
        "toward the shared Mixed/Reference region as purity drops. That's the",
        "property a SOM shows off that plain clustering doesn't: neighbouring",
        "map nodes correspond to genuinely similar spectra (smooth topology),",
        "not just 'same bucket'. The Mixed/Reference class itself is a random",
        "blend of every class's bands with no fixed identity of its own, so",
        "expect it to land in the middle of the trained map, touching several",
        "of the pure-class regions, rather than forming its own tight island.",
        "",
        "How to use this file",
        "1. File -> Import data -> select this workbook (Spectra sheet).",
        f"2. Select all {len(labels)} imported spectra, open Visualization &",
        "   Analysis -> SOM.",
        "3. Leave 'Full spectrum shape' training mode, try Grid rows/cols",
        "   around 8 x 8, Iterations ~300, then click Run SOM.",
        "4. Hit Map / U-Matrix: look for roughly 6 separated regions with",
        "   the Mixed/Reference samples scattered near the boundaries between",
        "   them rather than forming their own island -- compare node",
        "   membership (click a node, or use the results table) against the",
        "   True_class column on the Ground_truth sheet.",
        "5. Component Plane -> try 'Ratio of two ranges (A/B)' with Band A",
        "   X1/X2 = 1630/1680 (protein Amide I) and Band B X1/X2 = 1420/1460",
        "   (lipid CH2 bending) -- the resulting plane should track where",
        "   protein- vs lipid-rich spectra mapped.",
        "6. Try Training Data -> Custom features with rows such as",
        "   'AmideI' (Mean, 1630-1680), 'Lipid_CH2' (Mean, 1420-1460),",
        "   'Phosphate' (Mean, 770-800) and re-run -- the map should",
        "   reorganize around those three numbers instead of full shape,",
        "   and still separate the classes.",
        "7. Sample Map -> color by 'Distance to BMU' to see which spectra",
        "   sit furthest from their node's prototype (typically the",
        "   lowest-purity samples of each class).",
        "",
        "Ground truth (for reference; also see the Ground_truth sheet)",
    ]
    extra_rows = [
        ["Classes:", ", ".join(CLASSES + ["mixedref"])],
        ["Samples per class:", n_per_class],
        ["Mixed/Reference samples:", n_mixed],
        ["Total spectra:", len(labels)],
        ["Suggested ratio feature:", "Amide I (1630-1680) / Lipid CH2 (1420-1460)"],
    ]
    _write_info_sheet(wb, lines, extra_rows)

    wb.save(path)
    return labels


# ======================================================================
# Dataset 2 -- UV/Vis absorption-like: broad, overlapping electronic bands
# ======================================================================

def build_uvvis_dataset(path, seed=202, n_per_class=50):
    rng = np.random.default_rng(seed)
    x = np.linspace(220, 500, 280)  # nm

    # Each class's defining band(s): list of (center, width, base_amp).
    CLASS_BANDS = {
        "aromatic":      [(278, 12, 1.00)],
        "conjugated":    [(320, 25, 0.90), (260, 10, 0.30)],
        "chargexfer":    [(400, 40, 0.70)],
        "metaldd":       [(480, 35, 0.35), (300, 20, 0.15)],
    }
    CLASSES = list(CLASS_BANDS.keys())

    def render(bands, amp_scale, rng):
        y = np.zeros_like(x)
        for center, width, amp in bands:
            jitter_c = center + rng.uniform(-4, 4)
            jitter_a = amp * amp_scale * rng.uniform(0.9, 1.1)
            y = y + gaussian(x, jitter_c, width, jitter_a)
        return y

    def scattering_background(rng, strength):
        # Rayleigh-like scattering tail, stronger at low wavelength --
        # realistic turbid-sample baseline, independent of chromophore class.
        return strength * (300.0 / x) ** 4

    def add_noise(y, rng):
        # Heteroscedastic: a bit noisier at low wavelength (lamp intensity
        # falls off there on a real instrument).
        scale = 0.006 + 0.010 * np.exp(-(x - 220) / 80.0)
        return y + rng.normal(0, 1, size=x.shape) * scale

    labels, spectra, truth_rows = [], [], []

    for cls in CLASSES:
        for i in range(n_per_class):
            purity = rng.uniform(0.55, 1.0)
            y = render(CLASS_BANDS[cls], purity, rng)
            if purity < 1.0:
                contam_scale = (1.0 - purity) * 0.30
                for other_cls, other_bands in CLASS_BANDS.items():
                    if other_cls == cls:
                        continue
                    w = rng.uniform(0.3, 1.0)
                    y = y + render(other_bands, contam_scale * w / len(CLASSES), rng)
            y = y + scattering_background(rng, rng.uniform(0.005, 0.02))
            y = add_noise(y, rng)
            label = f"{cls}_{i + 1:03d}_p{int(round(purity * 100)):03d}"
            labels.append(label)
            spectra.append(y)
            truth_rows.append((label, cls, f"purity={purity:.2f}"))

    # "Turbid/scattering" reference class: scattering-dominated, only faint
    # discrete bands -- the UV/Vis analogue of the Raman set's Mixed/
    # Reference class, expected to sit apart from the four chromophore
    # regions (it's defined by an ABSENCE of a strong discrete band, not a
    # blend of them, so unlike the Raman Mixed/Reference class it should
    # form its own distinct region rather than sitting between the others --
    # a deliberate contrast worth noticing on the Hit Map/U-Matrix).
    n_turbid = n_per_class
    for i in range(n_turbid):
        weights = rng.dirichlet(np.ones(len(CLASSES)))
        y = np.zeros_like(x)
        for cls, w in zip(CLASSES, weights):
            y = y + render(CLASS_BANDS[cls], 0.25 * w * len(CLASSES) / len(CLASSES), rng)
        y = y + scattering_background(rng, rng.uniform(0.04, 0.09))
        y = add_noise(y, rng)
        label = f"turbid_{i + 1:03d}"
        labels.append(label)
        spectra.append(y)
        blend_desc = ", ".join(f"{c}={w:.2f}" for c, w in zip(CLASSES, weights))
        truth_rows.append((label, "turbid", blend_desc))

    order = rng.permutation(len(labels))
    labels = [labels[i] for i in order]
    spectra = [spectra[i] for i in order]
    truth_rows = [truth_rows[i] for i in order]

    wb = openpyxl.Workbook()
    _write_spectra_sheet(wb, "Wavelength_nm", x, labels, spectra)
    _write_ground_truth_sheet(wb, truth_rows)

    lines = [
        "Story",
        f"{len(labels)} UV/Vis absorption-like spectra ({len(CLASSES)} chromophore",
        f"classes x {n_per_class} samples, plus {n_turbid} 'turbid/scattering'",
        "samples) -- a broad-band (220-500 nm) illustration for the Self-",
        "Organizing Map (SOM) tool, deliberately a different 'texture' than",
        "the sharp-fingerprint Raman demo (som_raman_multiclass_demo.xlsx):",
        "few, broad, overlapping electronic bands instead of many sharp",
        "vibrational ones. Classes: aromatic (~278 nm), extended conjugation",
        "(~320 nm + 260 nm shoulder), charge-transfer complex (~400 nm,",
        "broad), and weak metal d-d transition (~480 nm, broad and weak).",
        "",
        "As in the Raman demo, each class has a random 'purity' (55-100%)",
        "and blends in a bit of the other classes at low purity, so classes",
        "form gradients rather than tight dots. The extra 'turbid' class is",
        "scattering-dominated (a realistic 1/wavelength^4-ish Rayleigh tail,",
        "stronger and noisier than the other classes) with only faint",
        "discrete bands -- unlike the Raman demo's Mixed/Reference class",
        "(defined by blending everything together, so it sits BETWEEN the",
        "other regions), 'turbid' is defined by the ABSENCE of a strong",
        "discrete band, so on the trained map expect it to form its OWN",
        "separate region rather than sitting between the four chromophore",
        "clusters -- a useful contrast between the two demo files.",
        "",
        "How to use this file",
        "1. File -> Import data -> select this workbook (Spectra sheet).",
        f"2. Select all {len(labels)} imported spectra, open Visualization &",
        "   Analysis -> SOM.",
        "3. Leave 'Full spectrum shape' training mode, try Grid rows/cols",
        "   around 8 x 8, Iterations ~300, then click Run SOM.",
        "4. Hit Map / U-Matrix: look for the 4 chromophore regions plus a",
        "   separate 'turbid' region -- compare node membership against the",
        "   True_class column on the Ground_truth sheet.",
        "5. Component Plane -> try 'Ratio of two ranges (A/B)' with Band A",
        "   X1/X2 = 390/410 (charge-transfer) and Band B X1/X2 = 268/288",
        "   (aromatic) to see where charge-transfer-dominated spectra mapped.",
        "6. Try Training Data -> Custom features with rows such as",
        "   'Aromatic' (Mean, 268-288), 'Conjugated' (Mean, 310-330),",
        "   'ChargeTransfer' (Mean, 390-410) and re-run to compare training",
        "   on full shape vs. these three numbers.",
        "",
        "Ground truth (for reference; also see the Ground_truth sheet)",
    ]
    extra_rows = [
        ["Classes:", ", ".join(CLASSES + ["turbid"])],
        ["Samples per class:", n_per_class],
        ["Turbid/scattering samples:", n_turbid],
        ["Total spectra:", len(labels)],
        ["Suggested ratio feature:", "Charge-transfer (390-410) / Aromatic (268-288)"],
    ]
    _write_info_sheet(wb, lines, extra_rows)

    wb.save(path)
    return labels


if __name__ == "__main__":
    import os
    out_dir = os.path.dirname(os.path.abspath(__file__))

    p1 = os.path.join(out_dir, "som_raman_multiclass_demo.xlsx")
    r1 = build_raman_dataset(p1)
    print("Wrote:", p1, "-", len(r1), "spectra")

    p2 = os.path.join(out_dir, "som_uvvis_multiclass_demo.xlsx")
    r2 = build_uvvis_dataset(p2)
    print("Wrote:", p2, "-", len(r2), "spectra")
