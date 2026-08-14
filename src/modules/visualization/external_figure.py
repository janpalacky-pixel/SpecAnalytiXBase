# src/modules/visualization/external_figure.py
"""
Open the current plot in a standalone external matplotlib window.

Uses the same plot-mode functions as the main window by creating a
temporary off-screen QWidget as the graphics_view recipient, then
detaching the resulting figure and showing it via plt.show(block=False).
"""

import matplotlib
import matplotlib.pyplot as plt
from PyQt5.QtWidgets import QWidget

from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import shorten_spectra_labels
logger = get_logger(__name__)


def create_external_figure(mc):
    """
    Replicate the current main-window plot in a new standalone window.

    Parameters
    ----------
    mc : MainController
    """
    if not mc.selected_spectra:
        return

    from src.modules.visualization.plotting import (
        overlay_plot_mode, grid_plot_mode, waterfall_plot_mode,
        mean_sd_plot_mode, difference_plot_mode, heatmap_plot_mode,
    )

    plot_type   = mc.view.comboBox_plot_type_choice.currentText()
    spectra     = list(mc.selected_spectra)
    settings    = mc.custom_plot_properties_manager.spectrum_properties
    use_auto    = mc.use_automatic_line_colors      # authoritative stored value
    use_pts     = mc.use_default_points
    x_scale     = mc.view.x_scale_comboBox.currentText()
    y_scale     = mc.view.y_scale_comboBox.currentText()
    legend_mgr  = getattr(mc, 'legend_manager',           None)
    axis_mgr    = getattr(mc, 'axis_manager',             None)
    grid_mgr    = getattr(mc, 'grid_manager',             None)
    band_mgr    = getattr(mc, 'band_marker_manager',      None)
    cl_mgr      = getattr(mc, 'constrained_layout_manager', None)

    if plot_type == 'Single spectrum':
        sel = mc.spectra_list_widget.selectedItems()
        if sel:
            spectra = [mc.original_spectra[mc.spectra_list_widget.row(sel[0])]]
        else:
            spectra = spectra[:1]

    # Use a throw-away off-screen widget as the graphics_view recipient
    tmp = QWidget()

    # Legend text only — mirrors the main window's "shorten names"
    # checkbox, same as _plot_spectra_impl in main_controller.py.
    shorten_enabled = getattr(mc, 'checkBox_shorten_names', None)
    shorten_enabled = shorten_enabled.isChecked() if shorten_enabled is not None else False
    display_labels = shorten_spectra_labels(spectra, shorten_enabled)

    common = dict(
        plot_settings            = settings,
        use_automatic_line_colors = use_auto,
        use_default_points       = use_pts,
        x_scale                  = x_scale,
        y_scale                  = y_scale,
        legend_manager           = legend_mgr,
        axis_manager             = axis_mgr,
        band_marker_manager      = band_mgr,
        display_labels           = display_labels,
    )

    try:
        if plot_type == 'Grid plot':
            gs = mc.grid_settings
            lx = (mc.view.comboBox_linking_x_axes.currentText()
                  if mc.view.link_x_axes_checkBox.isChecked() else 'none')
            ly = (mc.view.comboBox_linking_y_axes.currentText()
                  if mc.view.link_y_axes_checkBox.isChecked() else 'none')
            canvas, _ = grid_plot_mode(
                tmp, spectra,
                nrows=gs['rows'], ncols=gs['columns'],
                link_x_axes_direction=lx,
                link_y_axes_direction=ly,
                grid_manager=grid_mgr,
                **common,
            )

        elif plot_type == 'Waterfall plot':
            offset = mc.view.waterfall_offset_spinBox.value()
            canvas, _ = waterfall_plot_mode(
                tmp, spectra,
                offset=offset if offset > 0 else None,
                **{k: v for k, v in common.items()
                   if k not in ('use_default_points',)},
            )

        elif plot_type == 'Mean \u00b1 SD':
            show_ind = mc.view.mean_sd_show_individual_checkBox.isChecked()
            canvas, _ = mean_sd_plot_mode(
                tmp, spectra,
                show_individual=show_ind,
                **{k: v for k, v in common.items()
                   if k not in ('use_default_points',)},
            )

        elif plot_type == 'Difference':
            ref_lbl  = (mc.view.difference_reference_comboBox.currentText()
                        if hasattr(mc.view, 'difference_reference_comboBox')
                        else '')
            hide_ref = (not mc.view.difference_show_ref_checkBox.isChecked()
                        if hasattr(mc.view, 'difference_show_ref_checkBox')
                        else False)
            canvas, _ = difference_plot_mode(
                tmp, spectra,
                ref_label=ref_lbl,
                hide_reference=hide_ref,
                **{k: v for k, v in common.items()
                   if k not in ('use_default_points',)},
            )

        elif plot_type == 'Heatmap':
            colormap = mc.view.heatmap_colormap_comboBox.currentText()
            interp   = mc.view.heatmap_interpolation_comboBox.currentText()
            canvas, _ = heatmap_plot_mode(
                tmp, spectra,
                colormap=colormap,
                interpolation=interp,
                **{k: v for k, v in common.items()
                   if k not in ('use_default_points',
                                'use_automatic_line_colors',
                                'plot_settings')},
            )

        else:  # Overlay / Single spectrum
            canvas, _ = overlay_plot_mode(
                tmp, spectra,
                grid_manager=grid_mgr,
                **common,
            )

    except Exception as exc:
        logger.error("create_external_figure: plot failed: %s", exc)
        import traceback; traceback.print_exc()
        return

    if canvas is None:
        logger.warning("create_external_figure: canvas is None")
        return

    # ── Detach figure from Qt and show in standalone window ───────────────
    fig = canvas.figure

    # Apply constrained layout manager if available
    if cl_mgr is not None:
        try:
            cl_mgr.apply_settings_to_figure(fig)
        except Exception:
            pass

    # Only call tight_layout when no colorbar / constrained-layout engine active
    engine = fig.get_layout_engine()
    has_colorbar_engine = (engine is not None and
                           type(engine).__name__ != 'TightLayoutEngine' and
                           type(engine).__name__ != 'PlaceHolderLayoutEngine')
    if not has_colorbar_engine:
        try:
            fig.tight_layout()
        except Exception:
            pass

    # Detach from the temporary widget's layout and re-show via pyplot
    figure_count = len(plt.get_fignums()) + 1

    # Create a new pyplot-managed figure and copy our axes into it
    new_fig = plt.figure(figsize=fig.get_size_inches())
    new_manager = new_fig.canvas.manager

    # Transfer axes
    for ax in fig.get_axes():
        ax.figure = new_fig
        new_fig.add_axes(ax)
    new_fig.set_facecolor(fig.get_facecolor())

    # Set window title
    title = f'Figure {figure_count}: {plot_type}'
    try:
        new_manager.set_window_title(title)
    except AttributeError:
        try:
            new_manager.window.setWindowTitle(title)
        except Exception:
            pass

    new_fig.canvas.draw()
    plt.show(block=False)
    logger.info("create_external_figure: opened '%s'", plot_type)
    return new_fig
