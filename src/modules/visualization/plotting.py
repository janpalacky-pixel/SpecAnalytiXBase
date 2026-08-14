
import numpy as np
from src.modules.utils.progress_utils import notify_progress
from src.modules.utils.spectrum_identity import spectrum_key
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas, NavigationToolbar2QT as NavigationToolbar
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from matplotlib.figure import Figure
from src.modules.visualization.legend_properties_manager import LegendManager
from src.modules.visualization.axis_properties_manager import AxisManager
from src.modules.visualization.grid_properties_manager import GridManager

def get_default_plot_settings():
    """Return default plot settings."""
    return {
        'linecolor': 'blue',
        'linestyle': '-',
        'linewidth': 1.0,
        'marker': 'None',
        'markersize': 6.0,
        'markeredgecolor': 'black',
        'markeredgewidth': 1.0,
        'markerfacecolor': 'black',
    }

def apply_plot_settings(ax, x_data, y_data, label, plot_settings=None, use_automatic_line_colors=False, use_default_points=False, x_scale="linear", y_scale="linear" ):
    """
    Apply plot settings to a single plot.

    Parameters:
    - ax: Matplotlib axis object
    - x_data: X-axis data
    - y_data: Y-axis data
    - label: Plot label
    - plot_settings: Dictionary containing plot styling parameters
    - use_automatic_line_colors: Boolean to enable automatic color cycling
    - use_default_points: Boolean to use default point styling
    - x_scale, y_scale: unused here — kept as parameters for call-site
      compatibility, but NOT applied per-call anymore (see below). Callers
      set these ONCE on the axes before looping over spectra instead.
    """
    # Start with default settings
    settings = get_default_plot_settings()
    
    # Update with provided settings if any
    if plot_settings is not None:
        settings.update(plot_settings)

    # NOTE: ax.set_xscale(x_scale) / ax.set_yscale(y_scale) used to be
    # called HERE — once per SPECTRUM, i.e. once per call to this
    # function — even though the scale is the same for every spectrum in
    # a single plot. Confirmed by profiling: setting an axis scale isn't
    # a cheap no-op even when the value doesn't change (it invalidates
    # tick locators/formatters internally), and this cost was being paid
    # redundantly hundreds or thousands of times for a large overlay
    # plot. Callers (overlay_plot_mode, grid_plot_mode) now set this
    # ONCE on the axes before their per-spectrum loop instead.

    # When default points is enabled, use the predefined point style regardless of custom settings
    if use_default_points:
        marker = 'o'  # circle marker
    else:
        # Convert 'None' string to None for marker
        marker = None if settings['marker'] == 'None' else settings['marker']

    # Plot line
    plot_kwargs = {
        'label': label,
        'linestyle': settings['linestyle'],
        'linewidth': settings['linewidth']
    }
    
    # Only set color if not using automatic colors
    if not use_automatic_line_colors:
        plot_kwargs['color'] = settings['linecolor']

    line = ax.plot(x_data, y_data, **plot_kwargs)

    # Plot markers if specified or if default points are enabled
    if marker is not None or use_default_points:
        marker_kwargs = {
            'label': None,  # Avoid duplicate labels for markers
            'linestyle': 'None',
        }
        
        if use_default_points:
            # Use default point settings
            marker_kwargs.update({
                'marker': 'o',  # circle marker
                'markersize': 6,
                'markeredgecolor': 'black',
                'markeredgewidth': 0.6,
                'markerfacecolor': 'none'  # No face color
            })
        else:
            # Use custom settings
            marker_kwargs.update({
                'marker': marker,
                'markersize': settings['markersize'],
                'markeredgecolor': settings['markeredgecolor'],
                'markeredgewidth': settings['markeredgewidth'],
                'markerfacecolor': settings['markerfacecolor']
            })
        
        # Only set color if not using automatic colors
        if not use_automatic_line_colors and not use_default_points:
            marker_kwargs['color'] = settings['linecolor']
        elif use_default_points and use_automatic_line_colors:
            # For default points with automatic colors, get the color from the line
            marker_kwargs['color'] = line[0].get_color()
            
        ax.plot(x_data, y_data, **marker_kwargs)        
    
