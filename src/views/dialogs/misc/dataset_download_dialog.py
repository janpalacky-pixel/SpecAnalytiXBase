# src/views/dialogs/misc/dataset_download_dialog.py
"""Dialog for fetching real-data test datasets that are too large to keep
in the git repository (some are 100+ MB). They're hosted instead as assets
attached to a GitHub Release; this dialog downloads whichever the user
picks into a writable, per-user folder (see
MainController._downloaded_real_datasets_dir() — never the app's own
install directory, which a non-admin user typically can't write into).

These files are never bundled, whether running from source or from a
packaged install — the whole point of hosting them as release assets
instead of shipping them is that a normal build never carries them, so
this dialog is the only way to get them locally either way.
"""

import os
import urllib.error
import urllib.request

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
)


class _DownloadWorker(QThread):
    """Runs the actual downloads off the GUI thread so a large file (some
    of these are 100+ MB) doesn't freeze the dialog."""

    progress     = pyqtSignal(int, int)        # bytes_done, bytes_total (-1 if unknown)
    finished_one = pyqtSignal(str, bool, str)  # filename, success, error_message
    all_done     = pyqtSignal()

    def __init__(self, jobs):
        """jobs : list of (filename, url, dest_path) tuples."""
        super().__init__()
        self._jobs = jobs
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        for filename, url, dest_path in self._jobs:
            if self._cancelled:
                break
            tmp_path = dest_path + '.part'

            def _report(block_num, block_size, total_size):
                if self._cancelled:
                    raise InterruptedError("cancelled")
                done = (min(block_num * block_size, total_size)
                        if total_size > 0 else block_num * block_size)
                self.progress.emit(done, total_size)

            try:
                urllib.request.urlretrieve(url, tmp_path, reporthook=_report)
                os.replace(tmp_path, dest_path)
                self.finished_one.emit(filename, True, "")
            except Exception as exc:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except OSError:
                    pass
                self.finished_one.emit(filename, False, str(exc))
        self.all_done.emit()


class DatasetDownloadDialog(QDialog):
    """Lets the user pick which large real-data test datasets to download
    from the app's GitHub Release assets into a writable, per-user
    folder (dest_dir — see MainController._downloaded_real_datasets_dir())."""

    def __init__(self, parent, datasets, dest_dir, base_url):
        """
        datasets : list of (label, filename) tuples — filename must match
                   the asset name attached to the release exactly.
        dest_dir : local folder to save into (resources/test_data/real/).
        base_url : "https://github.com/<owner>/<repo>/releases/download/<tag>"
        """
        super().__init__(parent)
        self.setWindowTitle("Download large test datasets")
        self.setMinimumWidth(480)
        self._dest_dir = dest_dir
        self._base_url = base_url
        self._worker = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "These real-data 2D maps are too large to keep in the git "
            "repository, so they're hosted as GitHub Release assets "
            "instead. Check which ones to download into your test data "
            "folder:"
        ))

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.NoSelection)
        for label, filename in datasets:
            already_have = os.path.exists(os.path.join(dest_dir, filename))
            text = f"{label}  ({filename})"
            if already_have:
                text += "  [already downloaded]"
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, filename)
            self._list.addItem(item)
        layout.addWidget(self._list)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_download = QPushButton("Download selected")
        self._btn_download.clicked.connect(self._start_download)
        btn_row.addWidget(self._btn_download)
        self._btn_close = QPushButton("Close")
        self._btn_close.clicked.connect(self._on_close)
        btn_row.addWidget(self._btn_close)
        layout.addLayout(btn_row)

    def _start_download(self):
        jobs = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.Checked:
                filename = item.data(Qt.UserRole)
                url = f"{self._base_url}/{filename}"
                dest_path = os.path.join(self._dest_dir, filename)
                jobs.append((filename, url, dest_path))
        if not jobs:
            QMessageBox.information(self, "Nothing selected",
                                    "Check at least one dataset to download.")
            return

        os.makedirs(self._dest_dir, exist_ok=True)
        self._btn_download.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)   # indeterminate until first progress signal

        self._worker = _DownloadWorker(jobs)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_one.connect(self._on_one_done)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _on_progress(self, done, total):
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(done)
        else:
            self._progress.setRange(0, 0)

    def _on_one_done(self, filename, success, error_message):
        if success:
            self._status_label.setText(f"Downloaded {filename}")
        else:
            self._status_label.setText(f"Failed: {filename} — {error_message}")

    def _on_all_done(self):
        self._btn_download.setEnabled(True)
        self._progress.setVisible(False)
        QMessageBox.information(
            self, "Download complete",
            "Finished downloading the selected datasets.\n"
            "Open them from Help \u2192 Test datasets \u2192 Real (measured) "
            "\u2192 2D maps, same as any other test dataset.")

    def _on_close(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        self.reject()

    def closeEvent(self, event):
        self._on_close()
        super().closeEvent(event)
