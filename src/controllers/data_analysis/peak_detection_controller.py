
# src/controllers/peak_detection_controller.py
from src.views.dialogs.data_analysis.peak_detection_dialog import PeakDetectionDialog
from src.modules.data_analysis.peak_detection_manager import PeakDetector

class PeakDetectionController:
    def __init__(self, main_controller):
        self.controller = main_controller
        self.peak_detector = PeakDetector()
        
        # Default settings
        self.peak_threshold = 0.5
        self.peak_prominence = 0.1
        self.peak_distance = 0.05
        self.peak_detection_mode = "Positive"
        self.peak_font_size = 10
        self.peak_rotation = 0
        self.peak_decimals = 2
        self.peak_number_format = "fixed"
        self.peak_format_type = "X value only"
        self.show_labels = True

    def show_dialog(self):
        """Show enhanced dialog for peak detection parameters."""
        dialog = PeakDetectionDialog(
            self.controller.view,
            threshold=self.peak_threshold,
            prominence=self.peak_prominence,
            distance=self.peak_distance,
            peak_mode=self.peak_detection_mode,
            font_size=self.peak_font_size,
            rotation=self.peak_rotation,
            decimals=self.peak_decimals,
            format_type=self.peak_format_type,
            number_format=self.peak_number_format,
        )
        
        if dialog.exec_():
            settings = dialog.get_settings()
            # Store all settings as class attributes
            self.peak_threshold = settings['threshold']
            self.peak_font_size = settings['font_size']
            self.peak_rotation = settings['rotation']
            self.peak_decimals = settings['decimals']
            self.peak_number_format = settings['number_format']
            self.peak_format_type = settings['format_type']
            self.peak_prominence = settings['prominence']
            self.peak_distance = settings['distance']
            self.peak_detection_mode = settings['peak_mode']
            
            # Apply the settings to detect peaks
            self.detect_peaks()

    def detect_peaks(self):
        """Detect peaks using the current settings."""
        canvas = self.controller.static_canvas
        self.peak_detector.detect_peaks(
            canvas,
            self.peak_threshold,
            self.peak_font_size,
            self.peak_rotation,
            self.peak_decimals,
            self.peak_number_format,
            self.peak_format_type,
            self.show_labels,
            self.peak_prominence,
            self.peak_distance,
            self.peak_detection_mode
        )

    def clear_peaks(self):
        """Clear all detected peaks."""
        canvas = self.controller.static_canvas
        self.peak_detector.clear_peaks(canvas)