def apply_all_plot_properties(ax, grid_manager=None, legend_manager=None,
                              axis_manager=None, constrained_layout_manager=None,
                              band_marker_manager=None):
    """
    Apply all plot properties (axis, legend, grid, band markers) to the given axis.
    
    Args:
        ax: Matplotlib axis object
        grid_manager: Optional GridManager instance to use
        legend_manager: Optional LegendManager instance to use
        axis_manager: Optional AxisManager instance to use
        band_marker_manager: Optional BandMarkerManager instance to use
    """
    apply_axis_settings(ax, axis_manager)
    apply_legend_settings(ax, legend_manager)
    apply_grid_settings(ax, grid_manager)

    if band_marker_manager is not None:
        band_marker_manager.apply_to_axes(ax)

    # Apply constrained layout settings to the figure if manager is provided
    if constrained_layout_manager is not None:
        constrained_layout_manager.apply_settings_to_figure(ax.figure)

def apply_legend_settings(ax, legend_manager=None):
    """
    Apply stored legend settings to the axis.
    
    Args:
        ax: Matplotlib axis object
        legend_manager: Optional LegendManager instance to use. If None, a new one is created.
    """
    # Use the provided legend_manager or create a new one
    if legend_manager is None:
        legend_manager = LegendManager()
        
    legend_manager.apply_settings_to_legend(ax)

def apply_axis_settings(ax, axis_manager=None):
    """
    Apply stored axis settings to the given axis.
    
    Args:
        ax: Matplotlib axis object
        axis_manager: Optional AxisManager instance to use. If None, a new one is created.
    """
    # Use the provided axis_manager or create a new one
    if axis_manager is None:
        axis_manager = AxisManager()
    
    axis_manager.apply_settings_to_axis(ax)    

def apply_grid_settings(ax, grid_manager=None):
    """
    Apply stored grid settings to the axis.
    
    Args:
        ax: Matplotlib axis object
        grid_manager: Optional GridManager instance to use. If None, a new one is created.
    """
    # Use the provided grid_manager or create a new one
    if grid_manager is None:
        grid_manager = GridManager()
    
    grid_manager.apply_settings_to_grid(ax)
 
