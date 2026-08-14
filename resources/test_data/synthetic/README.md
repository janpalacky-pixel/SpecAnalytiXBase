# MCR-ALS / NMF benchmark datasets (with ground truth)

Eight synthetic datasets for testing the MCR-ALS and NMF tools. Each `.xlsx`
holds five sheets:

| Sheet | Contents |
|-------|----------|
| **Spectra** | The mixture spectra to import into the app. First column = x axis (Raman shift or wavelength), then one column per spectrum. **This is the only sheet you feed to MCR-ALS / NMF.** |
| **Pure_components** | The true underlying pure-component spectra. Compare the resolved components against these. |
| **Concentrations** | The true amount of each component in each spectrum — raw values and normalised (% per spectrum). Compare the resolved concentration profiles against these. |
| **Ground_truth** | Every true peak: component, centre, height, FWHM, sign. |
| **Info** | Dataset design summary, recommended settings, and a sheet legend. |

Each mixture set = 30 spectra built as `D = Concentrations · Pure_components`
(+ optional noise). Concentration profiles are smooth, non-negative, and
verified low-collinearity so the components are genuinely resolvable.

## The files

| File | Type | Components | Noise |
|------|------|-----------|-------|
| `raman_2comp_clean.xlsx` | Raman (all-positive bands) | 2 | none |
| `raman_2comp_noisy.xlsx` | Raman | 2 | 1% |
| `raman_3comp_clean.xlsx` | Raman | 3 | none |
| `raman_3comp_noisy.xlsx` | Raman | 3 | 1% |
| `raman_4comp_clean.xlsx` | Raman | 4 | none |
| `raman_4comp_noisy.xlsx` | Raman | 4 | 1% |

Raman bands have varied heights and bandwidths at distinct positions.

## Recommended settings

- **Raman (all-positive):** MCR-ALS with C and ST non-negativity ON, or NMF.
  Both should recover the pure spectra well. Use "Run N times, keep best"
  and set Components to the known count.
- **CD (signed):** MCR-ALS with **C non-negativity ON, ST non-negativity
  OFF** (real negative bands). **NMF is not suitable** — it would clip the
  negative bands. Note these CD sets fit perfectly (~0% lack-of-fit) but the
  recovered component shapes only partly match the truth — a deliberate,
  honest illustration that signed blind resolution is ambiguous even when the
  fit looks perfect.

## What to expect (best of ~20 random restarts, matched correlation to truth)

- Raman 2-comp: ~1.00 (essentially exact)
- Raman 3-comp: ~0.94 (clean) / ~0.99 (this depends on the restart)
- Raman 4-comp: ~0.99 clean, noticeably harder with noise
- CD 2- & 3-comp: fit ~0% but recovery only ~0.79 (rotational ambiguity)

Use these to sanity-check the tools: on the Raman clean sets the resolved
components should closely match `Pure_components`; where they don't, that's
the ambiguity the Help discusses, not necessarily a bug.

## Closed-system datasets (for the Closure constraint)

Two extra datasets model a **closed system** — total material is conserved, so
the component fractions sum to exactly 100% in every spectrum. This is the one
situation where MCR-ALS's **Closure** constraint is physically correct and
genuinely useful.

| File | Story | Components | Noise |
|------|-------|-----------|-------|
| `closed_dna_melting_2comp_clean.xlsx` | DNA duplex melting into single strands as temperature rises | 2 | none |
| `closed_dna_melting_2comp_noisy.xlsx` | same system, same true components | 2 | 1% |
| `closed_dna_melting_3comp_clean.xlsx` | Three-state melting: duplex → intermediate → single strand | 3 | none |
| `closed_dna_melting_3comp_noisy.xlsx` | same system, same true components | 3 | 1% |

Each clean/noisy pair shares the same seed, so the pure spectra and the true
concentrations are *identical* between them — the only difference is the noise.
That lets you see exactly what noise costs you. All four recover the true
components essentially perfectly (similarity 1.000) with Closure ON.

Total nucleic acid is conserved — material only converts between forms — so
duplex% + single-strand% = 100% in every spectrum. The `Concentrations` sheet
has a `SUM_check` column that is 1.000 for every spectrum, confirming closure.

**Run these with Closure ON.** What it buys you: with closure OFF the raw
concentrations come out on an arbitrary scale (row sums ~4.5, e.g. `[2.51,
2.02]` at spectrum 15) and only become interpretable after the display's
"Normalize to 100%" rescaling. With closure ON the raw concentrations *are*
mole fractions directly — `[0.551, 0.449]` against a true `[0.548, 0.452]`.
Both settings recover the pure spectra essentially perfectly here (similarity
~1.00), so closure isn't needed to *find* the answer on this data; its value is
that the numbers come out already physically meaningful.

## Other spectroscopies

