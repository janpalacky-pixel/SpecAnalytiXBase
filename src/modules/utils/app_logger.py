# src/utils/app_logger.py
#
# Central logging configuration for SpecAnalytiXBase.
#
# Usage in any module
# -------------------
#   from src.modules.utils.app_logger import get_logger
#   logger = get_logger(__name__)
#
#   logger.debug("Detailed diagnostic info")
#   logger.info("Normal operational message")
#   logger.warning("Something unexpected but recoverable")
#   logger.error("Something failed")
#   logger.exception("Error with full traceback")  # use inside except blocks
#
# Log level is controlled by the LOG_LEVEL environment variable:
#   LOG_LEVEL=DEBUG python main.py   → show everything
#   LOG_LEVEL=WARNING python main.py → show only warnings and errors
#
# Default level: DEBUG.
#
# TEMPORARY: set LOG_DISABLE=1 in the environment (or just hardcode
# _DISABLE_LOGGING = True below) to turn logging off entirely during
# development without touching call sites. Remove/set back to False
# before the final build.
#
# WHERE THE LOG FILE LIVES
# ------------------------
# Every run writes to a file at a fixed, predictable location so it can be
# found after the fact, even after a freeze that closed the console:
#
#   Windows : %LOCALAPPDATA%\SpecAnalytiXBase\logs\specanalytixbase.log
#   other   : ~/.specanalytixbase/logs/specanalytixbase.log
#
# The file rotates at 5 MB, keeping 3 backups (specanalytixbase.log.1, .2,
# .3), so it can't silently grow forever, but also won't be empty right
# when you need it.

import faulthandler
import logging
import logging.handlers
import os
import sys
import traceback
from datetime import datetime

# Kept alive for the whole process so the file object faulthandler is
# writing into (see enable_crash_diagnostics() below) never gets garbage
# collected/closed out from under it.
_crash_log_file = None

# TEMPORARY switch — flip to True (or set LOG_DISABLE=1) to silence
# logging entirely while debugging. Set back to False before release.
_DISABLE_LOGGING = False


def _log_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "SpecAnalytiXBase", "logs")
    return os.path.join(os.path.expanduser("~"), ".specanalytixbase", "logs")


def get_log_file_path() -> str:
    """
    Return the path to the active log file. Useful for surfacing the
    location to the user directly (e.g. a "Show Log File" menu action)
    instead of relying on them remembering or finding this comment.
    """
    return os.path.join(_log_dir(), "specanalytixbase.log")


class _SafeRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """
    RotatingFileHandler that tolerates a locked log file on rollover.

    On Windows, antivirus / sync-agent file scanning or a stray lingering
    process can briefly hold specanalytixbase.log open exactly when a
    rollover is triggered, causing os.rename() to raise PermissionError.
    The stock handler lets that exception propagate out of emit(), which
    logging swallows into an ugly "--- Logging error ---" traceback
    printed to stderr — and the record that triggered it is lost.

    Here we catch that specific failure and just skip rotation for this
    one write (carry on appending to the existing file). The next
    successful rollover opportunity will catch up. This never silently
    discards a log record — it only skips the file rename/rotate step.
    """

    def doRollover(self):
        try:
            super().doRollover()
        except PermissionError:
            # Couldn't rotate (file locked by something else momentarily).
            # Re-open the current file in append mode and continue rather
            # than crashing logging or losing the pending record.
            if self.stream:
                self.stream.close()
                self.stream = None
            self.stream = self._open()


def configure_logging() -> None:
    """
    Configure the root logger for the application.
    Call this once from main.py before anything else.
    """
    if _DISABLE_LOGGING or os.environ.get("LOG_DISABLE") == "1":
        logging.disable(logging.CRITICAL)
        return

    # level_name = os.environ.get('LOG_LEVEL', 'DEBUG').upper()
    level_name = os.environ.get('LOG_LEVEL', 'INFO').upper()
    level = getattr(logging, level_name, logging.DEBUG)

    # Format: time | level | module | message
    fmt = '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
    date_fmt = '%H:%M:%S'
    formatter = logging.Formatter(fmt, datefmt=date_fmt)

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid adding duplicate handlers if configure_logging() is called twice
    if root.handlers:
        return

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    try:
        log_dir = _log_dir()
        os.makedirs(log_dir, exist_ok=True)
        file_handler = _SafeRotatingFileHandler(
            get_log_file_path(),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        root.info("=" * 70)
        root.info("Session started %s — log file: %s",
                   datetime.now().isoformat(timespec="seconds"),
                   get_log_file_path())
    except OSError:
        # If the log directory can't be created/written (locked-down
        # machine, permissions issue, etc.), fall back to console-only
        # rather than crashing the app over logging itself.
        root.warning(
            "Could not open log file at %s — continuing with console "
            "logging only.", get_log_file_path()
        )

    # Catch anything that would otherwise crash/hang silently with no
    # trace. A freeze is often an unhandled exception on a background
    # thread or inside a Qt callback that never reaches a normal
    # try/except — this guarantees it still gets written to the log file
    # before the app potentially becomes unresponsive.
    def _log_unhandled_exception(exc_type, exc_value, exc_tb):
        # SystemExit is how sys.exit() — including the app's own normal
        # `sys.exit(app.exec_())` shutdown path in main.py — signals a
        # clean exit internally. It is NOT a crash. Logging it as critical
        # was a bug: it made every ordinary app close look like an
        # unhandled exception in the log, which is misleading and would
        # bury a genuine freeze/crash in false alarms.
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        root.critical("UNHANDLED EXCEPTION:\n%s", text)
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        _show_unhandled_error(text)

    sys.excepthook = _log_unhandled_exception

    # Suppress noisy third-party loggers
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)


