# src/modules/data_analysis/incremental_operations_manager.py

from datetime import datetime
from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)
from PyQt5.QtCore import pyqtSignal, QObject

class IncrementalOperationsManager(QObject):
    """
    Manages a chain of operations applied incrementally to spectra.
    Each operation builds on the previous operation's output.
    Only tracks and applies operations to the spectra they were explicitly applied to.
    """
    
    baseline_state_changed = pyqtSignal(object)  # Signal emitted when baseline state changes
    
    def __init__(self):
        super().__init__()
        self.original_spectra = []  # Original spectra before any operations
        self.operations_chain = []  # List of operations in order of application
        self.active_operation_index = -1  # Index of currently active operation (-1 for original)
        self._controller = None   # Reference to main controller, will be set in OperationsController.__init__
        self.import_batches = []  # List to track import batches
        # Original State has no operation record of its own to carry a
        # fixed "affected_labels" list, the way every other step in the
        # chain does. This is its equivalent: whatever was selected the
        # last time an operation was committed while Original State was
        # still the active state — i.e. the last time Original State was
        # actually "current". Updated in apply_operation(), read back in
        # OperationsController.jump_to_operation_state().
        self.original_state_selected_labels = []

        # A single, monotonically-increasing counter, bumped every time
        # the ACTUAL spectra content a dialog would be looking at
        # changes -- a new operation applied (apply_operation), history
        # navigation landing on a different state (set_active_operation),
        # or new spectra being imported (add_spectra_to_original).
        #
        # Exists so a dialog whose controller keeps ONE persistent
        # manager alive across close/reopen (Map2DController,
        # BaselineCorrectionController, NMFController, ... -- see each
        # one's own __init__) can tell "nothing happened since I was
        # last open, it's safe to restore what I had" apart from
        # "something changed underneath me while I was closed, my
        # cached state/results no longer describe these spectra and
        # must be dropped" -- without this, a controller had only two
        # bad choices: never forget (a stale NMF/MCR-ALS map, or stale
        # manual-baseline points from before a SNIP correction, silently
        # shown as current -- see Map2DManager.reset()'s docstring for
        # the concrete bug), or always forget (NMFController/
        # MCRALSController's show_dialog() today -- correct, but throws
        # away a perfectly good remembered state on every single
        # reopen, even when literally nothing changed).
        #
        # A caller records this value (e.g. self._last_seen_revision)
        # when it last trusted its own cached state, and compares it
        # against self.operations_manager.revision the next time its
        # dialog opens: equal -> restore, different -> reset. It is a
        # plain monotonic counter, NOT a state identifier -- jumping to
        # a history state (undo/redo) always bumps it to a new number
        # too, even if you land back on an index you'd visited before,
        # so "equal" only ever means "provably nothing happened since",
        # never "we're back to a state I've cached before". That's the
        # right tradeoff for every current caller (each just resets its
        # own cache on any change), and keeps this simple; if a future
        # caller ever wants "restore my cache for this exact history
        # state even across undo/redo", that needs a real per-state
        # identifier instead of this counter, not an assumption about it.
        #
        # Deliberately NOT bumped by: a Rename commit (see
        # apply_operation()'s own exception for it -- labels aren't
        # data), or a plain spectrum deletion/removal (never routed
        # through apply_operation() at all -- no Operations History
        # entry is created for it). Both leave every other spectrum's
        # own identity-keyed cached state exactly as valid as it was.
        self.revision = 0
        
    def add_spectra_to_original(self, new_spectra):
        """
        Add new spectra to the original spectra list without affecting existing operations.
        
        Args:
            new_spectra: List of new spectrum dictionaries to add
        """
        if not new_spectra:
            return
            
        logger.debug("Adding %d new spectra to operations manager", len(new_spectra))
        logger.debug("Current import_batches before adding: %d", len(getattr(self, "import_batches", [])))
        
        # Initialize import_batches if it doesn't exist
        if not hasattr(self, 'import_batches'):
            self.import_batches = []
            logger.debug("Created new import_batches list")
        
        # Get existing spectrum labels
        existing_labels = {spectrum['label'] for spectrum in self.original_spectra}
        
        # Track new labels for this batch
        new_batch_labels = []
        
        # Add only new spectra that don't already exist
        added_count = 0
        for spectrum in new_spectra:
            if spectrum['label'] not in existing_labels:
                import numpy as np
                spectrum_copy = {}
                for key, value in spectrum.items():
                    if isinstance(value, np.ndarray):
                        spectrum_copy[key] = value.copy()
                    elif isinstance(value, dict):
                        inner = {}
                        for k, v in value.items():
                            inner[k] = v.copy() if isinstance(v, np.ndarray) else v
                        spectrum_copy[key] = inner
                    else:
                        spectrum_copy[key] = value
                
                self.original_spectra.append(spectrum_copy)
                new_batch_labels.append(spectrum['label'])
                added_count += 1
        
        # Record this new batch
        if new_batch_labels:
            self.import_batches.append({
                'timestamp': datetime.now().isoformat(),
                'spectra_labels': new_batch_labels
            })
            logger.debug("Added new batch with %d spectra", len(new_batch_labels))
            logger.debug("New import_batches count: %d", len(self.import_batches))
        
        logger.debug("Added %d new spectra to original_spectra", added_count)
        if added_count:
            self.revision += 1
        
    def _deep_copy_spectra(self, spectra):
        """Create a proper deep copy of a list of spectra.

        Copies ALL numpy array values (not just x_scale/y_scale) and all nested
        dicts so that no spectrum in the result shares mutable data with any
        other spectrum or with the source list.
        """
        import numpy as np
        result = []
        for spectrum in spectra:
            copied_spectrum = {}
            for key, value in spectrum.items():
                if isinstance(value, np.ndarray):
                    copied_spectrum[key] = value.copy()
                elif isinstance(value, dict):
                    # Shallow copy the dict, deep-copy any arrays inside it
                    inner = {}
                    for k, v in value.items():
                        inner[k] = v.copy() if isinstance(v, np.ndarray) else v
                    copied_spectrum[key] = inner
                elif isinstance(value, list):
                    copied_spectrum[key] = list(value)
                else:
                    copied_spectrum[key] = value
            result.append(copied_spectrum)
        return result
    
    def initialize_with_spectra(self, spectra):
        """Initialize with original spectra (first import)."""
        # Reset state
        self.operations_chain = []
        self.active_operation_index = -1
        self.revision += 1

        # Store a deep copy of the original spectra
        self.original_spectra = self._deep_copy_spectra(spectra)
        
        # Initialize import batches tracking
        self.import_batches = [{'timestamp': datetime.now().isoformat(), 'spectra_labels': [s['label'] for s in spectra]}]
        logger.debug("Initialized import_batches with first batch of %d spectra", len(spectra))
        
    def apply_operation(self, operation_type, parameters, affected_spectra, new_state_spectra=None, baseline_state=None):
        """
        Apply a new operation, building on previous operations.
    
        Args:
            operation_type: String identifier for the operation type.
            parameters: Dictionary of parameters for the operation.
            affected_spectra: List of spectra that were modified or used by the operation.
            new_state_spectra: (Optional) A complete list of all spectra for the next state.
                               If provided, this is used directly. If None, the next state is
                               constructed by updating the current state with affected_spectra.
            baseline_state: Optional dictionary for baseline operations.
        """
        if self.active_operation_index < len(self.operations_chain) - 1:
            self.operations_chain = self.operations_chain[:self.active_operation_index + 1]

        # If Original State is still the active state right now, this
        # commit is about to move away from it — record what was selected
        # at this exact moment as Original State's own remembered
        # selection (overwriting whatever was captured the previous time,
        # since this is now the most recent moment it was actually
        # current). Mirrors how every other step's affected_labels is
        # fixed at the moment that step was applied.
        if self.active_operation_index == -1:
            self.original_state_selected_labels = [s['label'] for s in affected_spectra]
    
        # Use the provided new state directly if available (for add/remove/replace operations)
        if new_state_spectra is not None:
            complete_output_spectra = new_state_spectra
        else:
            # Original logic for modification-in-place operations
            current_state = self.get_current_spectra()
            affected_labels = {s['label'] for s in affected_spectra}
            unaffected_spectra = [s for s in current_state if s['label'] not in affected_labels]
            complete_output_spectra = unaffected_spectra + affected_spectra
    
        # Always deep-copy before storing so that subsequent in-place mutations
        # (e.g. Data Range modifying x_scale/y_scale) cannot corrupt this record.
        complete_output_spectra = self._deep_copy_spectra(complete_output_spectra)

        # Create the operation record
        timestamp = datetime.now().isoformat()
        operation_record = {
            'type': operation_type,
            'timestamp': timestamp,
            'parameters': parameters,
            'affected_labels': [s['label'] for s in affected_spectra], # For display in history
            'output_spectra': complete_output_spectra,
        }
        
        if baseline_state is not None:
            operation_record['baseline_state'] = baseline_state
        
        self.operations_chain.append(operation_record)
        self.active_operation_index = len(self.operations_chain) - 1

        # Rename is the one operation type recorded here that never
        # touches any spectrum's actual measured data (x_scale/y_scale)
        # -- it only changes labels. Every cache this counter protects
        # (manual baseline points, NMF/MCR-ALS fits, stored subtraction
        # factors, detected spikes, ...) is already keyed by unique_id
        # rather than by label specifically so it survives a rename (see
        # e.g. BaselineManager._key_for, SpikeRemovalManager._key_for,
        # InteractiveSubtractionManager._key_for) -- bumping revision for
        # a Rename would throw all of that cached state away for no
        # reason every single time, which is exactly the "always forget"
        # problem this counter exists to avoid. Every other operation
        # type recorded here does change data, so it still bumps.
        if operation_type != 'Rename':
            self.revision += 1

        return True
    
    def get_current_spectra(self):
        """
        Get the spectra at the currently active operation.
        
        Returns:
            List of current spectra
        """
        if self.active_operation_index < 0:
            # Return original spectra
            spectra = self._deep_copy_spectra(self.original_spectra)
        else:
            # Return the output of the active operation
            output_spectra = self.operations_chain[self.active_operation_index].get('output_spectra', [])
            spectra = self._deep_copy_spectra(output_spectra)
        return self._dedupe_labels(spectra)

    def _dedupe_labels(self, spectra):
        """Guarantee no two spectra in *spectra* share a label — a general
        safety net in case a duplicate ever arises by any means (e.g. a
        label freed up by deletion later reused by an unrelated spectrum
        on the same step, or any other cause not anticipated here). Every
        consumer of spectra state goes through get_current_spectra(), so
        enforcing the invariant here covers all of them. Renaming itself
        is forward-only (see RenameSpectraController) and is already
        blocked outright by a live "Duplicate Name" check before it ever
        reaches here — this dedup pass is a backstop for anything else,
        not the primary defense against renaming collisions.

        Any duplicate beyond the first occurrence of a given label is
        suffixed to stay unique. This only ever changes the display
        label, never unique_id, and is logged so it's visible rather than
        silent.
        """
        seen = {}
        for spectrum in spectra:
            label = spectrum['label']
            if label not in seen:
                seen[label] = 1
                continue
            seen[label] += 1
            new_label = f"{label}_{seen[label]}"
            while new_label in seen:
                seen[label] += 1
                new_label = f"{label}_{seen[label]}"
            logger.warning(
                "IncrementalOperationsManager: duplicate label '%s' detected "
                "when building current state — renaming the duplicate to '%s'.",
                label, new_label
            )
            spectrum['label'] = new_label
            if isinstance(spectrum.get('metadata'), dict) and 'label' in spectrum['metadata']:
                spectrum['metadata']['label'] = new_label
            seen[new_label] = 1
        return spectra
    
    def get_operation_at_index(self, index):
        """
        Get operation record at specified index.
        
        Args:
            index: Index of operation to retrieve
            
        Returns:
            Operation record or None if not found
        """
        if 0 <= index < len(self.operations_chain):
            return self.operations_chain[index]
        return None
    
    def set_active_operation(self, index):
        """
        Set the active operation to the given index.
        
        Args:
            index: Index of operation to set as active (-1 for original state)
            
        Returns:
            Current spectra after setting the active operation
        """
        if index < -1 or index >= len(self.operations_chain):
            return None

        # Landing on a different state changes what a dialog would see
        # just as much as a brand-new operation does (see self.revision's
        # own docstring in __init__) -- bump only when the index is
        # actually moving, so re-selecting the state already active
        # (e.g. re-clicking the current row in Operations History) isn't
        # treated as a change.
        if index != self.active_operation_index:
            self.revision += 1

        # Update active operation index
        self.active_operation_index = index
        
        # Get current spectra
        spectra = self.get_current_spectra()
        
        # Restore baseline state if this is a baseline operation
        if index >= 0:
            operation = self.operations_chain[index]
            if operation['type'] == 'Manual baseline' and 'baseline_state' in operation:
                self._restore_baseline_state(operation['baseline_state'])
        else:
            # Clear baseline state when returning to original
            self._clear_baseline_state()
        
        return spectra
    
    def _restore_baseline_state(self, baseline_state):
        """Restore baseline state to main controller."""
        if hasattr(self, '_controller') and hasattr(self._controller, 'baseline_correction_controller'):
            bc_controller = self._controller.baseline_correction_controller
            manager = bc_controller.manager
            
            # Clear current state
            manager.clear_all_baselines()
            
            # Restore points and settings from baseline_state
            for label, state in baseline_state.items():
                # Set fit type
                if 'type' in state:
                    manager.set_fit_type(label, state['type'])
                
                # Set polynomial order if applicable
                if 'order' in state and state['order'] is not None:
                    manager.set_poly_order(label, state['order'])
                
                # Add each baseline point
                if 'points' in state and isinstance(state['points'], list):
                    for point in state['points']:
                        if isinstance(point, (list, tuple)) and len(point) >= 2:
                            manager.add_baseline_point(label, point[0], point[1])
        
    def _clear_baseline_state(self):
        """Clear baseline state in main controller."""
        if hasattr(self, '_controller') and hasattr(self._controller, 'baseline_correction_controller'):
            bc_controller = self._controller.baseline_correction_controller
            bc_controller.manager.clear_all_baselines()    

    def get_operations_summary(self):
        """
        Get a summary of all operations in the chain.
        
        Returns:
            List of summary strings for each operation
        """
        summary = []
        
        for i, operation in enumerate(self.operations_chain):
            op_type = operation['type']
            timestamp = datetime.fromisoformat(operation['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            
            # Get the number of affected spectra
            affected_labels = operation.get('affected_labels', [])
            
            # Mark the active operation
            is_active = "(active)" if i == self.active_operation_index else ""
            
            summary_str = f"{i+1}. {op_type} {is_active}\n"
            
            # Clearer description of affected spectra
            if affected_labels:
                summary_str += f"   Operation affected {len(affected_labels)} spectra\n"
            else:
                summary_str += "   No spectra were affected\n"
                
            summary_str += f"   Applied: {timestamp}"
            
            summary.append(summary_str)
        
        return summary

    def get_formatted_parameters(self, index):
        """
        Get formatted parameters for an operation.
        
        Args:
            index: Index of the operation
            
        Returns:
            String with formatted parameters or None if operation not found
        """
        # NOTE on two bugs fixed here:
        #  1. `self.operations_manager` — this method is defined ON
        #     IncrementalOperationsManager itself, so `self` already IS
        #     the operations manager; `self.operations_manager` doesn't
        #     exist anywhere in __init__ and would raise AttributeError
        #     on every call. Should be `self.operations_chain` directly.
        #  2. Every op_type string compared below used to be lowercase
        #     ("data range", "normalization") while every real call to
        #     apply_operation() across the app uses Title Case ("Data
        #     range", "Normalization" — verified directly against every
        #     apply_operation() call site in operations_controller.py).
        #     Only "SG-smoothing" and "SVD background" happened to match
        #     by coincidence; the other two branches could never fire for
        #     any real operation and silently fell through to the generic
        #     formatter every time.
        if 0 <= index < len(self.operations_chain):
            operation = self.operations_chain[index]
            op_type = operation['type']
            params = operation['parameters']
            
            if op_type == "Data range":
                return self._format_data_range_params(params)
            elif op_type == "Normalization":
                return self._format_normalization_params(params)
            elif op_type == "SG-smoothing":
                return self._format_sg_parameters(params)
            elif op_type == "SVD background":
                return self._format_svd_background_params(params)
            elif op_type == "Manual baseline":
                return self._format_baseline_params(params)
            elif op_type == "Cosmic ray removal":
                return self._format_cosmic_ray_params(params)
            elif op_type == "Spike removal":
                return self._format_spike_removal_params(params)
            else:
                # Generic formatting for other operations
                return ", ".join(f"{k}: {self._humanize_value(v)}" for k, v in params.items())
        return None

    @staticmethod
    def _humanize_value(value):
        """Convert numpy scalar/array types to plain Python equivalents
        before display.

        A bare numpy scalar (e.g. np.float64(3.14)) already formats fine
        on its own with either str() or an f-string — that part didn't
        change in NumPy 2.0. What DID change: repr() of a numpy scalar
        now includes the type name (repr(np.float64(3.14)) ->
        "np.float64(3.14)"), and Python's own str()/repr() of a
        list/dict/tuple always uses repr() — not str() — on each element
        it contains. So a parameter value that's a plain number is fine,
        but one that's a LIST or DICT with numpy numbers inside it (e.g.
        fitting_ranges built from x_scale[idx] lookups, which are numpy
        floats, not plain Python ones) renders as
        "[np.float64(20.0), np.float64(100.2)]" the moment the whole
        list gets formatted, which is exactly what the generic
        "- key: value" formatter below does for any parameter it doesn't
        have dedicated formatting for. Recursing through and converting
        numpy types to native Python ones before formatting avoids this
        regardless of which operation or parameter shape it shows up in,
        rather than special-casing it per operation.
        """
        try:
            import numpy as np
        except ImportError:
            return value
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, dict):
            return {k: IncrementalOperationsManager._humanize_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return type(value)(IncrementalOperationsManager._humanize_value(v) for v in value)
        return value

    def _format_svd_background_params(self, params):
        """Format SVD background parameters for display."""
        summary_parts = []
        
        mode = params.get('correction_mode', 'all_subspectra')
        mode_display = {
            'all_subspectra': 'All subspectra',
            'corrected_only': 'Corrected subspectra only',
            'first_n': 'First N components',
            'selected': 'Selected components'
        }.get(mode, mode)
        
        summary_parts.append(f"- Mode: {mode_display}")
        
        if mode == 'first_n':
            max_comp = params.get('max_components', 10)
            summary_parts.append(f"- Components: First {max_comp}")
        elif mode == 'selected':
            selected = params.get('selected_subspectra', [])
            if selected:
                selected_str = ', '.join(str(i+1) for i in selected)
                summary_parts.append(f"- Selected: {selected_str}")
        
        # Show baseline correction info
        baseline_corrections = params.get('baseline_corrections', {})
        if baseline_corrections:
            summary_parts.append(f"- Baseline corrections: {len(baseline_corrections)} subspectra")
        
        return "\n".join(summary_parts)    
   
    
    def _format_cosmic_ray_params(self, params):
        """Format Cosmic ray removal parameters for display.

        Replaces a formatter that referenced a 'removed_spectra_count' key
        the settings dict passed to apply_operation() never actually
        contains (cosmic_ray_dialog.get_settings() only ever produces
        'threshold' and 'replace_window') — every Cosmic ray removal
        entry in Operations History / the exported parameters file showed
        "removed_spectra_count: 0" regardless of what actually happened.
        Per-spectrum specifics (which points, at which x-positions) live
        in each affected spectrum's own metadata['correction_history']
        (see CosmicRayManager.apply) — this is just the batch-level
        settings the operation was run with.
        """
        summary_parts = [f"- Threshold (modified Z-score): {params.get('threshold')}"]
        replace_window = params.get('replace_window')
        if replace_window is not None:
            summary_parts.append(f"- Replace window: ±{replace_window} point(s)")
        return "\n".join(summary_parts)

    def _format_spike_removal_params(self, params):
        """Format Spike removal parameters for display.

        Same 'removed_spectra_count' bug as Cosmic ray removal above (see
        _format_cosmic_ray_params) — spike_removal_interactive_dialog's
        get_settings() produces 'threshold', 'half_window',
        'effective_spikes' (per-spectrum spike-index lists) and
        'half_window_map', never 'removed_spectra_count'. Derives a
        batch-level spike/spectra count straight from 'effective_spikes'
        rather than requiring yet another dedicated key. Per-spectrum
        specifics (which points, at which x-positions) live in each
        affected spectrum's own metadata['correction_history'] (see
        SpikeRemovalController.apply_interactive_removal).
        """
        effective_spikes = params.get('effective_spikes', {})
        total_spikes = sum(len(v) for v in effective_spikes.values())
        n_affected = sum(1 for v in effective_spikes.values() if v)
        summary_parts = [
            f"- Spikes removed: {total_spikes} across {n_affected} spectrum/spectra",
            f"- Detection threshold (modified Z-score): {params.get('threshold')}",
            f"- Replace window: ±{params.get('half_window')} point(s)",
        ]
        return "\n".join(summary_parts)

    def _format_data_range_params(self, params):
        """Format data range parameters for display."""
        mode = "Exclude" if params.get('is_exclude_mode', False) else "Include"
        ranges_str = ", ".join([f"[{r[0]}-{r[1]}]" for r in params.get('ranges', [])])
        
        summary_parts = []
        summary_parts.append(f"- {mode} ranges: {ranges_str if ranges_str else 'None'}")
        
        if params.get('apply_linearization', False):
            summary_parts.append(f"- Linearization step: {params.get('x_step', 1.0)}")
        
        if params.get('x_min') is not None and params.get('x_max') is not None:
            summary_parts.append(f"- X limits: {params.get('x_min')} to {params.get('x_max')}")
        
        return "\n".join(summary_parts)
    
    def _format_normalization_params(self, params):
        """Format normalization parameters for display."""
        try:
            summary_parts = []
            
            # Safely get the normalization mode with a default
            mode = params.get('normalization_mode', 'minmax')
            mode_display = {
                'minmax': 'Min-Max',
                'area': 'Area',
                'peak': 'Peak'
            }.get(mode, mode)
            
            summary_parts.append(f"- Mode: {mode_display}")
            
            # Safely get min_target and normalize_to_value with defaults
            min_target = params.get('min_target', 0.0)
            normalize_to_value = params.get('normalize_to_value', 1.0)
            
            if mode == 'minmax':
                summary_parts.append(f"- Range: {min_target} to {normalize_to_value}")
            else:
                summary_parts.append(f"- Target value: {normalize_to_value}")
            
            # Safely check for custom range
            use_custom_range = params.get('use_custom_range', False)
            x_min = params.get('x_min')
            x_max = params.get('x_max')
            
            if use_custom_range and x_min is not None and x_max is not None:
                summary_parts.append(f"- X-range: {x_min} to {x_max}")
            
            return "\n".join(summary_parts)
        except Exception as e:
            logger.error("Error in _format_normalization_params: %s", e)
            return "- Error formatting normalization parameters"
    
    def _format_sg_parameters(self, params):
        """Format Savitzky-Golay parameters for display."""
        summary_parts = []
        
        # Add window length and polynomial order
        window_length = params.get('window_length', 11)
        polyorder = params.get('polyorder', 3)
        summary_parts.append(f"- Window: {window_length}, Polynomial: {polyorder}")
        
        # Add derivative information if applicable
        deriv_order = params.get('deriv_order', 0)
        if deriv_order > 0:
            summary_parts.append(f"- Derivative order: {deriv_order}")
        else:
            summary_parts.append("- No derivative (smoothing only)")
        
        # Add edge handling mode
        mode = params.get('mode', 'interp')
        summary_parts.append(f"- Edge mode: {mode}")
        
        # Add summary of individual delta values
        individual_values = params.get('individual_delta_values', {})
        if individual_values:
            summary_parts.append(f"- Delta values: {len(individual_values)} custom values")
        else:
            summary_parts.append("- Delta values: default (1.0)")
        
        return "\n".join(summary_parts)

    def get_sg_delta_values_table(self, operation_index):
        """
        Format Savitzky-Golay delta values as a table for display in parameters dialog.
        
        Args:
            operation_index: Index of the operation
            
        Returns:
            Dictionary with two entries: headers and rows for the table
        """
        operation = self.get_operation_at_index(operation_index)
        if not operation or operation['type'] != "SG-smoothing":
            return None
            
        params = operation.get('parameters', {})
        individual_values = params.get('individual_delta_values', {})
        
        if not individual_values:
            return None
        
        # Build a table dictionary with headers and rows
        table = {
            'headers': ["Spectrum", "Delta Value"],
            'rows': []
        }
        
        # Sort by spectrum name for consistent display
        for spectrum, delta in sorted(individual_values.items()):
            table['rows'].append([spectrum, f"{delta:.6g}"])
        
        return table
    
    def _format_sg_delta_values(self, params):
        """Format individual delta values as a table for display."""
        individual_values = params.get('individual_delta_values', {})
        if not individual_values:
            return "No individual delta values defined."
            
        # Format as a simple table
        table = "Spectrum Name\tDelta Value\n"
        table += "------------\t-----------\n"
        
        for spectrum, delta in sorted(individual_values.items()):
            table += f"{spectrum}\t{delta:.6g}\n"
            
        return table 

    @staticmethod
    def _baseline_points_count(info):
        """Return how many baseline points *info* represents, regardless
        of whether 'points' is stored as a plain count or as a list of
        (x, y) coordinates. Other methods in this same file
        (_restore_baseline_state, get_baseline_points) both treat
        params['corrections'][label]['points'] as a LIST of coordinate
        pairs, not a count — this formatter previously assumed it was
        already an int (`info.get('points', 0)` summed directly), which
        would either raise a TypeError summing lists as numbers, or
        silently show 0 for every spectrum, depending on the exact shape
        actually stored. Handling both shapes here means this displays
        correctly either way."""
        pts = info.get('points', 0)
        if isinstance(pts, (list, tuple)):
            return len(pts)
        try:
            return int(pts)
        except (TypeError, ValueError):
            return 0

    def _format_baseline_params(self, params):
        """Format baseline parameters for display."""
        if 'corrections' not in params or not params['corrections']:
            return "No baseline corrections defined"
        
        # Format in a more readable way
        formatted_output = []
        corrections = params['corrections']
        
        # First, count total points and spectra with actual points
        total_points = sum(self._baseline_points_count(info) for info in corrections.values())
        spectra_with_points = sum(1 for info in corrections.values() if self._baseline_points_count(info) > 0)
        formatted_output.append(f"- Total: {len(corrections)} spectra, {total_points} baseline points")
        
        # Get affected spectra from parent operation if available
        affected_spectra = []
        if hasattr(self, 'operations_chain'):
            # Find the operation with this baseline correction
            for operation in self.operations_chain:
                if operation['type'] == 'Manual baseline' and operation.get('parameters') == params:
                    affected_spectra = operation.get('affected_labels', [])
                    break
        
        # Then list each spectrum's details, including those with 0 points
        formatted_output.append("- Corrections by spectrum:")
        
        # Process spectra with corrections first
        for spectrum, info in sorted(corrections.items()):
            fit_type = info.get('type', 'unknown')
            points_count = self._baseline_points_count(info)
            line = f"  • {spectrum}: {points_count} points, {fit_type}"
            if fit_type == 'polynomial' and 'order' in info:
                line += f" (order {info['order']})"
            formatted_output.append(line)
        
        # Add affected spectra that aren't in corrections (with 0 points)
        for spectrum in sorted(affected_spectra):
            if spectrum not in corrections:
                formatted_output.append(f"  • {spectrum}: 0 points, no baseline")
        
        return "\n".join(formatted_output)
    
    def save_parameters_to_file(self, filename):
        """
        Save all operation parameters to a text file.
        
        Args:
            filename: Path to save the file
            
        Returns:
            Boolean indicating success
        """
        try:
            # Ensure the directory exists
            import os
            directory = os.path.dirname(filename)
            if directory and not os.path.exists(directory):
                os.makedirs(directory)
                
            with open(filename, 'w', encoding='utf-8') as f:
                try:
                    f.write("Operations History (Incremental Chain)\n")
                    f.write("===================================\n\n")
                    
                    # Write info about original state
                    f.write("0. Original State\n")
                    f.write(f"   Number of spectra: {len(self.original_spectra)}\n")
                    
                    # Write chain of operations
                    f.write("\nOperation Chain\n")
                    f.write("--------------\n")
                    
                    for i, operation in enumerate(self.operations_chain):
                        try:
                            op_type = operation['type']
                            timestamp = datetime.fromisoformat(operation['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                            
                            # Mark active operation
                            is_active = " (ACTIVE)" if i == self.active_operation_index else ""
                            
                            # Get counts
                            affected_labels = operation.get('affected_labels', [])
                            
                            f.write(f"\n{i+1}. {op_type}{is_active}\n")
                            f.write(f"   Applied: {timestamp}\n")
                            
                            # Clearer description of affected spectra
                            if affected_labels:
                                f.write(f"   Operation affected {len(affected_labels)} spectra\n")
                                
                                # Write affected spectra list - one per line with indentation
                                f.write("   Affected spectra:\n")
                                for label in sorted(affected_labels):
                                    f.write(f"      {label}\n")
                            else:
                                f.write("   No spectra were affected\n")

                            # Write parameters
                            params = operation.get('parameters', {})
                            if not params:
                                f.write("   Parameters: None\n")
                                continue
                                
                            # Format parameters based on operation type.
                            #
                            # Every comparison below used to be lowercase
                            # or otherwise not the exact real string
                            # (op_type == "data range", "normalization",
                            # "baseline", "removal") while every actual
                            # call to apply_operation() across the app
                            # uses a different exact string — verified
                            # directly against every apply_operation()
                            # call site in operations_controller.py:
                            # "Data range", "Normalization", "Manual
                            # baseline", "Cosmic ray removal", "Spike
                            # removal". Only "SG-smoothing" happened to
                            # already match exactly. That meant 4 of these
                            # 5 special-cased, carefully-written formatters
                            # could never fire for any real operation —
                            # every one of them silently fell through to
                            # the generic "- key: value" dump instead,
                            # with no error or warning anywhere that the
                            # nicer formatting was being skipped.
                            try:
                                if op_type == "Data range":
                                    param_text = self._format_data_range_params(params)
                                elif op_type == "Normalization":
                                    param_text = self._format_normalization_params(params)
                                elif op_type == "SG-smoothing":
                                    param_text = self._format_sg_parameters(params)
                                elif op_type == "Manual baseline":
                                    param_text = self._format_baseline_params(params)
                                elif op_type == "Cosmic ray removal":
                                    param_text = self._format_cosmic_ray_params(params)
                                elif op_type == "Spike removal":
                                    param_text = self._format_spike_removal_params(params)
                                elif op_type == "SVD background":
                                    param_text = self._format_svd_background_params(params)
                                else:
                                    # Generic formatting for other operations - put each parameter on a new line
                                    param_text = "\n".join([f"- {k}: {self._humanize_value(v)}" for k, v in params.items()])
                            except Exception as e:
                                logger.error("Error formatting parameters for %s: %s", op_type, e)
                                param_text = "- Error formatting parameters"
                            
                            # Write formatted parameters header
                            f.write("   Parameters:\n")
                            
                            # Write formatted parameters (already has proper line prefixes)
                            for line in param_text.split("\n"):
                                f.write(f"     {line}\n")
                        except Exception as e:
                            logger.error("Error processing operation %d: %s", i+1, e)
                            f.write(f"\n{i+1}. Error processing operation: {str(e)}\n")
                except Exception as e:
                    f.write(f"\nError during file generation: {str(e)}\n")
            
            return True
        
        except Exception as e:
            logger.error("Error saving parameters to file: %s", e)
            logger.exception("Traceback:")
            return False

    def get_baseline_points(self, operation_index, spectrum_key_or_label):
        """
        Get baseline points for a specific spectrum in a baseline operation.

        Args:
            operation_index: Index of the operation in operations_chain
            spectrum_key_or_label: spectrum_key() (unique_id) of the
                spectrum to get points for — every current caller passes
                this. A plain label is also accepted as a fallback purely
                for backward compatibility with any external/older caller
                still passing one (label-keyed data predates this
                identity system — see developer_guide_help.py's "Golden
                Rule: Spectrum Identity").

        Returns:
            List of (x,y) coordinate tuples for baseline points, or empty list if not found
        """
        # Check if this is a valid operation
        if operation_index < 0 or operation_index >= len(self.operations_chain):
            return []

        operation = self.operations_chain[operation_index]

        # Check if this is a baseline operation
        if operation['type'] != 'Manual baseline':
            return []

        # baseline_state is keyed by each spectrum's unique_id (see
        # commit_manual_baseline / BaselineManager._key_for) — the normal
        # case is a direct hit.
        baseline_state = operation.get('baseline_state', {})
        if spectrum_key_or_label in baseline_state:
            points = baseline_state[spectrum_key_or_label].get('points', [])
            if isinstance(points, list) and all(isinstance(p, (list, tuple)) for p in points):
                return points

        # Backward-compat fallback: if what was passed is actually a
        # label (not an id), resolve it via this same operation's own
        # output_spectra (captured at the same moment baseline_state was
        # built, so the two agree on identity).
        key = None
        for spectrum in operation.get('output_spectra', []):
            if spectrum.get('label') == spectrum_key_or_label:
                metadata = spectrum.get('metadata') or {}
                key = metadata.get('unique_id')
                break

        if key and key in baseline_state:
            points = baseline_state[key].get('points', [])
            if isinstance(points, list) and all(isinstance(p, (list, tuple)) for p in points):
                return points
        
        # Look for baseline points in other sources
        # 1. Check output_spectra — match by identity first, label second
        # (back-compat only; see the parameter docstring above).
        output_spectra = operation.get('output_spectra', [])
        for spectrum in output_spectra:
            metadata = spectrum.get('metadata') or {}
            matches = (metadata.get('unique_id') == spectrum_key_or_label
                       or spectrum.get('label') == spectrum_key_or_label)
            if matches and 'baseline_points' in spectrum:
                return spectrum['baseline_points']

        # 2. If available, try to get from baseline controller. Its
        # manager's dicts are keyed by unique_id too (see
        # BaselineManager._key_for) — use the same resolved key as above,
        # falling back to the raw value only if resolution failed.
        try:
            if hasattr(self, '_controller') and hasattr(self._controller, 'baseline_correction_controller'):
                bc_controller = self._controller.baseline_correction_controller
                if hasattr(bc_controller, 'manager'):
                    return bc_controller.manager.get_baseline_points(key or spectrum_key_or_label)
        except Exception:
            logger.warning("Could not read baseline points of %r from the baseline controller",
                           spectrum_key_or_label, exc_info=True)

        # No points found
        return []