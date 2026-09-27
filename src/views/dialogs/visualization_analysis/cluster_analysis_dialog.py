# src/views/dialogs/visualization_analysis/cluster_analysis_dialog.py

import numpy as np
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, 
                            QSpinBox, QLabel, QPushButton, QDialogButtonBox,
                            QSplitter, QWidget, QMessageBox, QComboBox, 
                            QSizePolicy, QFileDialog, QListWidget, QDoubleSpinBox,
                            QListWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
                            QMenu, QAction, QTextEdit, QCheckBox, QScrollArea)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QEvent, QObject, QThread
from PyQt5.QtGui import QFont
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import make_shorten_names_checkbox
logger = get_logger(__name__)


def _shorten_for_display(enabled, labels):
    """
    Display-only "shorten names" pass for a list of spectrum labels.
    Shared by both ClusterAnalysisCanvas (plot point/leaf labels) and
    ClusterAnalysisDialog (the "Member Spectra:" text panel) so both stay
    consistent with each other.

    Returns a NEW list; never mutates manager.spectrum_labels or anything
    else cluster analysis still keys by full/original label (cluster
    membership, CSV/Excel export, silhouette data, etc.).

    enabled: plain bool — this dialog's OWN checkBox_shorten_names state,
    NOT the main window's. Each dialog has its own independent toggle (see
    label_shortening.make_shorten_names_checkbox); this function no longer
    reaches into a cluster_controller/main_controller chain to find one.
    """
    if not enabled:
        return list(labels)
    from src.modules.utils.label_shortening import compute_distinguishing_labels
    shortened = compute_distinguishing_labels(list(labels))
    return [shortened.get(lbl, lbl) for lbl in labels]

class _ViewportResizeFilter(QObject):
    """Event filter installed on the QScrollArea viewport.
    Fires the canvas redraw timer whenever the viewport is resized,
    which happens when the dialog window is resized by the user."""

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self._canvas = canvas

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            if self._canvas.visualization_mode == 'dendrogram':
                self._canvas._resize_timer.start(200)
        return False   # never consume the event


