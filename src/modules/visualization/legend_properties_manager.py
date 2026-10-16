
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
            'visible': True,           # On by default (since 1.5): at most max_items
                                       # entries, evenly spread -- quick also with
                                       # thousands of spectra; off via ☰ Legend
            'position': 'upper right',
            'outside_plot': False,
            'use_pagination': False,
            'columns': 1,
        }
        
        # Current settings (starts with defaults)
        self.current_settings = self.default_settings.copy()
        # Entries picked with "Choose..." (orange strip above the plot): the
        # legend texts of the plot they were picked for and the picked
        # positions. Dropped as soon as the plotted spectra differ. Not a
        # setting (not saved), only for the plot on screen.
        self.chosen = None
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
                # already limited: a legend of thousands of entries is slow to
                # build even though it is replaced below
                handles, labels, _ = self.limit_entries(handles, labels, settings)
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
                handles, labels, info = self.limit_entries(handles, labels, settings)
                ax._legend_entries_info = info      # for the note above the plot
                
                # Always recreate the legend to apply any changes
                legend.remove()
                legend = ax.legend(handles, labels, loc=settings['position'], ncol=settings['columns'])
                
                # Reapply font properties to new legend
                for text in legend.get_texts():
                    text.set_fontproperties(font_prop)
                
                # Step 5: Set legend draggability
                legend.set_draggable(settings['movable'])

    def limit_entries(self, handles, labels, settings=None):
        """The legend entries to list: all with 'Show all'; the ones picked
        with Choose... (same plot only); otherwise, above the maximum, an
        evenly spread subset (first and last included, like the plot
        preview of very many spectra). Returns (handles, labels, info) with
        info = {'total', 'shown', 'mode': 'all' | 'chosen' | 'spread'}."""
        settings = settings if settings is not None else self.current_settings
        total = len(handles)
        mode = 'all'
        keep = None
        if not settings.get('show_all_items', False):
            keep = self.chosen_indices(labels)
            if keep is not None:
                mode = 'chosen'
            elif total > settings.get('max_items', 20):
                from src.modules.visualization.large_selection import preview_indices
                keep = preview_indices(total, settings.get('max_items', 20))
                mode = 'spread'
        if keep is not None:
            handles = [handles[i] for i in keep]
            labels = [labels[i] for i in keep]
        return handles, labels, {'total': total, 'shown': len(handles), 'mode': mode}

    def chosen_indices(self, labels):
        """Positions picked with Choose... -- only for the same plotted
        entries (the same legend texts in the same order)."""
        if not self.chosen or tuple(labels) != self.chosen['labels']:
            return None
        return [i for i in self.chosen['indices'] if 0 <= i < len(labels)]

    def set_chosen(self, labels, indices):
        self.chosen = ({'labels': tuple(labels), 'indices': sorted(set(indices))}
                       if indices else None)

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