def overlay_plot_mode(graphics_view, spectra, plot_settings=None, use_automatic_line_colors=False,
                      use_default_points=False, x_scale="linear", y_scale="linear",
                      grid_manager=None, legend_manager=None, axis_manager=None,
                      constrained_layout_manager=None, band_marker_manager=None,
                      progress_callback=None, display_labels=None):
    """
    Sets up the 'Overlay Plot Mode' where all spectra are plotted on a single axis.

    Parameters:
    - graphics_view: The widget where the plot will be displayed.
    - spectra: List of dictionaries, each containing 'x_scale', 'y_scale', and optionally 'label'.
    - plot_settings: Dictionary containing plot styling parameters for each spectrum
    - use_automatic_line_colors: Boolean to enable automatic color cycling
    - use_default_points: Boolean to use default point styling
    - x_scale: Scale type for x-axis ('linear', 'log', 'symlog', 'logit')
    - y_scale: Scale type for y-axis ('linear', 'log', 'symlog', 'logit')
    - grid_manager: Optional GridManager instance to use for grid settings
    - legend_manager: Optional LegendManager instance to use for legend settings
    - axis_manager: Optional AxisManager instance to use for axis settings
    - progress_callback: Optional callable, invoked periodically (every 50
      spectra) during the per-spectrum plotting loop below. Purely a hook —
      this module has no Qt-event-loop awareness of its own and doesn't need
      any; a caller showing a progress dialog can pass e.g.
      `lambda: QApplication.processEvents()` here so the dialog's busy
      animation can actually animate during a large plot, instead of the
      event loop being frozen for the whole duration of this one call (which
      is otherwise a single long blocking loop from Qt's perspective, no
      matter how fast each individual line is to plot). None (the default)
      means exactly today's behavior — nothing extra happens.
    - display_labels: Optional {full_label: display_label} map (see
      src/modules/utils/label_shortening.py) used ONLY for the legend text
      drawn here — mirrors the main spectra list's "shorten names" checkbox.
      Purely cosmetic: spectrum['label'] itself, plot_settings lookups (keyed
      by spectrum_key, unaffected), and everything else about the spectrum
      are completely untouched. None (the default) means full labels, same
      as before this parameter existed.
    """
    # Initialize the plot widget
    fig, canvas, toolbar = initialize_plot_widget(graphics_view)

    # Apply constrained layout settings if manager is provided
    if constrained_layout_manager:
        constrained_layout_manager.apply_settings_to_figure(fig)
    else:
        # Default behavior if no manager is provided
        fig.set_constrained_layout(True)

    # Create a single axis for overlay plot
    ax = fig.add_subplot(111)

    # Set once, not per spectrum inside the loop below — see
    # apply_plot_settings' docstring for why that was wasted, repeated
    # work at scale.
    ax.set_xscale(x_scale)
    ax.set_yscale(y_scale)

    # Plot each spectrum on the same axis with settings
    for i, spectrum in enumerate(spectra):
        
        spectrum_label = spectrum.get('label', "Spectrum")
        if display_labels:
            spectrum_label = display_labels.get(spectrum_label, spectrum_label)
        spectrum_settings = plot_settings.get(spectrum_key(spectrum)) if plot_settings else None

        apply_plot_settings(
            ax,
            spectrum['x_scale'],
            spectrum['y_scale'],
            spectrum_label,
            spectrum_settings,
            use_automatic_line_colors,
            use_default_points,
            x_scale,
            y_scale
        )

        # Every 50 spectra, not every single one — frequent enough that a
        # progress dialog's busy animation still looks smooth, infrequent
        # enough to keep the overhead (and the window, how often something
        # else could sneak in via a fully pumped event queue) small.
        notify_progress(progress_callback, i)

    # Legend creation is handled by apply_all_plot_properties below (via
    # LegendManager.apply_settings_to_legend) — that function builds its
    # OWN legend from scratch when needed, using a fast fixed position
    # and truncating to max_items, and respects the visible setting
    # (legends are off by default). A standalone ax.legend() here used
    # to run first regardless — with no loc specified, that defaults to
    # loc='best', which does an expensive collision-search that scales
    # badly with the number of lines/legend entries (matplotlib itself
    # warns about this for large datasets), building every entry
    # untrimmed — all of which was then either discarded and rebuilt, or
    # simply hidden, by the very next call. Confirmed by profiling: pure
    # wasted work, safe to remove outright.
    apply_all_plot_properties(ax, grid_manager, legend_manager, axis_manager,
                              band_marker_manager=band_marker_manager)

    # Redraw the canvas
    canvas.draw()

    return canvas, toolbar

def initialize_plot_widget(graphics_view):
    """
    Clears any existing layout in graphics_view and initializes a fresh Figure, Canvas, and Toolbar.
    """
    # Clear any existing layout from the graphicsView
    if graphics_view.layout():
        QWidget().setLayout(graphics_view.layout())

    # Create a new layout for the graphics_view
    layout = QVBoxLayout(graphics_view)
    layout.setContentsMargins(0, 0, 0, 0)

    # Initialize figure, canvas, and toolbar
    fig = Figure()
    canvas = FigureCanvas(fig)
    toolbar = NavigationToolbar(canvas, graphics_view)

    # Add the canvas and toolbar to the layout
    layout.addWidget(canvas)
    layout.addWidget(toolbar)

    # Set the new layout to the graphicsView
    graphics_view.setLayout(layout)

    return fig, canvas, toolbar

