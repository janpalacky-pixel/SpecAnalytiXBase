
# src/controllers/axis_properties_controller.py
from src.views.dialogs.visualization.axis_properties_dialog import AxisPropertiesDialog
from src.modules.visualization.axis_properties_manager import AxisManager

class AxisPropertiesController:
    def __init__(self, main_controller):
        self.controller = main_controller
        # self.axis_manager = AxisManager()
        
        # Create the axis_manager attribute if it doesn't exist
        if not hasattr(main_controller, 'axis_manager'):
            main_controller.axis_manager = AxisManager()
        self.axis_manager = main_controller.axis_manager        

    def show_dialog(self):
        """Show the axis properties dialog and apply settings."""
        dialog = AxisPropertiesDialog(
            self.controller.view,
            settings=self.axis_manager.get_current_settings()
        )

        # beside the plot (zoom and pan it while the window is open); Apply
        # shows the settings at once
        from src.views.plot_only_mode import add_apply_button, run_beside_plot
        add_apply_button(dialog, lambda: self._apply_from(dialog))
        if run_beside_plot(dialog, "Axis properties"):
            settings = dialog.get_settings()
            self.axis_manager.update_settings(settings)
            self.apply_settings()
            
    def _apply_from(self, dialog):
        """Apply in the window: its settings on the plot, the window stays open."""
        self.axis_manager.update_settings(dialog.get_settings())
        self.apply_settings()

    def apply_settings(self):
        """Apply current settings to the plot."""
        if self.controller.static_canvas:
            figure = self.controller.static_canvas.figure
            for ax in figure.get_axes():
                self.axis_manager.apply_settings_to_axis(ax)
            
            # Redraw the canvas to show changes
            self.controller.static_canvas.draw()
            
    def reset_to_defaults(self):
        """Reset settings to defaults and apply them."""
        self.axis_manager.reset_to_defaults()
        self.apply_settings()
        
    def get_current_settings(self):
        """Get the current axis settings."""
        return self.axis_manager.get_current_settings()