| File | Type | Components | Noise |
|------|------|-----------|-------|
| `uvvis_2comp_clean/noisy.xlsx` | UV/Vis electronic absorption — only a few, **very broad**, all-positive bands | 2 | none / 1% |
| `uvvis_3comp_clean/noisy.xlsx` | same | 3 | none / 1% |
| `cd_2comp_clean/noisy.xlsx` | Circular dichroism — broad electronic bands, **signed (+/−)** | 2 | none / 1% |
| `cd_3comp_clean/noisy.xlsx` | same | 3 | none / 1% |
| `roa_2comp_clean/noisy.xlsx` | ROA / VCD — **many sharp vibrational bands** like Raman (varied width and height) but **signed (+/−)** | 2 | none / 1% |
| `roa_3comp_clean/noisy.xlsx` | same | 3 | none / 1% |

Each clean/noisy pair shares a seed, so the true components and concentrations
are identical within a pair — only the noise differs.

**Settings.** UV/Vis is all-positive: use MCR-ALS with both non-negativity
constraints on, or NMF (NMF does very well here, ~0.99). CD and ROA/VCD are
genuinely signed: use **MCR-ALS with ST non-negativity OFF**; NMF is not
applicable (it would clip the negative bands). Leave **Closure OFF** for all of
these — the concentrations do not sum to a constant.

**What to expect.** UV/Vis recovers well blind (~0.95). The signed sets (CD,
ROA) fit to ~0% lack-of-fit but recover the true components only partially blind
(~0.44–0.95, depending on the set) — a deliberate, honest illustration that a
perfect-looking fit does **not** mean the components are right when the data is
signed. Anchoring known components in the **Reference spectra** panel lifts ROA
recovery to ~0.99. That contrast is the whole lesson.

## PLS / PLS-DA demo datasets

Two workbooks for the **PLS / PLS-DA** tool (Analysis && Visualization ->
Visualization -> PLS / PLS-DA), each with a `Spectra` sheet (import this),
a `Calibration_values` sheet (values to type into the PLS calibration
table), an `Answer_key` sheet (true values for a held-out "unknown" set —
don't peek until after predicting), and an `Info` sheet with the full
story and expected result. Both are also reachable straight from
**Help -> Test datasets -> Synthetic**, and the PLS help page has a
step-by-step walkthrough for each ("Try it yourself").

| File | Task | Calibration | Unknowns |
|------|------|-------------|----------|
| `pls_regression_protein_concentration_demo.xlsx` | PLS Regression | 15 spectra, known concentration 0.1–2.0 mg/mL | 5 (`unknown_A`–`unknown_E`) |
| `pls_da_sample_type_classification_demo.xlsx` | PLS-DA (classification) | 20 spectra, 10 each of class A / B | 4 (`unknown_1`–`unknown_4`) |

Both are deliberately **not** solvable by reading a single wavelength: each
has a second, class/concentration-independent source of spectral variation
overlapping the real signal, so PLS's use of the whole spectral shape
genuinely earns its keep over a one-point calibration. Regenerate both with
`generate_pls_test_datasets.py` in this folder.

## Kinetics Fitting demo datasets

Two workbooks for the **Kinetics Fitting** tool (Analysis && Visualization ->
Visualization -> Kinetics Fitting), each with a `Spectra` sheet (import this),
a `Time_values` sheet (times are also auto-guessed from the spectrum labels,
so this is just for reference), and an `Info` sheet with the full story and
expected result. Both are also reachable straight from
**Help -> Test datasets -> Synthetic**, and the Kinetics Fitting help page
has a step-by-step walkthrough for each ("Try it yourself").

| File | Task | True rate constant(s) |
|------|------|------------------------|
| `kinetics_single_exponential_decay_demo.xlsx` | Single wavelength, 1 component | k ~ 0.20 (tau ~ 5) |
| `kinetics_global_two_step_demo.xlsx` | Global analysis, 2 shared components | k ~ 0.08 and k ~ 0.5 (tau ~ 12.5 and ~ 2) |

The global demo's two components have overlapping, oppositely-signed spectral
bands — no single wavelength cleanly isolates either process, so global
analysis (shared rate constants fit across every wavelength at once) earns
its keep over a single-trace fit. Regenerate both with
`generate_kinetics_test_datasets.py` in this folder.

## QC / Outlier Detection demo dataset

One workbook for the **QC / Outlier Detection** tool (Analysis &&
Visualization -> Visualization -> QC / Outlier Detection), with a `Spectra`
sheet (import this) and an `Info` sheet with the full story and expected
result. Also reachable straight from **Help -> Test datasets -> Synthetic**,
and the QC / Outlier Detection help page has a step-by-step walkthrough
("Try it yourself").

| File | Batch | Planted outliers |
|------|-------|-------------------|
| `qc_outlier_planted_outliers_demo.xlsx` | 30 normal spectra (~8% RSD concentration variation) | 3: extreme concentration (T² type), spike artifact (Q type), both combined |

Running the tool with default settings (auto-select components, 95%
confidence) flags exactly the 3 `PLANTED_*` spectra and no others.
Regenerate with `generate_qc_outlier_test_dataset.py` in this folder.