def grid_plot_mode(graphics_view, spectra, nrows=1, ncols=1,
                  link_x_axes_direction="all", link_y_axes_direction="all",
                  plot_settings=None, use_automatic_line_colors=False, use_default_points=False,
                  x_scale="linear", y_scale="linear", grid_manager=None,
                  legend_manager=None, axis_manager=None, constrained_layout_manager=None,
                  band_marker_manager=None, progress_callback=None, display_labels=None):
    """
    Sets up the 'Grid Plot Mode' with a dynamic grid of subplots in the graphics_view.

    Parameters:
    - graphics_view: The widget where the plots will be displayed.
    - spectra: List of dictionaries, each containing 'x_scale', 'y_scale', and optionally 'label'.
    - nrows: Number of rows in the subplot grid.
    - ncols: Number of columns in the subplot grid.
    - link_x_axes_direction: Direction for linking x-axes ("all", "row", "col", "none")
    - link_y_axes_direction: Direction for linking y-axes ("all", "row", "col", "none")
    - plot_settings: Dictionary containing plot styling parameters
    - use_automatic_line_colors: Boolean to enable automatic color cycling
    - use_default_points: Boolean to use default point styling
    - x_scale: Scale type for x-axis ('linear', 'log', 'symlog', 'logit')
    - y_scale: Scale type for y-axis ('linear', 'log', 'symlog', 'logit')
    - grid_manager: Optional GridManager instance to use for grid settings
    - legend_manager: Optional LegendManager instance to use for legend settings
    - axis_manager: Optional AxisManager instance to use for axis settings
    - progress_callback: Optional callable, invoked periodically during the
      per-subplot loop below — see overlay_plot_mode's docstring for the
      full reasoning; same hook, same default (None = today's behavior).
    - display_labels: Optional {full_label: display_label} map — see
      overlay_plot_mode's docstring; same purely-cosmetic legend-text-only
      behavior here.
    """
    # Initialize the plot widget
    fig, canvas, toolbar = initialize_plot_widget(graphics_view)

    # Apply constrained layout settings if manager is provided
    if constrained_layout_manager:
        constrained_layout_manager.apply_settings_to_figure(fig)
    else:
        # Default behavior if no manager is provided
        fig.set_constrained_layout(True)

    # Create subplot axes based on linking strategy
    axs = create_linked_subplots(fig, nrows, ncols, link_x_axes_direction, link_y_axes_direction)

    # Flatten the axes array for easy iteration
    axs = np.array(axs).flatten()

    # Plot spectra with settings
    num_spectra = len(spectra)
    for i, ax in enumerate(axs):
        if i < num_spectra:  # Plot the spectrum if within the number of spectra

            spectrum = spectra[i]
            spectrum_label = spectrum.get('label', f"Spectrum {i+1}")
            if display_labels:
                spectrum_label = display_labels.get(spectrum_label, spectrum_label)
            spectrum_settings = plot_settings.get(spectrum_key(spectrum)) if plot_settings else None
            
            apply_plot_settings(
                ax,
                spectrum['x_scale'],
                spectrum['y_scale'],
                spectrum_label,
                spectrum_settings,
                use_automatic_line_colors,
                use_default_points,
                x_scale,
                y_scale
            )
            # See overlay_plot_mode's comment for why the eager
            # ax.legend() call that used to sit here was removed —
            # apply_all_plot_properties (below) already builds the
            # legend correctly via LegendManager when one is actually
            # wanted.
            apply_all_plot_properties(ax, grid_manager, legend_manager, axis_manager,
                                      band_marker_manager=band_marker_manager)
        else:  # Hide unused subplots
            ax.set_visible(False)

        notify_progress(progress_callback, i)

    # Redraw the canvas
    canvas.draw()

    return canvas, toolbar

def create_linked_subplots(fig, nrows, ncols, link_x_axes_direction, link_y_axes_direction):
    """
    Create subplots with the specified axis linking configuration.
    """
    linking_configs = {
        ("all", "all"): {"sharex": True, "sharey": True},
        ("all", "none"): {"sharex": True, "sharey": False},
        ("none", "all"): {"sharex": False, "sharey": True},
        ("row", "row"): {"sharex": "row", "sharey": "row"},
        ("col", "col"): {"sharex": "col", "sharey": "col"},
        ("all", "row"): {"sharex": True, "sharey": "row"},
        ("all", "col"): {"sharex": True, "sharey": "col"},
        ("row", "all"): {"sharex": "row", "sharey": True},
        ("col", "all"): {"sharex": "col", "sharey": True},
        ("row", "col"): {"sharex": "row", "sharey": "col"},
        ("col", "row"): {"sharex": "col", "sharey": "row"},
        ("none", "row"): {"sharex": False, "sharey": "row"},
        ("none", "col"): {"sharex": False, "sharey": "col"},
        ("row", "none"): {"sharex": "row", "sharey": False},
        ("col", "none"): {"sharex": "col", "sharey": False},
        ("none", "none"): {"sharex": False, "sharey": False}
    }

    config = linking_configs.get(
        (link_x_axes_direction, link_y_axes_direction),
        {"sharex": False, "sharey": False}  # Default if combination not found
    )

    return fig.subplots(nrows, ncols, **config)

