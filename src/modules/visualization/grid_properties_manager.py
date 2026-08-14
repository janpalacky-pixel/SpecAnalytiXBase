
# src/modules/visualization/grid_properties_manager.py

class GridManager:
    """Business logic for managing grid properties and applying them to plots."""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """Implement the singleton pattern to ensure only one instance exists."""
        if cls._instance is None:
            cls._instance = super(GridManager, cls).__new__(cls)
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
            'major_grid_visible': True,
            'minor_grid_visible': False,
            'major_grid_width': 0.8,
            'minor_grid_width': 0.5,
            'major_grid_color': '#CCCCCC',  # Light gray
            'minor_grid_color': '#E5E5E5',  # Lighter gray
            'major_grid_style': '-',        # Solid line
            'minor_grid_style': ':'         # Dotted line
        }
        
        # Current settings (starts with defaults)
        self.current_settings = self.default_settings.copy()
        self._initialized = True
    
    def apply_settings_to_grid(self, ax, settings=None):
        """
        Apply grid settings to the given axis.
        
        Args:
            ax: matplotlib axis object
            settings: optional dictionary to override current settings
        """
        if settings is None:
            settings = self.current_settings
            
        # Enable minor ticks (required for minor grid)
        ax.minorticks_on()
        
        # Configure major grid
        if settings['major_grid_visible']:
            ax.grid(True, which='major',
                   linewidth=settings['major_grid_width'],
                   linestyle=settings['major_grid_style'],
                   color=settings['major_grid_color'])
        else:
            ax.grid(False, which='major')
        
        # Configure minor grid
        if settings['minor_grid_visible']:
            ax.grid(True, which='minor',
                   linewidth=settings['minor_grid_width'],
                   linestyle=settings['minor_grid_style'],
                   color=settings['minor_grid_color'])
        else:
            ax.grid(False, which='minor')
            
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