# src/controllers/visualization/plot_notes_controller.py
"""Your own labels on the main plot (right-click on the plot): "Label the
band here" (its position, e.g. 1004, above the peak), "Add text here",
"Add an arrow here", and "Labels on the plot…" (a list to change or delete
them). On the plot a label is
  * clicked: chosen (a dashed frame) - the Delete key then deletes it;
  * double-clicked: changed in a small window (text, size, colour, ...);
  * dragged: moved. An arrow (chosen: its two ends as small squares): drag
    its tail end (or text) to turn and stretch it, its tip to move the tip,
    its middle to move the whole arrow.
Everything is kept in the plot's units, so a label stays at its place when
the plot is zoomed or the window made larger.
The labels are drawn on the (first) plot again after every new plot, saved
in snapshots, and shown in Save plot for publication (plot_notes.PlotNotes)."""

from src.modules.visualization.plot_notes import GID, PlotNotes, fmt, peak_top

GRAB_PX = 9                 # how near (screen pixels) the mouse must be to an arrow's end


class PlotNotesController:

    def __init__(self, main_controller):
        self.main = main_controller
        self.notes = PlotNotes()
        self.canvas = None
        self.selected = None        # the number of the chosen label (or None)
        self._artists = []
        self._cids = []
        self._drag = None           # (index, part, start pixel, note before)
        self.dialog = None
        self.changed_callbacks = []     # e.g. Save plot for publication: show again

    # ------------------------------------------------------------------ the plot
    @staticmethod
    def target_axes(figure):
        """The plot the labels are drawn on: the first one (not a colour bar)."""
        for ax in figure.axes:
            if ax.get_visible() and not hasattr(ax, '_colorbar'):
                return ax
        return None

    def attach(self, canvas):
        """Called after every plot (the canvas is new each time)."""
        if self.canvas is not None:
            for cid in self._cids:
                try:
                    self.canvas.mpl_disconnect(cid)
                except Exception:
                    pass
        self._cids = []
        self.canvas = canvas
        self._artists = []
        self._drag = None
        if canvas is None:
            return
        self._cids = [canvas.mpl_connect('button_press_event', self._pressed),
                      canvas.mpl_connect('motion_notify_event', self._moved),
                      canvas.mpl_connect('button_release_event', self._released)]
        self.redraw(draw=False)

    def redraw(self, draw=True, quiet=False):
        """The labels drawn again (after a change); quiet: only on the plot
        (while dragging - the list and other windows follow at the end)."""
        if self.selected is not None and not 0 <= self.selected < len(self.notes):
            self.selected = None
        if self.canvas is not None:
            figure = self.canvas.figure
            for ax in figure.axes:
                for a in list(ax.texts) + list(ax.get_lines()):
                    if str(a.get_gid() or '').startswith(GID):
                        a.remove()                 # labels, an arrow's end squares
            self._artists = []
            ax = self.target_axes(figure)
            # "scale each" (scale_each.py): the labels are in the spectra's own
            # units, which the scaled plot does not show - kept, not drawn
            from src.modules.visualization import scale_each
            if ax is not None and len(self.notes) and not scale_each.is_on(figure):
                self._artists = self.notes.draw(ax, selected=self.selected)
            if draw:
                self.canvas.draw_idle()
        if quiet:
            return
        if self.dialog is not None:
            self.dialog.refresh()
        for callback in list(self.changed_callbacks):
            try:
                callback()
            except Exception:
                pass

    # ------------------------------------------------------------------ the mouse
    def hit(self, event):
        """(label number, part) under the mouse - part: 'text', 'tail', 'tip'
        or 'shaft' (an arrow's middle) - or None."""
        if self.canvas is None or event.x is None:
            return None
        ax = self.target_axes(self.canvas.figure)
        if ax is None:
            return None
        import numpy as np
        try:                                   # a screen at 150 %: more pixels to the same place
            grab = GRAB_PX * float(self.canvas.devicePixelRatioF())
        except Exception:
            grab = GRAB_PX
        for i in reversed(range(min(len(self._artists), len(self.notes)))):
            ann, n = self._artists[i], self.notes.notes[i]
            if n['kind'] == 'arrow':
                tip = np.array(ax.transData.transform((n['x'], n['y'])), dtype=float)
                place = self.notes.text_place(n) or (n['x'], n['y'])
                tail = np.array(ax.transData.transform(place), dtype=float)
                p = np.array([event.x, event.y], dtype=float)
                if np.hypot(*(p - tip)) <= grab:
                    return i, 'tip'
                if np.hypot(*(p - tail)) <= grab:
                    return i, 'tail'
            try:
                if n['text'] and ann.contains(event)[0]:
                    return i, 'text'
            except Exception:
                pass
            if n['kind'] == 'arrow':
                seg = tail - tip
                length = float(np.hypot(*seg))
                if length > 0:
                    t = float(np.clip(np.dot(p - tip, seg) / length ** 2, 0, 1))
                    if np.hypot(*(p - (tip + t * seg))) <= grab / 2:
                        return i, 'shaft'
        return None

    def _pressed(self, event):
        if event.button != 1:
            return
        found = self.hit(event)
        if found is None:
            if self.selected is not None:
                self.select(None)
            return
        i, part = found
        if getattr(event, 'dblclick', False):
            self._drag = None
            self.select(i)
            self.edit(i)
            return
        try:
            self.canvas.setFocus()                 # the Delete key reaches the plot
        except Exception:
            pass
        self._drag = (i, part, (event.x, event.y), dict(self.notes.notes[i]))
        if self.selected != i:
            self.select(i)

    def _moved(self, event):
        if self._drag is None or event.x is None:
            return
        i, part, (x0, y0), before = self._drag
        ax = self.target_axes(self.canvas.figure)
        if ax is None or not 0 <= i < len(self.notes):
            return
        self.notes.move(i, part, ax, before, event.x - x0, event.y - y0)
        self.redraw(quiet=True)

    def dragging(self):
        """True while a label is dragged (the cursor then does not follow)."""
        return self._drag is not None

    def _released(self, event):
        if self._drag is None:
            return
        self._drag = None
        self.redraw()

    # ------------------------------------------------------------------ choosing, changing
    def select(self, i):
        self.selected = i if i is not None and 0 <= i < len(self.notes) else None
        self.redraw()

    def delete_selected(self):
        """The Delete key: the chosen label deleted. True when one was."""
        if self.selected is None:
            return False
        self.notes.remove(self.selected)
        self.selected = None
        self.redraw()
        return True

    def edit(self, i, parent=None):
        """The small window to change one label (text, size, colour, ...)."""
        from src.views.dialogs.visualization.plot_notes_dialog import NoteEditDialog
        if not 0 <= i < len(self.notes):
            return False
        dlg = NoteEditDialog(self.notes.notes[i], parent or getattr(self.main, 'view', None))
        result = dlg.exec_()
        if result == NoteEditDialog.DELETE:
            self.notes.remove(i)
            self.selected = None
        elif result:
            self.notes.update(i, **dlg.values())
        self.redraw()
        return bool(result)

    # ------------------------------------------------------------------ adding
    def scaled(self):
        """"scale each" on in the plot: labels are neither drawn nor added."""
        from src.modules.visualization import scale_each
        return self.canvas is not None and scale_each.is_on(self.canvas.figure)

    def add_at(self, kind, event, text=None):
        """A new label at the place clicked (`event`: a matplotlib mouse
        event on a plot). `text` None: asked for. Returns its number or None."""
        if event is None or event.inaxes is None or event.xdata is None:
            return None
        if self.scaled():
            return None                        # not in the scaled units (redraw)
        x, y = float(event.xdata), float(event.ydata)
        if kind == 'band':
            cursor = getattr(self.main, 'plot_cursor_controller', None)
            curves = cursor._curves(event.inaxes) if cursor is not None else []
            top = peak_top(curves, x, event.inaxes.get_xlim())
            if top is not None:
                y = top
        if text is None:
            text = self._ask_text(kind, x)
            if text is None:
                return None
        i = self.notes.add(kind, x, y, text, ax=event.inaxes)
        self.selected = i
        self.redraw()
        return i

    def add_in_middle(self, kind, text):
        """A new label in the middle of the plot (from Save plot for
        publication); drag it to its place. Returns its number or None."""
        if self.canvas is None or self.scaled():
            return None
        ax = self.target_axes(self.canvas.figure)
        if ax is None:
            return None
        (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
        i = self.notes.add(kind, (x0 + x1) / 2, (y0 + y1) / 2, text, ax=ax)
        self.selected = i
        self.redraw()
        return i

    def _ask_text(self, kind, x):
        from src.views.dialogs.misc.rich_text import RichTextDialog
        title, hint, start = {
            'band': ("Label the band", "Label (e.g. the band's position or a name):", fmt(x)),
            'text': ("Add text", "Text:", ''),
            'arrow': ("Add an arrow", "Text at the arrow's tail (may be empty):", ''),
        }[kind]
        text, ok = RichTextDialog.ask(start, getattr(self.main, 'view', None), title, hint)
        if not ok:
            return None
        if kind == 'text' and not text.strip():
            return None
        return text

    def clear(self):
        self.notes.clear()
        self.selected = None
        self.redraw()

    def show_dialog(self):
        from src.views.dialogs.visualization.plot_notes_dialog import PlotNotesDialog
        if self.dialog is None:
            self.dialog = PlotNotesDialog(self, getattr(self.main, 'view', None))
            self.dialog.finished.connect(lambda *_: setattr(self, 'dialog', None))
        self.dialog.refresh()
        self.dialog.show()
        self.dialog.raise_()
        return self.dialog

    # ------------------------------------------------------------------ snapshots
    def to_dict(self):
        return self.notes.to_dict()

    def from_dict(self, data):
        self.notes.from_dict(data)
        self.selected = None
        self.redraw()
