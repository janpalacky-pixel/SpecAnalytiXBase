# src/controllers/misc/import_settings_controller.py

from src.modules.misc.import_settings_manager import ImportSettingsManager

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)


class ImportSettingsController:
    def __init__(self, main_controller):
        self.controller = main_controller
        self.settings_manager = ImportSettingsManager()

    def reset_after_import(self) -> None:
        """
        Reset per-file flags (e.g. interlaced_format) back to their defaults
        after an import completes.

        Call this from ImportController.execute() and execute_add() once the
        import is done, so that interlaced_format does not leak into the next
        import and silently corrupt standard files.
        """
        self.settings_manager.reset_non_persistent()
        self.controller.import_settings.update(
            self.settings_manager.get_current_settings()
        )
        logger.debug("Post-import reset: %s", self.controller.import_settings)

    def reset_to_defaults(self) -> None:
        """Reset all settings to factory defaults."""
        settings = self.settings_manager.reset_to_defaults()
        self.controller.import_settings.update(settings)

    def get_current_settings(self) -> dict:
        """Return the current import settings."""
        return self.settings_manager.get_current_settings()
