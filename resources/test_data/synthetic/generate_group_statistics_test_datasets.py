"""
generate_group_statistics_test_datasets.py

Three synthetic Raman workbooks for trying Group Statistics (Analysis &
Visualization -> Data Analysis -> Group Statistics). Each has the usual
'Spectra' sheet (what gets imported), an 'Info' sheet (the story, the true
effects and what to try) and a 'Groups' sheet (Spectrum, Group[, Sample])
that Group Statistics loads by itself when it opens with these spectra.

1. group_stats_treatment_demo.xlsx -- three independent groups
   (control / low dose / high dose, 12 spectra each, every spectrum its own
   sample). True effects: the 1655 band grows with dose, the 1585 band
   shifts up by ~1.4 cm-1, the high-dose group varies more; the intensity
   scale (focus) varies from spectrum to spectrum; one control spectrum is an
   outlier. Groups sheet: Spectrum, Group.
2. group_stats_cells_samples_demo.xlsx -- pseudoreplication: wild type vs
   mutant, 3 cells each, 15 pixels per cell. There is NO true difference
   between wild type and mutant, but the cells differ from each other. Tested
   pixel by pixel the groups look "significantly" different; with one value
   per sample (cell) they do not. Groups sheet: Spectrum, Group, Sample.
3. group_stats_paired_demo.xlsx -- paired: 8 samples measured before and
   after heating. The samples differ a lot from each other, heating lowers
   the 1655 band by a small, consistent amount: unpaired tests miss it, the
   paired test finds it. Groups sheet: Spectrum, Group, Sample.
4. group_stats_skewed_demo.xlsx -- skewed (log-normal) values: lipid band
   of 15 control and 15 nitrogen-starved cells. The t-test misses the
   3-fold difference, Mann-Whitney U finds it, and so does the t-test on
   log2(A / B). Groups sheet: Spectrum, Group.
5. group_stats_cell_map_demo.mat -- a Raman map (40 x 30 pixels, WITec
   .mat format) of one cell: cytoplasm (protein) and nucleus (protein +
   DNA bands 785 / 1095 cm-1). Draw ROI regions in the 2D Map and use
   ROI -> Compare ROI regions in Group Statistics. No Groups sheet (the
   regions are the groups).

Run from this folder: python generate_group_statistics_test_datasets.py
"""
import os

import numpy as np
import openpyxl
from openpyxl.styles import Font, PatternFill

HEADER_FILL = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
BOLD = Font(bold=True)
X = np.arange(600.0, 1801.0, 1.0)          # Raman shift, cm-1


def band(x, centre, fwhm, height):
    return height * np.exp(-4 * np.log(2) * ((x - centre) / fwhm) ** 2)


def spectrum(rng, h1655=1.0, c1585=1585.0, scale=1.0, noise=0.01):
    """A cell-like Raman spectrum: phenylalanine 1003, CH2 1450, 1585,
    amide I / C=C 1655, on a sloping background, times an intensity scale."""
    y = (band(X, 1003, 8, 1.0) + band(X, 1450, 28, 1.2)
         + band(X, c1585, 14, 0.5) + band(X, 1655, 30, h1655)
         + 0.25 + 0.0002 * (X - 600))
    return scale * y + rng.normal(0, noise, X.size)


