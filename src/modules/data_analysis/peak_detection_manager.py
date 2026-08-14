
# src/modules/peak_detection.py
from scipy.signal import find_peaks
import numpy as np

class PeakDetector:
    def __init__(self):
        self.peak_indices = {}
        self.peak_lines = []
        self.peak_texts = []
        self.peak_font_size = 10
        self.show_labels = True

    @staticmethod
    def format_number(value, number_format, decimals):
        if number_format == "fixed":
            return f"{value:.{decimals}f}"
        elif number_format == "sci":
            return f"{value:.{decimals}e}"
        elif number_format == "general":
            return f"{value:.{decimals}g}"
        elif number_format == "mixed":
            abs_val = abs(value)
            if abs_val != 0 and (abs_val < 0.01 or abs_val >= 10000):
                return f"{value:.{decimals}e}"
            else:
                return f"{value:.{decimals}f}"
        return str(value)

    def detect_peaks(self, canvas, threshold, font_size, rotation, decimals, number_format, format_type, show_labels, prominence, distance, peak_mode):
        if canvas is None:
            return
    
        self.clear_peaks(canvas)

        axes = canvas.figure.get_axes()
        

    
        for ax_idx, ax in enumerate(axes):
            lines = [line for line in ax.get_lines() 
                    if line.get_color() not in ('r', 'red') or line.get_marker() != 'o']
    
            for line_idx, line in enumerate(lines):
                x_data = line.get_xdata()
                y_data = line.get_ydata()
                line_label = line.get_label() or f"Line {line_idx+1}"
    
                if len(y_data) < 2:
                    continue
    
                # Compute thresholds
                # height_threshold below is deliberately NOT shared between
                # positive and negative detection — it must be computed
                # from whichever array find_peaks() is actually being
                # applied to. Previously the same value (derived from the
                # ORIGINAL, non-inverted y_data's own min/max) was reused
                # unchanged for the inverted data too. That's only correct
                # when a spectrum is perfectly symmetric around its own
                # midpoint — for virtually any real asymmetric spectrum
                # (e.g. a mostly-positive baseline with a genuine dip, or
                # vice versa) it silently miscalibrates the negative-peak
                # threshold. Verified directly: a deep, unambiguous trough
                # (baseline ~5, dipping to ~1 — an 80%+ deep feature) was
                # completely missed by "Negative" mode as a result,
                # because the threshold required inverted_y to exceed a
                # value mirrored from the POSITIVE side's own range, not
                # computed from the inverted data's own range.
                prominence_threshold = prominence * (np.max(y_data) - np.min(y_data))
                distance_threshold = max(1, int(distance * len(y_data)))
    
                peaks_positive = []
                peaks_negative = []
    
                # Detect peaks based on mode
                if peak_mode in ["Positive", "Both"]:
                    height_threshold_pos = np.min(y_data) + threshold * (np.max(y_data) - np.min(y_data))
                    peaks_positive, _ = find_peaks(
                        y_data,
                        height=height_threshold_pos,
                        prominence=prominence_threshold,
                        distance=distance_threshold
                    )
    
                if peak_mode in ["Negative", "Both"]:
                    inverted_y_data = -y_data  # Invert for negative peaks
                    # Threshold computed from inverted_y_data's OWN
                    # min/max — not mirrored from the positive side's
                    # threshold (see comment above).
                    height_threshold_neg = (np.min(inverted_y_data)
                                             + threshold * (np.max(inverted_y_data) - np.min(inverted_y_data)))
                    peaks_negative, _ = find_peaks(
                        inverted_y_data,
                        height=height_threshold_neg,
                        prominence=prominence_threshold,
                        distance=distance_threshold
                    )
    
                # Combine peaks if detecting both
                peaks = np.unique(np.concatenate((peaks_positive, peaks_negative)))
                
                # Ensure peaks are integers
                peaks = peaks.astype(int)
    
                # Store peaks
                key = (ax_idx, line_idx)
                self.peak_indices[key] = peaks
    
                # Instead of plotting all peaks at once, plot each peak individually
                # This allows us to set unique labels for each peak
                if len(peaks) > 0:
                    for i, peak_idx in enumerate(peaks):
                        x_val = x_data[peak_idx]
                        y_val = y_data[peak_idx]
                        
                        x_str = self.format_number(x_val, number_format, decimals)
                        y_str = self.format_number(y_val, number_format, decimals)
                        
                        # Create a unique identifier for each peak
                        peak_identifier = f"Peak at {x_str} from {line_label}"
                        
                        # Plot individual peak with unique label that starts with "_"
                        # This keeps it out of the legend but allows unique identification
                        peak_line = ax.plot(
                            [x_val], [y_val],
                            'ro', markersize=8,
                            label=f"_{peak_identifier}"  # Prefixing with underscore to hide from legend
                        )[0]
                        self.peak_lines.append(peak_line)
                        
                        # Add peak text label
                        if show_labels:
                            display_label = f"({x_str}, {y_str})" if format_type == "both" else f"{x_str}"
                            
                            text = ax.text(
                                x_val, y_val, display_label,
                                fontsize=font_size,
                                ha='center', va='bottom',
                                rotation=rotation
                            )
                            self.peak_texts.append(text)
    
            canvas.draw()    

    def clear_peaks(self, canvas):
        if canvas is None:
            return

        for line in self.peak_lines:
            if line in line.axes.lines:
                line.remove()
        self.peak_lines = []
        
        for text in self.peak_texts:
            if text in text.axes.texts:
                text.remove()
        self.peak_texts = []
        
        self.peak_indices.clear()

        canvas.draw()


