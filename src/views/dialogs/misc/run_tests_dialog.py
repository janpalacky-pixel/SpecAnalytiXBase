# src/views/dialogs/misc/run_tests_dialog.py
"""Help -> Run tests... (also a button in Help -> About): runs the program's own
test suite in a separate, invisible process and shows progress, live counts
and the output; the result can be copied or saved as one file (with the About
information) to send to the developer. See src/modules/utils/self_test.py."""

import datetime
import os

from PyQt5.QtCore import QProcess, QProcessEnvironment, Qt
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel,
                             QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                             QVBoxLayout)

from src.modules.utils import self_test

_INTRO = ("Runs the program's own checks (about 1300 tests, roughly 5–10 minutes) to see "
          "whether SpecAnalytiXBase works correctly on this computer. They run in the "
          "background in a separate, invisible process: you can keep working, and your "
          "spectra, settings and automatic saves are not touched.\n\n"
          "If something fails, save the output and send the file to the developer.")


class RunTestsDialog(QDialog):

    def __init__(self, parent=None, args=('tests',), workdir=self_test.PROJECT_ROOT):
        super().__init__(parent)
        self.setWindowTitle("Run tests")
        # an ordinary window of its own: it can be minimized and put behind
        # the main window while the tests run (a dialog owned by the main
        # window always stays on top of it and has no minimize button)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self._saved = False
        self.resize(820, 560)
        self._args = tuple(args)
        self._workdir = workdir
        self._process = None
        self._stopped = False
        self._buffer = ''
        self.reader = self_test.OutputReader()
        self.started_at = None

        layout = QVBoxLayout(self)
        intro = QLabel(_INTRO)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.counts_label = QLabel("Not started.")
        layout.addWidget(self.counts_label)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.output.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.output, 1)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        row = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        self.copy_button = QPushButton("Copy")
        self.copy_button.setToolTip("Copy the result with the About information, e.g. into an e-mail.")
        self.copy_button.clicked.connect(self.copy_report)
        self.save_button = QPushButton("Save output…")
        self.save_button.setToolTip("Save the result with the About information as a text file.")
        self.save_button.clicked.connect(self.save_report)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        for b in (self.start_button, self.stop_button):
            row.addWidget(b)
        row.addStretch(1)
        for b in (self.copy_button, self.save_button, self.close_button):
            row.addWidget(b)
        layout.addLayout(row)
        self.copy_button.setEnabled(False)
        self.save_button.setEnabled(False)

        ok, why = self_test.availability()
        if not ok:
            self.start_button.setEnabled(False)
            self.counts_label.setText(why)

    # ------------------------------------------------------------------ run
    def is_running(self):
        return self._process is not None and self._process.state() != QProcess.NotRunning

    def start(self):
        if self.is_running():
            return
        self.reader = self_test.OutputReader()
        self._stopped = False
        self._buffer = ''
        self.output.clear()
        self._saved = False
        self.result_label.setText("")
        self.result_label.setStyleSheet("")
        self.progress.setValue(0)
        self.started_at = datetime.datetime.now()
        cmd = self_test.command(self._args)
        self._cmd = cmd
        proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        for k, v in self_test.environment().items():
            env.insert(k, v)
        proc.setProcessEnvironment(env)
        proc.setWorkingDirectory(self._workdir)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self._read)
        proc.finished.connect(self._finished)
        proc.errorOccurred.connect(self._error)
        self._process = proc
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.copy_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.counts_label.setText("Starting…")
        proc.start(cmd[0], cmd[1:])

    def stop(self):
        if self.is_running():
            self._stopped = True
            self._process.kill()

    def _read(self):
        data = bytes(self._process.readAllStandardOutput()).decode('utf-8', errors='replace')
        self._buffer += data
        *lines, self._buffer = self._buffer.split('\n')
        if lines:
            self.output.appendPlainText('\n'.join(l.rstrip('\r') for l in lines))
        for line in lines:
            self.reader.feed(line)
        self._show_counts()

    def _show_counts(self):
        c = self.reader.counts
        self.progress.setValue(self.reader.percent)
        text = f"{c['passed']} passed, {c['failed']} failed, {c['skipped']} skipped"
        if c['error']:
            text += f", {c['error']} errors"
        if self.reader.current and self.is_running():
            text += f"   —   {self.reader.current}"
        self.counts_label.setText(text)

    def _finished(self, exit_code, _status=None):
        if self._buffer:
            self.output.appendPlainText(self._buffer.rstrip('\r'))
            self.reader.feed(self._buffer)
            self._buffer = ''
        self._show_counts()
        ok, text = self.reader.result(exit_code, stopped=self._stopped)
        if ok:
            self.progress.setValue(100)
        self.result_label.setText(text)
        self.result_label.setStyleSheet(
            "font-weight: bold; color: %s;" % ('#1a7f37' if ok else '#c62828'))
        self.start_button.setEnabled(True)
        self.start_button.setText("Run again")
        self.stop_button.setEnabled(False)
        self.copy_button.setEnabled(True)
        self.save_button.setEnabled(True)

    def _error(self, error):
        if error == QProcess.FailedToStart:
            self.result_label.setText("The tests could not be started (Python was not found).")
            self.result_label.setStyleSheet("font-weight: bold; color: #c62828;")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)

    # --------------------------------------------------------------- report
    def report_text(self):
        from src.modules.utils.about_info import format_about_text, get_about_info
        when = (self.started_at or datetime.datetime.now()).strftime('%Y-%m-%d %H:%M')
        body = self.output.toPlainText()
        if self.result_label.text():
            body += "\n\nResult: " + self.result_label.text() + "\n"
        return self_test.report(format_about_text(get_about_info()), body,
                                getattr(self, '_cmd', self_test.command(self._args)), when)

    def copy_report(self):
        QApplication.clipboard().setText(self.report_text())
        self._saved = True

    def save_report(self):
        stamp = (self.started_at or datetime.datetime.now()).strftime('%Y-%m-%d_%H-%M')
        default = os.path.join(os.path.expanduser('~'), f'SpecAnalytiXBase_tests_{stamp}.txt')
        path, _ = QFileDialog.getSaveFileName(self, "Save test output", default,
                                              "Text files (*.txt);;All files (*)")
        if not path:
            return None
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.report_text())
        self._saved = True
        self.counts_label.setText(f"Saved: {path}")
        return path

    # ---------------------------------------------------------------- close
    def _may_close(self):
        """Ask before closing: while the tests run (stop them?), and after a
        run with failures whose output was neither saved nor copied."""
        if self.is_running():
            reply = QMessageBox.question(
                self, "Stop the tests?",
                f"The tests are still running ({self.reader.done_tests()} done so far).\n\n"
                "Do you want to stop them and close this window?\n"
                "(To keep them running, choose No; you can minimize the window.)",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return False
            self.stop()
            self._process.waitForFinished(5000)
            return True
        if self._needs_saving():
            reply = QMessageBox.question(
                self, "Close without saving?",
                "Some tests did not pass, and the output has not been saved or copied.\n\n"
                "Close the window anyway? (Choose No, then \"Save output\u2026\" to keep "
                "a file for the developer.)",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return False
            self._saved = True                 # asked once is enough
        return True

    def _needs_saving(self):
        text = self.result_label.text()
        return bool(text) and not text.startswith(('All tests passed', 'Stopped by you')) \
            and not self._saved

    def closeEvent(self, event):
        """The window's X and the Close button."""
        if not self._may_close():
            event.ignore()
            return
        self._confirmed = True
        try:
            super().closeEvent(event)          # QDialog calls reject() from here
        finally:
            self._confirmed = False

    def reject(self):
        """Esc (and QDialog's own closing): with the same questions."""
        if getattr(self, '_confirmed', False) or self._may_close():
            super().reject()


_open = []


def open_run_tests_dialog(parent=None):
    """Show the one Run tests window (raise it if it is already open)."""
    for dlg in list(_open):
        try:
            dlg.show(); dlg.raise_(); dlg.activateWindow()
            return dlg
        except RuntimeError:            # deleted with its parent
            _open.remove(dlg)
    dlg = RunTestsDialog(None)             # a window of its own, not owned by `parent`
    dlg.setWindowModality(Qt.NonModal)
    _open.append(dlg)
    dlg.show()
    return dlg
