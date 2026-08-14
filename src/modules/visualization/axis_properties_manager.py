# src/modules/visualization/axis_properties_manager.py

class AxisManager:
    """Business logic for managing axis properties and applying them to plots."""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """Implement the singleton pattern to ensure only one instance exists."""
        if cls._instance is None:
            cls._instance = super(AxisManager, cls).__new__(cls)
            # Initialize the instance (will be called only once)
            cls._instance._initialized = False
        return cls._instance    
    
    def __init__(self):
        # Guard against re-initialization: __new__ returns the same
        # cached singleton instance on every call, but Python still
        # runs __init__ on it EVERY time regardless — unguarded, this
        # silently resets current_settings back to defaults on any
        # second instantiation, discarding whatever the user had
        # customized. Currently this only 'works' because every caller
        # happens to gate its own instantiation behind a hasattr()
        # check on the owning controller (see e.g.
        # AxisPropertiesController.__init__) — an external convention
        # with no protection here if anything else ever calls this
        # constructor directly. Matches the guard
        # ConstrainedLayoutManager already uses correctly.
        if hasattr(self, '_initialized') and self._initialized:
            return
        # Default settings
        self.default_settings = {
            'x_label': 'X-axis',
            'y_label': 'Y-axis',
            'x_label_font_family': 'Arial',
            'y_label_font_family': 'Arial',
            'x_label_font_size': 12,
            'y_label_font_size': 12,
            'x_tick_font_family': 'Arial',
            'y_tick_font_family': 'Arial',
            'x_tick_font_size': 10,
            'y_tick_font_size': 10,
        }
        
        # Current settings (starts with defaults)
        self.current_settings = self.default_settings.copy()
        self._initialized = True
    
    def apply_settings_to_axis(self, ax, settings=None):
        """
        Apply axis settings to the given matplotlib axis.
        
        Args:
            ax: matplotlib axis object
            settings: optional dictionary to override current settings
        """
        if settings is None:
            settings = self.current_settings
        
        # Set X-axis properties
        ax.set_xlabel(settings['x_label'], 
                    fontfamily=settings['x_label_font_family'],
                    fontsize=settings['x_label_font_size'])
        
        # Set Y-axis properties
        ax.set_ylabel(settings['y_label'],
                    fontfamily=settings['y_label_font_family'],
                    fontsize=settings['y_label_font_size'])
        
        # Set tick label properties
        ax.tick_params(axis='x', labelsize=settings['x_tick_font_size'])
        ax.tick_params(axis='y', labelsize=settings['y_tick_font_size'])
        
        # Update tick label fonts
        for label in ax.get_xticklabels():
            label.set_family(settings['x_tick_font_family'])
        for label in ax.get_yticklabels():
            label.set_family(settings['y_tick_font_family'])
            
    def reset_to_defaults(self):
        """Reset settings to default values."""
        self.current_settings = self.default_settings.copy()
        return self.current_settings
        
    def update_settings(self, new_settings):
        """Update current settings with new values."""
        self.current_settings.update(new_settings)
        return self.current_settings
        
    def get_current_settings(self):
        """Return the current settings."""
        return self.current_settings.copy()
