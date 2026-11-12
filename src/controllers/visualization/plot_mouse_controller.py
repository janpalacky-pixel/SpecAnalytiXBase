# src/controllers/visualization/plot_mouse_controller.py
"""Small mouse conveniences on the main plot, as in Origin, Spectragryph or
Excel:

* the mouse wheel zooms where the mouse is - the x axis; with Ctrl the y
  axis (Back / Home in the toolbar under the plot go back, step by step or
  to the start);
* pointing at a spectrum's line shows its name (a tooltip), and a click on
  the line draws it thicker and shows its row of the spectra list in bold,
  scrolled into view (the selection stays as it is) until the next click;
  the line nearest to the mouse counts, not the one drawn on top;
* the left mouse button held and the mouse moved drags the plot, as Pan of
  the toolbar does (Back / Home go back); a click without moving still
  marks a line;
* a click on a name in the legend hides that spectrum (its entry turns
  pale) and a second click shows it again. A hidden spectrum is in no plot:
  Overlay, Waterfall and Grid leave its line out (its legend entry pale);
  Mean ± SD, Difference and Heatmap are computed without it (no row in the
  Heatmap) - also in "Open in New Window". The hiding is kept when another
  plot type is chosen and ends with another selection, or with right-click
  > "Show all spectra". Processing (Apply) still uses the whole selection.

Pointing at lines, clicking lines, dragging the plot and clicking the legend
do nothing while the toolbar's Zoom or Pan is chosen (it uses the clicks and
drags itself; a click on the legend then says so in the status bar). With the
Cursor on, a click pins a cursor (plot_cursor_controller, on the release) -
so no line is marked and no spectrum hidden - but a drag still moves the plot
(and pins nothing). A press on one of your labels (plot_notes_controller) chooses
or drags that label, a press on the legend's frame drags a movable legend.
The wheel zooms always. Like the cursor, it is attached
again after every plot (the canvas is new each time)."""

from contextlib import contextmanager

import numpy as np

HOVER_MS = 120                 # the name shows when the mouse rests this long
MAX_LINES_TO_POINT = 400       # more lines in one plot: no name on pointing
PICK_PX = 6                    # how near (screen pixels) the mouse must be to a line
WHEEL_IN = 0.8                 # one wheel step forward (away from you) zooms in by this
DRAG_PX = 3                    # moved further with the button held: a drag, not a click
PALE = 0.3                     # a hidden spectrum's legend entry
_OWN_GIDS = ('sax_cursor', 'sax_cursor_pinned', 'sax_band')
# plot types computed from the spectra: a hidden spectrum is left out of
# the computation (not only its line made invisible)
LEFT_OUT_IN = ('Mean \u00b1 SD', 'Difference', 'Heatmap')


