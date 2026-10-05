# src/help/help_window.py
"""
Help system for SpecAnalytiXBase.

DESIGN: each help topic is written to a real .html file and opened in the
user's own default web browser (webbrowser.open) — NOT rendered inside this
app via any embedded engine (no QWebEngineView/Chromium subprocess, no
QTextBrowser HTML-subset hacks).

Why: this app is distributed publicly (GitHub). We have zero control over,
and zero ability to predict, what antivirus software — if any — a given
user has installed, or how it's configured. Anything that spawns or embeds
its own rendering subprocess (QtWebEngine) is something SOME antivirus,
SOMEWHERE, may silently block, with no error and nothing for us to catch.
Anything that hand-rolls a partial HTML/CSS renderer (QTextBrowser) is
something that will always lag behind real browser behavior (zoom,
spacing, layout quirks).

Opening a plain .html file via the OS's own "open with default application"
mechanism has none of those problems: it is the exact same operation as a
user double-clicking any .html or .pdf file in File Explorer. It doesn't
launch an unknown executable — it launches whatever browser the user
already has, already trusts, and already uses every day. There is nothing
here for any antivirus to flag, on any machine, ever.

Trade-off, openly: the help page opens in a separate browser window/tab,
not embedded inside the app's own window. In exchange: perfect rendering,
perfect native zoom, perfect everything — for free, on every machine,
unconditionally.
"""
import os
import re
import sys
import tempfile

from PyQt5.QtWidgets import QMessageBox

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)


# ======================================================================
# Help topic registry  —  maps a help key to (module, title_fn, content_fn)
# ======================================================================

