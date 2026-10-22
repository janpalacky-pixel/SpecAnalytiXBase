
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
    
                # Which points are peaks: the same rule as the peak list
                # (peak_list.peak_indices; each side - maxima, minima - is
                # judged on its own range).
                from src.modules.data_analysis.peak_list import peak_indices
                peaks = peak_indices(np.asarray(y_data, dtype=float), threshold, prominence,
                                     distance, peak_mode)

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