class PlotMouseController:

    def __init__(self, main_controller):
        self.main = main_controller
        self.canvas = None
        self._cids = []
        self.hidden = set()            # (full) labels hidden with a click on the legend
        self._selection = None         # the selection's labels when `hidden` was made
        self.marked = None             # (line, its width) drawn thicker
        self._bold_item = None         # its row of the list, in bold
        self._press = None             # (x, y, legend entry) of a press on the legend
        self._drag = None              # a press on the plot: a click or a drag (pan)
        self._last_move = None
        self._timer = None

    # ------------------------------------------------------------ wiring
    def attach(self, canvas):
        """Called after every plot."""
        self.detach()
        self.canvas = canvas
        if canvas is None:
            return
        canvas._sax_main_plot = True           # plot_navigation.py leaves it to us
        self._cids = [canvas.mpl_connect('scroll_event', self._on_scroll),
                      canvas.mpl_connect('motion_notify_event', self._on_move),
                      canvas.mpl_connect('button_press_event', self._on_press),
                      canvas.mpl_connect('button_release_event', self._on_release),
                      canvas.mpl_connect('figure_leave_event', lambda e: self._hide_tip())]
        self.marked = None
        self._bold_row(None)
        self._apply_hidden(draw=bool(self.hidden))

    # ------------------------------------------------------------ the selection
    def sync_selection(self, spectra):
        """Called before every plot: another selection shows all again;
        the same one (also in another plot type) keeps the hidden ones."""
        key = frozenset(str(s.get('label', '')) for s in spectra or [])
        if key != self._selection:
            self.hidden = set()
            self._selection = key

    def _shown_names(self):
        return getattr(self.main, '_display_labels', None) or {}

    def hidden_names(self):
        """The hidden spectra as their names in the legend (shortened when
        "shorten names" is on)."""
        shown = self._shown_names()
        return {shown.get(l, l) for l in self.hidden}

    def full_label(self, name):
        """The spectrum's label for a name in the legend - None when the
        entry is not a spectrum (e.g. "Mean (n = 3)", "Reference: ...")."""
        shown = self._shown_names()
        if not shown:
            return name
        for full, short in shown.items():
            if short == name:
                return full
        return None

    def visible(self, spectra, keep=None):
        """`spectra` without the hidden ones (`keep`: a label kept anyway -
        the reference of a Difference plot). All of them when every one is
        hidden (an empty Mean ± SD or Heatmap would say "no spectra")."""
        if not self.hidden:
            return list(spectra)
        left = [s for s in spectra
                if s.get('label') not in self.hidden or s.get('label') == keep]
        return left or list(spectra)

    def _plot_type(self):
        try:
            return self.main.view.comboBox_plot_type_choice.currentText()
        except Exception:
            return ''

    def detach(self):
        self._drag = None
        if self.canvas is not None:
            for cid in self._cids:
                try:
                    self.canvas.mpl_disconnect(cid)
                except Exception:
                    pass
        self._cids = []
        self.canvas = None
        self._hide_tip()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def data_lines(ax):
        """The spectra's lines (not the cursor's, band markers', labels')."""
        return [l for l in ax.get_lines()
                if not str(l.get_label()).startswith('_') and l.get_gid() not in _OWN_GIDS]

    def _busy(self):
        """Zoom / Pan chosen in the toolbar, or the Cursor on."""
        return self._toolbar_busy() or self._cursor_on()

    def _toolbar_busy(self):
        toolbar = getattr(self.canvas, 'toolbar', None)
        return bool(toolbar is not None and str(getattr(toolbar, 'mode', '') or ''))

    def _cursor_on(self):
        """The Cursor ticked: a click pins a cursor (plot_cursor_controller),
        not marks a line nor hides a spectrum - but a drag still moves the
        plot (then no cursor is pinned)."""
        cursor = getattr(self.main, 'plot_cursor_controller', None)
        return bool(cursor is not None and cursor.enabled)

    def _on_a_label(self, event):
        notes = getattr(self.main, 'plot_notes_controller', None)
        try:
            return notes is not None and notes.hit(event) is not None
        except Exception:
            return False

    @staticmethod
    def distance(line, x, y):
        """The distance in screen pixels from (x, y) to the drawn line (to
        its nearest segment, not only its nearest point)."""
        xy = np.column_stack([np.asarray(line.get_xdata(), float),
                              np.asarray(line.get_ydata(), float)])
        xy = xy[np.all(np.isfinite(xy), axis=1)]
        if len(xy) == 0:
            return np.inf
        p = line.axes.transData.transform(xy)
        if len(p) == 1:
            return float(np.hypot(*(p[0] - (x, y))))
        a, b = p[:-1], p[1:]
        d = b - a
        length2 = (d ** 2).sum(axis=1)
        t = np.clip(((x - a[:, 0]) * d[:, 0] + (y - a[:, 1]) * d[:, 1])
                    / np.where(length2 > 0, length2, 1), 0, 1)
        nearest = a + d * t[:, None]
        return float(np.min(np.hypot(nearest[:, 0] - x, nearest[:, 1] - y)))

    def line_at(self, event):
        """The spectrum's line nearest to the mouse - within a few pixels -
        or None. The nearest, not the one drawn on top: two lines close to
        each other (e.g. raman_06 under raman_07) are told apart."""
        ax = event.inaxes
        if ax is None or event.x is None:
            return None
        lines = [l for l in self.data_lines(ax) if l.get_visible()]
        if not lines or len(lines) > MAX_LINES_TO_POINT:
            return None
        dpr = 1.0
        try:
            dpr = float(self.canvas.device_pixel_ratio)
        except Exception:
            pass
        best, best_d = None, PICK_PX * dpr
        for line in reversed(lines):               # equally near: the one on top
            try:
                d = self.distance(line, event.x, event.y)
            except Exception:
                continue
            if d < best_d - 1e-9:
                best, best_d = line, d
        return best

    # ------------------------------------------------------------ the wheel
    @staticmethod
    def zoomed(lo, hi, at, factor, log=False):
        """New limits after zooming by `factor` around `at` (the order - a
        reversed axis - is kept; a log axis zooms in its logarithm)."""
        if log:
            if at <= 0 or lo <= 0 or hi <= 0:
                return lo, hi
            lo, hi, at = np.log10(lo), np.log10(hi), np.log10(at)
        new = at - (at - lo) * factor, at + (hi - at) * factor
        if log:
            new = 10 ** new[0], 10 ** new[1]
        return float(new[0]), float(new[1])

    @staticmethod
    def ctrl_held(event):
        """Ctrl held during the wheel. matplotlib (3.8 and later) puts the
        keys held into event.modifiers ({'ctrl'}); event.key is only the
        last key pressed while the plot had the keyboard focus - usually
        None, so it alone did not see Ctrl."""
        mods = getattr(event, 'modifiers', None) or ()
        if 'ctrl' in mods or 'control' in mods:
            return True
        gui = getattr(event, 'guiEvent', None)
        try:
            from PyQt5.QtCore import Qt
            if gui is not None and gui.modifiers() & Qt.ControlModifier:
                return True
        except Exception:
            pass
        key = str(getattr(event, 'key', '') or '')
        return 'control' in key or 'ctrl' in key

    def _on_scroll(self, event):
        ax = event.inaxes
        if ax is None or event.xdata is None or hasattr(ax, '_colorbar'):
            return
        steps = getattr(event, 'step', 0) or (1 if event.button == 'up' else -1)
        # a touchpad reports many small (or a few large) steps: not a jump
        factor = WHEEL_IN ** float(np.clip(steps, -2, 2))
        toolbar = getattr(self.canvas, 'toolbar', None)
        stack = getattr(toolbar, '_nav_stack', None)
        try:
            if toolbar is not None and stack is not None and stack() is None:
                toolbar.push_current()             # Home: the view before the wheel
        except Exception:
            pass
        if self.ctrl_held(event):
            ax.set_ylim(*self.zoomed(*ax.get_ylim(), event.ydata, factor,
                                     ax.get_yscale() == 'log'))
        else:
            ax.set_xlim(*self.zoomed(*ax.get_xlim(), event.xdata, factor,
                                     ax.get_xscale() == 'log'))
        try:
            if toolbar is not None:
                toolbar.push_current()             # Back: one wheel step back
        except Exception:
            pass
        self.canvas.draw_idle()

    # ------------------------------------------------------------ pointing
    def _on_move(self, event):
        if self._drag is not None:
            self._drag_to(event)
            return
        if getattr(event, 'button', None) is not None:
            return                                 # dragging something
        self._last_move = event
        if self._timer is None:
            from PyQt5.QtCore import QTimer
            self._timer = QTimer()
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._show_name)
        self._timer.start(HOVER_MS)

    def _show_name(self):
        event = self._last_move
        if event is None or self.canvas is None or self._busy():
            self._hide_tip()
            return
        line = self.line_at(event)
        if line is None:
            self._hide_tip()
            return
        from PyQt5.QtGui import QCursor
        from PyQt5.QtWidgets import QToolTip
        QToolTip.showText(QCursor.pos(), str(line.get_label()), self.canvas)

    def _hide_tip(self):
        try:
            from PyQt5.QtWidgets import QToolTip
            QToolTip.hideText()
        except Exception:
            pass

    # ------------------------------------------------------------ clicks
    def legend_entry_at(self, event):
        """(axes, the entry's text) of a legend entry under the mouse, or None."""
        if self.canvas is None:
            return None
        try:
            renderer = self.canvas.get_renderer()
        except Exception:
            renderer = None
        for ax in self.canvas.figure.axes:
            leg = ax.get_legend()
            if leg is None or not leg.get_visible():
                continue
            texts = leg.get_texts()
            handles = list(getattr(leg, 'legend_handles', None)
                           or getattr(leg, 'legendHandles', []))
            for i, text in enumerate(texts):
                boxes = [text.get_window_extent(renderer)]
                if i < len(handles):
                    try:
                        boxes.append(handles[i].get_window_extent(renderer))
                    except Exception:
                        pass
                y0 = min(b.y0 for b in boxes) - 2
                y1 = max(b.y1 for b in boxes) + 2
                x0 = min(b.x0 for b in boxes) - 2
                x1 = max(b.x1 for b in boxes) + 2
                if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                    return ax, text.get_text()
        return None

    def _on_press(self, event):
        self._press = None
        self._end_drag()
        if event.button != 1 or getattr(event, 'dblclick', False):
            return
        if self._toolbar_busy():
            if self.legend_entry_at(event) is not None:
                self._say_busy()
            return
        entry = self.legend_entry_at(event)
        if entry is not None and self._cursor_on():
            self._say_busy()
            return
        if entry is not None:
            self._press = (event.x, event.y, entry)    # a click, unless the legend is dragged
            return
        if self._on_a_label(event) or self._on_a_legend(event):
            return                                     # the label / the legend is dragged
        ax = event.inaxes
        if ax is None or hasattr(ax, '_colorbar') or not ax.get_navigate():
            if self.marked is not None and not self._cursor_on():
                self.mark(None)                        # a click off the plot ends the marking
            return
        # a click (marks a line, on the release) or a drag (moves the plot)
        # (with the Cursor on: a click pins a cursor instead, a drag moves the plot)
        line = None if self._cursor_on() else self.line_at(event)
        self._drag = {'x': event.x, 'y': event.y, 'ax': ax, 'line': line,
                      'moving': False, 'cursor': self._cursor_on()}

    def _on_release(self, event):
        drag = self._drag
        if drag is not None and event.button == 1:
            self._end_drag()
            if not drag['moving'] and not drag['cursor']:   # a click: mark the line (or none)
                line = drag['line']
                self.mark(line)
                if line is not None:
                    self.show_in_list(str(line.get_label()))
            return
        press, self._press = self._press, None
        if press is None or event.button != 1:
            return
        x, y, (ax, label) = press
        if abs(event.x - x) > DRAG_PX or abs(event.y - y) > DRAG_PX:
            return                                     # the legend was moved
        self.toggle(label)

    # ------------------------------------------------------------ dragging the plot
    def _on_a_legend(self, event):
        """A press on a legend (its frame): a movable legend is dragged."""
        if self.canvas is None:
            return False
        for ax in self.canvas.figure.axes:
            leg = ax.get_legend()
            try:
                if leg is not None and leg.get_visible() and leg.contains(event)[0]:
                    return True
            except Exception:
                pass
        return False

    def _drag_to(self, event):
        """The mouse moved with the left button held: the plot follows it,
        as Pan of the toolbar (Axes.start_pan / drag_pan)."""
        drag = self._drag
        if self.canvas is None or event.x is None:
            return
        if not drag['moving']:
            if abs(event.x - drag['x']) <= DRAG_PX and abs(event.y - drag['y']) <= DRAG_PX:
                return                                 # not yet: maybe a click
            if self._toolbar_busy():
                self._drag = None
                return
            self._hide_tip()
            toolbar = getattr(self.canvas, 'toolbar', None)
            stack = getattr(toolbar, '_nav_stack', None)
            try:
                if toolbar is not None and stack is not None and stack() is None:
                    toolbar.push_current()             # Home: the view before the drag
            except Exception:
                pass
            drag['ax'].start_pan(drag['x'], drag['y'], 1)
            drag['moving'] = True
            try:
                from PyQt5.QtCore import Qt
                self.canvas.setCursor(Qt.ClosedHandCursor)
            except Exception:
                pass
        drag['ax'].drag_pan(1, None, event.x, event.y)
        self.canvas.draw_idle()

    def _end_drag(self):
        drag, self._drag = self._drag, None
        if drag is None or not drag['moving']:
            return
        try:
            drag['ax'].end_pan()
        except Exception:
            pass
        try:
            from PyQt5.QtCore import Qt
            self.canvas.setCursor(Qt.ArrowCursor)
        except Exception:
            pass
        toolbar = getattr(self.canvas, 'toolbar', None)
        try:
            if toolbar is not None:
                toolbar.push_current()                 # Back: before the drag
        except Exception:
            pass

    def _say_busy(self):
        """A click on the legend while a toolbar mode or the Cursor takes
        the clicks: the status bar says why nothing happens."""
        status = getattr(self.main, '_status', None)
        if not callable(status):
            return
        toolbar = getattr(self.canvas, 'toolbar', None)
        mode = str(getattr(getattr(toolbar, 'mode', ''), 'name', '') or '').lower()
        if mode in ('pan', 'zoom'):
            what = f"{mode.capitalize()} is on in the toolbar under the plot"
            end = f"click {mode.capitalize()} there again to turn it off"
        else:
            what = "The Cursor is on (Basic plot options)"
            end = "untick Cursor"
        status(f"{what}: a click on the legend does not hide a spectrum now - {end}.", 8000)

    # ------------------------------------------------------------ hide / show
    def toggle(self, name):
        """Hide the spectrum named `name` in the legend (or show it again).
        A legend entry that is not a spectrum does nothing."""
        label = self.full_label(name)
        if label is None:
            return
        if label in self.hidden:
            self.hidden.discard(label)
        else:
            self.hidden.add(label)
        status = getattr(self.main, '_status', None)
        if self._plot_type() in LEFT_OUT_IN:
            self.main.plot_spectra()           # computed again without it
            if callable(status):
                status(f"{name}: {'hidden' if label in self.hidden else 'shown again'} - "
                       "right-click > Show all spectra shows all again")
            return
        self._apply_hidden()
        self._peaks_again()
        if callable(status):
            status(f"{name}: {'hidden' if label in self.hidden else 'shown again'} - "
                   "a click on its name in the legend "
                   f"{'shows it again' if label in self.hidden else 'hides it'}")

    def show_all(self):
        """Right-click > Show all spectra."""
        if not self.hidden:
            return
        self.hidden = set()
        if self._plot_type() in LEFT_OUT_IN:
            self.main.plot_spectra()
        else:
            self._apply_hidden()
            self._peaks_again()

    def _peaks_again(self):
        """Peaks marked on the plot (Detect Peaks): marked again, so a hidden
        spectrum has no red dots and a shown one gets them back."""
        peaks = getattr(self.main, 'peak_detection_controller', None)
        detector = getattr(peaks, 'peak_detector', None)
        if detector is not None and getattr(detector, 'peak_lines', None):
            try:
                peaks.detect_peaks()
            except Exception:
                pass

    def reapply(self):
        """After the legend was made again (show legend, the Legend window):
        the hidden spectra's entries pale again."""
        if self.hidden:
            self._apply_hidden(draw=False)

    @contextmanager
    def hidden_left_out(self):
        """Copy plot to clipboard: meanwhile the hidden spectra are not in
        the legend either (not pale entries); afterwards as before."""
        names = self.hidden_names()
        manager = getattr(self.main, 'legend_manager', None)
        if self.canvas is None or not names or manager is None:
            yield
            return
        renamed, axes = [], []
        for ax in self.canvas.figure.axes:
            leg = ax.get_legend()
            if leg is None or not leg.get_visible():
                continue
            if not any(t.get_text() in names for t in leg.get_texts()):
                continue
            for line in self.data_lines(ax):
                if str(line.get_label()) in names:
                    renamed.append((line, line.get_label()))
                    line.set_label('_hidden_' + str(line.get_label()))
            axes.append(ax)
        try:
            for ax in axes:
                if self.data_lines(ax):
                    manager.apply_settings_to_legend(ax)
                else:                                  # every entry hidden
                    ax.get_legend().set_visible(False)
            yield
        finally:
            for line, label in renamed:
                line.set_label(label)
            for ax in axes:
                leg = ax.get_legend()
                if leg is not None and not leg.get_visible():
                    leg.set_visible(True)
                manager.apply_settings_to_legend(ax)
            self._apply_hidden()

    @classmethod
    def drop_hidden(cls, figure, names, legend_manager=None):
        """Open in New Window: the hidden spectra's lines invisible and not
        in the legend (nothing to click there)."""
        for ax in figure.axes:
            had_legend = ax.get_legend() is not None
            hit = False
            for line in cls.data_lines(ax):
                if str(line.get_label()) in names:
                    line.set_visible(False)
                    line.set_label('_hidden_' + str(line.get_label()))
                    hit = True
            if hit and had_legend and legend_manager is not None:
                if cls.data_lines(ax):
                    legend_manager.apply_settings_to_legend(ax)
                else:
                    ax.get_legend().set_visible(False)

    def _apply_hidden(self, draw=True):
        if self.canvas is None:
            return
        self.hide_in(self.canvas.figure, self.hidden_names())
        if draw:
            self.canvas.draw_idle()

    @classmethod
    def hide_in(cls, figure, names):
        """The lines named `names` invisible, their legend entries pale (the
        others visible) - the main plot and "Open in New Window"."""
        for ax in figure.axes:
            for line in cls.data_lines(ax):
                line.set_visible(str(line.get_label()) not in names)
            leg = ax.get_legend()
            if leg is None:
                continue
            handles = list(getattr(leg, 'legend_handles', None)
                           or getattr(leg, 'legendHandles', []))
            for i, text in enumerate(leg.get_texts()):
                alpha = PALE if text.get_text() in names else 1.0
                text.set_alpha(alpha)
                if i < len(handles):
                    try:
                        # a legend made again copies the invisible line's
                        # "invisible": its entry then had no line at all
                        handles[i].set_visible(True)
                        handles[i].set_alpha(alpha)
                    except Exception:
                        pass

    # ------------------------------------------------------------ the list
    def mark(self, line):
        """Draw `line` thicker (the one before back to its width; its row
        of the list no longer bold)."""
        if self.marked is not None:
            old, width = self.marked
            try:
                old.set_linewidth(width)
            except Exception:
                pass
            self.marked = None
        self._bold_row(None)
        if line is not None:
            self.marked = (line, line.get_linewidth())
            line.set_linewidth(max(2.5, line.get_linewidth() * 2.5))
        if self.canvas is not None:
            self.canvas.draw_idle()

    def _bold_row(self, item):
        """The marked spectrum's row in bold with a frame (None: the one
        before normal).
        The list's signals are blocked meanwhile: a changed font is an
        "item changed" for Qt, and the main window would draw the plot
        again (and end the marking at once)."""
        lw = getattr(self.main, 'spectra_list_widget', None)
        blocked = lw.blockSignals(True) if lw is not None else None
        try:
            old = getattr(self, '_bold_item', None)
            if old is not None:
                try:
                    font = old.font()
                    font.setBold(False)
                    old.setFont(font)
                except RuntimeError:               # the list was filled again
                    pass
            self._bold_item = item
            if item is not None:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
        finally:
            if lw is not None:
                lw.blockSignals(blocked)
        if lw is not None:
            # and a frame in a contrasting colour (_SpectraListWidget.paintEvent):
            # yellow on a red (selected) row, dark blue on a white one
            lw.marked_item = item
            lw.viewport().update()

    def show_in_list(self, label):
        """The spectrum's row of the list: current (a frame) and scrolled
        into view - the selection is not changed."""
        lw = getattr(self.main, 'spectra_list_widget', None)
        if lw is None:
            return False
        item = None
        for i in range(lw.count()):
            text = lw.item(i).text()
            if text == label or text.endswith(' : ' + label):
                item = lw.item(i)
                break
        if item is None:
            return False
        from PyQt5.QtCore import QItemSelectionModel
        lw.selectionModel().setCurrentIndex(lw.indexFromItem(item),
                                            QItemSelectionModel.NoUpdate)
        lw.scrollToItem(item)
        self._bold_row(item)                       # easy to see, also in a red (selected) row
        status = getattr(self.main, '_status', None)
        if callable(status):
            status(f"{item.text()} - row {lw.row(item) + 1} of the list")
        return True