_PLOT_COLORS = [
    '#1f77b4', '#d62728', '#2ca02c', '#ff7f0e',
    '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
]


def waterfall_plot_mode(
    graphics_view,
    spectra,
    offset=None,
    plot_settings=None,
    use_automatic_line_colors=True,
    x_scale='linear',
    y_scale='linear',
    legend_manager=None,
    axis_manager=None,
    display_labels=None,
    **kwargs,
):
    """
    Waterfall (stacked offset) plot mode.

    Each spectrum is shifted upward by a fixed y-offset relative to the
    previous one, producing the classic stacked display used to compare
    spectral series.

    Parameters
    ----------
    graphics_view : QWidget
        Container widget (same role as in overlay_plot_mode).
    spectra : list of dict
        Each dict must have 'x_scale', 'y_scale', and 'label'.
    offset : float or None
        Y offset between consecutive spectra in data units.
        None / 0 → auto: 10 % of the peak-to-peak range of the largest
        spectrum in the selection.
    plot_settings : dict, optional
        Per-spectrum style overrides keyed by label.
    use_automatic_line_colors : bool
        Cycle through _PLOT_COLORS when True.
    x_scale, y_scale : str
        Axis scale type ('linear', 'log', etc.).
    legend_manager, axis_manager : optional
        Applied after drawing (same pattern as overlay_plot_mode).
    display_labels : dict, optional
        {full_label: display_label} map — see overlay_plot_mode's docstring;
        same purely-cosmetic legend-text-only behavior here.

    Returns
    -------
    (FigureCanvas, NavigationToolbar)
    """
    if plot_settings is None:
        plot_settings = {}

    # Auto offset: 10 % of the largest peak-to-peak range
    if not offset:
        max_range = max(
            (float(np.ptp(np.asarray(s.get('y_scale', []), dtype=float)))
             for s in spectra
             if len(s.get('y_scale', []))),
            default=1.0,
        )
        offset = max_range * 0.10 if max_range > 0 else 1.0

    fig, canvas, toolbar = initialize_plot_widget(graphics_view)
    fig.set_constrained_layout(True)
    ax = fig.add_subplot(111)

    cumulative_offset = 0.0
    for i, spectrum in enumerate(spectra):
        x = np.asarray(spectrum.get('x_scale', []), dtype=float)
        y = np.asarray(spectrum.get('y_scale', []), dtype=float)
        if not len(x):
            cumulative_offset += offset
            continue

        label = spectrum.get('label', f'Spectrum {i + 1}')
        if display_labels:
            label = display_labels.get(label, label)
        sp    = (plot_settings.get(spectrum_key(spectrum)) or {})
        color = (_PLOT_COLORS[i % len(_PLOT_COLORS)] if use_automatic_line_colors
                 else sp.get('linecolor', _PLOT_COLORS[i % len(_PLOT_COLORS)]))
        lw    = sp.get('linewidth', 1.0)
        ls    = sp.get('linestyle', '-')

        ax.plot(x, y + cumulative_offset, color=color, lw=lw, ls=ls,
                alpha=0.90, label=label)
        cumulative_offset += offset

    ax.set_xlabel('x', fontsize=10)
    ax.set_ylabel('Intensity  (offset)', fontsize=10)
    ax.set_title(f'Waterfall plot  —  {len(spectra)} spectra', fontsize=11)

    try:
        ax.set_xscale(x_scale)
    except Exception:
        ax.set_xscale('linear')

    band_marker_manager = kwargs.get("band_marker_manager", None)
    apply_all_plot_properties(ax, legend_manager=legend_manager,
                              axis_manager=axis_manager,
                              band_marker_manager=band_marker_manager)
    canvas.draw()
    return canvas, toolbar


