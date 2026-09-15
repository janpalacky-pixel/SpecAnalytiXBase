# Real (measured) test datasets

This folder is for **measured, experimental** spectra — as opposed to the
synthetic datasets in `../synthetic/`.

The crucial difference: for real data the **true components are not known**.
Nothing here can be checked against a ground truth, so these datasets can show
you that the tools *run*, and let you practise the workflow, but they cannot
tell you whether a decomposition is *correct*. That is exactly why the
synthetic datasets exist.

## Adding a single-series dataset

1. Drop the file (`.xlsx`, `.csv`, `.txt`, …) into this folder.
2. Add one line to `REAL_TEST_DATASETS` near the top of
   `src/views/main_window.py`:

   ```python
   REAL_TEST_DATASETS = [
       ('My measured series', 'my_measured_series.xlsx'),
   ]
   ```

It will then appear under **Help → Test datasets → Real (measured)**.

## Adding a 2D map dataset

2D maps (files meant to be opened with the **2D Map** dialog) live in their
own `2D map/` subfolder here, and get their own **2D maps** submenu instead
of sitting flat alongside the single-series datasets above — a spatial map
needs to be opened as a whole, with its row/col geometry, rather than as one
series.

1. Drop the file into `2D map/`.
2. Add one line to `REAL_TEST_DATASETS_2D_MAPS` near the top of
   `src/views/main_window.py`, using a forward-slash relative path:

   ```python
   REAL_TEST_DATASETS_2D_MAPS = [
       ('My measured map', '2D map/my_measured_map.mat'),
   ]
   ```

It will then appear under **Help → Test datasets → Real (measured) → 2D maps**.

If the file is a MAT/WITec map import, every one of its spectra carries the
map's row/col size in `metadata['import_parameters']` (`map_n_rows` /
`map_n_cols`) — the 2D Map dialog reads this automatically and skips asking
for dimensions. A plain text/column-format map (like
`Raman_2D_map_85x55.txt`) doesn't carry this, so the dialog falls back to
its normal "Suggest…" dimension picker for those.

## Datasets too large for git

GitHub hard-refuses any file over 100 MB, and strongly discourages anything
over 50 MB — several real 2D maps are well past that. Those are **not**
committed to git at all; instead they're attached as assets to a GitHub
Release, and downloaded on demand from inside the app via
**Help → Test datasets → Real (measured) → Download large test datasets…**,
which saves them into this folder (`resources/test_data/real/`, or
`2D map/` for a map — the download filename must match wherever the app
expects to find it). Installer builds bundle these files directly, so this
only matters when running from source.

To add one:

1. Add the file's local path to `.gitignore` (see the existing entries
   under "Large real-data 2D map test datasets") so it can never be
   committed by accident.
2. Attach the file to the GitHub Release named by
   `LARGE_TEST_DATASETS_RELEASE_TAG` in `src/views/main_window.py`
   (create that release first if it doesn't exist yet — GitHub's web UI:
   repo → Releases → Draft a new release → drag the file into the
   assets area → Publish), keeping the asset's filename **exactly** the
   same as the local filename (the download URL is built from it).
3. Add one line to `LARGE_TEST_DATASETS` near the top of
   `src/views/main_window.py`:

   ```python
   LARGE_TEST_DATASETS = [
       ('My large measured map', 'my_large_measured_map.mat'),
   ]
   ```
