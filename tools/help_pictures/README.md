# Help pictures

The pictures in the help (`resources/images/help_screenshots/`) are made by
these scripts from the real program, with the test datasets that come with it.

## Make all pictures

Double-click **`tools/make_all_help_pictures.bat`** (on Windows, so the pictures
have the Windows look). It takes about 5 minutes; windows of the program
open and close by themselves, so do not use the mouse or keyboard meanwhile.

Afterwards **GitHub Desktop → Changes** lists only the pictures that really
changed: an unchanged window gives exactly the same picture (the same data, the
same settings and the same window sizes every time; the clock, the random ids and
the mouse are fixed too), so it is not listed. A picture whose only difference
is a few pixels in one small spot (Windows draws the message-box icons slightly
differently each time) is put back as it was by `keep_unchanged.py`
(`tools/logs/pictures_kept.txt`).
Commit the changed ones together, e.g. "Help pictures".

Run it whenever you like — after changing a window, or before a release.

- Logs: `tools/logs/pictures_*.txt` (not in git).
- Problems: `tools/logs/pictures_problems.txt` lists a picture that could not be
  taken ("NOT TAKEN": a button or tab was not found, e.g. after it was renamed —
  the old picture stays), an error, or a part that was skipped.
- Python: `%SAX_PYTHON%` if set, else `%USERPROFILE%\fresh_env`, else `python`.

## The scripts

| Script | Pictures |
|---|---|
| `make_user_guide_screenshots.py` | User Guide: the main window, menus, Import, Save, History, … |
| `make_tool_screenshots.py` | the tool windows (2D Map, Melting Curve, SVD, PCA, NMF, MCR-ALS, Normalization, Peak Fitting, Peak Detection, …); `python tools/help_pictures/make_tool_screenshots.py map2d` makes only one part (see `PARTS`) |
| `make_group_statistics_tutorial_figures.py` | Group Statistics and its tutorial (also checks the numbers quoted in the tutorial) |
| `make_peak_detection_figures.py` | the explanatory figures of Peak Detection |
| `make_calculation_figures.py` | how areas and Voigt areas are calculated |
| `make_unmixing_figures.py` | Unmixing (2D Map) on a demo |
| `make_unmixing_glenodinium_figures.py`, `make_suggest_explained_figure.py` | Unmixing on the real Glenodinium map — need its snapshot (not in git, see `glenodinium_data.py`); skipped without it |

Each script does what a user would do: it loads a test dataset, opens the
window, sets the values the help talks about, clicks the buttons and takes the
picture of the window or of a part of it. Every window gets a fixed size.

When a window changes (a new control, a renamed button), the part of the
script for it may need a small update: the log then says "NOT TAKEN".
