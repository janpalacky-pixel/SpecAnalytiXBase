# src/modules/utils/progress_utils.py
"""Shared helper for the progress_callback pattern used throughout this
codebase's long-running per-item loops.

Every Manager/Controller method that processes a batch of spectra (or
subspectra, or stored factors) and supports an optional progress dialog
follows the same convention: accept a `progress_callback=None` parameter,
and call it every 50 items during the loop, so a caller showing a
QProgressDialog can pass e.g. `lambda: QApplication.processEvents()` to
keep its busy animation actually animating during the call — see
operations_controller.py's `_show_busy_progress` and
plotting.py's `overlay_plot_mode` for the full reasoning behind why this
is needed at all (Qt's event loop is otherwise frozen for the whole
duration of one long blocking call).

Before this module existed, the same 3-line snippet —

    if progress_callback is not None and i % 50 == 0:
        progress_callback()

— was hand-copied into 10+ methods across 8+ files (every operation's
Manager or Controller that has a per-spectrum loop, plus plotting.py's
two plot modes). This module exists purely to remove that duplication;
it doesn't change the pattern's contract or behavior at all.
"""


def notify_progress(progress_callback, index, every=50):
    """Call progress_callback() every `every` iterations, if given.

    Parameters
    ----------
    progress_callback : callable or None
        Takes no arguments. None means "no progress dialog is active" —
        this becomes a no-op, exactly as if the check were inlined.
    index : int
        The current loop index (0-based) — typically `i` from
        `for i, item in enumerate(items):`.
    every : int
        How often to call progress_callback. Every codebase caller uses
        the default (50) for consistency; only override this if a
        specific loop has a good reason to notify more or less often.

    Usage
    -----
        for i, spectrum in enumerate(spectra):
            notify_progress(progress_callback, i)
            ...actual per-spectrum work...
    """
    if progress_callback is not None and index % every == 0:
        progress_callback()
