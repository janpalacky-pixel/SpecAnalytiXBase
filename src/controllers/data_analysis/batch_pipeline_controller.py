# src/controllers/data_analysis/batch_pipeline_controller.py
"""
Controller for Batch Pipeline Replay — named, reusable sequences of
processing operations.

Two entry points, both opened from dialogs of their own (not through the
generic OperationsController.show_parameters_dialog() elif chain the way
a single operation would be, since this controller has TWO distinct
dialogs rather than one):

  • show_save_dialog()  – capture a named pipeline from the session's
                           Operations History (IncrementalOperationsManager.
                           operations_chain, which holds each committed
                           operation's FULL settings dict — unlike the
                           trimmed per-spectrum correction_history, this
                           is a faithful source to replay from). Launched
                           from the Operations History dialog's own
                           "Save as Pipeline..." button.
  • show_run_dialog()    – pick a saved pipeline, preview its steps, run
                           it against any spectra selection, and commit
                           the result via Apply / Add as New exactly like
                           every other operation.

Follows the same owning-controller shape as CDUnitConversionController /
XAxisUnitConversionController: owns its manager(s), exposes a
commit_*() method the dialog's own Apply/Add-as-New buttons call via
commit_callback.
"""

import uuid
from PyQt5.QtWidgets import QApplication
from src.modules.data_analysis.batch_pipeline_manager import BatchPipelineManager, PipelineStepError
from src.modules.misc.pipeline_manager import PipelineManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key

logger = get_logger(__name__)


class BatchPipelineController:
    def __init__(self, main_controller):
        self.controller = main_controller
        self.pipeline_manager = PipelineManager()
        self.replay_manager = BatchPipelineManager()

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state — same
        pattern as every other data-analysis controller's .oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------
    # Save (capture from Operations History)
    # ------------------------------------------------------------------
    def show_save_dialog(self, operations_manager=None, parent=None):
        """Open the Save-as-Pipeline dialog, seeded with the session's
        committed operations chain. Returns True if a pipeline was saved."""
        from src.views.dialogs.data_analysis.batch_pipeline_save_dialog import BatchPipelineSaveDialog

        operations_manager = operations_manager or self.oc.operations_manager
        dialog = BatchPipelineSaveDialog(
            parent=parent or self.controller.view,
            operations_chain=list(getattr(operations_manager, 'operations_chain', [])),
            pipeline_manager=self.pipeline_manager,
        )
        return dialog.exec_() == dialog.Accepted

    # ------------------------------------------------------------------
    # Run (replay on a selection)
    # ------------------------------------------------------------------
    def show_run_dialog(self, selected_spectra=None):
        """Open the Run Pipeline dialog."""
        from src.views.dialogs.data_analysis.batch_pipeline_run_dialog import BatchPipelineRunDialog
        from PyQt5.QtWidgets import QMessageBox

        if not self.pipeline_manager.list_pipelines():
            QMessageBox.information(
                self.controller.view, 'No saved pipelines',
                'No batch pipelines have been saved yet. Open the Operations History '
                'dialog and use "Save as Pipeline..." to create one first.'
            )
            return None

        if selected_spectra is None:
            selected_spectra = self.controller.spectrum_selector.get_selected_spectra()

        dialog = BatchPipelineRunDialog(
            parent=self.controller.view,
            selected_spectra=selected_spectra,
            pipeline_manager=self.pipeline_manager,
            replay_manager=self.replay_manager,
            commit_callback=self.commit_pipeline_run,
        )
        dialog.exec_()
        return dialog

    def show_parameters_dialog(self):
        """Convenience wrapper used by OperationsController's dispatch,
        mirroring every other operation's show_parameters_dialog()."""
        selected = self.controller.spectrum_selector.get_selected_spectra()
        self.show_run_dialog(selected)
        return True

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------
    def commit_pipeline_run(self, pipeline_name, steps, add_as_new, selected_spectra):
        """Run *steps* against *selected_spectra* and commit the result
        via Apply / Add as New, called by the Run Pipeline dialog's own
        buttons. Returns (success: bool, message: str)."""
        if not selected_spectra:
            return False, 'Please select one or more spectra to run the pipeline on.'

        n_spectra = len(selected_spectra)
        progress = self.oc._show_busy_progress(
            "Batch Pipeline", f"Running '{pipeline_name}' on {n_spectra} spectra…", len(steps),
        )
        try:
            def _progress(done, total, label):
                if progress is not None:
                    progress.setLabelText(label)
                    progress.setValue(done)
                    QApplication.processEvents()

            try:
                result_spectra = self.replay_manager.run_pipeline(
                    selected_spectra, steps, progress_callback=_progress,
                )
            except PipelineStepError as exc:
                return False, str(exc)
            except Exception as exc:
                logger.exception('Unexpected error running batch pipeline %r', pipeline_name)
                return False, f'An unexpected error occurred: {exc}'

            if not result_spectra:
                return False, 'The pipeline produced no output spectra.'

            slug = ''.join(c if (c.isalnum() or c in '-_') else '_' for c in pipeline_name)
            suffix = f'pipeline_{slug}'
            current_state = self.oc.operations_manager.get_current_spectra()

            if add_as_new:
                all_labels = {s['label'] for s in current_state}
                renamed = []
                for spec in result_spectra:
                    base_name = f"{spec['label']}_{suffix}"
                    new_name = base_name
                    bump = 1
                    while new_name in all_labels:
                        new_name = f'{base_name}_{bump}'
                        bump += 1
                    all_labels.add(new_name)
                    spec = dict(spec)
                    spec['label'] = new_name
                    spec['metadata'] = dict(spec.get('metadata') or {})
                    spec['metadata']['unique_id'] = str(uuid.uuid4())
                    renamed.append(spec)
                result_spectra = renamed
                output_spectra = current_state + result_spectra
            else:
                result_labels = {s['label'] for s in result_spectra}
                output_spectra = [s for s in current_state if s['label'] not in result_labels]
                output_spectra.extend(result_spectra)

            operation_name = f'Batch Pipeline: {pipeline_name}'
            self.oc.operations_manager.apply_operation(
                operation_name, {'pipeline_name': pipeline_name, 'steps': steps},
                selected_spectra, new_state_spectra=output_spectra,
            )

            if add_as_new:
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    selected_spectra, result_spectra,
                    operation_name=operation_name, pre_state=current_state,
                )

            if progress is not None:
                progress.setLabelText("Updating spectrum list…")
                QApplication.processEvents()

            self.controller.original_spectra = self.oc.operations_manager.get_current_spectra()
            self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)

            highlight_ids = {
                spectrum_key(s) for s in (selected_spectra if add_as_new else result_spectra)
            }
            self.oc._rebuild_spectra_list_with_selection(highlight_ids)

            self.controller.selected_spectra = (
                selected_spectra if add_as_new else result_spectra
            )

            if progress is not None:
                progress.setLabelText("Redrawing plot…")
                QApplication.processEvents()
            try:
                self.controller.plot_spectra(
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None
                )
            except Exception as exc:
                logger.error('Error plotting after batch pipeline run: %s', exc)
        finally:
            if progress is not None:
                progress.close()

        n = len(result_spectra)
        noun = 'spectrum' if n == 1 else 'spectra'
        if add_as_new:
            new_names = self.oc._format_names_for_message(s['label'] for s in result_spectra)
            message = f"Added {n} new {noun} from pipeline '{pipeline_name}': {new_names}."
        else:
            message = f"Replaced {n} {noun} with the output of pipeline '{pipeline_name}'."
        return True, message
