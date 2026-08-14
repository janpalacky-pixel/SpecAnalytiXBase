
# src/modules/visualization/constrained_layout_manager.py
class ConstrainedLayoutManager:
    """Manager for constrained layout properties and applying them to plots."""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """Implement the singleton pattern to ensure only one instance exists."""
        if cls._instance is None:
            cls._instance = super(ConstrainedLayoutManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize default settings (only runs once due to singleton pattern)."""
        if not hasattr(self, '_initialized') or not self._initialized:
            # Default settings
            self.default_settings = {
                'w_pad': 0.03,  # Width padding in inches
                'h_pad': 0.03,  # Height padding in inches
                'wspace': 0.01,  # Width space between subplots (fraction)
                'hspace': 0.01,  # Height space between subplots (fraction)
                'use_adaptive_padding': True,  # Whether to adapt padding to figure size
                'adaptive_factor': 0.01  # Percentage of figure size for adaptive padding
            }
            
            # Current settings (starts with defaults)
            self.current_settings = self.default_settings.copy()
            self._initialized = True
    
    def apply_settings_to_figure(self, fig):
        """
        Apply constrained layout settings to the given figure.
        
        Args:
            fig: matplotlib figure object
        """
        settings = self.current_settings
        
        # Enable constrained layout
        fig.set_constrained_layout(True)
        
        # Calculate adaptive padding if enabled
        if settings['use_adaptive_padding']:
            width, height = fig.get_size_inches()
            w_padding = max(settings['w_pad'], width * settings['adaptive_factor'])
            h_padding = max(settings['h_pad'], height * settings['adaptive_factor'])
        else:
            w_padding = settings['w_pad']
            h_padding = settings['h_pad']
        
        # Apply settings to figure
        fig.set_constrained_layout_pads(
            w_pad=w_padding,
            h_pad=h_padding,
            wspace=settings['wspace'],
            hspace=settings['hspace']
        )
            
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