def mean_sd_plot_mode(
    graphics_view,
    spectra,
    show_individual=True,
    plot_settings=None,
    use_automatic_line_colors=True,
    x_scale='linear',
    y_scale='linear',
    legend_manager=None,
    axis_manager=None,
    **kwargs,
):
    """
    Mean ± 1 SD plot mode.

    Draws the mean spectrum as a thick line with a shaded ±1 SD band.
    Individual spectra can be shown as thin semi-transparent lines behind
    the mean.

    All selected spectra must share the same x-axis length.  If lengths
    differ, only spectra matching the most common length are included and
    a warning is shown in the plot title.

    Parameters
    ----------
    graphics_view : QWidget
        Container widget.
    spectra : list of dict
        Each dict must have 'x_scale', 'y_scale', and 'label'.
    show_individual : bool
        Draw individual spectra as thin faded lines when True.
    plot_settings : dict, optional
        Per-spectrum style overrides (used for individual line colours).
    use_automatic_line_colors : bool
        Cycle through _PLOT_COLORS for individual lines when True.
    x_scale, y_scale : str
        Axis scale type.
    legend_manager, axis_manager : optional
        Applied after drawing.

    Returns
    -------
    (FigureCanvas, NavigationToolbar)
    """
    from collections import Counter
    if plot_settings is None:
        plot_settings = {}

    fig, canvas, toolbar = initialize_plot_widget(graphics_view)
    fig.set_constrained_layout(True)
    ax = fig.add_subplot(111)

    if not spectra:
        ax.text(0.5, 0.5, 'No spectra selected.',
                transform=ax.transAxes, ha='center', va='center', color='grey')
        canvas.draw()
        return canvas, toolbar

    # Keep only spectra whose x-axis length matches the most common length
    lengths    = [len(s.get('x_scale', [])) for s in spectra]
    common_len = Counter(lengths).most_common(1)[0][0]
    valid      = [s for s in spectra if len(s.get('x_scale', [])) == common_len]
    skipped    = len(spectra) - len(valid)

    x_ref  = np.asarray(valid[0]['x_scale'], dtype=float)
    y_mat  = np.vstack([np.asarray(s['y_scale'], dtype=float) for s in valid])
    y_mean = np.mean(y_mat, axis=0)
    y_sd   = (np.std(y_mat, axis=0, ddof=1)
              if len(valid) > 1 else np.zeros_like(y_mean))

    # Individual spectra — thin, faded
    if show_individual:
        for i, s in enumerate(valid):
            sp    = (plot_settings.get(spectrum_key(s)) or {})
            color = (_PLOT_COLORS[i % len(_PLOT_COLORS)] if use_automatic_line_colors
                     else sp.get('linecolor', _PLOT_COLORS[i % len(_PLOT_COLORS)]))
            ax.plot(x_ref, np.asarray(s['y_scale'], dtype=float),
                    color=color, lw=0.8, alpha=0.28, zorder=1)

    # ±1 SD shaded band
    ax.fill_between(x_ref, y_mean - y_sd, y_mean + y_sd,
                    color='#1565C0', alpha=0.18, zorder=2, label='±1 SD')

    # Mean line
    ax.plot(x_ref, y_mean, color='#1565C0', lw=2.2, zorder=3,
            label=f'Mean (n = {len(valid)})')

    ax.set_xlabel('x', fontsize=10)
    ax.set_ylabel('Intensity', fontsize=10)
    title = f'Mean ± SD  —  {len(valid)} spectra'
    if skipped:
        title += f'  (⚠ {skipped} skipped: x-axis length mismatch)'
    ax.set_title(title, fontsize=11)

    try:
        ax.set_xscale(x_scale)
        ax.set_yscale(y_scale)
    except Exception:
        pass

    ax.legend(fontsize=9, loc='best')
    band_marker_manager = kwargs.get("band_marker_manager", None)
    apply_all_plot_properties(ax, legend_manager=legend_manager,
                              axis_manager=axis_manager,
                              band_marker_manager=band_marker_manager)
    canvas.draw()
    return canvas, toolbar

