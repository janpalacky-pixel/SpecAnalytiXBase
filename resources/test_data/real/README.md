# Real (measured) test datasets

This folder is for **measured, experimental** spectra — as opposed to the
synthetic datasets in `../synthetic/`.

The crucial difference: for real data the **true components are not known**.
Nothing here can be checked against a ground truth, so these datasets can show
you that the tools *run*, and let you practise the workflow, but they cannot
tell you whether a decomposition is *correct*. That is exactly why the
synthetic datasets exist.

## Adding a dataset

1. Drop the file (`.xlsx`, `.csv`, `.txt`, …) into this folder.
2. Add one line to `REAL_TEST_DATASETS` near the top of
   `src/views/main_window.py`:

   ```python
   REAL_TEST_DATASETS = [
       ('My measured series', 'my_measured_series.xlsx'),
   ]
   ```

It will then appear under **Help → Test datasets → Real (measured)**.
