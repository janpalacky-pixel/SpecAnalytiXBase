# SpecAnalytiXBase

A PyQt5 desktop application for processing and analyzing spectroscopic data — UV-Vis, CD, Raman, IR, fluorescence, NMR, and related techniques.

## Overview

SpecAnalytiXBase is built around a single spectra list: import data from several instrument formats, apply a chain of processing operations, and run a range of multivariate and quantitative analyses — all while keeping a full, human-readable history of every operation performed on each spectrum. Each spectrum can be renamed, annotated, and styled independently, and carries its own metadata generated automatically from the operations applied to it.

## Import / Export Formats

| Format | Extension | Notes |
|---|---|---|
| Plain text | `.txt`, `.dat`, `.csv` | Delimiter auto-detected |
| Excel | `.xlsx`, `.xls` | Single or multiple sheets |
| SPC (Thermo/GRAMS) | `.spc` | Calibrated x-axis |
| SPE (LightField/WinSpec) | `.spe` | Raman/CCD instrument files |
| JWS (JASCO SpectraManager) | `.jws` | CD spectropolarimeter files, multi-channel |
| MAT (WITec/Project FIVE map) | `.mat` | Hyperspectral Raman/IR map — one spectrum per pixel, row/col + µm position kept in metadata |

Spectra can also be exported back out to text, Excel, and SPC.

## Processing Operations (19)

**Baseline Correction** — Manual Baseline Correction, Automated Baseline Correction, SNIP Baseline, SVD Background

**Smoothing** — Savitzky-Golay Smoothing, FFT Denoising

**Data Manipulation** — Data Range, Combine Spectra, Interactive Subtraction, X-Axis Alignment, SVD Interpolation

**Axis & Unit Conversion** — Spectral Calculator, Normalization, CD Unit Conversion, X-axis Unit Conversion, Mean-Center Spectra (Dataset)

**Spike Removal** — Spike Removal, Cosmic Ray Removal

**Resolution** — Resolution Enhancement

Plus **Batch Pipeline Replay** — save a sequence of operations and re-run it on a new batch of spectra.

## Analysis & Visualization Tools (16)

**Visualization** — SVD Analysis, PCA Scores, NMF, MCR-ALS, Cluster Analysis, Self-Organizing Map (SOM), 2D Map, 2D Correlation, PLS/PLS-DA

**Data Analysis** — Peak Fitting, Band Ratio, Reference Matching, Melting Curve Analysis, Isosbestic Point Detection, Kinetics Fitting, QC/Outlier Detection

## Other Features

- Test datasets bundled with the app for every major operation and analysis tool
- Context-sensitive help on every dialog, plus in-app User Guide, Quick Start, and Developer Guide pages
- Apply / Add-as-New on every operation, so you can either overwrite a spectrum or keep the original and add a processed copy
- Each spectrum handled independently — its own name, metadata, and plot styling
- PDF report export from analysis dialogs
- Project save/load, so a full working session can be reopened later

## Downloads

The [Releases page](../../releases) has two kinds of build:

- **Stable releases** (e.g. `v1.3.0`) — tested, versioned snapshots. This is what most users want. GitHub marks the newest one **Latest** automatically — grab the installer `.exe` from that one.
- **[Nightly build](../../releases/tag/nightly)** — rebuilt automatically once a day from whatever is on `main` (or on demand). Always has the newest fixes, but isn't a tested release. Useful if you need a fix that hasn't made it into a numbered release yet; not recommended as your everyday install.

## Installation

See [`INSTALLATION.txt`](INSTALLATION.txt) for full details. In short:

- **Windows, easiest:** download and run the installer `.exe` from the [Releases](../../releases) page.
- **Any OS, from source:**
  ```
  python -m venv venv
  venv\Scripts\activate            # (Windows)  or  source venv/bin/activate  (macOS/Linux)
  pip install -r requirements.txt
  python main.py
  ```
- **Build your own installer:** run `BuildInstaller.bat` (Windows, requires PyInstaller and Inno Setup 6).

## Documentation

Full documentation is built into the application itself — open the **Help** menu once running for the User Guide, Quick Start, Installation, Developer Guide, and per-dialog help pages.

## License

GNU General Public License v3.0 — see [`LICENSE`](LICENSE) for the full text, or [`installer_assets/license.txt`](installer_assets/license.txt) for a plain-language summary. Free to use, modify, and redistribute; modified versions must remain open under the same terms.

Copyright (C) 2026 Institute of Biophysics of the Czech Academy of Sciences, v. v. i. — SpecAnalytiXBase was developed there as an employee work, with the Institute holding the copyright.

Provided "as-is," without warranty of any kind.

## Contact

Developed by Jan Palacký, Ph.D., at the Institute of Biophysics of the Czech Academy of Sciences (BFU) — lead developer and point of contact for questions, bug reports, and collaboration.

- Email: [janpalacky@ibp.cz](mailto:janpalacky@ibp.cz)
- Research group: [Biophysics of Nucleic Acids](https://www.ibp.cz/en/research/departments/biophysics-of-nucleic-acids/research-profile)
- Institute: [ibp.cz](https://www.ibp.cz/en/)

## Acknowledgements

The real, measured 2D Raman map datasets bundled with the app, or offered
as an in-app download for testing (see `resources/test_data/real/`), were
measured and kindly provided by Assoc. Prof. Peter Mojzeš, Division of
Biomolecular Physics, Institute of Physics, Charles University in Prague.
