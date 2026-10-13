# src/views/dialogs/misc/worker_count_slider.py
"""The "Parallel workers" control shared by the Automated Baseline dialog
and the 2D Map's Peak-fit settings: a slider from 1 to the number of CPU
cores, with the chosen number and the maximum always visible.

value() is 0 when the slider is at the maximum -- stored that way, the
setting means "all cores" on whatever computer it is used next
(parallel_utils.requested_workers) -- and the chosen number otherwise.
The free-memory estimate is shown as a hint only; it does not limit the
number (see requested_workers for why)."""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from src.modules.utils.parallel_utils import max_worker_count, memory_worker_estimate


class WorkerCountSlider(QWidget):

    valueChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._max = max_worker_count()
        self._by_memory = memory_worker_estimate()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(1)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(1, self._max)
        self.slider.setValue(self._max)
        self.slider.setPageStep(1)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setTickInterval(max(1, self._max // 10))
        self.slider.setMinimumWidth(120)
        self.number_label = QLabel()
        self.number_label.setMinimumWidth(
            self.number_label.fontMetrics().horizontalAdvance(f"{self._max} / {self._max} (max)") + 6)
        row.addWidget(self.slider, 1)
        row.addWidget(self.number_label)
        outer.addLayout(row)
        self.hint_label = QLabel()
        outer.addWidget(self.hint_label)
        self.setToolTip(
            "Number of worker processes for parallel processing, from 1 to the number\n"
            f"of CPU cores of this computer ({self._max}). The default is the maximum.\n"
            "Each worker needs roughly 200 MB of memory. The orange note appears when\n"
            "the memory that is free right now suits fewer workers: more workers may then\n"
            "slow the computer down, and if they cannot start or run out of memory, the\n"
            "job is redone serially (same result, slower).")
        self.slider.valueChanged.connect(self._changed)
        self._changed(self.slider.value())

    # -- the QSpinBox-like interface used by the dialogs
    def value(self):
        v = self.slider.value()
        return 0 if v >= self._max else v

    def setValue(self, value):
        try:
            value = int(value or 0)
        except (TypeError, ValueError):
            value = 0
        self.slider.setValue(self._max if value <= 0 else min(value, self._max))

    def maximum(self):
        return self._max

    def workers(self):
        """The number of workers that will be used."""
        return self.slider.value()

    # -- internals
    def _changed(self, v):
        if v >= self._max:
            self.number_label.setText(f"{v} / {self._max} (max)")
        else:
            self.number_label.setText(f"{v} / {self._max}")
        if self._by_memory is not None and v > self._by_memory:
            self.hint_label.setText(
                f"<span style='color:#B26A00;font-size:8pt'>free memory now suits about "
                f"{self._by_memory} (see tooltip)</span>")
            self.hint_label.show()
        else:
            self.hint_label.hide()
        self.valueChanged.emit(self.value())