class ClusterAnalysisCanvas(FigureCanvas):
    """Canvas for cluster analysis visualization with interactive features."""
    
    # Signal emitted when cluster is clicked
    cluster_selected = pyqtSignal(int, list)  # cluster_id, member_indices
    
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(12, 8))
        super().__init__(self.fig)
        self.setParent(parent)
        
        self.cluster_controller = None
        self.visualization_mode = 'pca_2d'
        self.canvas_scroll = None   # set by create_canvas_panel after construction
        # Zero-arg callable, set by ClusterAnalysisDialog right after
        # constructing this canvas, returning the DIALOG's own (not the
        # main window's) checkBox_shorten_names.isChecked() — same
        # "callable handed down from dialog" convention used by
        # InteractiveSVDAnalysisCanvas.get_shorten_enabled.
        self.get_shorten_enabled = None
        self._elbow_cache_key = None
        self._elbow_cache_data = None

        # Debounce timer — redraws dendrogram 150 ms after the last resize event
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_settled)  # 'pca_2d', 'pca_3d', 'spectra', 'centroids', 'silhouette'
        
        # Interactive selection state
        self.interactive_mode = True
        self.highlighted_cluster = None
        self.original_colors = {}  # Store original colors for reset
        self.click_connection_id = None

    def leaveEvent(self, event):
        """Handle the mouse leaving the canvas.

        Deliberate override, not inherited behavior. matplotlib's own
        FigureCanvasQT.leaveEvent() unconditionally calls
        QApplication.restoreOverrideCursor() — it assumes matplotlib itself is
        the only thing that ever pushes a global override cursor. That's not
        true here: this dialog pushes its own override cursors (see
        ClusterAnalysisDialog.__init__, run_clustering's progress dialog, and
        on_method_changed's WaitCursor while replotting), and the code that
        opens this dialog may show it under its own "please wait" cursor too.
        If the mouse happens to be over this canvas while any of those is
        active, matplotlib's leaveEvent pops it early and desyncs the cursor
        stack — visible as a "busy" cursor that lingers regardless of actual
        state and only clears the next time the mouse crosses this canvas
        again. Reimplement the same hover-leave notification without the
        blind cursor pop. (Same fix as InteractiveSVDAnalysisCanvas in
        svd_analysis_dialog.py.)
        """
        if self.figure is not None:
            from matplotlib.backend_bases import LocationEvent
            LocationEvent("figure_leave_event", self, *self.mouseEventCoords(),
                          guiEvent=event)._process()

    def set_cluster_controller(self, controller):
        """Set the cluster controller."""
        self.cluster_controller = controller

    def _shortened(self, labels):
        """Display-only "shorten names" pass — see module-level
        _shorten_for_display() for the full explanation."""
        enabled = self.get_shorten_enabled() if self.get_shorten_enabled else False
        return _shorten_for_display(enabled, labels)

    def _on_resize_settled(self):
        """Called once the viewport has stopped being resized."""
        if self.visualization_mode == 'dendrogram' and self.cluster_controller:
            self.plot_clusters()
    
    def set_interactive_mode(self, enabled):
        """Enable/disable interactive cluster selection."""
        self.interactive_mode = enabled
        if enabled and self.visualization_mode in ['pca_2d', 'pca_3d']:
            self._connect_click_handler()
        else:
            self._disconnect_click_handler()
    
    def _connect_click_handler(self):
        """Connect mouse click handler for interactive selection."""
        if self.click_connection_id is None:
            self.click_connection_id = self.mpl_connect('button_press_event', self._on_click)
    
    def _disconnect_click_handler(self):
        """Disconnect mouse click handler."""
        if self.click_connection_id is not None:
            self.mpl_disconnect(self.click_connection_id)
            self.click_connection_id = None
    
    def _on_click(self, event):
        """Handle mouse click for cluster selection."""
        if not self.interactive_mode or not event.inaxes:
            return
            
        if self.visualization_mode == 'pca_2d':
            self._handle_pca_2d_click(event)
        elif self.visualization_mode == 'pca_3d':
            self._handle_pca_3d_click(event)
    
    def _handle_pca_2d_click(self, event):
        """Handle click on 2D PCA plot."""
        logger.debug(f"DEBUG: 2D click detected at ({event.xdata:.3f}, {event.ydata:.3f})")
        
        pca_data = self.cluster_controller.get_pca_data()
        if not pca_data or pca_data['components'].shape[1] < 2:
            logger.debug("DEBUG: No PCA data available for click handling")
            return
            
        components = pca_data['components']
        labels = pca_data['labels']
        
        logger.debug(f"DEBUG: Have {len(components)} data points")
        
        # Find nearest point to click
        distances = np.sqrt((components[:, 0] - event.xdata)**2 + 
                          (components[:, 1] - event.ydata)**2)
        
        # Check if click is reasonably close to a point
        min_distance = np.min(distances)
        data_range = np.max(components) - np.min(components)
        threshold = 0.1 * data_range  # 10% of data range
        
        logger.debug(f"DEBUG: Min distance = {min_distance:.3f}, threshold = {threshold:.3f}")
        
        if min_distance < threshold:
            nearest_idx = np.argmin(distances)
            clicked_cluster_id = labels[nearest_idx]
            
            logger.debug(f"DEBUG: Clicked on point {nearest_idx}, cluster {clicked_cluster_id}")
            
            # Get all members of this cluster
            member_indices = self.cluster_controller.get_cluster_members(clicked_cluster_id)
            logger.debug(f"DEBUG: Cluster {clicked_cluster_id} has {len(member_indices)} members")
            
            # Highlight the cluster
            self._highlight_cluster(clicked_cluster_id)
            
            # Emit signal with cluster info
            self.cluster_selected.emit(clicked_cluster_id, member_indices)
        else:
            logger.debug(f"DEBUG: Click too far from any point (distance {min_distance:.3f} > threshold {threshold:.3f})")
    
    def _handle_pca_3d_click(self, event):
        """Handle click on 3D PCA plot using screen coordinate approach."""
        logger.debug(f"DEBUG: === 3D CLICK (SCREEN METHOD) ===")
        
        if event.x is None or event.y is None:
            logger.debug("DEBUG: No screen coordinates available")
            return
            
        pca_data = self.cluster_controller.get_pca_data()
        if not pca_data or pca_data['components'].shape[1] < 3:
            logger.debug("DEBUG: No 3D PCA data available")
            return
            
        ax = self.fig.gca()
        if not hasattr(ax, 'zaxis'):
            logger.debug("DEBUG: Not a 3D axes")
            return
            
        components = pca_data['components']
        labels = pca_data['labels']
        
        logger.debug(f"DEBUG: Screen click at ({event.x}, {event.y})")
        logger.debug(f"DEBUG: Have {len(components)} data points")
        
        try:
            # For 3D axes, we need to use proj3d to transform coordinates
            from mpl_toolkits.mplot3d import proj3d
            
            # Project all 3D data points to screen coordinates
            screen_points = []
            for i, point_3d in enumerate(components):
                # Use proj3d to transform 3D point to 2D screen coordinates
                x2, y2, _ = proj3d.proj_transform(point_3d[0], point_3d[1], point_3d[2], ax.get_proj())
                
                # Convert to screen coordinates
                screen_x, screen_y = ax.transData.transform([[x2, y2]])[0]
                screen_points.append([screen_x, screen_y])
                
                if i < 3:  # Debug first few
                    logger.debug(f"DEBUG: Point {i} at ({point_3d[0]:.1f}, {point_3d[1]:.1f}, {point_3d[2]:.1f}) -> screen ({screen_x:.1f}, {screen_y:.1f})")
            
            screen_points = np.array(screen_points)
            click_screen = np.array([event.x, event.y])
            
            # Calculate distances in screen space (pixels)
            distances = np.sqrt(np.sum((screen_points - click_screen)**2, axis=1))
            
            min_distance = np.min(distances)
            nearest_idx = np.argmin(distances)
            nearest_cluster = labels[nearest_idx]
            
            logger.debug(f"DEBUG: Nearest point {nearest_idx} at screen distance {min_distance:.1f} pixels")
            logger.debug(f"DEBUG: Nearest point belongs to cluster {nearest_cluster}")
            
            # Use pixel threshold - reasonable clicking accuracy
            threshold = 50  # pixels
            
            if min_distance < threshold:
                logger.info(f"DEBUG: SUCCESS! Screen distance {min_distance:.1f} < {threshold} pixels")
                logger.debug(f"DEBUG: Selecting cluster {nearest_cluster}")
                
                member_indices = self.cluster_controller.get_cluster_members(nearest_cluster)
                logger.debug(f"DEBUG: Cluster {nearest_cluster} has {len(member_indices)} members")
                
                self._highlight_cluster(nearest_cluster)
                self.cluster_selected.emit(nearest_cluster, member_indices)
            else:
                logger.error(f"DEBUG: FAILED - Screen distance {min_distance:.1f} >= {threshold} pixels")
                logger.debug("DEBUG: Click was too far from any data point")
                
        except Exception as e:
            logger.error(f"DEBUG: 3D screen coordinate method failed: {e}")
            logger.exception("Traceback:")
            
        logger.debug(f"DEBUG: === 3D CLICK END ===")
    
    def _highlight_cluster(self, cluster_id):
        """Highlight a specific cluster and dim others."""
        if self.visualization_mode not in ['pca_2d', 'pca_3d']:
            return
            
        ax = self.fig.gca()
        if ax is None:
            return
            
        logger.debug(f"DEBUG: Highlighting cluster {cluster_id}")
        
        # Get PCA data and cluster info
        pca_data = self.cluster_controller.get_pca_data()
        if not pca_data:
            logger.debug("DEBUG: No PCA data available")
            return
            
        labels = pca_data['labels']
        unique_labels = np.unique(labels)
        
        logger.debug(f"DEBUG: Available clusters: {unique_labels}")
        logger.debug(f"DEBUG: Number of scatter collections: {len(ax.collections)}")
        
        # Store original properties if not already stored
        if not self.original_colors:
            logger.debug("DEBUG: Storing original colors")
            for i, collection in enumerate(ax.collections):
                self.original_colors[i] = {
                    'facecolors': collection.get_facecolors().copy(),
                    'alpha': collection.get_alpha() or 1.0,
                    'sizes': collection.get_sizes().copy() if hasattr(collection, 'get_sizes') else None
                }
        
        # FIRST: Reset all clusters to original state
        for i, collection in enumerate(ax.collections):
            if i in self.original_colors:
                original_data = self.original_colors[i]
                collection.set_facecolors(original_data['facecolors'])
                if original_data['sizes'] is not None:
                    collection.set_sizes(original_data['sizes'])
        
        # THEN: Dim all clusters (alpha=0.3)
        for i, collection in enumerate(ax.collections):
            if i in self.original_colors:
                original_colors = self.original_colors[i]['facecolors']
                dimmed_colors = original_colors.copy()
                if len(dimmed_colors.shape) > 1 and dimmed_colors.shape[1] >= 4:
                    dimmed_colors[:, 3] = 0.3  # Set alpha column
                collection.set_facecolors(dimmed_colors)
                logger.debug(f"DEBUG: Dimmed collection {i}")
        
        # FINALLY: Highlight the selected cluster
        for i, label in enumerate(unique_labels):
            if label == cluster_id:
                logger.debug(f"DEBUG: Found target cluster {cluster_id} at index {i}")
                if i < len(ax.collections) and i in self.original_colors:
                    collection = ax.collections[i]
                    original_colors = self.original_colors[i]['facecolors']
                    
                    # Restore full opacity for selected cluster
                    bright_colors = original_colors.copy()
                    if len(bright_colors.shape) > 1 and bright_colors.shape[1] >= 4:
                        bright_colors[:, 3] = 1.0  # Full alpha
                    collection.set_facecolors(bright_colors)
                    
                    # Also increase point size slightly for better visibility
                    if self.original_colors[i]['sizes'] is not None:
                        enlarged_sizes = self.original_colors[i]['sizes'] * 1.5
                        collection.set_sizes(enlarged_sizes)
                    
                    logger.debug(f"DEBUG: Highlighted cluster {cluster_id}")
                break
        
        self.highlighted_cluster = cluster_id
        self.draw()
    
    def reset_highlight(self):
        """Reset all clusters to original appearance."""
        if not self.original_colors:
            logger.debug("DEBUG: No stored colors to reset")
            return
            
        ax = self.fig.gca()
        if ax is None:
            logger.debug("DEBUG: No axes to reset")
            return
            
        logger.debug("DEBUG: Resetting highlights")
        
        # Restore original colors, alpha, and sizes
        for i, collection in enumerate(ax.collections):
            if i in self.original_colors:
                original_data = self.original_colors[i]
                
                # Restore original colors
                collection.set_facecolors(original_data['facecolors'])
                
                # Restore original sizes if they exist
                if original_data['sizes'] is not None:
                    collection.set_sizes(original_data['sizes'])
                
                logger.info(f"DEBUG: Restored collection {i}")
        
        self.highlighted_cluster = None
        self.draw()
        logger.debug("DEBUG: Reset complete")
    
    def set_visualization_mode(self, mode):
        """Set visualization mode."""
        logger.debug(f"DEBUG: Changing visualization mode to {mode}")

        # Clear highlights and stored colors when changing mode
        self.reset_highlight()
        self.original_colors = {}
        self.highlighted_cluster = None

        self.visualization_mode = mode

        # Restore scroll area to resizable so canvas fills the viewport in other views
        if mode != 'dendrogram':
            scroll = getattr(self, 'canvas_scroll', None)
            if scroll is not None:
                scroll.setWidgetResizable(True)

        # Connect/disconnect interactive handler based on mode
        if self.interactive_mode and mode in ['pca_2d', 'pca_3d']:
            self._connect_click_handler()
            logger.debug("DEBUG: Click handler connected for interactive mode")
        else:
            self._disconnect_click_handler()
            logger.debug("DEBUG: Click handler disconnected")

        self.plot_clusters()
    
    def plot_clusters(self):
        """Plot cluster analysis results."""
        if not self.cluster_controller or self.cluster_controller.manager.cluster_labels is None:
            self.fig.clear()
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, "Run cluster analysis to display results", 
                   transform=ax.transAxes, ha='center', va='center', fontsize=14)
            ax.axis('off')
            self.draw()
            return
        
        self.fig.clear()
        
        try:
            if self.visualization_mode == 'pca_2d':
                self._plot_pca_2d()
            elif self.visualization_mode == 'pca_3d':
                self._plot_pca_3d()
            elif self.visualization_mode == 'spectra':
                self._plot_clustered_spectra()
            elif self.visualization_mode == 'centroids':
                self._plot_cluster_centroids()
            elif self.visualization_mode == 'dendrogram':
                # Read options directly from the dialog and pass them in
                dialog = self.cluster_controller.dialog
                rotation = 90
                trunc_mode = "Full label"
                trunc_n = 10
                font_size = None
                if dialog is not None:
                    rotation = int(dialog.dendro_rotation_combo.currentText().replace('°', ''))
                    trunc_mode = dialog.dendro_trunc_combo.currentText()
                    trunc_n = dialog.dendro_n_spin.value()
                    fontsize_text = dialog.dendro_fontsize_combo.currentText()
                    font_size = None if fontsize_text == "Auto" else int(fontsize_text)
                self._plot_dendrogram(rotation=rotation, trunc_mode=trunc_mode,
                                      trunc_n=trunc_n, font_size=font_size)
            elif self.visualization_mode == 'elbow':
                self._plot_elbow_curve()
            elif self.visualization_mode == 'silhouette':
                self._plot_silhouette_analysis()
                
            # tight_layout conflicts with dendrogram's subplots_adjust — skip it
            if self.visualization_mode != 'dendrogram':
                self.fig.tight_layout()
            self.draw()
            
        except Exception as e:
            logger.error(f"ERROR plotting clusters: {e}")
            logger.exception("Traceback:")
            
    def _plot_silhouette_analysis(self):
        """Plot silhouette analysis for cluster quality assessment."""
        silhouette_data = self.cluster_controller.manager.get_silhouette_data()
        
        if not silhouette_data:
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, "Silhouette analysis not available\n(Need at least 2 clusters)", 
                   transform=ax.transAxes, ha='center', va='center', fontsize=14)
            ax.axis('off')
            return
        
        sample_scores = silhouette_data['sample_scores']
        cluster_labels = silhouette_data['cluster_labels']
        avg_score = silhouette_data['avg_score']
        spectrum_labels = silhouette_data['spectrum_labels']
        method = silhouette_data['method']
        
        # Create silhouette plot
        ax = self.fig.add_subplot(111)
        
        unique_labels = np.unique(cluster_labels)
        n_clusters = len(unique_labels)
        
        # Handle DBSCAN noise points
        if method == 'dbscan' and -1 in unique_labels:
            # Remove noise label from plotting but keep track
            plot_labels = [label for label in unique_labels if label != -1]
            n_clusters_plot = len(plot_labels)
            noise_count = np.sum(cluster_labels == -1)
        else:
            plot_labels = unique_labels
            n_clusters_plot = n_clusters
            noise_count = 0
        
        y_lower = 10
        colors = plt.cm.tab10(np.linspace(0, 1, n_clusters_plot))
        
        for i, cluster_label in enumerate(plot_labels):
            # Get silhouette scores for this cluster
            cluster_mask = cluster_labels == cluster_label
            cluster_silhouette_values = sample_scores[cluster_mask]
            
            # Filter out NaN values (shouldn't happen for non-noise points)
            cluster_silhouette_values = cluster_silhouette_values[~np.isnan(cluster_silhouette_values)]
            
            if len(cluster_silhouette_values) == 0:
                continue
                
            cluster_silhouette_values.sort()
            
            size_cluster = len(cluster_silhouette_values)
            y_upper = y_lower + size_cluster
            
            color = colors[i]
            ax.fill_betweenx(np.arange(y_lower, y_upper),
                            0, cluster_silhouette_values,
                            facecolor=color, edgecolor=color, alpha=0.7)
            
            # Label the silhouette plots with their cluster numbers at the middle
            ax.text(-0.05, y_lower + 0.5 * size_cluster, str(cluster_label),
                   fontsize=10, fontweight='bold')
            
            y_lower = y_upper + 10  # 10 for the 0 samples
        
        ax.set_xlabel('Silhouette Coefficient Values')
        ax.set_ylabel('Cluster Label')
        
        # Add title with method and score information
        title = f'Silhouette Analysis - {method.upper()}'
        if n_clusters_plot > 1:
            title += f'\nAverage Score: {avg_score:.3f}'
        
        if noise_count > 0:
            title += f' ({noise_count} noise points excluded)'
            
        ax.set_title(title)
        
        # Add vertical line for average silhouette score
        if avg_score is not None:
            ax.axvline(x=avg_score, color="red", linestyle="--", 
                      linewidth=2, label=f'Average Score: {avg_score:.3f}')
        
        # Set x-axis limits — lower bound adapts if scores are negative
        valid_scores = sample_scores[~np.isnan(sample_scores)]
        x_min = min(-0.1, float(np.min(valid_scores)) - 0.05) if len(valid_scores) > 0 else -0.1
        ax.set_xlim([x_min, 1])
        ax.set_ylim([0, len(sample_scores) + (n_clusters_plot + 1) * 10])
        
        # Add legend and grid
        if avg_score is not None:
            ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3, axis='x')
        
        # Add interpretation text
        interpretation = self._get_silhouette_interpretation(avg_score)
        ax.text(0.02, 0.98, interpretation, transform=ax.transAxes, 
                verticalalignment='top', fontsize=9,
                bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8))
    
    def _get_silhouette_interpretation(self, avg_score):
        """Get interpretation text for silhouette score."""
        if avg_score is None:
            return "Score unavailable"
        elif avg_score > 0.7:
            return f"Excellent separation\n({avg_score:.3f} > 0.7)"
        elif avg_score > 0.5:
            return f"Good separation\n({avg_score:.3f} > 0.5)"
        elif avg_score > 0.3:
            return f"Moderate separation\n({avg_score:.3f} > 0.3)"
        elif avg_score > 0:
            return f"Weak separation\n({avg_score:.3f} > 0)"
        else:
            return f"Poor clustering\n({avg_score:.3f} ≤ 0)"
            
    def _plot_dendrogram(self, rotation=90, trunc_mode="Full label", trunc_n=10, font_size=None):
        """Plot hierarchical clustering dendrogram."""
        from scipy.cluster.hierarchy import dendrogram, linkage

        manager = self.cluster_controller.manager
        if manager.method != 'hierarchical':
            return

        n_spectra = len(manager.spectrum_labels)

        # ---- Build display labels ----
        # "Shorten names" (main window checkbox) is applied first — it
        # strips only the part shared across the WHOLE selection, same as
        # every other display context in the app. The dendrogram's own
        # trunc_mode (First/Last N chars) is a separate, manual truncation
        # on TOP of that, for when even the shortened names are still too
        # long to fit — the two are independent and compose in this order.
        raw_labels = self._shortened(manager.spectrum_labels)
        if trunc_mode == "First N chars":
            display_labels = [lbl[:trunc_n] for lbl in raw_labels]
        elif trunc_mode == "Last N chars":
            display_labels = [lbl[-trunc_n:] for lbl in raw_labels]
        else:
            display_labels = list(raw_labels)

        # ---- Font size — explicit override, or auto-sized by spectrum count ----
        if font_size is not None:
            label_fontsize = font_size
        elif n_spectra <= 20:
            label_fontsize = 9
        elif n_spectra <= 40:
            label_fontsize = 7
        elif n_spectra <= 80:
            label_fontsize = 5
        else:
            label_fontsize = 3

        # ---- Viewport dimensions ----
        scroll = getattr(self, 'canvas_scroll', None)
        if scroll is not None:
            scroll.setWidgetResizable(False)
            vp_width_px  = scroll.viewport().width()
            vp_height_px = scroll.viewport().height()
        else:
            vp_width_px  = 1200
            vp_height_px = 600

        dpi = self.fig.get_dpi()

        # ---- Canvas size: exactly the viewport — no scrolling needed ----
        # Capped well under matplotlib/Agg's hard 65536px-per-dimension
        # limit. Without this cap, n_spectra * width_per_spectrum * dpi
        # grows without bound — at a few thousand spectra it silently
        # crashes the whole dialog (ValueError: Image size ... too large).
        # At that many leaves the labels aren't individually readable
        # anyway, so capping rather than growing unbounded doesn't lose
        # anything actually usable; the dendrogram's tree *structure* is
        # still meaningful, just zoomed out further than at smaller counts.
        _MAX_DENDRO_WIDTH_PX = 16000
        width_per_spectrum = {90: 0.35, 45: 0.5, 0: 0.25}.get(rotation, 0.35)
        fig_width_px  = max(vp_width_px, int(n_spectra * width_per_spectrum * dpi))
        width_capped = fig_width_px > _MAX_DENDRO_WIDTH_PX
        fig_width_px = min(fig_width_px, _MAX_DENDRO_WIDTH_PX)
        fig_height_px = vp_height_px

        self.fig.set_size_inches(fig_width_px / dpi, fig_height_px / dpi)
        self.fig.set_dpi(dpi)
        self.resize(fig_width_px, fig_height_px)

        ax = self.fig.add_subplot(111)

        # ---- Compute linkage and draw ----
        linkage_method = getattr(manager, 'linkage', 'ward')
        Z = linkage(manager.scaled_data, method=linkage_method)
        dendrogram(Z, labels=display_labels, ax=ax,
                   leaf_rotation=rotation, leaf_font_size=label_fontsize)

        title = f'Hierarchical Clustering Dendrogram  [linkage: {linkage_method}]'
        if width_capped:
            title += f'\n({n_spectra} leaves \u2014 width capped for stability; individual labels will overlap at this scale)'
        ax.set_title(title)
        ax.set_xlabel('Spectrum')
        ax.set_ylabel('Distance')

        for tick_lbl in ax.get_xticklabels():
            tick_lbl.set_clip_on(False)

        # ---- Bottom margin: enough room for labels + x-axis title ----
        # Compute required label height in figure-fraction units.
        max_label_len = max((len(lbl) for lbl in display_labels), default=10)
        # Points per character (approximate) at the given font size, converted to px
        pts_per_char = label_fontsize * 0.6      # width of one char in pts
        px_per_pt    = dpi / 72.0
        label_px = max_label_len * pts_per_char * px_per_pt   # label height at 90°

        if rotation != 90:
            label_px *= 0.55   # diagonal labels need less vertical space

        # Extra room: tick marks (~10px) + x-axis title (~label_fontsize * 2.5 * px_per_pt)
        extra_px = 10 + label_fontsize * 2.5 * px_per_pt
        total_bottom_px = label_px + extra_px

        bottom = min(0.55, max(0.10, total_bottom_px / fig_height_px))
        self.fig.subplots_adjust(left=0.07, right=0.99, top=0.95, bottom=bottom)
            
    def _plot_pca_2d(self):
        """Plot 2D PCA projection with clusters."""
        pca_data = self.cluster_controller.get_pca_data()
        if not pca_data or pca_data['components'].shape[1] < 2:
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, "Insufficient PCA components", 
                   transform=ax.transAxes, ha='center', va='center')
            return
        
        ax = self.fig.add_subplot(111)
        
        components = pca_data['components']
        labels = pca_data['labels']
        unique_labels = np.unique(labels)
        colors = plt.cm.tab10(np.linspace(0, 1, len(unique_labels)))
        
        for i, label in enumerate(unique_labels):
            mask = labels == label
            cluster_name = f'Cluster {label}' if label != -1 else 'Noise'
            ax.scatter(components[mask, 0], components[mask, 1], 
                      c=[colors[i]], label=cluster_name, s=100, alpha=0.7)
        
        # Add spectrum labels — optional, since labeling every point is the
        # slowest part of this plot with many spectra. Clusters are still
        # distinguished by colour even with labels off.
        dialog = self.cluster_controller.dialog
        show_labels = True
        label_fontsize = 8
        if dialog is not None and hasattr(dialog, 'pca2d_labels_cb'):
            show_labels = dialog.pca2d_labels_cb.isChecked()
            label_fontsize = dialog.pca2d_fontsize_spin.value()
        if show_labels:
            for i, txt in enumerate(self._shortened(pca_data['spectrum_labels'])):
                ax.annotate(txt, (components[i, 0], components[i, 1]),
                           fontsize=label_fontsize, alpha=0.7)
        
        variance = pca_data['explained_variance']
        ax.set_xlabel(f'PC1 ({variance[0]*100:.1f}%)')
        ax.set_ylabel(f'PC2 ({variance[1]*100:.1f}%)')
        
        # Add interactive instruction if enabled
        title = 'Cluster Analysis - PCA Projection (2D)'
        if self.interactive_mode:
            title += '\n(Click on points to highlight clusters)'
        ax.set_title(title)
        
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
    
    def _plot_pca_3d(self):
        """Plot 3D PCA projection with clusters."""
        pca_data = self.cluster_controller.get_pca_data()
        if not pca_data or pca_data['components'].shape[1] < 3:
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, "Insufficient PCA components for 3D", 
                   transform=ax.transAxes, ha='center', va='center')
            return
        
        ax = self.fig.add_subplot(111, projection='3d')
        
        components = pca_data['components']
        labels = pca_data['labels']
        unique_labels = np.unique(labels)
        colors = plt.cm.tab10(np.linspace(0, 1, len(unique_labels)))
        
        for i, label in enumerate(unique_labels):
            mask = labels == label
            cluster_name = f'Cluster {label}' if label != -1 else 'Noise'
            ax.scatter(components[mask, 0], components[mask, 1], components[mask, 2],
                      c=[colors[i]], label=cluster_name, s=100, alpha=0.7)
        
        variance = pca_data['explained_variance']
        ax.set_xlabel(f'PC1 ({variance[0]*100:.1f}%)')
        ax.set_ylabel(f'PC2 ({variance[1]*100:.1f}%)')
        ax.set_zlabel(f'PC3 ({variance[2]*100:.1f}%)')
        
        # Add interactive instruction if enabled
        title = 'Cluster Analysis - PCA Projection (3D)'
        if self.interactive_mode:
            title += '\n(Click on points to highlight clusters)'
        ax.set_title(title)
        
        ax.legend(loc='upper right')
    
    def _plot_clustered_spectra(self):
        """Plot spectra colored by cluster."""
        manager = self.cluster_controller.manager
        unique_labels = np.unique(manager.cluster_labels)
        colors = plt.cm.tab10(np.linspace(0, 1, len(unique_labels)))
        
        ax = self.fig.add_subplot(111)
        
        for i, label in enumerate(unique_labels):
            members = self.cluster_controller.get_cluster_members(label)
            cluster_name = f'Cluster {label}' if label != -1 else 'Noise'
            for idx in members:
                ax.plot(manager.x_axis, manager.data_matrix[idx, :], 
                       color=colors[i], alpha=0.5, linewidth=1)
        
        # Create legend
        from matplotlib.lines import Line2D
        legend_elements = [Line2D([0], [0], color=colors[i], lw=2, 
                                 label=f'Cluster {label}' if label != -1 else 'Noise') 
                          for i, label in enumerate(unique_labels)]
        ax.legend(handles=legend_elements, loc='upper right')
        
        ax.set_xlabel('Wavenumber')
        ax.set_ylabel('Intensity')
        ax.set_title('Clustered Spectra')
        ax.grid(True, alpha=0.3)
    
    def _plot_cluster_centroids(self):
        """Plot cluster centroid spectra."""
        manager = self.cluster_controller.manager
        unique_labels = np.unique(manager.cluster_labels)
        colors = plt.cm.tab10(np.linspace(0, 1, len(unique_labels)))
        
        ax = self.fig.add_subplot(111)
        
        for i, label in enumerate(unique_labels):
            if label == -1:  # Skip noise points for DBSCAN
                continue
            x, centroid = self.cluster_controller.get_cluster_centroid(label)
            if x is not None:
                members = self.cluster_controller.get_cluster_members(label)
                ax.plot(x, centroid, color=colors[i], linewidth=2,
                       label=f'Cluster {label} ({len(members)} spectra)')
        
        ax.set_xlabel('Wavenumber')
        ax.set_ylabel('Intensity')
        ax.set_title('Cluster Centroids')
        if ax.get_legend_handles_labels()[0]:
            ax.legend(loc='upper right')
        else:
            ax.text(0.5, 0.5, 'No clusters found (all points are noise)\u2014\n'
                    'try a larger Epsilon or smaller Min samples',
                    transform=ax.transAxes, ha='center', va='center')
        ax.grid(True, alpha=0.3)
        
    def _plot_elbow_curve(self):
        """Plot elbow curve for K-Means optimal cluster selection."""
        if not self.cluster_controller:
            return
            
        # Get the original spectra from the dialog
        dialog = self.cluster_controller.dialog
        if not dialog or not dialog.spectra:
            return

        max_clusters = max(10, dialog.n_clusters_spin.value())
        cache_key = (len(dialog.spectra), max_clusters)
        if cache_key == self._elbow_cache_key and self._elbow_cache_data is not None:
            k_values, wcss = self._elbow_cache_data
        else:
            k_values, wcss = self._compute_elbow_with_progress(dialog.spectra, max_clusters)
            if k_values is None:
                ax = self.fig.add_subplot(111)
                ax.text(0.5, 0.5, "Elbow plot not computed (cancelled or failed)",
                       transform=ax.transAxes, ha='center', va='center')
                return
            self._elbow_cache_key = cache_key
            self._elbow_cache_data = (k_values, wcss)
        
        ax = self.fig.add_subplot(111)
        ax.plot(k_values, wcss, 'bo-', linewidth=2, markersize=8)
        ax.set_xlabel('Number of Clusters (k)')
        ax.set_ylabel('Within-Cluster Sum of Squares (WCSS)')
        ax.set_title('Elbow Plot for Optimal Number of Clusters')
        ax.grid(True, alpha=0.3)
        
        # Highlight the current number of clusters if available
        if hasattr(dialog, 'n_clusters_spin'):
            current_k = dialog.n_clusters_spin.value()
            if current_k in k_values:
                idx = k_values.index(current_k)
                ax.plot(current_k, wcss[idx], 'ro', markersize=12, 
                       label=f'Current: k={current_k}')
                ax.legend(loc='upper right')

    def _compute_elbow_with_progress(self, spectra, max_clusters=10):
        """Run the elbow computation with a determinate progress dialog —
        up to (max_clusters - 1) separate K-Means fits (each with 10
        internal restarts), which previously had no visual feedback at all."""
        from PyQt5.QtWidgets import QProgressDialog, QApplication

        progress = QProgressDialog('Computing elbow plot…', 'Cancel', 0, max_clusters - 1, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle('Cluster Analysis')
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()

        cancelled = {'flag': False}

        def _on_progress(done, total):
            if progress.wasCanceled():
                cancelled['flag'] = True
                return False
            progress.setMaximum(total)
            progress.setLabelText(f'Computing elbow plot… ({done} of {total})')
            progress.setValue(done)
            QApplication.processEvents()
            return True

        k_values, wcss = self.cluster_controller.compute_elbow_curve(
            spectra, max_clusters=max_clusters, progress_callback=_on_progress)
        progress.close()

        if cancelled['flag']:
            return None, None
        return k_values, wcss

class _ComputeWorker(QThread):
    """Runs a single callable on a background thread — see the equivalent
    class in nmf_dialog.py for the full rationale: a long blocking call on
    the GUI thread freezes Qt's entire event loop, including the ability
    to paint, show, or hide a progress dialog, for its whole duration.
    The callable must not touch any Qt widgets — only pure computation is
    safe to run here.

    `progress` is available for callables that support a progress_callback
    argument (see ClusterAnalysisManager.compute_clustering). Emitting a
    pyqtSignal from this worker's own run() — i.e. from the background
    thread — is safe; Qt automatically queues the emission onto whichever
    thread the connected slot lives in (the GUI thread here), so slots
    connected to it can safely touch widgets.
    """
    done = pyqtSignal()
    progress = pyqtSignal(int, int, str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self._fn()
        except Exception as exc:
            self.error = exc
        self.done.emit()


class ClusterAnalysisDialog(QDialog):
    """Dialog for cluster analysis with interactive features."""
    
    def __init__(self, parent=None, controller=None, spectra=None):
        super().__init__(parent)
        self.controller = controller
        self.spectra = spectra
        self._last_cluster_id = None
        self._last_member_indices = None

        self.setWindowTitle("Cluster Analysis")
        self.setModal(True)
        self.setMinimumSize(1020, 620)
        self.resize(1280, 760)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint)
        
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
        try:
            self.setup_ui()
            # The method combo starts with a method already selected, so
            # currentTextChanged (connected inside setup_ui) never fires for
            # that initial value — without this explicit call, viz_combo never
            # gets Elbow Plot/Dendrogram added until the user changes the
            # method at least once.
            self.on_method_changed()
        finally:
            QApplication.restoreOverrideCursor()

    def showEvent(self, event):
        super().showEvent(event)
        # Defensive: clear any override cursor(s) still active once this
        # dialog is actually on screen — e.g. a "please wait" cursor left
        # active by whoever opened this modal dialog (it won't get restored
        # by the caller until the dialog closes, since exec_() blocks). This
        # dialog is interactive as soon as it's shown, so nothing inherited
        # should still be forcing a busy look. See ClusterAnalysisCanvas.leaveEvent
        # for the other half of this fix.
        from PyQt5.QtWidgets import QApplication
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

    def setup_ui(self):
        """Set up UI."""
        main_layout = QHBoxLayout(self)
        
        # Main splitter (left panel | right content)
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setChildrenCollapsible(False)
        main_layout.addWidget(main_splitter)
        
        # Left panel
        control_panel = self.create_control_panel()
        main_splitter.addWidget(control_panel)
        
        # Right side splitter (canvas | info panel)
        self.right_splitter = QSplitter(Qt.Vertical)  # Store reference to control sizes
        self.right_splitter.setChildrenCollapsible(False)
        main_splitter.addWidget(self.right_splitter)
        
        # Canvas panel
        canvas_panel = self.create_canvas_panel()
        self.right_splitter.addWidget(canvas_panel)
        
        # Info panel for cluster details
        self.info_panel_widget = self.create_info_panel()  # Store reference
        self.right_splitter.addWidget(self.info_panel_widget)
        
        # Set splitter sizes
        main_splitter.setSizes([400, 1100])
        self.right_splitter.setSizes([700, 300])  # Initial sizes
    
    def create_info_panel(self):
        """Create information panel for cluster details."""
        widget = QWidget()
        widget.setMaximumHeight(300)
        layout = QVBoxLayout(widget)
        
        # Interactive controls - this should ALWAYS be visible
        self.interactive_group = QGroupBox("Interactive Selection")
        interactive_layout = QHBoxLayout(self.interactive_group)
        
        self.interactive_checkbox = QCheckBox("Enable Click Selection")
        self.interactive_checkbox.setChecked(True)
        self.interactive_checkbox.stateChanged.connect(self.on_interactive_changed)
        interactive_layout.addWidget(self.interactive_checkbox)
        
        self.reset_highlight_btn = QPushButton("Reset Highlights")
        self.reset_highlight_btn.clicked.connect(self.reset_highlights)
        interactive_layout.addWidget(self.reset_highlight_btn)
        
        interactive_layout.addStretch()
        layout.addWidget(self.interactive_group)
        
        # Cluster info display - this should hide/show
        self.cluster_info_group = QGroupBox("Cluster Information")  # Separate reference
        info_layout = QVBoxLayout(self.cluster_info_group)
        
        self.cluster_info_text = QTextEdit()
        self.cluster_info_text.setMaximumHeight(200)
        self.cluster_info_text.setReadOnly(True)
        
        # Set monospace font for better formatting
        font = QFont("Courier New", 9)
        font.setStyleHint(QFont.Monospace)
        self.cluster_info_text.setFont(font)
        
        info_layout.addWidget(self.cluster_info_text)
        layout.addWidget(self.cluster_info_group)
        
        return widget
    
    def create_control_panel(self):
        """Create control panel."""
        widget = QWidget()
        widget.setMinimumWidth(340)
        layout = QVBoxLayout(widget)
        
        # Method selection — renamed to "Clustering"
        method_group = QGroupBox("Clustering")
        method_layout = QVBoxLayout(method_group)

        method_row = QHBoxLayout()
        method_label = QLabel("Method:")
        method_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        method_row.addWidget(method_label)
        self.method_combo = QComboBox()
        self.method_combo.addItems(['K-Means', 'Hierarchical', 'DBSCAN'])
        self.method_combo.currentTextChanged.connect(self.on_method_changed)
        method_row.addWidget(self.method_combo)
        method_layout.addLayout(method_row)

        # Parameters
        self.params_widget = QWidget()
        self.params_layout = QVBoxLayout(self.params_widget)
        method_layout.addWidget(self.params_widget)

        self.update_parameters_ui()

        # Visualization dropdown moved inside the Clustering group
        viz_row = QHBoxLayout()
        viz_label = QLabel("Visualization:")
        viz_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        viz_row.addWidget(viz_label)
        self.viz_combo = QComboBox()
        self.viz_combo.addItems(['PCA 2D', 'PCA 3D', 'Spectra', 'Centroids', 'Silhouette Analysis'])
        self.viz_combo.currentTextChanged.connect(self.on_viz_changed)
        viz_row.addWidget(self.viz_combo)
        method_layout.addLayout(viz_row)

        layout.addWidget(method_group)

        # Run button — green, prominent
        self.run_btn = QPushButton("Run Clustering")
        self.run_btn.clicked.connect(self.run_clustering)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #2E7D32;
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 6px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
            QPushButton:pressed {
                background-color: #1B5E20;
            }
        """)
        layout.addWidget(self.run_btn)

        self._stale_warning_label = QLabel(
            "\u26a0  Settings changed \u2014 click Run Clustering to update the results below.")
        self._stale_warning_label.setStyleSheet(
            "color: #C62828; font-size: 8pt; font-weight: bold;")
        self._stale_warning_label.setWordWrap(True)
        self._stale_warning_label.setVisible(False)
        layout.addWidget(self._stale_warning_label)

        # Results
        results_group = QGroupBox("Cluster Results")
        results_layout = QVBoxLayout(results_group)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(3)
        self.results_table.setHorizontalHeaderLabels(['Cluster', 'Size', 'Silhouette'])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_table.cellClicked.connect(self.on_table_cell_clicked)

        results_layout.addWidget(self.results_table)
        layout.addWidget(results_group)
        self.dendro_group = QGroupBox("Dendrogram options")
        dendro_layout = QVBoxLayout(self.dendro_group)

        # Label rotation — label then combo then stretch
        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel("Label rotation:"))
        self.dendro_rotation_combo = QComboBox()
        self.dendro_rotation_combo.addItems(["90°", "45°", "0°"])
        self.dendro_rotation_combo.setCurrentText("90°")
        self.dendro_rotation_combo.setFixedWidth(60)
        self.dendro_rotation_combo.currentTextChanged.connect(self._replot_dendrogram)
        rot_row.addWidget(self.dendro_rotation_combo)
        rot_row.addStretch()
        dendro_layout.addLayout(rot_row)

        # Label font size — Auto (adapts to spectrum count) or an explicit size
        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("Label font size:"))
        self.dendro_fontsize_combo = QComboBox()
        self.dendro_fontsize_combo.addItems(["Auto", "3", "5", "7", "9", "11", "14"])
        self.dendro_fontsize_combo.setCurrentText("Auto")
        self.dendro_fontsize_combo.setFixedWidth(70)
        self.dendro_fontsize_combo.setToolTip(
            "Auto shrinks labels as the number of spectra grows, so they\n"
            "stay legible without the dendrogram becoming unreasonably wide.\n"
            "Choose an explicit size to override that."
        )
        self.dendro_fontsize_combo.currentTextChanged.connect(self._replot_dendrogram)
        font_row.addWidget(self.dendro_fontsize_combo)
        font_row.addStretch()
        dendro_layout.addLayout(font_row)

        # Label truncation — [combo][N:][spinbox] all fixed-width, left-aligned
        trunc_row = QHBoxLayout()
        trunc_row.setContentsMargins(0, 0, 0, 0)
        trunc_row.setSpacing(4)
        self.dendro_trunc_combo = QComboBox()
        self.dendro_trunc_combo.addItems(["Full label", "First N chars", "Last N chars"])
        self.dendro_trunc_combo.setToolTip("How to display labels when they are too long")
        self.dendro_trunc_combo.setFixedWidth(110)
        trunc_row.addWidget(self.dendro_trunc_combo)
        n_label = QLabel("N:")
        n_label.setFixedWidth(20)
        trunc_row.addWidget(n_label)
        self.dendro_n_spin = QSpinBox()
        self.dendro_n_spin.setMinimum(1)
        self.dendro_n_spin.setMaximum(200)
        self.dendro_n_spin.setValue(10)
        self.dendro_n_spin.setFixedWidth(55)
        self.dendro_n_spin.setToolTip("Number of characters (N) to keep from each label")
        self.dendro_n_spin.setEnabled(False)
        self.dendro_n_spin.setKeyboardTracking(False)
        trunc_row.addWidget(self.dendro_n_spin)
        trunc_row.addStretch()
        dendro_layout.addLayout(trunc_row)

        def _on_trunc_changed():
            is_n_mode = self.dendro_trunc_combo.currentText() != "Full label"
            self.dendro_n_spin.setEnabled(is_n_mode)
            self._replot_dendrogram()

        self.dendro_trunc_combo.currentTextChanged.connect(_on_trunc_changed)
        self.dendro_n_spin.valueChanged.connect(self._replot_dendrogram)

        self.dendro_group.setVisible(False)   # hidden until Dendrogram is selected
        layout.addWidget(self.dendro_group)

        self.pca2d_group = QGroupBox("PCA 2D options")
        pca2d_layout = QVBoxLayout(self.pca2d_group)

        labels_row = QHBoxLayout()
        self.pca2d_labels_cb = QCheckBox("Show point labels")
        self.pca2d_labels_cb.setChecked(False)
        self.pca2d_labels_cb.stateChanged.connect(self._replot_pca2d)
        labels_row.addWidget(self.pca2d_labels_cb)
        labels_row.addStretch()
        pca2d_help_btn = QPushButton('?')
        pca2d_help_btn.setFixedSize(28, 22)
        pca2d_help_btn.setToolTip('About these options')
        pca2d_help_btn.clicked.connect(self._show_pca2d_options_help)
        labels_row.addWidget(pca2d_help_btn)
        pca2d_layout.addLayout(labels_row)

        pca2d_font_row = QHBoxLayout()
        pca2d_font_row.addWidget(self._fixed_label("Label font size:"))
        self.pca2d_fontsize_spin = QSpinBox()
        self.pca2d_fontsize_spin.setRange(4, 16)
        self.pca2d_fontsize_spin.setValue(8)
        self.pca2d_fontsize_spin.setFixedWidth(50)
        # Without this, every digit typed re-draws every point label at
        # the new size — exactly the slow case _show_pca2d_options_help's
        # own tip below warns about ("changing the font size while labels
        # are visible... can be slow with many spectra"), except it used
        # to happen once per keystroke instead of once per change.
        self.pca2d_fontsize_spin.setKeyboardTracking(False)
        self.pca2d_fontsize_spin.valueChanged.connect(self._replot_pca2d)
        pca2d_font_row.addWidget(self.pca2d_fontsize_spin)
        pca2d_font_row.addStretch()
        pca2d_layout.addLayout(pca2d_font_row)

        self.pca2d_group.setVisible(True)   # 'PCA 2D' is viz_combo's initial selection
        layout.addWidget(self.pca2d_group)
        
        # Export section
        export_group = QGroupBox("Export Results")
        export_layout = QVBoxLayout(export_group)
        
        # Create a horizontal layout for the two save buttons
        save_buttons_layout = QHBoxLayout()
        
        # Excel export button (existing)
        self.save_excel_btn = QPushButton("Save Excel...")
        self.save_excel_btn.clicked.connect(self.save_excel_results)
        self.save_excel_btn.setEnabled(False)
        self.save_excel_btn.setToolTip("Export clustering results to Excel file with multiple sheets")
        save_buttons_layout.addWidget(self.save_excel_btn)
        
        # CSV export button (new)
        self.export_csv_btn = QPushButton("Export CSV...")
        self.export_csv_btn.clicked.connect(self.show_export_menu)
        self.export_csv_btn.setEnabled(False)
        self.export_csv_btn.setToolTip("Export detailed cluster membership to CSV files")
        save_buttons_layout.addWidget(self.export_csv_btn)
        
        export_layout.addLayout(save_buttons_layout)
        layout.addWidget(export_group)
        
        layout.addStretch()
        
        # Dialog buttons
        self.button_box = QDialogButtonBox()
        
        self.help_button = QPushButton("Help")
        self.help_button.clicked.connect(self.show_help)
        self.button_box.addButton(self.help_button, QDialogButtonBox.HelpRole)
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        self.button_box.addButton(self.close_button, QDialogButtonBox.AcceptRole)
        
        layout.addWidget(self.button_box)
        
        return widget
    
    def create_canvas_panel(self):
        """Create canvas panel."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.canvas = ClusterAnalysisCanvas()
        self.canvas.set_cluster_controller(self.controller)

        # This dialog's OWN, independent Shorten Names toggle — not tied to
        # the main window's shared checkbox of the same name (see
        # make_shorten_names_checkbox docstring). Off by default. Handed
        # down to the canvas as a callable since the canvas has no direct
        # access to this dialog's widgets otherwise.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.canvas.get_shorten_enabled = self.checkBox_shorten_names.isChecked
        self.checkBox_shorten_names.stateChanged.connect(self._on_shorten_names_toggled)

        # Connect canvas signals
        self.canvas.cluster_selected.connect(self.on_cluster_selected)

        self.toolbar = NavigationToolbar(self.canvas, widget)

        # Wrap canvas in a scroll area so wide dendrograms are scrollable.
        # setWidgetResizable(False) is essential — True would shrink the canvas to fit.
        self.canvas_scroll = QScrollArea()
        self.canvas_scroll.setWidget(self.canvas)
        self.canvas_scroll.setWidgetResizable(True)   # default: fills viewport
        self.canvas_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.canvas_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.canvas.canvas_scroll = self.canvas_scroll

        # Install event filter on the viewport so we detect when the scroll area is resized
        self._viewport_filter = _ViewportResizeFilter(self.canvas)
        self.canvas_scroll.viewport().installEventFilter(self._viewport_filter)

        toolbar_row = QHBoxLayout()
        toolbar_row.addWidget(self.toolbar)
        toolbar_row.addStretch()
        toolbar_row.addWidget(self.checkBox_shorten_names)
        layout.addLayout(toolbar_row)
        layout.addWidget(self.canvas_scroll)

        return widget
    
    def on_interactive_changed(self, state):
        """Handle interactive mode checkbox change."""
        enabled = (state == Qt.Checked)
        self.canvas.set_interactive_mode(enabled)
        
        # Hide/show ONLY the cluster information group, not the interactive controls
        self.cluster_info_group.setVisible(enabled)
        logger.debug(f"DEBUG: Set cluster_info_group visible = {enabled}")
        
        # Adjust splitter sizes - but keep the info panel visible (it contains interactive controls)
        if enabled:
            # Show both sections - normal split
            self.right_splitter.setSizes([700, 300])
        else:
            # Hide only cluster info section - less space needed for info panel
            self.right_splitter.setSizes([850, 150])  # Smaller bottom panel but still visible
        
        if not enabled:
            self.reset_highlights()
            self.cluster_info_text.clear()
    
    def reset_highlights(self):
        """Reset all cluster highlights."""
        self.canvas.reset_highlight()
        self.cluster_info_text.clear()
    
    def on_cluster_selected(self, cluster_id, member_indices):
        """Handle cluster selection from canvas."""
        self.display_cluster_info(cluster_id, member_indices)

    def _on_shorten_names_toggled(self, _state=None):
        """Refresh everything this dialog's own Shorten Names checkbox
        affects: the plot's point/leaf labels (redrawn via plot_clusters)
        and the "Member Spectra:" text panel, which is only rebuilt when a
        cluster is actually selected — re-display the last-selected
        cluster (if any) so toggling doesn't require reselecting it."""
        if self.controller and self.controller.manager.cluster_labels is not None:
            self.canvas.plot_clusters()
        if self._last_cluster_id is not None and self._last_member_indices is not None:
            self.display_cluster_info(self._last_cluster_id, self._last_member_indices)
    
    def on_table_cell_clicked(self, row, column):
        """Handle table cell click to highlight cluster."""
        if not self.interactive_checkbox.isChecked():
            return
            
        # Get cluster ID from table
        cluster_item = self.results_table.item(row, 0)
        if cluster_item is None:
            return
            
        cluster_text = cluster_item.text()
        if cluster_text in ["", "Overall"]:
            return
            
        # Parse cluster ID
        try:
            if cluster_text == "Noise":
                cluster_id = -1
            else:
                cluster_id = int(cluster_text)
                
            # Get member indices
            member_indices = self.controller.get_cluster_members(cluster_id)
            
            # Highlight cluster and show info
            self.canvas._highlight_cluster(cluster_id)
            self.display_cluster_info(cluster_id, member_indices)
            
        except (ValueError, TypeError):
            pass  # Invalid cluster ID
    
    def display_cluster_info(self, cluster_id, member_indices):
        """Display detailed information about selected cluster."""
        if not self.controller or not self.controller.manager.cluster_labels is not None:
            return

        # Remembered so _on_shorten_names_toggled can rebuild this same
        # panel with updated (shortened or full) labels without requiring
        # the user to reselect the cluster.
        self._last_cluster_id = cluster_id
        self._last_member_indices = member_indices

        manager = self.controller.manager
        
        # Build info text
        info_lines = []
        
        # Cluster header
        cluster_name = f"Cluster {cluster_id}" if cluster_id != -1 else "Noise Cluster"
        info_lines.append(f"=== {cluster_name} ===")
        info_lines.append("")
        
        # Basic statistics
        cluster_size = len(member_indices)
        total_spectra = len(manager.spectrum_labels)
        percentage = (cluster_size / total_spectra) * 100
        
        info_lines.append(f"Size: {cluster_size} spectra ({percentage:.1f}%)")
        info_lines.append(f"Method: {manager.method.upper()}")
        info_lines.append("")
        
        # Silhouette analysis
        if manager.silhouette_sample_scores is not None:
            cluster_silhouettes = manager.silhouette_sample_scores[member_indices]
            # Filter out NaN values
            valid_silhouettes = cluster_silhouettes[~np.isnan(cluster_silhouettes)]
            
            if len(valid_silhouettes) > 0:
                avg_silhouette = np.mean(valid_silhouettes)
                min_silhouette = np.min(valid_silhouettes)
                max_silhouette = np.max(valid_silhouettes)
                std_silhouette = np.std(valid_silhouettes)
                
                quality = self._interpret_silhouette_score(avg_silhouette)
                
                info_lines.append("Silhouette Analysis:")
                info_lines.append(f"  Average: {avg_silhouette:.4f} ({quality})")
                info_lines.append(f"  Range: {min_silhouette:.4f} to {max_silhouette:.4f}")
                info_lines.append(f"  Std Dev: {std_silhouette:.4f}")
                info_lines.append("")
            else:
                info_lines.append("Silhouette Analysis: N/A (Noise cluster)")
                info_lines.append("")
        
        # PCA coordinates summary
        if manager.pca_components is not None:
            pca_coords = manager.pca_components[member_indices]
            n_components = pca_coords.shape[1]
            
            info_lines.append("PCA Coordinates (centroid):")
            for comp in range(n_components):
                centroid_coord = np.mean(pca_coords[:, comp])
                info_lines.append(f"  PC{comp+1}: {centroid_coord:.3f}")
            info_lines.append("")
        
        # Member spectra list
        info_lines.append("Member Spectra:")
        member_display_names = _shorten_for_display(
            self.checkBox_shorten_names.isChecked(),
            [manager.spectrum_labels[idx] for idx in member_indices]
        )
        for i, idx in enumerate(member_indices):
            spectrum_name = member_display_names[i]
            
            # Add silhouette score if available
            silhouette_str = ""
            if manager.silhouette_sample_scores is not None:
                score = manager.silhouette_sample_scores[idx]
                if not np.isnan(score):
                    silhouette_str = f" (sil: {score:.3f})"
            
            info_lines.append(f"  {i+1:2d}. {spectrum_name}{silhouette_str}")
            
            # Limit display to first 20 members
            if i >= 19 and len(member_indices) > 20:
                remaining = len(member_indices) - 20
                info_lines.append(f"      ... and {remaining} more spectra")
                break
        
        # Set the text
        self.cluster_info_text.setText("\n".join(info_lines))
    
    def _interpret_silhouette_score(self, score):
        """Interpret silhouette score as quality text."""
        if score > 0.7:
            return "Excellent"
        elif score > 0.5:
            return "Good"
        elif score > 0.3:
            return "Moderate"
        elif score > 0:
            return "Weak"
        else:
            return "Poor"
    
    def show_export_menu(self):
        """Show export options menu."""
        menu = QMenu(self)
        
        # Export detailed membership
        export_detailed_action = menu.addAction("Export Detailed Membership...")
        export_detailed_action.setToolTip("Export all spectra with cluster assignments, silhouette scores, and PCA coordinates")
        
        menu.addSeparator()
        
        # Export summary statistics
        export_summary_action = menu.addAction("Export Summary Only...")
        export_summary_action.setToolTip("Export cluster summary statistics and member lists")
        
        # Show menu at button position
        action = menu.exec_(self.export_csv_btn.mapToGlobal(self.export_csv_btn.rect().bottomLeft()))
        
        if action == export_detailed_action:
            self.export_detailed_csv()
        elif action == export_summary_action:
            self.export_summary_csv()
    
    def export_detailed_csv(self):
        """Export detailed cluster membership to CSV."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, 
            "Export Detailed Cluster Membership", 
            "cluster_members_detailed.csv",
            "CSV Files (*.csv)"
        )
        
        if filepath:
            if self.controller.manager.export_cluster_members(filepath):
                # The method creates both detailed and summary files
                summary_path = filepath.replace('.csv', '_summary.csv')
                QMessageBox.information(
                    self, 
                    "Export Successful", 
                    f"Cluster membership exported successfully!\n\n"
                    f"Detailed file: {filepath}\n"
                    f"Summary file: {summary_path}\n\n"
                    f"The detailed file contains all spectra with cluster assignments, "
                    f"silhouette scores, and PCA coordinates.\n"
                    f"The summary file contains cluster statistics and member lists."
                )
            else:
                QMessageBox.warning(self, "Export Error", "Failed to export cluster membership")
    
    def export_summary_csv(self):
        """Export only cluster summary to CSV."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, 
            "Export Cluster Summary", 
            "cluster_summary.csv",
            "CSV Files (*.csv)"
        )
        
        if filepath:
            try:
                # Generate and save only the summary
                summary_stats = self.controller.manager._generate_cluster_summary_stats()
                summary_stats.to_csv(filepath, index=False)
                
                QMessageBox.information(
                    self, 
                    "Export Successful", 
                    f"Cluster summary exported successfully!\n\n"
                    f"File: {filepath}\n\n"
                    f"Contains cluster sizes, silhouette statistics, "
                    f"and lists of member spectra for each cluster."
                )
            except Exception as e:
                QMessageBox.warning(self, "Export Error", f"Failed to export cluster summary:\n{str(e)}")
    
    def on_method_changed(self):
        """Handle method change - update UI and clear plot."""
        # Update parameters UI
        self.update_parameters_ui()
        
        # Update visualization dropdown
        method = self.method_combo.currentText()
        
        # Handle Dendrogram for Hierarchical
        if method == 'Hierarchical':
            if self.viz_combo.findText('Dendrogram') == -1:
                self.viz_combo.addItem('Dendrogram')
        else:
            idx = self.viz_combo.findText('Dendrogram')
            if idx >= 0:
                if self.viz_combo.currentText() == 'Dendrogram':
                    self.viz_combo.setCurrentText('PCA 2D')
                self.viz_combo.removeItem(idx)
        
        # Handle Elbow Plot for K-Means
        if method == 'K-Means':
            if self.viz_combo.findText('Elbow Plot') == -1:
                self.viz_combo.addItem('Elbow Plot')
        else:
            idx = self.viz_combo.findText('Elbow Plot')
            if idx >= 0:
                if self.viz_combo.currentText() == 'Elbow Plot':
                    self.viz_combo.setCurrentText('PCA 2D')
                self.viz_combo.removeItem(idx)
        
        # Clear the plot and info
        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        ax.text(0.5, 0.5, "Press 'Run Clustering' to compute results", 
               transform=ax.transAxes, ha='center', va='center', fontsize=14)
        ax.axis('off')
        self.canvas.draw()
        
        # Clear results table and info panel
        self.results_table.setRowCount(0)
        self.cluster_info_text.clear()
        self.save_excel_btn.setEnabled(False)
        self.export_csv_btn.setEnabled(False)
        self._has_run_once = False
        self._stale_warning_label.setVisible(False)

    @staticmethod
    def _fixed_label(text):
        """QLabel that stays snug against its text instead of growing to
        absorb a row's extra width — Qt's default label size policy
        permits growth, which otherwise leaves an awkward gap before
        whatever follows it in the row."""
        label = QLabel(text)
        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        return label

    def update_parameters_ui(self):
        """Update parameters UI based on method."""
        # Clear existing widgets using helper method
        self._clear_layout(self.params_layout)
        
        method = self.method_combo.currentText()
        
        if method in ['K-Means', 'Hierarchical']:
            row = QHBoxLayout()
            row.addWidget(self._fixed_label("Clusters:"))
            self.n_clusters_spin = QSpinBox()
            self.n_clusters_spin.setMinimum(2)
            self.n_clusters_spin.setMaximum(20)
            self.n_clusters_spin.setValue(3)
            self.n_clusters_spin.valueChanged.connect(self._mark_results_stale)
            row.addWidget(self.n_clusters_spin)
            self.params_layout.addLayout(row)
            
            if method == 'Hierarchical':
                link_row = QHBoxLayout()
                link_row.addWidget(self._fixed_label("Linkage:"))
                self.linkage_combo = QComboBox()
                self.linkage_combo.addItems(['ward', 'complete', 'average', 'single'])
                self.linkage_combo.currentTextChanged.connect(self._mark_results_stale)
                link_row.addWidget(self.linkage_combo)
                self.params_layout.addLayout(link_row)
        
        elif method == 'DBSCAN':
            eps_row = QHBoxLayout()
            eps_row.addWidget(self._fixed_label("Epsilon:"))
            self.eps_spin = QDoubleSpinBox()
            self.eps_spin.setMinimum(0.1)
            self.eps_spin.setMaximum(50.0)
            self.eps_spin.setValue(3.0)
            self.eps_spin.setSingleStep(0.5)
            self.eps_spin.valueChanged.connect(self._mark_results_stale)
            eps_row.addWidget(self.eps_spin)
            self.params_layout.addLayout(eps_row)
            
            min_row = QHBoxLayout()
            min_row.addWidget(self._fixed_label("Min Samples:"))
            self.min_samples_spin = QSpinBox()
            self.min_samples_spin.setMinimum(2)
            self.min_samples_spin.setMaximum(20)
            self.min_samples_spin.setValue(2)
            self.min_samples_spin.valueChanged.connect(self._mark_results_stale)
            min_row.addWidget(self.min_samples_spin)
            self.params_layout.addLayout(min_row)
    
    def _clear_layout(self, layout):
        """Helper method to recursively clear a layout."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                widget = item.widget()
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _mark_results_stale(self, *_):
        """Show a warning that the displayed plot no longer reflects the
        current parameter values — without this, changing e.g. the number
        of clusters after a run leaves the plot showing results for the
        old value with no indication anything's out of sync."""
        if getattr(self, '_has_run_once', False):
            self._stale_warning_label.setVisible(True)

    def run_clustering(self):
        """Run clustering analysis."""
        if getattr(self, '_clustering_running', False):
            return  # already running — ignore a second trigger outright
        self._clustering_running = True
        method_map = {
            'K-Means': 'kmeans',
            'Hierarchical': 'hierarchical',
            'DBSCAN': 'dbscan'
        }
        
        method = method_map[self.method_combo.currentText()]
        kwargs = {}
        
        if method in ['kmeans', 'hierarchical']:
            n_clusters = self.n_clusters_spin.value()
            if method == 'hierarchical':
                kwargs['linkage'] = self.linkage_combo.currentText()
        else:
            n_clusters = None
            kwargs['eps'] = self.eps_spin.value()
            kwargs['min_samples'] = self.min_samples_spin.value()
        
        from PyQt5.QtWidgets import QProgressDialog, QApplication
        from PyQt5.QtGui import QCursor
        self.run_btn.setEnabled(False)
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))

        # Determinate, staged progress bar instead of an indeterminate
        # "marquee" one. The clustering fit, PCA, and silhouette scoring are
        # each a single opaque call into scikit-learn with no way to peek
        # inside — an indeterminate bar's animation depends on the OS/Qt
        # animation timer getting a regular turn, which isn't guaranteed
        # during a long call like that, so it can visibly stall partway
        # through for reasons unrelated to whether the app is actually
        # frozen. Reporting the real stage boundaries (see
        # ClusterAnalysisManager.compute_clustering) is the honest version
        # of a progress indicator here: the bar visibly steps forward at
        # real checkpoints instead of implying continuous motion it can't
        # back up.
        self._cluster_progress = QProgressDialog('Running clustering…', None, 0, 4, self)
        self._cluster_progress.setWindowModality(Qt.WindowModal)
        self._cluster_progress.setWindowTitle('Cluster Analysis')
        self._cluster_progress.setMinimumDuration(0)
        self._cluster_progress.setCancelButton(None)
        self._cluster_progress.setValue(0)
        self._cluster_progress.show()

        self._cluster_worker = _ComputeWorker(None, self)
        self._cluster_worker._fn = lambda: self.controller.compute_clustering(
            self.spectra, method, n_clusters,
            progress_callback=self._cluster_worker.progress.emit, **kwargs)
        self._cluster_worker.progress.connect(self._on_clustering_progress)
        self._cluster_worker.done.connect(self._on_clustering_computed)
        self._cluster_worker.start(QThread.LowPriority)

    def _on_clustering_progress(self, step, total_steps, label):
        """Slot for _ComputeWorker.progress — runs on the GUI thread even
        though the signal was emitted from the background thread (Qt queues
        it automatically), so touching the progress dialog here is safe."""
        if total_steps != self._cluster_progress.maximum():
            self._cluster_progress.setMaximum(total_steps)
        self._cluster_progress.setLabelText(label)
        self._cluster_progress.setValue(step)

    def _on_clustering_computed(self):
        try:
            if self._cluster_worker.error is not None:
                # QMessageBox is already imported at module level (top of
                # this file) -- this used to re-import it locally right
                # here, which makes Python treat the name as LOCAL to the
                # whole function (an assignment anywhere in a function body
                # does that, even one that only runs on some branches).
                # Real bug found in practice: when clustering finishes
                # without raising but still reports success=False (e.g.
                # ClusterAnalysisManager.compute_clustering caught an
                # internal error and returned False rather than raising),
                # this branch is skipped entirely, so the local import
                # never runs -- and the `else: QMessageBox.warning(...)`
                # below then crashes with "UnboundLocalError: cannot
                # access local variable 'QMessageBox'" instead of showing
                # the "Clustering failed" message, leaving the progress
                # dialog/run button in a stuck state.
                QMessageBox.critical(self, "Clustering Error", str(self._cluster_worker.error))
                return

            success = self._cluster_worker.result
            if success:
                self.update_results()
                self.canvas.plot_clusters()
                self.save_excel_btn.setEnabled(True)
                self.export_csv_btn.setEnabled(True)
                self._has_run_once = True
                self._stale_warning_label.setVisible(False)
                
                # Enable interactive features
                self.canvas.set_interactive_mode(self.interactive_checkbox.isChecked())
            else:
                QMessageBox.warning(self, "Error", "Clustering failed")
        finally:
            from PyQt5.QtWidgets import QApplication
            self._cluster_progress.close()
            self.run_btn.setEnabled(True)
            self._clustering_running = False
            QApplication.restoreOverrideCursor()

    def update_results(self):
        """Update results table with silhouette scores."""
        info = self.controller.get_cluster_info()
        if not info:
            return
        
        # Get silhouette data for per-cluster scores
        silhouette_data = self.controller.manager.get_silhouette_data()
        cluster_silhouette_scores = {}
        
        if silhouette_data:
            sample_scores = silhouette_data['sample_scores']
            cluster_labels = silhouette_data['cluster_labels']
            
            # Calculate per-cluster average silhouette scores
            for label in info['cluster_labels']:
                cluster_mask = cluster_labels == label
                if np.any(cluster_mask):
                    cluster_scores = sample_scores[cluster_mask]
                    # Filter out NaN values for DBSCAN noise points
                    cluster_scores = cluster_scores[~np.isnan(cluster_scores)]
                    if len(cluster_scores) > 0:
                        cluster_silhouette_scores[label] = np.mean(cluster_scores)
        
        self.results_table.setRowCount(info['n_clusters'])
        for i, (label, size) in enumerate(zip(info['cluster_labels'], info['cluster_sizes'])):
            # Cluster label
            cluster_text = str(label) if label != -1 else "Noise"
            self.results_table.setItem(i, 0, QTableWidgetItem(cluster_text))
            
            # Cluster size
            self.results_table.setItem(i, 1, QTableWidgetItem(str(size)))
            
            # Silhouette score
            if label in cluster_silhouette_scores:
                score_text = f"{cluster_silhouette_scores[label]:.3f}"
            else:
                score_text = "N/A"
            self.results_table.setItem(i, 2, QTableWidgetItem(score_text))
        
        # Add overall silhouette score if available
        if 'silhouette_score' in info:
            # Add a separator row and overall score
            current_rows = self.results_table.rowCount()
            self.results_table.setRowCount(current_rows + 2)
            
            # Empty separator row
            for col in range(3):
                self.results_table.setItem(current_rows, col, QTableWidgetItem(""))
            
            # Overall score row
            self.results_table.setItem(current_rows + 1, 0, QTableWidgetItem("Overall"))
            self.results_table.setItem(current_rows + 1, 1, QTableWidgetItem(""))
            self.results_table.setItem(current_rows + 1, 2, 
                                     QTableWidgetItem(f"{info['silhouette_score']:.3f}"))
    
    def on_viz_changed(self):
        """Handle visualization mode change."""
        mode_map = {
            'PCA 2D': 'pca_2d',
            'PCA 3D': 'pca_3d',
            'Spectra': 'spectra',
            'Centroids': 'centroids',
            'Dendrogram': 'dendrogram',
            'Elbow Plot': 'elbow',
            'Silhouette Analysis': 'silhouette'
        }
        current = self.viz_combo.currentText()
        self.dendro_group.setVisible(current == 'Dendrogram')
        self.pca2d_group.setVisible(current == 'PCA 2D')
        # Rendering for views with one line/point per spectrum (Spectra,
        # PCA 2D/3D) can take a noticeable moment with many spectra. This
        # can't be threaded the way the clustering computation itself was
        # — matplotlib's draw() must run on the GUI thread, since it
        # touches the canvas widget directly — so a busy cursor is the
        # most that can honestly be shown here, not a progress dialog.
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        QApplication.processEvents()
        try:
            self.canvas.set_visualization_mode(mode_map[current])
        finally:
            QApplication.restoreOverrideCursor()

    def _replot_dendrogram(self):
        """Re-draw the dendrogram when any of its display options change."""
        if self.viz_combo.currentText() == 'Dendrogram':
            self.canvas.set_visualization_mode('dendrogram')

    def _replot_pca2d(self):
        """Re-draw the PCA 2D plot when its display options change."""
        if self.viz_combo.currentText() == 'PCA 2D':
            self.canvas.set_visualization_mode('pca_2d')

    def _show_pca2d_options_help(self):
        QMessageBox.information(
            self, 'PCA 2D options',
            "With many spectra, drawing a label on every point is the "
            "slowest part of this plot. Turning labels off speeds up "
            "plotting noticeably; clusters are still distinguished by "
            "colour, which gives a clear global picture even without them.\n\n"
            "Tip: changing the font size while labels are visible re-draws "
            "every label at the new size, which can be slow with many "
            "spectra. It's faster to turn labels off, change the font "
            "size, then turn labels back on."
        )
    
    def save_excel_results(self):
        """Save clustering results to Excel."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Cluster Analysis", "cluster_results.xlsx",
            "Excel Files (*.xlsx)"
        )
        
        if filepath:
            if self.controller.manager.save_results_excel(filepath):
                QMessageBox.information(self, "Success", "Results saved successfully to Excel")
            else:
                QMessageBox.warning(self, "Error", "Failed to save results")
                
    def show_help(self):
        """Show cluster analysis help window."""
        from src.help.cluster_analysis_help import (
            get_cluster_analysis_help_content,
            get_cluster_analysis_help_title
        )
        from src.help.help_window import show_help_window
        
        content = get_cluster_analysis_help_content()
        title = get_cluster_analysis_help_title()
        show_help_window(self, title, content)