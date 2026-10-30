
# src/controllers/grid_properties_controller.py
from src.views.dialogs.visualization.grid_properties_dialog import GridPropertiesDialog
from src.modules.visualization.grid_properties_manager import GridManager

class GridPropertiesController:
    def __init__(self, main_controller):
        self.controller = main_controller
        # self.grid_manager = GridManager()
        
        # Create the grid_manager attribute if it doesn't exist
        if not hasattr(main_controller, 'grid_manager'):
            main_controller.grid_manager = GridManager()
        self.grid_manager = main_controller.grid_manager        

    def show_dialog(self):
        """Show the grid properties dialog and apply settings."""
        dialog = GridPropertiesDialog(
            self.controller.view,
            settings=self.grid_manager.get_current_settings()
        )

        # beside the plot (zoom and pan it while the window is open); Apply
        # shows the settings at once
        from src.views.plot_only_mode import add_apply_button, run_beside_plot
        add_apply_button(dialog, lambda: self._apply_from(dialog))
        if run_beside_plot(dialog, "Grid"):
            settings = dialog.get_settings()
            self.grid_manager.update_settings(settings)
            self.apply_settings()
            
    def _apply_from(self, dialog):
        """Apply in the window: its settings on the plot, the window stays open."""
        self.grid_manager.update_settings(dialog.get_settings())
        self.apply_settings()

    def apply_settings(self):
        """Apply current settings to the plot."""
        if self.controller.static_canvas:
            figure = self.controller.static_canvas.figure
            for ax in figure.get_axes():
                self.grid_manager.apply_settings_to_grid(ax)
            
            # Redraw the canvas to show changes
            self.controller.static_canvas.draw()
            
    def reset_to_defaults(self):
        """Reset settings to defaults and apply them."""
        self.grid_manager.reset_to_defaults()
        self.apply_settings()
        
    def get_current_settings(self):
        """Get the current grid settings."""
        return self.grid_manager.get_current_settings()