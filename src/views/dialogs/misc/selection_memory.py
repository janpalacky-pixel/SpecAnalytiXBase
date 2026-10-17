"""Which spectra were selected in a tool window, remembered for the next
time it is opened (during the session).

A tool window (FFT Denoising, Normalization, X-axis alignment, ...) has
its own list of the spectra handed to it. Its selection there is saved when
the window closes (by label) and restored when it opens again -- as far as
those spectra are still in the list. If none of them is, the window's
default applies (all spectra, or the first one)."""
from src.modules.utils.list_selection import select_rows

_MEMORY = {}


def restore_selection(key, list_widget, default='all'):
    """Select the remembered rows of `list_widget` (by item text), else the
    default ('all', 'first' or None). Returns True if a remembered selection
    was restored. Selects with one call (fast for 21 000 rows); signals are
    the caller's business (block them if needed)."""
    saved = _MEMORY.get(key)
    count = list_widget.count()
    if saved:
        rows = [i for i in range(count) if list_widget.item(i).text() in saved]
        if rows:
            select_rows(list_widget, rows)
            return True
    if default == 'all':
        select_rows(list_widget, range(count))
    elif default == 'first' and count:
        select_rows(list_widget, [0])
    return False


def remembered(key):
    """The remembered labels for `key` (a set), or an empty set."""
    return set(_MEMORY.get(key) or ())


def remember_on_close(dialog, key, list_widget):
    """Save the selection of `list_widget` whenever `dialog` closes."""
    def save(*_):
        try:
            _MEMORY[key] = {item.text() for item in list_widget.selectedItems()}
        except RuntimeError:            # widget already deleted
            pass
    dialog.finished.connect(save)


def forget_all():
    """For tests."""
    _MEMORY.clear()
