# src/views/publication_actions.py
"""Save plot for publication / Print for the plots of tool windows (2D Map
first): the same window as the main window's File > Save plot for
publication (publication_dialog), opened with a COPY of the tool's plot.

On that copy - never on the plot on the screen - the tool's own marks get
the ids publication_style.MARKS knows (so the window's Labels tab can leave
each kind out), the mark that follows the mouse is taken away, and lines
without a name get one (so the Lines tab lists them). How to add it to a
tool window: a button in the plot's toolbar (add_toolbar_button) and two
items in its right-click menu (add_menu_items), both calling
open_publication(parent, figure_copy(...))."""

import pickle


SAVE_TEXT = "Save plot for publication…"
PRINT_TEXT = "Print plot…"


def figure_copy(figure, marks=(), names=(), hide=()):
    """A copy of `figure` for the publication window.
    marks: [(artist, gid)] - e.g. (the clicked pixel's +, MAP_PIXEL_GID);
    names: [(line, name)] - lines without a name shown with this one;
    hide: artists not wanted at all (e.g. a tooltip that follows the mouse).
    The artists on the screen are changed only for the moment of copying."""
    changes = []

    def change(artist, setter, getter, value):
        try:
            changes.append((setter, getter()))
            setter(value)
        except Exception:
            pass

    for artist, gid in marks:
        if artist is not None:
            change(artist, artist.set_gid, artist.get_gid, gid)
    for line, name in names:
        if line is not None and name:
            change(line, line.set_label, line.get_label, name)
    for artist in hide:
        if artist is not None:
            change(artist, artist.set_gid, artist.get_gid, 'sax_cursor')   # left out
    try:
        return pickle.loads(pickle.dumps(figure))
    finally:
        for setter, old in reversed(changes):
            try:
                setter(old)
            except Exception:
                pass


def preferences_of(widget):
    """The program's preferences (for the window's profiles), found from a
    tool window: its controller's main controller, else None."""
    for owner in (widget, getattr(widget, 'controller', None)):
        main = getattr(owner, 'controller', None)
        for candidate in (main, owner):
            prefs = getattr(getattr(candidate, 'autosave_controller', None), 'preferences', None)
            if prefs is not None:
                return prefs
    return None


def open_publication(parent, figure, what="plot", print_first=False, preferences=None):
    """The Save plot for publication window for `figure` (a copy - see
    figure_copy). what: named in the title (e.g. "2D map"); print_first:
    opened on its Printing tab (Print plot...). Returns the window."""
    from src.views.dialogs.visualization.publication_dialog import PublicationDialog
    if figure is None or not figure.axes:
        return None
    title = "Print plot" if print_first else "Save plot for publication"
    dlg = PublicationDialog(figure, parent,
                            preferences=preferences if preferences is not None
                            else preferences_of(parent),
                            title=f"{title} – {what}",
                            tab="Printing" if print_first else None)
    dlg.exec_()
    return dlg


def add_toolbar_button(toolbar, callback, what="plot"):
    """A Save plot for publication button in a plot's toolbar (matplotlib's
    NavigationToolbar), right after its own Save button (the floppy disk)."""
    from PyQt5.QtWidgets import QAction
    from src.views import icons
    action = QAction(icons.publication_icon(), SAVE_TEXT, toolbar)
    action.setToolTip(f"<b>Save plot for publication</b><br>The {what} in a journal's "
                      "size, font and look -<br>TIFF, PNG, PDF, SVG, EPS or printed")
    action.setObjectName("publicationButton")
    action.triggered.connect(lambda: callback())
    after = getattr(toolbar, '_actions', {}).get('save_figure')
    actions = toolbar.actions()
    if after in actions and actions.index(after) + 1 < len(actions):
        toolbar.insertAction(actions[actions.index(after) + 1], action)
    else:
        toolbar.addAction(action)
    return action


def add_menu_items(menu, save, print_, what="plot"):
    """'Save plot for publication...' and 'Print plot...' in a right-click
    menu (save / print_: what they call)."""
    from src.views import icons
    a = menu.addAction(icons.publication_icon(), SAVE_TEXT)
    a.setToolTip(f"The {what} in a journal's size, font and look")
    a.triggered.connect(lambda: save())
    b = menu.addAction(PRINT_TEXT)
    b.triggered.connect(lambda: print_())
    return a, b