_REGISTRY = {
    # Data import / export
    'import':                 ('src.help.import_help', 'get_import_help_title', 'get_import_help_content'),
    'save':                   ('src.help.save_help', 'get_save_help_title', 'get_save_help_content'),

    # Spectra Processing
    'data_range':             ('src.help.data_range_help', 'get_data_range_help_title', 'get_data_range_help_content'),
    'normalization':          ('src.help.normalization_help', 'get_normalization_help_title', 'get_normalization_help_content'),
    'sg_smoothing':           ('src.help.sg_smoothing_help', 'get_sg_smoothing_help_title', 'get_sg_smoothing_help_content'),
    'fft_denoising':          ('src.help.fft_denoising_help', 'get_fft_denoising_help_title', 'get_fft_denoising_help_content'),
    'manual_baseline':        ('src.help.baseline_correction_help', 'get_baseline_correction_help_title', 'get_baseline_correction_help_content'),
    'automated_baseline':     ('src.help.automated_baseline_help', 'get_automated_baseline_help_title', 'get_automated_baseline_help_content'),
    'snip_baseline':          ('src.help.snip_baseline_help', 'get_snip_baseline_help_title', 'get_snip_baseline_help_content'),
    'svd_background':         ('src.help.svd_background_help', 'get_svd_background_help_title', 'get_svd_background_help_content'),
    'interactive_subtraction':('src.help.interactive_subtraction_help', 'get_interactive_subtraction_help_title', 'get_interactive_subtraction_help_content'),
    'combine_spectra':        ('src.help.spectra_combine_help', 'get_combine_spectra_help_title', 'get_combine_spectra_help_content'),
    'spectral_calculator':    ('src.help.spectral_calculator_help', 'get_spectral_calculator_help_title', 'get_spectral_calculator_help_content'),
    'spike_removal':          ('src.help.spike_removal_help', 'get_spike_removal_help_title', 'get_spike_removal_help_content'),
    'peak_fitting':           ('src.help.peak_fitting_help', 'get_peak_fitting_help_title', 'get_peak_fitting_help_content'),
    'cosmic_ray':             ('src.help.cosmic_ray_help', 'get_cosmic_ray_help_title', 'get_cosmic_ray_help_content'),
    'resolution':             ('src.help.resolution_enhancement_help', 'get_resolution_help_title', 'get_resolution_help_content'),
    'xaxis_alignment':        ('src.help.xaxis_alignment_help', 'get_xaxis_alignment_help_title', 'get_xaxis_alignment_help_content'),
    'svd_interpolation':      ('src.help.svd_interpolation_help', 'get_svd_interpolation_help_title', 'get_svd_interpolation_help_content'),
    'cd_unit_conversion':     ('src.help.cd_unit_conversion_help', 'get_cd_unit_conversion_help_title', 'get_cd_unit_conversion_help_content'),
    'xaxis_unit_conversion':  ('src.help.xaxis_unit_conversion_help', 'get_xaxis_unit_conversion_help_title', 'get_xaxis_unit_conversion_help_content'),
    'mean_centering':         ('src.help.mean_centering_help', 'get_mean_centering_help_title', 'get_mean_centering_help_content'),

    # Spectra Analysis & Visualization
    'svd_analysis':           ('src.help.svd_reconstruction_help', 'get_svd_reconstruction_help_title', 'get_svd_reconstruction_help_content'),
    'pca_scores':              ('src.help.pca_scores_help', 'get_pca_scores_help_title', 'get_pca_scores_help_content'),
    'nmf':                     ('src.help.nmf_help', 'get_nmf_help_title', 'get_nmf_help_content'),
    'mcr_als':                 ('src.help.mcr_als_help', 'get_mcr_als_help_title', 'get_mcr_als_help_content'),
    'cluster_analysis':       ('src.help.cluster_analysis_help', 'get_cluster_analysis_help_title', 'get_cluster_analysis_help_content'),
    'som':                     ('src.help.som_help', 'get_som_help_title', 'get_som_help_content'),
    'band_ratio':              ('src.help.band_ratio_help', 'get_band_ratio_help_title', 'get_band_ratio_help_content'),
    'reference_matching':     ('src.help.reference_matching_help', 'get_reference_matching_help_title', 'get_reference_matching_help_content'),
    'melting_curve':           ('src.help.melting_curve_help', 'get_melting_curve_help_title', 'get_melting_curve_help_content'),
    'isosbestic_point':        ('src.help.isosbestic_point_help', 'get_isosbestic_point_help_title', 'get_isosbestic_point_help_content'),
    'batch_pipeline':          ('src.help.batch_pipeline_help', 'get_batch_pipeline_help_title', 'get_batch_pipeline_help_content'),
    'pls':                     ('src.help.pls_help', 'get_pls_help_title', 'get_pls_help_content'),
    'kinetics_fitting':        ('src.help.kinetics_fitting_help', 'get_kinetics_fitting_help_title', 'get_kinetics_fitting_help_content'),
    'qc_outlier':              ('src.help.qc_outlier_help', 'get_qc_outlier_help_title', 'get_qc_outlier_help_content'),
    'map2d':                   ('src.help.map2d_help', 'get_map2d_help_title', 'get_map2d_help_content'),
    'two_d_correlation':       ('src.help.two_d_correlation_help', 'get_two_d_correlation_help_title', 'get_two_d_correlation_help_content'),
    'band_markers':            ('src.help.band_markers_help', 'get_band_markers_help_title', 'get_band_markers_help_content'),
    'quick_start':             ('src.help.quick_start_help', 'get_quick_start_help_title', 'get_quick_start_help_content'),
    'installation':            ('src.help.installation_help', 'get_installation_help_title', 'get_installation_help_content'),
    'license':                 ('src.help.license_help', 'get_license_help_title', 'get_license_help_content'),
    'user_guide':              ('src.help.user_guide_help', 'get_user_guide_help_title', 'get_user_guide_help_content'),
    'developer_guide':         ('src.help.developer_guide_help', 'get_developer_guide_help_title', 'get_developer_guide_help_content'),
    'plot_controls':           ('src.help.plot_controls_help', 'get_plot_controls_help_title', 'get_plot_controls_help_content'),
}


