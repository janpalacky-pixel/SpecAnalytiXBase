"""The same picture every run: what would otherwise differ between two runs
of the picture scripts although the window did not change.

- start(): the IDs given to imported spectra (shown e.g. in the Metadata
  window) come from a fixed sequence instead of random, and the random
  numbers of numpy start from a fixed seed; call it before the program's
  modules are imported. (make_all_help_pictures.bat also runs the numerical
  libraries on one thread, so a calculation gives the same last digits.)
- fixed_clock(): the times written into the Operations History (and the
  other records with a time) are a fixed date and time.
- park_mouse(): the mouse pointer is moved to the bottom-right corner of the
  screen, so no button is drawn highlighted because the pointer happens to
  be over it (call it before each picture)."""
import datetime as _dt
import random
import sys
import uuid

FIXED_TIME = _dt.datetime(2026, 1, 15, 10, 30, 0)


def start():
    rng = random.Random(20260115)
    uuid.uuid4 = lambda: uuid.UUID(int=rng.getrandbits(128), version=4)
    random.seed(20260115)
    import numpy as np
    np.random.seed(20260115)


class _FixedDateTime(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED_TIME if tz is None else FIXED_TIME.replace(tzinfo=tz)


class _DateTimeModule:
    """Stands in for the module `datetime` where a module imported it whole."""
    datetime = _FixedDateTime

    def __getattr__(self, name):
        return getattr(_dt, name)


def fixed_clock():
    """Every loaded module of the program that uses datetime.now()."""
    for name, module in list(sys.modules.items()):
        if not name.startswith('src.') or module is None:
            continue
        current = getattr(module, 'datetime', None)
        if current is _dt.datetime:
            module.datetime = _FixedDateTime
        elif current is _dt:
            module.datetime = _DateTimeModule()


def park_mouse():
    from PyQt5.QtGui import QCursor
    from PyQt5.QtWidgets import QApplication
    screen = QApplication.primaryScreen()
    if screen is not None:
        corner = screen.geometry().bottomRight()
        if QCursor.pos() != corner:
            QCursor.setPos(corner)
        QApplication.processEvents()