def difference_plot_mode(
    graphics_view,
    spectra,
    ref_label=None,
    hide_reference=False,
    plot_settings=None,
    use_automatic_line_colors=True,
    x_scale='linear',
    y_scale='linear',
    legend_manager=None,
    axis_manager=None,
    display_labels=None,
    **kwargs,
):
    """
    Difference plot mode.

    Subtracts a reference from every selected spectrum and plots the residuals
    on a single axes.  The reference is either:

    * A specific spectrum selected by label (one of the selected spectra)
    * "Mean" (or None / unrecognised label) — the group mean is subtracted

    Spectra whose x-axis length does not match the most common length are
    skipped and noted in the title.  The reference itself is shown as a
    zero line.

    Parameters
    ----------
    graphics_view : QWidget
    spectra       : list of spectrum dicts
    ref_label     : str or None  — label of the reference spectrum, or "Mean"
    plot_settings, use_automatic_line_colors, x_scale, y_scale,
    legend_manager, axis_manager : same as overlay_plot_mode
    display_labels : dict, optional — {full_label: display_label} map, see
        overlay_plot_mode's docstring. Applied only to legend text (the
        per-line "label=" and the "Reference: ..." entry) — ref_label
        matching against spectrum['label'] to pick out the reference
        spectrum stays on full labels, unaffected.

    Returns
    -------
    (FigureCanvas, NavigationToolbar)
    """
    from collections import Counter
    if plot_settings is None:
        plot_settings = {}

    fig, canvas, toolbar = initialize_plot_widget(graphics_view)
    fig.set_constrained_layout(True)
    ax = fig.add_subplot(111)

    if not spectra:
        ax.text(0.5, 0.5, 'No spectra selected.',
                transform=ax.transAxes, ha='center', va='center', color='grey')
        canvas.draw()
        return canvas, toolbar

    # Filter to most common x-axis length
    lengths    = [len(s.get('x_scale', [])) for s in spectra]
    common_len = Counter(lengths).most_common(1)[0][0]
    valid      = [s for s in spectra if len(s.get('x_scale', [])) == common_len]
    skipped    = len(spectra) - len(valid)

    x_ref = np.asarray(valid[0]['x_scale'], dtype=float)
    y_mat = np.vstack([np.asarray(s['y_scale'], dtype=float) for s in valid])

    # Determine the reference vector
    use_mean = (not ref_label) or (ref_label == 'Mean')
    if not use_mean:
        ref_matches = [s for s in valid if s['label'] == ref_label]
        use_mean    = len(ref_matches) == 0
    ref_vec     = (np.mean(y_mat, axis=0) if use_mean
                   else np.asarray(ref_matches[0]['y_scale'], dtype=float))
    ref_display = 'group mean' if use_mean else ref_label
    if display_labels:
        ref_display = display_labels.get(ref_display, ref_display)

    # Show reference spectrum unless hidden
    if not hide_reference:
        ax.plot(x_ref, ref_vec, color='#333', lw=1.5, ls='--', alpha=0.75,
                zorder=1, label=f'Reference: {ref_display}')
        ax.axhline(0, color='#999', lw=0.8, ls=':', alpha=0.5, zorder=0)

    plotted = 0
    for i, s in enumerate(valid):
        if not use_mean and s['label'] == ref_label:
            continue   # skip the reference spectrum itself
        diff = np.asarray(s['y_scale'], dtype=float) - ref_vec
        sp   = (plot_settings.get(spectrum_key(s)) or {})
        col  = (_PLOT_COLORS[i % len(_PLOT_COLORS)] if use_automatic_line_colors
                else sp.get('linecolor', _PLOT_COLORS[i % len(_PLOT_COLORS)]))
        line_label = display_labels.get(s['label'], s['label']) if display_labels else s['label']
        ax.plot(x_ref, diff, color=col, lw=1.0, alpha=0.85,
                label=line_label, zorder=2)
        plotted += 1

    title = f'Difference plot  —  {plotted} spectra  (ref: {ref_display})'
    if skipped:
        title += f'  (⚠ {skipped} skipped: x-axis length mismatch)'
    ax.set_title(title, fontsize=11)
    ax.set_xlabel('x', fontsize=10)
    ax.set_ylabel('Intensity difference', fontsize=10)
    ax.legend(fontsize=8, loc='best')

    try:
        ax.set_xscale(x_scale)
        ax.set_yscale(y_scale)
    except Exception:
        pass

    band_marker_manager = kwargs.get("band_marker_manager", None)
    apply_all_plot_properties(ax, legend_manager=legend_manager,
                              axis_manager=axis_manager,
                              band_marker_manager=band_marker_manager)
    canvas.draw()
    return canvas, toolbar

