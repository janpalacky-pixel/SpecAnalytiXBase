
# src/modules/visualization/legend_properties_manager.py
from matplotlib.font_manager import FontProperties

class LegendManager:
    """Business logic for managing legend properties and applying them to plots."""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """Implement the singleton pattern to ensure only one instance exists."""
        if cls._instance is None:
            cls._instance = super(LegendManager, cls).__new__(cls)
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
            'movable': True,
            'max_items': 20,
            'show_all_items': False,
            'font_size': 10,
            'font_family': 'Arial',
            'visible': False,          # Off by default — enable via ☰ Legend button
            'position': 'upper right',
            'outside_plot': False,
            'use_pagination': False,
            'columns': 1,
        }
        
        # Current settings (starts with defaults)
        self.current_settings = self.default_settings.copy()
        self._initialized = True
    
    def apply_settings_to_legend(self, ax, settings=None):
        """
        Apply legend settings to the given matplotlib axis.
        
        Args:
            ax: matplotlib axis object
            settings: optional dictionary to override current settings
        """
        if settings is None:
            settings = self.current_settings
            
        legend = ax.get_legend()
        
        # Step 1: Handle initial legend creation if needed
        if legend is None and settings['visible']:
            handles, labels = ax.get_legend_handles_labels()
            if handles:  # Only create legend if there are items to show
                legend = ax.legend(handles, labels, loc=settings['position'], ncol=settings['columns'])
        
        if legend:
            # Step 2: Update legend visibility
            legend.set_visible(settings['visible'])
            
            if settings['visible']:
                # Step 3: Create font properties object with desired settings
                font_prop = FontProperties(
                    family=settings['font_family'],
                    size=settings['font_size']
                )
                
                # Apply initial font properties to current legend
                for text in legend.get_texts():
                    text.set_fontproperties(font_prop)
                
                # Step 4: Handle legend items based on show_all_items setting
                handles, labels = ax.get_legend_handles_labels()
                
                # Limit items only if show_all_items is False and we exceed max_items
                if not settings['show_all_items']:
                    if len(handles) > settings['max_items']:
                        handles = handles[:settings['max_items']]
                        labels = labels[:settings['max_items']]
                
                # Always recreate the legend to apply any changes
                legend.remove()
                legend = ax.legend(handles, labels, loc=settings['position'], ncol=settings['columns'])
                
                # Reapply font properties to new legend
                for text in legend.get_texts():
                    text.set_fontproperties(font_prop)
                
                # Step 5: Set legend draggability
                legend.set_draggable(settings['movable'])

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