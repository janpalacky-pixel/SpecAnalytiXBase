# SpecAnalytiXBase — Test Suite

## What are these tests?

The tests in this folder are an automated safety net for the import/export
pipeline, the snapshot system, and (in `test_regression_bugs.py`) a handful
of specific computational bugs found by hand elsewhere in the app. Every
time you change the code, you can run the tests in a few seconds and
immediately know whether anything broke — without having to open the
application, import files manually, and check the results visually.

### A note on coverage

This suite covers the import/export pipeline, the snapshot system, NMF and
MCR-ALS (correctness against known ground truth, plus specific bug
regressions), and nothing else yet. The app's other ~43 analysis managers —
PCA, PLS, Kinetics Fitting, QC/Outlier Detection, Cluster Analysis, 2D
Correlation, Reference Matching, Band Ratio, the various
baseline/normalization/cosmic-ray/SNIP/SVD operations, and so on — have no
tests beyond whatever's caught incidentally. Those managers do real
scientific computation and are where a wrong-but-plausible answer is
hardest to notice by eye (the MCR-ALS bug documented in
`test_regression_bugs.py` is a real example: lack-of-fit silently went from
0.11% to 59.8% on one code path). Extending the
`test_ground_truth_correctness.py` pattern to the other managers with
shipped synthetic ground truth (Kinetics, QC/Outlier, PLS all have their
own demo datasets already), and adding a regression test for each new bug
as it's found, is the natural way to close that gap over time — see
"Adding new tests" below.

---

## How to run the tests

Open a terminal in the project root (the folder containing `main.py`) and run:

```
pytest tests/ -v
```

The `-v` flag means "verbose" — it prints each test name as it runs.
Without `-v` you get a shorter summary.

To run a single test file:
```
pytest tests/test_delimiter_detection.py -v
```

To run a single test class:
```
pytest tests/test_delimiter_detection.py::TestTabDelimiter -v
```

To run a single test:
```
pytest tests/test_delimiter_detection.py::TestTabDelimiter::test_simple_tab -v
```

To see diagnostic (DEBUG) output during tests:
```
LOG_LEVEL=DEBUG pytest tests/ -v
```

---

## What does the output mean?

```
tests/test_delimiter_detection.py::TestTabDelimiter::test_simple_tab PASSED
tests/test_round_trip.py::TestCommonScaleRoundTrip::test_three_spectra_tab_dot FAILED
```

- **PASSED** — the test ran and all assertions were correct
- **FAILED** — at least one assertion was wrong; details are shown below

When a test fails, pytest shows you exactly what value was returned versus
what was expected:

```
AssertionError:
    assert '\t' == ','
     where '\t' = _detect_delimiter(["100,0;1,23"])
```

This tells you immediately what the function returned and what it should
have returned.

At the end you get a summary:
```
97 passed in 1.96s
```
or:
```
1 failed, 96 passed in 1.96s
```

---

## What do the test files cover?

| File | What it tests |
|------|--------------|
| `test_delimiter_detection.py` | Column separator detection (tab, semicolon, comma, pipe, space). Verifies comma is NOT chosen when it is the decimal separator. |
| `test_decimal_detection.py` | Decimal separator detection (dot vs comma). Conversion of number strings including European format and scientific notation. |
| `test_header_detection.py` | Whether the first row of a file is a text header or numeric data. |
| `test_column_parser.py` | The core spectrum builder. Spectrum count, label handling, data values, NaN column skipping, performance. |
| `test_round_trip.py` | End-to-end: save spectra to a file, re-import them, verify values match to 10 decimal places. Tests all separator combinations. |
| `test_snapshot.py` | JSON snapshot save and load. Numpy array encoding/decoding. File format validation. Performance for large datasets. |
| `test_regression_bugs.py` | Regression tests for specific bugs found and fixed by hand (not caught by the rest of the suite): the MCR-ALS Closure+fixed-reference scale mismatch, ground-truth label matching across import prefixes, duplicate-x-value merging, and the single-point spectrum squeeze crash. Each test's docstring explains the original bug and the before/after numbers. See "A note on coverage" below. |
| `test_ground_truth_correctness.py` | Runs NMF and MCR-ALS against shipped synthetic benchmark datasets with a known true decomposition and asserts recovered components/concentrations match truth within tolerance — not just "did it run." Deliberately restricted to datasets where rotational ambiguity (a real mathematical property, not a bug — see the file's own docstring) doesn't make the expected recovery accuracy inherently variable. |

---

## What are fixtures? (conftest.py)

`conftest.py` is loaded automatically by pytest before running any tests.
It defines **fixtures** — reusable pieces of test setup that any test can
request by name.

For example, `three_spectra` is a fixture that creates 3 spectrum dicts
with numpy arrays. Instead of writing that setup code in every test file,
it is defined once and injected automatically:

```python
def test_something(self, three_spectra):
    # three_spectra is created automatically by pytest
    assert len(three_spectra) == 3
```

The `tmp_txt`, `tmp_xlsx`, and `tmp_snapx` fixtures provide paths to
temporary files that are created before each test and deleted after,
so tests never leave files behind and never interfere with each other.

---

## What is pytest and why not unittest?

Python has a built-in testing framework called `unittest`. pytest is a
third-party alternative that is simpler and more powerful.

With unittest you write:
```python
self.assertEqual(_detect_delimiter(lines), '\t')
self.assertRaises(ValueError, _convert_to_float, 'bad', '.')
```

With pytest you write:
```python
assert _detect_delimiter(lines) == '\t'
with pytest.raises(ValueError):
    _convert_to_float('bad', '.')
```

pytest also gives better failure messages — when an assertion fails it
shows you the actual values on both sides, not just "assertion failed".

pytest can run both its own test style and unittest-style tests, so they
are compatible.

Install pytest with:
```
pip install pytest
```

---

## When should you run the tests?

- **After changing any import/export code** — `table_data_converter.py`,
  `save_spectra_manager.py`, `import_controller.py`
- **After changing snapshot save/load** — `save_spectra_manager.py`
- **After a refactoring** — moving files, renaming functions
- **Before committing code** — to make sure nothing is broken

---

## When a test fails — what to do?

1. Read the failure message carefully — it tells you which assertion failed
   and what values were involved
2. Decide: is the **code** wrong, or is the **test** wrong?
   - If the code changed intentionally and the new behaviour is correct,
     update the test to match
   - If the code changed unintentionally (a regression), fix the code
3. Run the tests again to confirm the fix

---

## Adding new tests

When you add a new feature or fix a bug, add a test for it. The pattern is:

1. Create a small, controlled input (fake data)
2. Call the function you want to test
3. Assert the output is correct

Place the test in the most relevant existing file, or create a new
`test_*.py` file if it covers a completely new area.

Keep tests small and focused — one test should check one specific thing.
A test named `test_comma_NOT_chosen_when_decimal` is better than a
test named `test_delimiter_detection` that checks everything at once,
because when it fails you immediately know exactly what broke.
