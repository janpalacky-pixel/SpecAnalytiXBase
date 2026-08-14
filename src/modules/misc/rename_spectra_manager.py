
# src/modules/misc/rename_spectra_manager.py
from src.modules.utils.correction_history import append_correction_history


class RenameSpectraManager:
    """Business logic for managing spectrum renaming operations."""
    
    def __init__(self):
        pass  # No state to initialize for now
        
    def apply_renamed_labels(self, spectra, renamed_labels):
        """
        Apply renamed labels to spectra list.
        
        Args:
            spectra (list): List of spectrum dictionaries
            renamed_labels (dict): Dictionary mapping original labels to new labels
            
        Returns:
            bool: True if any changes were made
        """
        if not renamed_labels:
            return False
            
        changes_made = False
        
        # Update original_spectra metadata and labels
        for spectrum in spectra:
            if spectrum['label'] in renamed_labels:
                old_label = spectrum['label']
                new_label = renamed_labels[old_label]
                # Update the label
                spectrum['label'] = new_label
                # Update the metadata
                if 'label' in spectrum['metadata']:
                    spectrum['metadata']['label'] = new_label
                if 'spectrum_name' in spectrum['metadata']:
                    spectrum['metadata']['spectrum_name'] = new_label
                # Record the previous name via the same correction_history
                # mechanism every other operation uses — a spectrum
                # renamed more than once ends up with multiple 'Rename'
                # entries in order, so the FULL naming lineage is
                # visible, not just the single most-recent previous name.
                spectrum['metadata']['correction_history'] = append_correction_history(
                    spectrum['metadata'], 'Rename',
                    {'previous_label': old_label, 'new_label': new_label}
                )
                changes_made = True
                
        return changes_made