def heatmap_plot_mode(
    graphics_view,
    spectra,
    colormap='viridis',
    interpolation='nearest',
    aspect='auto',
    x_scale='linear',
    y_scale='linear',
    legend_manager=None,
    axis_manager=None,
    display_labels=None,
    **kwargs,
):
    """
    False-colour intensity heatmap (intensity image).

    x-axis  = wavenumber / x-scale of the spectra
    y-axis  = spectrum index (0 = first selected spectrum)
    colour  = intensity value, clipped to 2nd–98th percentile to ensure
              spectral features are visible even with a large background.
    """
    if not spectra:
        return None, None

    fig, canvas, toolbar = initialize_plot_widget(graphics_view)
    fig.set_constrained_layout(True)
    ax = fig.add_subplot(111)

    # Build common x-grid from first spectrum (sort ascending)
    x_ref = np.asarray(spectra[0].get('x_scale', []), dtype=float)
    if len(x_ref) > 1 and x_ref[0] > x_ref[-1]:
        x_ref = x_ref[::-1]

    rows = []
    for s in spectra:
        x = np.asarray(s.get('x_scale', []), dtype=float)
        y = np.asarray(s.get('y_scale', []), dtype=float)
        if len(x) < 2:
            rows.append(np.zeros_like(x_ref))
            continue
        if x[0] > x[-1]:
            x, y = x[::-1], y[::-1]
        rows.append(np.interp(x_ref, x, y))

    matrix = np.array(rows)   # shape: (n_spectra, n_points)

    # Clip to 2nd–98th percentile so background doesn't dominate colour scale
    vmin = float(np.percentile(matrix, 2))
    vmax = float(np.percentile(matrix, 98))
    if vmin >= vmax:
        vmin, vmax = float(matrix.min()), float(matrix.max())

    x_min, x_max = float(x_ref[0]), float(x_ref[-1])
    n_spectra = len(spectra)

    im = ax.imshow(
        matrix,
        aspect=aspect,
        origin='upper',
        extent=[x_min, x_max, n_spectra - 0.5, -0.5],
        cmap=colormap,
        interpolation=interpolation,
        vmin=vmin,
        vmax=vmax,
    )

    fig.colorbar(im, ax=ax, label='Intensity', fraction=0.03, pad=0.02)

    # Y-axis: show ~20 labels for ≤200 spectra, ~10 index numbers for >200
    if n_spectra <= 200:
        step = max(1, n_spectra // 20)
        ticks = list(range(0, n_spectra, step))
        ax.set_yticks(ticks)
        def _tick_label(t):
            lbl = spectra[t].get('label', str(t + 1))
            return display_labels.get(lbl, lbl) if display_labels else lbl

        ax.set_yticklabels(
            [_tick_label(t) for t in ticks],
            fontsize=max(5, 8 - max(0, step - 1))
        )
    else:
        step = max(1, n_spectra // 10)
        ticks = list(range(0, n_spectra, step))
        ax.set_yticks(ticks)
        ax.set_yticklabels([str(t + 1) for t in ticks], fontsize=7)

    ax.set_xlabel('x', fontsize=10)
    ax.set_ylabel('Spectrum index', fontsize=10)
    ax.set_title(
        f'Intensity heatmap  —  {n_spectra} spectra'
        f'  (colour range: {vmin:.3g} – {vmax:.3g})',
        fontsize=10
    )

    apply_all_plot_properties(ax, legend_manager=legend_manager,
                              axis_manager=axis_manager,
                              band_marker_manager=kwargs.get("band_marker_manager"))
    canvas.draw()
    return canvas, toolbar