_showing_error = [False]


def _show_unhandled_error(text: str) -> None:
    """Tell the user about an unhandled error (added 2026-10-09, same fix as
    in MeltAnalytiX): until now it went only into the log file, so the user
    noticed nothing while the program could be in a half-finished state.
    The program keeps running (a custom sys.excepthook also stops PyQt5 from
    aborting the process); the message says so and where the details are.
    Only from the main (GUI) thread, never two boxes at once, and silently
    skipped when no QApplication exists (e.g. tests, command-line tools)."""
    import threading
    if _showing_error[0] or threading.current_thread() is not threading.main_thread():
        return
    try:
        from PyQt5.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is None:
            return
        _showing_error[0] = True
        QMessageBox.critical(
            None, "SpecAnalytiXBase - unexpected error",
            "Something went wrong, but the program is still running - you can save your work.\n\n"
            "The details were written to the log file:\n" + get_log_file_path() +
            "\n\nPlease send that file (or this message) to the developer.\n\n" + text[-1500:])
    except Exception:
        pass
    finally:
        _showing_error[0] = False


def enable_crash_diagnostics() -> None:
    """
    Enable Python's built-in faulthandler so a genuine native crash (a
    real segfault/abort in C code — Qt, matplotlib's C extensions, numpy,
    etc.) leaves behind a low-level traceback of whatever Python code was
    running at the moment of the crash, instead of the process just
    vanishing with no trace at all.

    Why this is a different safety net from the sys.excepthook installed
    in configure_logging() above: that hook only ever runs for an
    unhandled *Python* exception, including the PyQt5-specific case of an
    exception raised inside a Qt-called virtual method override (PyQt5
    reports it via sys.excepthook, then aborts the process) — so a crash
    of that kind DOES get written to specanalytixbase.log as
    "UNHANDLED EXCEPTION: ...". A true native crash (a hard segfault
    inside compiled C/C++ code) never raises a Python exception at all —
    there's nothing for sys.excepthook to catch — so it would otherwise
    close the process with zero diagnostic output whatsoever, exactly the
    "no error message, the whole app just closes, nothing in the log"
    symptom. faulthandler installs a low-level signal handler for
    SIGSEGV/SIGABRT/etc. that dumps the Python call stack of every thread
    straight to a file before the process dies, bypassing normal Python
    exception machinery entirely (since none fired) — the only way to
    get any diagnostic at all out of that failure mode.

    Call once, near the very top of main.py, before anything else that
    might crash gets a chance to run.
    """
    global _crash_log_file
    try:
        log_dir = _log_dir()
        os.makedirs(log_dir, exist_ok=True)
        crash_log_path = os.path.join(log_dir, "crash_trace.log")
        _crash_log_file = open(crash_log_path, "a", encoding="utf-8")
        _crash_log_file.write(
            "\n" + "=" * 70 +
            f"\nSession started {datetime.now().isoformat(timespec='seconds')}"
            " — faulthandler armed\n"
        )
        _crash_log_file.flush()
        faulthandler.enable(file=_crash_log_file, all_threads=True)
        logging.getLogger().info(
            "Crash diagnostics armed — native-crash trace file: %s",
            crash_log_path,
        )
    except OSError:
        # Same reasoning as the log-file fallback in configure_logging():
        # never let diagnostics setup itself be the reason the app can't
        # start.
        logging.getLogger().warning(
            "Could not open crash trace file — continuing without "
            "faulthandler diagnostics."
        )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for the given module."""
    return logging.getLogger(name)