# ======================================================================
# Writing pages to disk
# ======================================================================

_HELP_LINK_RE = re.compile(r'help://([a-zA-Z0-9_]+)')


def _help_pages_dir():
    """
    A persistent, writable folder to hold generated help .html files.
    Same pattern/location as the app's log folder, for consistency.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.path.expanduser("~/.specanalytixbase")
    return os.path.join(base, "SpecAnalytiXBase", "help_pages")


def _rewrite_help_links(html, current_key):
    """
    Rewrite help://<key> links into plain relative <key>.html links, so
    cross-references between help topics work as ordinary links inside the
    browser — no custom URL scheme registration needed (which wouldn't be
    reliable on a machine where this app was never "installed", only
    downloaded and run from source).
    """
    return _HELP_LINK_RE.sub(lambda m: f"{m.group(1)}.html", html)


def _write_help_page(key, title, content):
    """
    Write a single help topic's content to <help_pages_dir>/<key>.html and
    return the file's path. Re-written every time the topic is opened, so
    edits to the help-content module are always reflected immediately —
    nothing is cached.
    """
    pages_dir = _help_pages_dir()
    os.makedirs(pages_dir, exist_ok=True)

    html = _rewrite_help_links(content, key)
    path = os.path.join(pages_dir, f"{key}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def _slugify(text):
    """Turn an arbitrary title into a safe filename fragment."""
    slug = re.sub(r'[^a-zA-Z0-9]+', '_', text).strip('_').lower()
    return slug or "help"


def _write_all_registered_pages():
    """
    Write every topic in _REGISTRY out to <key>.html.

    Necessary because help pages open in the user's own external browser
    (see module docstring) rather than something embedded in this app —
    once that browser window exists, this app has no way to react when a
    link inside it is clicked. So instead of writing pages lazily on
    demand, every help://<key> cross-reference must already point at a
    real file *before* the browser ever gets a chance to follow it. This
    writes the whole small "site" each time any topic is opened; content
    is cheap to (re)build, so nothing is cached (see _write_help_page).
    """
    import importlib
    for reg_key, (module_path, title_fn, content_fn) in _REGISTRY.items():
        try:
            mod     = importlib.import_module(module_path)
            title   = getattr(mod, title_fn)()
            content = getattr(mod, content_fn)()
            _write_help_page(reg_key, title, content)
        except Exception as exc:
            # Don't let one broken/unfinished topic stop the others from
            # being generated.
            logger.warning("help: failed to pre-generate page for '%s': %s", reg_key, exc)


def _declare_help_modules_for_bundlers():
    """Never called. Exists only so PyInstaller bundles every help topic.

    Topics are looked up by *string* in _REGISTRY and loaded with
    importlib.import_module() at runtime, which PyInstaller's static
    analysis cannot see. Any topic module that nothing else imports
    explicitly was therefore left out of the installer: Help > User Guide,
    Quick Start, Installation, Developer Guide and License (and a few other
    topics) opened nothing in v1.3.0 - v1.4.1 although they worked from
    source. An import statement inside a function body is still found by
    the analysis, so every registered module is listed here.

    tests/test_help_modules_bundled.py fails if a module is added to
    _REGISTRY without being listed here.
    """
    import src.help.automated_baseline_help  # noqa: F401
    import src.help.band_markers_help  # noqa: F401
    import src.help.band_ratio_help  # noqa: F401
    import src.help.baseline_correction_help  # noqa: F401
    import src.help.batch_pipeline_help  # noqa: F401
    import src.help.cd_unit_conversion_help  # noqa: F401
    import src.help.cluster_analysis_help  # noqa: F401
    import src.help.cosmic_ray_help  # noqa: F401
    import src.help.data_range_help  # noqa: F401
    import src.help.developer_guide_help  # noqa: F401
    import src.help.fft_denoising_help  # noqa: F401
    import src.help.import_help  # noqa: F401
    import src.help.installation_help  # noqa: F401
    import src.help.interactive_subtraction_help  # noqa: F401
    import src.help.isosbestic_point_help  # noqa: F401
    import src.help.kinetics_fitting_help  # noqa: F401
    import src.help.license_help  # noqa: F401
    import src.help.map2d_help  # noqa: F401
    import src.help.mcr_als_help  # noqa: F401
    import src.help.mean_centering_help  # noqa: F401
    import src.help.melting_curve_help  # noqa: F401
    import src.help.nmf_help  # noqa: F401
    import src.help.normalization_help  # noqa: F401
    import src.help.pca_scores_help  # noqa: F401
    import src.help.peak_fitting_help  # noqa: F401
    import src.help.plot_controls_help  # noqa: F401
    import src.help.pls_help  # noqa: F401
    import src.help.qc_outlier_help  # noqa: F401
    import src.help.quick_start_help  # noqa: F401
    import src.help.reference_matching_help  # noqa: F401
    import src.help.resolution_enhancement_help  # noqa: F401
    import src.help.save_help  # noqa: F401
    import src.help.sg_smoothing_help  # noqa: F401
    import src.help.snip_baseline_help  # noqa: F401
    import src.help.som_help  # noqa: F401
    import src.help.spectra_combine_help  # noqa: F401
    import src.help.spectral_calculator_help  # noqa: F401
    import src.help.spike_removal_help  # noqa: F401
    import src.help.svd_background_help  # noqa: F401
    import src.help.svd_interpolation_help  # noqa: F401
    import src.help.svd_reconstruction_help  # noqa: F401
    import src.help.two_d_correlation_help  # noqa: F401
    import src.help.user_guide_help  # noqa: F401
    import src.help.xaxis_alignment_help  # noqa: F401
    import src.help.xaxis_unit_conversion_help  # noqa: F401


# ======================================================================
# Public API
# ======================================================================

def open_help_topic(parent, key):
    """Open the help page for the given registry key (e.g. 'nmf') in the
    user's default browser."""
    logger.debug("open_help_topic: requested '%s'", key)
    entry = _REGISTRY.get(key)
    if entry is None:
        logger.warning("help: unknown topic key '%s'", key)
        QMessageBox.information(parent, 'Help', f'Help topic "{key}" is not available yet.')
        return

    try:
        _write_all_registered_pages()
        path = os.path.join(_help_pages_dir(), f"{key}.html")
        logger.debug("open_help_topic: opening %s in browser", path)
        _open_in_browser(path)
    except Exception as exc:
        logger.error("help: failed to open '%s': %s", key, exc)
        logger.exception("Traceback:")
        QMessageBox.information(parent, 'Help', f'Help not available: {exc}')


def show_help_window(parent, title, content):
    """
    Backward-compatible entry point for any call site that already has
    fully-built (title, content) rather than a registry key — writes it
    out and opens it the same way as open_help_topic().
    """
    try:
        _write_all_registered_pages()
        key = _slugify(title)
        path = _write_help_page(key, title, content)
        _open_in_browser(path)
    except Exception as exc:
        logger.error("help: failed to show '%s': %s", title, exc)
        logger.exception("Traceback:")
        QMessageBox.information(parent, 'Help', f'Help not available: {exc}')


def _open_in_browser(path):
    """
    Open a local file in the user's default application for .html files
    (their normal web browser) — the same OS-level operation as
    double-clicking the file in a file manager. Tries Qt's mechanism
    first (works without importing the stdlib webbrowser module, and
    integrates with Qt's own event loop), falling back to Python's
    built-in webbrowser module if that's unavailable for any reason.
    """
    file_url = "file:///" + path.replace(os.sep, "/")
    try:
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(file_url))
    except Exception:
        logger.exception("QDesktopServices.openUrl failed, falling back to webbrowser module")
        import webbrowser
        webbrowser.open(file_url)
