
# src/controllers/legend_properties_controller.py
from src.views.dialogs.visualization.legend_properties_dialog import LegendPropertiesDialog
from src.modules.visualization.legend_properties_manager import LegendManager

class LegendPropertiesController:
    def __init__(self, main_controller):
        self.controller = main_controller
        # self.legend_manager = LegendManager()
        
        # Create the legend_manager attribute if it doesn't exist
        if not hasattr(main_controller, 'legend_manager'):
            main_controller.legend_manager = LegendManager()
        self.legend_manager = main_controller.legend_manager        

    def show_dialog(self):
        """Show the legend properties dialog and apply settings."""
        dialog = LegendPropertiesDialog(
            self.controller.view,
            settings=self.legend_manager.get_current_settings()
        )

        # Show the dialog and wait for user response
        if dialog.exec_():
            settings = dialog.get_settings()
            self.legend_manager.update_settings(settings)
            self.apply_settings()
            
    def apply_settings(self):
        """Apply current settings to the plot."""
        if self.controller.static_canvas:
            figure = self.controller.static_canvas.figure
            for ax in figure.get_axes():
                self.legend_manager.apply_settings_to_legend(ax)
            
            # Redraw the canvas to show changes
            self.controller.static_canvas.draw()
            
    def reset_to_defaults(self):
        """Reset settings to defaults and apply them."""
        self.legend_manager.reset_to_defaults()
        self.apply_settings()
        
    def get_current_settings(self):
        """Get the current legend settings."""
        return self.legend_manager.get_current_settings()