
# src/controllers/visualization/constrained_layout_controller.py
from src.views.dialogs.visualization.constrained_layout_dialog import ConstrainedLayoutDialog
from src.modules.visualization.constrained_layout_manager import ConstrainedLayoutManager

class ConstrainedLayoutController:
    def __init__(self, main_controller):
        self.controller = main_controller
        
        # Create a shared ConstrainedLayoutManager instance or use an existing one
        if not hasattr(main_controller, 'constrained_layout_manager'):
            main_controller.constrained_layout_manager = ConstrainedLayoutManager()
        self.layout_manager = main_controller.constrained_layout_manager
        
    def show_dialog(self):
        """Show the constrained layout properties dialog and apply settings."""
        dialog = ConstrainedLayoutDialog(
            self.controller.view,
            settings=self.layout_manager.get_current_settings()
        )
        
        # beside the plot (zoom and pan it while the window is open); Apply
        # shows the settings at once
        from src.views.plot_only_mode import add_apply_button, run_beside_plot
        add_apply_button(dialog, lambda: self._apply_from(dialog))
        if run_beside_plot(dialog, "Layout properties"):
            settings = dialog.get_settings()
            self.layout_manager.update_settings(settings)
            self.apply_settings()
            
    def _apply_from(self, dialog):
        """Apply in the window: its settings on the plot, the window stays open."""
        self.layout_manager.update_settings(dialog.get_settings())
        self.apply_settings()

    def apply_settings(self):
        """Apply current settings to the plot."""
        if self.controller.static_canvas:
            figure = self.controller.static_canvas.figure
            self.layout_manager.apply_settings_to_figure(figure)
            
            # Redraw the canvas to show changes
            self.controller.static_canvas.draw()
            
    def reset_to_defaults(self):
        """Reset settings to defaults and apply them."""
        self.layout_manager.reset_to_defaults()
        self.apply_settings()
        
    def get_current_settings(self):
        """Get the current layout settings."""
        return self.layout_manager.get_current_settings()