# src/modules/utils/spectra_validation.py
#
# Shared validation for methods that combine several spectra.
#
# Single source of truth: SVD, PCA, Cluster analysis, MCR-ALS, NMF, 2D
# correlation and anything else that stacks spectra into one matrix must all
# agree on what "the spectra have the same x-axis" means. Having each of them
# hand-roll its own comparison is how they end up disagreeing — one accepting a
# dataset another rejects, or worse, one silently interpolating.

import numpy as np

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)


def axes_match(x1, x2) -> bool:
    """Do these two x-axes represent the same sampling grid?

    FLOATING-POINT TOLERANCE — this is the whole point of the function.

    An exact `==` comparison would be wrong, and dangerously so: two axes that
    are physically identical can still differ in their last bits. That happens
    routinely, for example when

      * one file writes "1000.1" and another writes "1000.10", or
      * an axis has been rebuilt by arithmetic (a Data Range linearisation,
        `np.arange`/`linspace`, a unit conversion) rather than read verbatim.

    Equally, the tolerance must not be so loose that genuinely different grids
    are accepted — the failure mode there is silent nonsense, which is far worse
    than an unnecessary error message.

    The tolerance is therefore scaled to the DATA, not fixed: two axes count as
    the same if every point agrees to within one millionth of the median point
    spacing. A millionth of a step is far below any real instrument's precision,
    so no genuine difference can hide under it; and it is enormously larger than
    float64 round-off (~1e-13 relative), so no accumulation of rounding error can
    trip it. A fixed absolute tolerance could not do both at once: 1e-9 is
    generous for a UV/Vis axis in nm, but for a THz axis in cm-1 with steps of
    0.001 it is nearly a whole step.

    Lengths must match exactly — a different number of points is a different grid,
    full stop, and no tolerance argument can bridge that.
    """
    x1 = np.asarray(x1, dtype=float)
    x2 = np.asarray(x2, dtype=float)

    if x1.shape != x2.shape:
        return False
    if x1.size == 0:
        return True
    if x1.size == 1:
        return bool(np.isclose(x1[0], x2[0], rtol=1e-9, atol=0.0))

    step = float(np.median(np.abs(np.diff(x1))))
    if not np.isfinite(step) or step <= 0:
        # Degenerate axis (all points equal, or non-finite): fall back to a
        # relative comparison against the values themselves.
        return bool(np.allclose(x1, x2, rtol=1e-9, atol=0.0))

    tol = step * 1e-6
    return bool(np.max(np.abs(x1 - x2)) <= tol)


def find_axis_mismatch(spectra):
    """Return (reference_spectrum, offending_spectrum) for the first spectrum
    whose x-axis differs from the first one's, or None if they all match.

    Note on where mismatches actually come from, which is worth knowing when
    reading this: within a SINGLE imported file, all spectra share one x column
    by construction, so they cannot disagree. Mismatches arise when several files
    are imported together, or from the interlaced format (where every spectrum
    carries its own x-axis and they may even have different lengths). Those are
    exactly the cases the Data Range operation exists to reconcile.
    """
    if not spectra or len(spectra) < 2:
        return None

    ref = spectra[0]
    ref_x = np.asarray(ref['x_scale'], dtype=float)
    for s in spectra[1:]:
        if not axes_match(ref_x, s['x_scale']):
            return ref, s
    return None


def describe_axis_mismatch(ref, other, tool_name='analysis') -> str:
    """The user-facing message. Same wording for every tool, so the application
    speaks with one voice."""
    ref_x = np.asarray(ref['x_scale'], dtype=float)
    ox = np.asarray(other['x_scale'], dtype=float)
    return (
        f"Cannot perform {tool_name}: spectra have different x-axes.\n\n"
        f"First spectrum ('{ref.get('label', '?')}'): {ref_x.size} points "
        f"({ref_x.min():g} to {ref_x.max():g})\n"
        f"Spectrum '{other.get('label', '?')}': {ox.size} points "
        f"({ox.min():g} to {ox.max():g})\n\n"
        "All spectra must share an identical x-axis. Use the Data Range "
        "operation to put them on a common axis first."
    )


def validate_common_x_axis(spectra, parent_view=None, tool_name='analysis') -> bool:
    """True if every selected spectrum shares one x-axis; otherwise show the
    warning and return False.

    Call this BEFORE opening a dialog or setting a wait cursor. Failing later —
    inside the computation — leaves an empty dialog on screen, or a spinning
    "busy" cursor over a warning box for work that never started.

    Only for methods that COMBINE spectra (they stack them into a matrix, so
    every row must be sampled at the same x). Per-spectrum operations — SNIP,
    smoothing, normalisation, ... — act on each spectrum independently and must
    NOT call this: for them, differing axes are perfectly fine.
    """
    from PyQt5.QtWidgets import QMessageBox

    mismatch = find_axis_mismatch(spectra)
    if mismatch is None:
        return True

    ref, other = mismatch
    msg = describe_axis_mismatch(ref, other, tool_name)
    logger.error("%s aborted: %s", tool_name, msg.replace('\n', ' '))
    QMessageBox.warning(parent_view, "Incompatible Spectra", msg)
    return False

def group_by_axis(spectra):
    """Partition spectra into groups that each share one x-axis.

    Used by 2D correlation, which is the one combining method that legitimately
    accepts a MIXED selection: hetero-COS correlates two different datasets
    against each other (e.g. IR against Raman), so Dataset X and Dataset Y each
    need to be internally consistent but must NOT match each other.

    Returns a list of lists, in first-seen order.
    """
    groups = []
    for s in spectra:
        x = np.asarray(s['x_scale'], dtype=float)
        for g in groups:
            if axes_match(np.asarray(g[0]['x_scale'], dtype=float), x):
                g.append(s)
                break
        else:
            groups.append([s])
    return groups


def validate_at_most_two_axis_groups(spectra, parent_view=None,
                                     tool_name='2D Correlation') -> bool:
    """For 2D correlation only.

    A blanket "all spectra must share one x-axis" check cannot be used here — it
    would block the legitimate hetero-COS workflow. But a selection that falls
    into THREE or more different x-axes cannot work in any mode: homo needs one
    group, hetero needs exactly two. So refuse that up front, and let the dialog
    handle the one- and two-group cases per-mode.
    """
    from PyQt5.QtWidgets import QMessageBox

    if not spectra:
        return True

    groups = group_by_axis(spectra)
    if len(groups) <= 2:
        return True

    lines = []
    for i, g in enumerate(groups, 1):
        gx = np.asarray(g[0]['x_scale'], dtype=float)
        lines.append(
            f"  Group {i}: {len(g)} spectrum/spectra, {gx.size} points "
            f"({gx.min():g} to {gx.max():g})")
    msg = (
        f"Cannot perform {tool_name}: the selected spectra fall into "
        f"{len(groups)} different x-axes.\n\n"
        + "\n".join(lines) +
        "\n\nStandard (homo) 2D correlation needs all spectra on ONE x-axis.\n"
        "Hetero 2D correlation needs exactly TWO groups (Dataset X and "
        "Dataset Y), each internally consistent.\n\n"
        "Use the Data Range operation to bring the spectra onto a common axis."
    )
    logger.error("%s aborted: %d axis groups", tool_name, len(groups))
    QMessageBox.warning(parent_view, "Incompatible Spectra", msg)
    return False
