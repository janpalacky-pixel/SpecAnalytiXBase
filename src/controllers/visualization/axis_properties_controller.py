
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

        # Show the dialog and wait for user response
        if dialog.exec_():
            settings = dialog.get_settings()
            self.axis_manager.update_settings(settings)
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