def write(path, labels, rows, info_lines, groups, samples=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Spectra"
    ws.append(["Raman_shift_cm-1"] + labels)
    for cell in ws[1]:
        cell.font = BOLD
        cell.fill = HEADER_FILL
    for i, x in enumerate(X):
        ws.append([float(x)] + [round(float(r[i]), 6) for r in rows])
    ws.column_dimensions["A"].width = 16
    info = wb.create_sheet("Info")
    for text in info_lines:
        info.append([text])
    info["A1"].font = BOLD
    info.column_dimensions["A"].width = 100
    gs = wb.create_sheet("Groups")
    gs.append(["Spectrum", "Group"] + (["Sample"] if samples else []))
    for cell in gs[1]:
        cell.font = BOLD
        cell.fill = HEADER_FILL
    for i, (lab, g) in enumerate(zip(labels, groups)):
        gs.append([lab, g] + ([samples[i]] if samples else []))
    gs.column_dimensions["A"].width = 26
    wb.save(path)


def treatment(path):
    rng = np.random.default_rng(101)
    labels, rows, groups = [], [], []
    for group, h, c, sd in (("control", 0.70, 1585.0, 0.04), ("low dose", 1.00, 1585.6, 0.04),
                            ("high dose", 1.35, 1586.4, 0.16)):
        for i in range(12):
            h_i = rng.normal(h, sd)
            if group == "control" and i == 4:
                h_i = 1.05                                   # the planted outlier
            labels.append(f"{group.replace(' ', '_')}_{i + 1:02d}")
            rows.append(spectrum(rng, h_i, rng.normal(c, 0.4), scale=rng.uniform(0.7, 1.3)))
            groups.append(group)
    info = [
        "Three independent groups (Group Statistics demo)",
        "control, low dose, high dose: 12 spectra each, every spectrum from its own sample.",
        "True effects: the 1655 band height grows with the dose (0.70 / 1.00 / 1.35 relative to the",
        "1450 band 1.2), more spread in the high-dose group (SD 0.16 instead of 0.04); the 1585 band",
        "shifts from 1585.0 to 1585.6 and 1586.4 cm-1 (SD 0.4). Every spectrum is multiplied by a",
        "random intensity scale 0.7-1.3 (focus); control_05 is an outlier (1655 height 1.05).",
        "",
        "Try (the groups are filled in automatically from the 'Groups' sheet):",
        "1. Value 'Area (integral) over a range' 1620-1690: the random intensity scale hides much of",
        "   the effect. Then 'Two bands': A = Integral 1620-1690, B = Integral 1420-1480, A / B:",
        "   the scale cancels -> a clear dose effect.",
        "2. Test 'Unequal spread: Welch t-test / Welch ANOVA + Games-Howell' (the high-dose spread",
        "   is larger: see the Brown-Forsythe check in the Test tab).",
        "3. Value 'Fitted peak position', range 1560-1610: the band shift between the groups.",
        "4. Plot: Mark outliers -> control_05.",
    ]
    write(path, labels, rows, info, groups)


def cells(path):
    rng = np.random.default_rng(7)
    labels, rows, groups, samples = [], [], [], []
    for group, prefix in (("wild type", "WT"), ("mutant", "MUT")):
        for cell in range(1, 4):
            cell_h = rng.normal(1.0, 0.10)                   # cells differ; groups do not
            for px in range(1, 16):
                labels.append(f"{prefix}_cell{cell}_px{px:02d}")
                rows.append(spectrum(rng, rng.normal(cell_h, 0.03), noise=0.01))
                groups.append(group)
                samples.append(f"{prefix}_cell{cell}")
    info = [
        "Pseudoreplication (Group Statistics demo)",
        "wild type vs mutant, 3 cells each, 15 pixels (spectra) per cell = 90 spectra.",
        "There is NO true difference between wild type and mutant: every cell has its own 1655 band",
        "height (SD 0.10 between cells), the pixels of one cell vary only a little (SD 0.03).",
        "",
        "Try (groups AND samples are filled in automatically from the 'Groups' sheet):",
        "1. Value: Two bands, A = Integral 1620-1690, B = Integral 1420-1480, A / B; Compute.",
        "   45 vs 45 pixels: a small p-value - and a red warning that the spectra are not",
        "   independent replicates (they come from only 3 cells per group).",
        "2. Tick 'One value per sample' and Compute again: 3 vs 3 cells, no significant difference",
        "   - the honest answer. (With only 3 samples per group the test has little power.)",
    ]
    write(path, labels, rows, info, groups, samples)


def paired(path):
    rng = np.random.default_rng(5)
    labels, rows, groups, samples = [], [], [], []
    for s in range(1, 9):
        h = rng.uniform(0.6, 1.4)                            # samples differ a lot
        for when, dh in (("before", 0.0), ("after", -0.05)):
            labels.append(f"s{s}_{when}")
            rows.append(spectrum(rng, h + dh + rng.normal(0, 0.008), noise=0.005))
            groups.append(when)
            samples.append(f"s{s}")
    info = [
        "Paired measurements (Group Statistics demo)",
        "8 samples, each measured before and after heating (16 spectra).",
        "The samples differ a lot (1655 band height 0.6-1.4); heating lowers it by 0.05 in every",
        "sample (SD 0.008).",
        "",
        "Try (groups and samples are filled in automatically from the 'Groups' sheet):",
        "1. Value 'Maximum (peak intensity) in a range' 1630-1680, test 'Parametric: Welch t-test /",
        "   one-way ANOVA': no",
        "   significant difference - the differences between the samples hide the small change.",
        "2. Test 'Paired (same samples): paired t-test': highly significant; the difference",
        "   before - after is about 0.05, with its 95 % confidence interval. The Sample column",
        "   pairs the spectra (s1 before with s1 after, ...).",
    ]
    write(path, labels, rows, info, groups, samples)


def skewed(path):
    rng = np.random.default_rng(59)
    labels, rows, groups = [], [], []
    for group, median in (("control", 0.10), ("nitrogen starved", 0.30)):
        for i in range(15):
            lipid = float(np.exp(rng.normal(np.log(median), 1.0)))     # log-normal: skewed
            y = spectrum(rng, 1.0, scale=rng.uniform(0.8, 1.2)) + band(X, 1745, 22, lipid)
            labels.append(f"{group.split()[0]}_{i + 1:02d}")
            rows.append(y)
            groups.append(group)
    info = [
        "Skewed values (Group Statistics demo)",
        "Lipid in algal cells: control vs nitrogen starved, 15 cells each (one spectrum per cell).",
        "The lipid band (ester C=O, 1745 cm-1) varies very much from cell to cell: most cells have",
        "little lipid, a few have a lot (log-normal values, typical for amounts). Starved cells have",
        "about 3 times more lipid (median band height 0.30 instead of 0.10).",
        "",
        "Try (the groups are filled in automatically from the 'Groups' sheet):",
        "1. Value: Two bands, A = Baseline-corrected integral 1715-1775, B = Baseline-corrected",
        "   integral 1420-1480, A / B; test 'Parametric': p about 0.07 - not significant. The",
        "   Test tab says the values are not bell-shaped (Shapiro-Wilk) and suggests a",
        "   non-parametric test.",
        "2. Test 'Non-parametric: Mann-Whitney U': p about 0.006 - significant.",
        "3. Or keep 'Parametric' and combine as log2(A / B): the logarithm makes the values",
        "   bell-shaped (Shapiro-Wilk fine) and p is about 0.005.",
        "4. The 'possible outliers' here are not mistakes - they are the long tail of skewed data.",
    ]
    write(path, labels, rows, info, groups)


def cell_map(path):
    """A synthetic Raman map of one cell (WITec / Project FIVE .mat format,
    40 x 30 pixels, 600-1800 cm-1 in 2 cm-1 steps): background (glass), the
    cytoplasm (protein) and the nucleus (protein + DNA bands at 785 and
    1095 cm-1), with a smooth change of the overall intensity across the
    map (focus) and pixel noise. For drawing ROI regions in the 2D Map and
    comparing them in Group Statistics."""
    import scipy.io
    rng = np.random.default_rng(11)
    n_cols, n_rows = 40, 30
    x = np.arange(600.0, 1801.0, 2.0)

    def b(c, w, h):
        return band(x, c, w, h)

    glass = 0.15 + 0.00005 * (x - 600) + b(1100, 120, 0.05)
    protein = b(1003, 8, 0.6) + b(1450, 28, 0.8) + b(1655, 30, 0.7) + b(1250, 40, 0.25)
    dna = b(785, 12, 0.45) + b(1095, 14, 0.35) + b(1578, 14, 0.15)
    data = np.zeros((n_rows * n_cols, x.size), dtype=np.float32)
    for r in range(n_rows):
        for c in range(n_cols):
            in_cell = ((c - 20) / 14.0) ** 2 + ((r - 15) / 10.0) ** 2 <= 1
            in_nucleus = ((c - 17) / 5.0) ** 2 + ((r - 14) / 5.0) ** 2 <= 1
            focus = 0.8 + 0.4 * c / (n_cols - 1)          # intensity drifts across the map
            y = glass.copy()
            if in_cell:
                y = y + protein * rng.normal(1.0, 0.08)
            if in_nucleus:
                y = y + dna * rng.normal(1.0, 0.10)
            data[r * n_cols + c] = (focus * y + rng.normal(0, 0.012, x.size)).astype(np.float32)
    axisscale = np.empty((2, 2), dtype=object)
    axisscale[0, 0] = np.empty((0, 0))
    axisscale[0, 1] = np.array([''])
    axisscale[1, 0] = x.reshape(1, -1)
    axisscale[1, 1] = 'rel. 1/cm'
    imageaxisscale = np.empty((2, 2), dtype=object)
    imageaxisscale[0, 0] = (np.arange(n_cols, dtype=float) * 0.5).reshape(1, -1)
    imageaxisscale[0, 1] = 'um'
    imageaxisscale[1, 0] = (np.arange(n_rows, dtype=float) * 0.5).reshape(1, -1)
    imageaxisscale[1, 1] = 'um'
    scipy.io.savemat(path, {'cell_map': {
        'name': 'synthetic cell map', 'type': 'image',
        'imagesize': np.array([[n_cols, n_rows]], dtype=np.uint8),
        'data': data, 'axisscale': axisscale, 'imageaxisscale': imageaxisscale,
        'history': 'generate_group_statistics_test_datasets.py'}}, do_compression=True)


if __name__ == "__main__":
    out = os.path.dirname(os.path.abspath(__file__))
    for name, fn in (("group_stats_treatment_demo.xlsx", treatment),
                     ("group_stats_cells_samples_demo.xlsx", cells),
                     ("group_stats_paired_demo.xlsx", paired),
                     ("group_stats_skewed_demo.xlsx", skewed),
                     ("group_stats_cell_map_demo.mat", cell_map)):
        fn(os.path.join(out, name))
        print("Wrote:", name)
