
# src/views/dialogs/misc/spectrum_metadata_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTextEdit,
                            QDialogButtonBox, QLabel, QApplication)
from PyQt5.QtCore import Qt

try:
    import numpy as np
except ImportError:
    np = None

# How many items a list/array can have before it's summarised instead of
# spelled out in full — protects against exactly the kind of accidental
# full-array dump (thousands of intensity values) that this formatter
# exists to prevent in the first place.
_MAX_DISPLAY_ITEMS = 20


class SpectrumMetadataDialog(QDialog):
    """Dialog to display metadata for a single spectrum."""
    
    def __init__(self, parent=None, spectrum_label=None, metadata=None):
        super().__init__(parent)
        self.setWindowTitle(f"Metadata: {spectrum_label}")
        self.setMinimumSize(500, 400)
        
        self.spectrum_label = spectrum_label
        self.metadata = metadata or {}

        self.setup_ui()
        
    def setup_ui(self):
        """Set up the dialog UI with metadata display."""
        layout = QVBoxLayout(self)
        
        # Add title label
        title_label = QLabel(f"<h2>{self.spectrum_label}</h2>")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Create text edit for metadata display
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        
        # Format metadata text with improved formatting
        metadata_html = self.format_metadata_html()
        self.text_edit.setHtml(metadata_html)
        
        layout.addWidget(self.text_edit)

        # Add close button, plus a screenshot-style copy button so the
        # whole metadata view (title + table, as currently laid out and
        # scrolled) can be pasted elsewhere — e.g. into a lab notebook or
        # a bug report — without the recipient needing this app open.
        # ActionRole (not a QDialogButtonBox standard button) since "copy
        # a screenshot" isn't one of Qt's predefined roles; it just sits
        # to the left of Close in the same row.
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        copy_btn = button_box.addButton(
            '\U0001f4f7  Copy screenshot', QDialogButtonBox.ActionRole
        )
        copy_btn.setToolTip(
            'Copy an image of this metadata view to the clipboard\n'
            '(paste into an email, chat, or document with Ctrl+V).'
        )
        copy_btn.clicked.connect(self._copy_screenshot)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _copy_screenshot(self):
        """Grab this dialog's current appearance as an image and put it
        on the system clipboard. QWidget.grab() rasterizes exactly what's
        on screen right now, including whatever portion of a long
        metadata table happens to be scrolled into view — same
        "screenshot", not a re-render of the full (possibly much taller)
        content."""
        pixmap = self.grab()
        QApplication.clipboard().setPixmap(pixmap)

    # ------------------------------------------------------------------ #
    # Value formatting                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _to_plain(value):
        """Convert a numpy scalar to a plain Python number; pass anything
        else through unchanged. numpy values show up here from metadata
        built directly out of computed results (e.g. Band Ratio, peak
        fitting) — without this they display as 'np.float64(2213135.5)'
        instead of a plain number."""
        if np is not None and isinstance(value, np.generic):
            return value.item()
        return value

    @classmethod
    def _format_float(cls, value):
        """Format a float the way an ordinary user would expect to read it:
        no scientific notation at everyday magnitudes (a plain %g would
        have turned 2341165.0 into '2.34116e+06'), a handful of
        significant decimals otherwise. No thousands-separator comma —
        that reads ambiguously as a second decimal point in a list of
        values (e.g. "[2,815.7, 2,817.77]") and isn't used anywhere else
        in this app."""
        if value != value:  # NaN
            return "NaN"
        if value in (float('inf'), float('-inf')):
            return str(value)
        if value == int(value) and abs(value) < 1e15:
            return f"{int(value)}"
        if abs(value) >= 1e9 or (0 < abs(value) < 1e-4):
            # Only genuinely extreme magnitudes fall back to scientific
            # notation — nothing else stays readable at that scale anyway.
            return f"{value:.4g}"
        return f"{value:.4f}".rstrip('0').rstrip('.')

    @classmethod
    def _format_scalar(cls, value):
        """Format a single (non-container) value for display."""
        value = cls._to_plain(value)
        if isinstance(value, (list, tuple)):
            return "[" + ", ".join(cls._format_scalar(v) for v in value) + "]"
        if isinstance(value, float):
            return cls._format_float(value)
        if value is None:
            return "<i>None</i>"
        return str(value)

    @classmethod
    def _format_value(cls, value):
        """Recursively format any metadata value into safe, readable HTML.

        - A dict becomes its own small nested table, one row per key —
          never a single str()'d blob like "{'value_a': 2213135.5, ...}".
        - A numpy array, or any list/tuple longer than _MAX_DISPLAY_ITEMS,
          is summarised (count + min/mean/max for numeric data) instead of
          being spelled out in full — this is what a raw spectrum array
          accidentally saved into metadata would otherwise dump as
          thousands of comma-separated numbers.
        - A short list of dicts (e.g. multiple band/range definitions)
          becomes a numbered sequence of nested tables.
        - Numpy scalars anywhere in the structure display as plain numbers.
        """
        value = cls._to_plain(value)

        # numpy array
        if np is not None and isinstance(value, np.ndarray):
            if value.size == 0:
                return "<i>(empty array)</i>"
            if value.size > _MAX_DISPLAY_ITEMS:
                try:
                    return (f"array of {value.size} values "
                            f"(min={np.min(value):.4g}, "
                            f"mean={np.mean(value):.4g}, "
                            f"max={np.max(value):.4g})")
                except Exception:
                    return f"array of {value.size} values"
            return cls._format_scalar(value.tolist())

        # dict -> nested table, one row per key
        if isinstance(value, dict):
            if not value:
                return "<i>(empty)</i>"
            rows = []
            for k, v in value.items():
                disp_key = str(k).replace('_', ' ').title()
                rows.append(
                    f"<tr><td class='nested-key'><i>{disp_key}</i></td>"
                    f"<td>{cls._format_value(v)}</td></tr>"
                )
            return "<table class='nested'>" + "".join(rows) + "</table>"

        # list / tuple
        if isinstance(value, (list, tuple)):
            if not value:
                return "<i>(empty)</i>"
            if len(value) > _MAX_DISPLAY_ITEMS:
                return f"list of {len(value)} items"
            if all(isinstance(v, dict) for v in value):
                parts = []
                for i, v in enumerate(value, 1):
                    # 'operation' and 'timestamp' are the two fields every
                    # correction_history entry carries regardless of which
                    # operation added it (see correction_history.py) — the
                    # operation name identifies WHICH correction this is,
                    # which reads more naturally as part of the "#N" label
                    # itself than as just another field buried in the list
                    # below it, and the timestamp reads naturally right
                    # alongside it. Popped from a COPY so the original
                    # metadata dict this dialog was given is never mutated.
                    v = dict(v)
                    operation = v.pop('operation', None)
                    timestamp = v.pop('timestamp', None)
                    header = f"<b>#{i}.</b>"
                    if operation:
                        header += f" <b>{operation}</b>"
                    if timestamp:
                        header += f" <span style='color:#777;font-weight:normal;'>({timestamp})</span>"
                    parts.append(f"{header}<br>{cls._format_value(v)}")
                return "<br>".join(parts)
            return cls._format_scalar(list(value))

        return cls._format_scalar(value)

    def format_metadata_html(self):
        """Format metadata as HTML with improved readability."""
        if not self.metadata:
            return "<p><i>No metadata available</i></p>"
        
        html_parts = ["<style>",
                     "table { width: 100%; border-collapse: collapse; }",
                     "th { text-align: left; background-color: #f2f2f2; }",
                     "td { padding: 8px; vertical-align: top; }",
                     "tr:nth-child(even) { background-color: #f9f9f9; }",
                     # Nested tables (for dict-valued metadata entries) get
                     # their own tighter styling so they read as "this
                     # parameter has sub-fields", not as another top-level
                     # row of the outer table — no striping, less padding,
                     # so they stay visually subordinate.
                     "table.nested { width: auto; margin: 2px 0; }",
                     "table.nested tr:nth-child(even) { background-color: transparent; }",
                     "table.nested td { padding: 2px 6px; border: none; }",
                     "table.nested td.nested-key { white-space: nowrap; color: #555; }",
                     "</style>",
                     "<table>"]
        
        # Add header
        html_parts.append("<tr><th>Property</th><th>Value</th></tr>")
        
        # Add rows for each metadata item
        for key, value in self.metadata.items():
            # Clean up the key for display (replace underscores with spaces, capitalize)
            display_key = key.replace('_', ' ').title()

            # A "section" entry is a top-level value that's itself a dict
            # or a list of dicts — a whole correction/operation record
            # (Svd Correction History, Baseline Correction, ...), not a
            # single scalar property. These get a visible divider above
            # them, applied as an INLINE style directly on this one <tr>
            # — not a CSS class + separate <style> rule. Qt's QTextEdit
            # HTML renderer has limited, non-browser-accurate CSS support
            # and does not reliably scope a class selector like
            # "tr.section-row td" away from rows inside NESTED tables —
            # the first version of this used exactly that, and the class
            # ended up matching (or the border otherwise leaking onto)
            # every nested row too, putting a divider between every single
            # field instead of just between sections. An inline style
            # attribute on one specific <tr> has no such ambiguity: it
            # can't be picked up by anything else.
            is_section = isinstance(value, dict) or (
                isinstance(value, (list, tuple)) and len(value) > 0
                and all(isinstance(v, dict) for v in value)
            )
            section_style = (
                ' style="border-top:3px solid #90a4ae;"' if is_section else ''
            )
            key_style = ' style="font-size:1.05em;"' if is_section else ''

            # Handle special case for file paths to make them more readable
            if isinstance(value, str) and ('path' in key.lower() or 'file' in key.lower()) and '/' in value:
                # Format file paths with line breaks at directory separators
                formatted_value = value.replace('/', '/<wbr>')
            else:
                formatted_value = self._format_value(value)
            
            html_parts.append(
                f"<tr{section_style}><td{key_style}><b>{display_key}</b></td>"
                f"<td{section_style}>{formatted_value}</td></tr>"
            )
        
        html_parts.append("</table>")
        return "".join(html_parts)
