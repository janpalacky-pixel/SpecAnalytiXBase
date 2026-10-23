
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

    def detect_peaks(self, canvas, threshold, font_size, rotation, decimals, number_format,
                     format_type, show_labels, prominence, distance, peak_mode,
                     labels='all', current_label=None):
        """Mark the peaks of every plotted line (a red dot each) and write
        their positions. labels: 'band' - one number per band, above its
        highest peak (the peaks of all lines of one plot at about the same
        position are one band, as in the Peak list; the number is the
        band's position); 'all' - on every peak; 'current' - only on the
        line whose label is current_label (the spectrum highlighted in the
        list); 'none' - the dots only."""
        if canvas is None:
            return
        from src.modules.data_analysis import peak_list as pl

        self.clear_peaks(canvas)
        if not show_labels:
            labels = 'none'

        for ax_idx, ax in enumerate(canvas.figure.get_axes()):
            lines = [line for line in ax.get_lines()
                     if line.get_color() not in ('r', 'red') or line.get_marker() != 'o']
            found = []            # (line_idx, line label, peak) of this plot
            for line_idx, line in enumerate(lines):
                x_data = np.asarray(line.get_xdata(), dtype=float)
                y_data = np.asarray(line.get_ydata(), dtype=float)
                line_label = line.get_label() or f"Line {line_idx+1}"
                if len(y_data) < 3:
                    continue
                # Which points are peaks: the same rule as the peak list
                # (each side - maxima, minima - judged on its own range)
                peaks = pl.spectrum_peaks(x_data, y_data, threshold, prominence, distance,
                                          peak_mode)
                self.peak_indices[(ax_idx, line_idx)] = np.array([p['index'] for p in peaks],
                                                                 dtype=int)
                for p in peaks:
                    found.append((line_idx, line_label, p))
                    x_str = self.format_number(p['x'], number_format, decimals)
                    # one dot per peak; a label starting with "_" keeps it out of the legend
                    dot = ax.plot([p['x']], [p['y']], 'ro', markersize=8,
                                  label=f"_Peak at {x_str} from {line_label}")[0]
                    self.peak_lines.append(dot)

            for x_val, y_val, kind in self._label_places(found, labels, current_label, pl):
                x_str = self.format_number(x_val, number_format, decimals)
                y_str = self.format_number(y_val, number_format, decimals)
                text = f"({x_str}, {y_str})" if format_type == "both" else x_str
                self.peak_texts.append(ax.text(
                    x_val, y_val, text, fontsize=font_size,
                    ha='center', va='bottom' if kind == 'max' else 'top', rotation=rotation))
        canvas.draw()

    @staticmethod
    def _label_places(found, labels, current_label, pl):
        """[(x written, y of the peak it stands on, kind)] of one plot."""
        if labels == 'none' or not found:
            return []
        if labels == 'current':
            return [(p['x'], p['y'], p['kind']) for _, lab, p in found if lab == current_label]
        if labels != 'band':
            return [(p['x'], p['y'], p['kind']) for _, _, p in found]
        out = []
        for kind in ('max', 'min'):
            peaks = [p for _, _, p in found if p['kind'] == kind]
            if not peaks:
                continue
            rows = []
            for p in peaks:
                r = [None] * len(pl.COLUMNS)
                r[pl.NUMERIC['Position (x)']] = p['x']
                r[pl.NUMERIC['FWHM']] = p['fwhm']
                rows.append(r)
            centres = pl.band_positions(rows, pl.default_tolerance(rows))
            bands = {}
            for p, c in zip(peaks, centres):
                bands.setdefault(c, []).append(p)
            for c, members in bands.items():
                top = (max if kind == 'max' else min)(members, key=lambda p: p['y'])
                out.append((c, top['y'], kind))
        return out

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


