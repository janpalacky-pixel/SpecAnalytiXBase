# src/views/dialogs/misc/settings_dialog.py
"""File -> Settings and saved items...: every setting SpecAnalytiXBase remembers
on this computer -- changed directly in the table, or reset (selected / all) --,
the saved items the user built up (deleted only on purpose, never by a reset),
and the folders where they are stored. See src/modules/misc/user_settings.py."""

import os

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QBrush, QColor, QDesktopServices, QFont
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                             QDialogButtonBox, QDoubleSpinBox, QGridLayout, QGroupBox,
                             QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem,
                             QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                             QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from src.modules.misc import user_settings as us
from src.modules.misc.session_files import Preferences

_OTHER_TIP = ("Values stored by another version of SpecAnalytiXBase on this computer: left over "
              "from an earlier version, or written by a newer one if you also use a newer version "
              "(all versions share the same settings). This version does not use them. Resetting "
              "removes them; a newer version would then use its default for them.")
_OTHER_GROUP = 'Not used by this version of the program'
_GROUP_BG = '#E3F2FD'


def _help_button(tooltip):
    """The small orange '?' of the program's context help."""
    btn = QPushButton('?')
    btn.setFixedSize(24, 24)
    btn.setAutoDefault(False)
    btn.setToolTip(tooltip)
    btn.setStyleSheet(
        'QPushButton { background-color:#F57C00; color:white; font-weight:bold; border:none; '
        'border-radius:4px; }'
        'QPushButton:hover { background-color:#E65100; }'
        'QPushButton:pressed { background-color:#BF360C; }')
    return btn


def _wrap(text, width=70):
    words, lines, line = text.split(), [], ''
    for w in words:
        if line and len(line) + 1 + len(w) > width:
            lines.append(line)
            line = w
        else:
            line = f'{line} {w}'.strip()
    return '\n'.join(lines + [line])


class _PickDialog(QDialog):
    """Choose which saved items of one kind to delete."""

    def __init__(self, parent, kind, names):
        super().__init__(parent)
        self.setWindowTitle(f"Delete – {kind.label.split(' (')[0]}")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.resize(520, 400)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Tick what should be deleted:"))
        self.list = QListWidget()
        for n in names:
            item = QListWidgetItem(n)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.list.addItem(item)
        layout.addWidget(self.list, 1)
        row = QHBoxLayout()
        all_btn = QPushButton("Select all")
        all_btn.clicked.connect(lambda: self._set_all(Qt.Checked))
        none_btn = QPushButton("Select none")
        none_btn.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        row.addWidget(all_btn)
        row.addWidget(none_btn)
        row.addStretch(1)
        layout.addLayout(row)
        buttons = QDialogButtonBox()
        self.delete_button = buttons.addButton("Delete selected", QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_all(self, state):
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(state)

    def chosen(self):
        return [self.list.item(i).text() for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]


class _SettingsHelp(QDialog):
    """What every setting means: the table of the User Guide (section
    Settings and Saved Items) in a small window. 'More…' opens the help page
    of that setting."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Settings – what each setting means")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.resize(760, 620)
        layout = QVBoxLayout(self)
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        self.text.anchorClicked.connect(self.open_link)
        table = us.help_table_html().replace(
            '<table>', '<table border="1" cellspacing="0" cellpadding="5" width="100%">', 1).replace(
            '<th>Setting</th><th>What it does</th><th>Default</th>',
            '<th width="27%">Setting</th><th width="55%">What it does</th>'
            '<th width="18%">Default</th>', 1)
        self.text.setHtml(
            '<p>What each setting does and its default value. The same text appears when you '
            'hold the mouse over a row. <i>More&hellip;</i> opens the help page about it.</p>'
            + table)
        layout.addWidget(self.text)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.close)
        layout.addWidget(close)

    def open_link(self, url):
        link = url.toString()
        if not link.startswith('help://'):
            QDesktopServices.openUrl(url)
            return
        key, _, anchor = link[len('help://'):].partition('#')
        from src.help import help_window
        help_window.open_help_topic(self, key, anchor or None)


class SettingsDialog(QDialog):

    def __init__(self, parent=None, main_controller=None, preferences=None, autosave_manager=None):
        super().__init__(parent)
        self.main = main_controller
        self.prefs = preferences or Preferences()
        self.kinds = us.saved_kinds(autosave_manager)
        self.setWindowTitle("Settings and saved items")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        screen = parent.screen() if parent is not None and hasattr(parent, 'screen') else None
        avail = screen.availableGeometry() if screen is not None else None
        self.resize(min(1050, avail.width() - 40) if avail else 1050,
                    min(720, avail.height() - 60) if avail else 720)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        intro = QLabel(
            "What SpecAnalytiXBase remembers on this computer between sessions. Every copy of the "
            "program (installed or run from source) uses the same settings and saved items; "
            "installing, updating or uninstalling the program does not change them.")
        intro.setWordWrap(True)
        top.addWidget(intro, 1)
        self.help_button = _help_button("What each setting means")
        self.help_button.clicked.connect(self.show_help)
        top.addWidget(self.help_button, 0, Qt.AlignTop)
        layout.addLayout(top)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabBar::tab { min-width: 170px; padding: 6px 14px; }")
        layout.addWidget(self.tabs, 1)

        # --- settings
        page = QWidget()
        b = QVBoxLayout(page)
        hint = QLabel("Change a value directly in the table, or tick rows and reset them to the "
                      "default. Values that differ from the default are shown in bold; point at a "
                      "setting to see what it does. Click a heading to open or close its group. "
                      "Your saved items (the other tab) are never touched by a reset.")
        hint.setWordWrap(True)
        b.addWidget(hint)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "Setting", "Value", "Default"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(2, 230)
        self.table.cellClicked.connect(self._cell_clicked)
        self.table.itemChanged.connect(self._item_changed)
        b.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.changed_label = QLabel("")
        row.addWidget(self.changed_label)
        row.addStretch(1)
        self.expand_button = QPushButton("Open all groups")
        self.expand_button.clicked.connect(lambda: self.set_all_collapsed(False))
        self.collapse_button = QPushButton("Close all groups")
        self.collapse_button.clicked.connect(lambda: self.set_all_collapsed(True))
        self.reset_selected_button = QPushButton("Reset selected…")
        self.reset_selected_button.clicked.connect(self.reset_selected)
        self.reset_all_button = QPushButton("Reset all settings…")
        self.reset_all_button.clicked.connect(self.reset_all)
        for w in (self.expand_button, self.collapse_button, self.reset_selected_button,
                  self.reset_all_button):
            row.addWidget(w)
        b.addLayout(row)
        self.tabs.addTab(page, "Settings")

        # --- saved items
        page2 = QWidget()
        p2 = QVBoxLayout(page2)
        intro2 = QLabel("What you saved yourself. It is kept when the program is installed, updated "
                        "or uninstalled, and a reset of the settings never touches it. Delete "
                        "items only on purpose — this cannot be undone.")
        intro2.setWordWrap(True)
        p2.addWidget(intro2)
        box2 = QGroupBox("Your saved items")
        g = QGridLayout(box2)
        self.count_labels, self.delete_buttons = {}, {}
        for r, kind in enumerate(self.kinds):
            name = QLabel(kind.label)
            if kind.note:
                name.setToolTip(kind.note)
            g.addWidget(name, r, 0)
            count = QLabel("")
            g.addWidget(count, r, 1)
            btn = QPushButton("Clear…" if kind.id == 'recent' else "Delete…")
            btn.clicked.connect(lambda _c=False, k=kind: self.delete_items(k))
            g.addWidget(btn, r, 2)
            self.count_labels[kind.id], self.delete_buttons[kind.id] = count, btn
        g.setColumnStretch(0, 1)
        p2.addWidget(box2)
        box3 = QGroupBox("Where they are stored — e.g. to back them up or copy them to another computer")
        f = QGridLayout(box3)
        self.folder_buttons = []
        for r, (what, path) in enumerate(us.folders()):
            label = QLabel(f"{what}:<br><code>{path}</code>")
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            f.addWidget(label, r, 0)
            btn = QPushButton("Open folder")
            btn.clicked.connect(lambda _c=False, p=path: self.open_folder(p))
            f.addWidget(btn, r, 1)
            self.folder_buttons.append((path, btn))
        f.setColumnStretch(0, 1)
        p2.addWidget(box3)
        p2.addStretch(1)
        self.tabs.addTab(page2, "Your saved items")

        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self.editors = {}
        self.help_window = None
        self._collapsed = None              # first build: groups with changes open
        self._building = False
        self.build_table()
        self.refresh()

    # ------------------------------------------------------------- help
    def show_help(self):
        """The '?': a window with what every setting means (the same texts as
        the tooltips), each with a link to its help page."""
        if self.help_window is None:
            self.help_window = _SettingsHelp(self)
        self.help_window.show()
        self.help_window.raise_()
        self.help_window.activateWindow()

    # ------------------------------------------------------------- the table
    def rows(self):
        """[(id, setting name, value text, default text, changed)] of every row
        that can be reset (other stored values with the id 'other:<key>')."""
        out = [(st.id, st.label, st.current_text(self.prefs), st.default_text,
                st.changed(self.prefs)) for st in us.SETTINGS]
        stored = self.prefs.all()
        for key in us.other_keys(self.prefs):
            out.append(('other:' + key, key, str(stored.get(key))[:80], '—', True))
        return out

    def _plain(self, text, tip=''):
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled)
        if tip:
            item.setToolTip(tip)
        return item

    def _check_item(self, rid):
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        check.setCheckState(Qt.Unchecked)
        check.setData(Qt.UserRole, rid)
        return check

    def _editor(self, st, tip):
        o = st.options or {}
        if st.kind == 'choice':
            w = QComboBox()
            for value, text in st.options:
                w.addItem(text, value)
            w.currentIndexChanged.connect(lambda _i, st=st, w=w: self._edited(st, w.currentData()))
        elif st.kind == 'bool':
            w = QCheckBox()
            w.toggled.connect(lambda on, st=st: self._edited(st, bool(on)))
        elif st.kind == 'int':
            w = QSpinBox()
            w.setRange(int(o['minimum']), int(o['maximum']))
            w.setSingleStep(int(o.get('step', 1)))
            w.setSuffix(o.get('suffix', ''))
            w.setKeyboardTracking(False)          # store when typing is finished
            w.valueChanged.connect(lambda v, st=st: self._edited(st, int(v)))
        else:
            w = QDoubleSpinBox()
            w.setDecimals(int(o.get('decimals', 2)))
            w.setRange(float(o['minimum']), float(o['maximum']))
            w.setSingleStep(float(o.get('step', 0.1)))
            w.setSuffix(o.get('suffix', ''))
            w.setKeyboardTracking(False)
            w.valueChanged.connect(lambda v, st=st: self._edited(st, float(v)))
        w.setToolTip(tip)
        return w

    def _tip(self, st):
        text, _link = us.HELP.get(st.id, ('', ''))
        note = f" ({st.note})" if st.note else ''
        return _wrap(text) + f"\n\nDefault: {st.default_text}{note}"

    def build_table(self):
        """Groups of several settings get a heading row that opens / closes
        them (with a box that ticks all of them); a group of one setting is
        one row. At the end the values this version does not use."""
        self._building = True
        self.table.clearContents()
        self.table.clearSpans()
        self.editors, self._row_of, self._groups = {}, {}, {}
        plan = []
        for title, settings in us.groups():
            if len(settings) > 1:
                plan.append(('group', title))
            plan.extend(('setting', st, title if len(settings) > 1 else None) for st in settings)
        others = us.other_keys(self.prefs)
        if others:
            plan.append(('group', _OTHER_GROUP))
            plan.extend(('other', k, _OTHER_GROUP) for k in others)
        if self._collapsed is None:                  # first time: open where something changed
            changed = {st.group for st in us.SETTINGS if st.changed(self.prefs)}
            self._collapsed = {t for t, s in us.groups() if len(s) > 1 and t not in changed}
        self.table.setRowCount(len(plan))
        stored = self.prefs.all()
        bg = QBrush(QColor(_GROUP_BG))
        for r, entry in enumerate(plan):
            if entry[0] == 'group':
                title = entry[1]
                self._groups[title] = {'row': r, 'rows': []}
                check = self._check_item('group:' + title)
                check.setBackground(bg)
                self.table.setItem(r, 0, check)
                head = self._plain('')
                head.setBackground(bg)
                f = QFont(self.table.font())
                f.setBold(True)
                head.setFont(f)
                head.setToolTip(_OTHER_TIP if title == _OTHER_GROUP else
                                "Click to open or close this group")
                self.table.setItem(r, 1, head)
                self.table.setSpan(r, 1, 1, 3)
                continue
            if entry[0] == 'setting':
                st, group = entry[1], entry[2]
                tip = self._tip(st)
                self.table.setItem(r, 0, self._check_item(st.id))
                self.table.setItem(r, 1, self._plain(st.label + (f" ({st.note})" if st.note else ''), tip))
                editor = self._editor(st, tip)
                self.editors[st.id] = editor
                self.table.setCellWidget(r, 2, editor)
                self.table.setItem(r, 3, self._plain(st.default_text, tip))
                self._row_of[st.id] = r
            else:
                key, group = entry[1], entry[2]
                self.table.setItem(r, 0, self._check_item('other:' + key))
                for c, text in ((1, key), (2, str(stored.get(key))[:80]), (3, '—')):
                    self.table.setItem(r, c, self._plain(text, _wrap(_OTHER_TIP)))
                self._row_of['other:' + key] = r
            if group is not None:
                self._groups[group]['rows'].append(r)
        height = max(QComboBox().sizeHint().height(), QSpinBox().sizeHint().height()) + 8
        vh = self.table.verticalHeader()
        vh.setSectionResizeMode(QHeaderView.Fixed)
        vh.setDefaultSectionSize(height)
        for r in range(self.table.rowCount()):
            self.table.setRowHeight(r, height)
        self._building = False
        self._apply_collapsed()

    def _apply_collapsed(self):
        for title, g in self._groups.items():
            closed = title in self._collapsed
            for r in g['rows']:
                self.table.setRowHidden(r, closed)
        self._update_headings()

    def _update_headings(self):
        for title, g in self._groups.items():
            ids = [self.table.item(r, 0).data(Qt.UserRole) for r in g['rows']]
            n_changed = sum(1 for i in ids if i.startswith('other:')) if title == _OTHER_GROUP else \
                sum(1 for st in us.SETTINGS if st.id in ids and st.changed(self.prefs))
            arrow = '▸' if title in self._collapsed else '▾'
            extra = f"   ({n_changed} of {len(ids)} changed)" if n_changed and title != _OTHER_GROUP else ''
            if title == _OTHER_GROUP:
                extra = "   — stored by another version on this computer"
            self.table.item(g['row'], 1).setText(f"{arrow}  {title}{extra}")

    def is_collapsed(self, title):
        return title in self._collapsed

    def toggle_group(self, title):
        self._collapsed ^= {title}
        self._apply_collapsed()

    def set_all_collapsed(self, closed):
        self._collapsed = set(self._groups) if closed else set()
        self._apply_collapsed()

    def _cell_clicked(self, r, c):
        if c == 0:
            return
        for title, g in self._groups.items():
            if g['row'] == r:
                self.toggle_group(title)
                return

    def _item_changed(self, item):
        """The box of a heading ticks or unticks the whole group."""
        if self._building or item.column() != 0:
            return
        rid = item.data(Qt.UserRole) or ''
        if rid.startswith('group:'):
            g = self._groups.get(rid[len('group:'):])
            if g:
                self._building = True
                for r in g['rows']:
                    self.table.item(r, 0).setCheckState(item.checkState())
                self._building = False

    def _show_value(self, st):
        w = self.editors[st.id]
        v = st.value(self.prefs)
        w.blockSignals(True)
        if st.kind == 'choice':
            i = w.findData(v)
            w.setCurrentIndex(i if i >= 0 else 0)
        elif st.kind == 'bool':
            w.setChecked(bool(v))
        else:
            w.setValue(v)
        w.blockSignals(False)
        bold = st.changed(self.prefs)
        f = QFont(w.font())
        f.setBold(bold)
        w.setFont(f)
        label = self.table.item(self._row_of[st.id], 1)
        f2 = QFont(self.table.font())
        f2.setBold(bold)
        label.setFont(f2)

    def refresh(self):
        if set(us.other_keys(self.prefs)) != {k[len('other:'):] for k in self._row_of
                                               if k.startswith('other:')}:
            self.build_table()
        for st in us.SETTINGS:
            self._show_value(st)
        self._update_headings()
        n = sum(1 for row in self.rows() if row[4])
        self.changed_label.setText("All settings are at their defaults." if not n else
                                   f"{n} setting{'s' if n != 1 else ''} differ{'s' if n == 1 else ''} "
                                   "from the default.")
        self.reset_all_button.setEnabled(bool(n))
        for kind in self.kinds:
            k = len(kind.names())
            self.count_labels[kind.id].setText(f"{k}")
            self.delete_buttons[kind.id].setEnabled(bool(k))

    def _edited(self, st, value):
        """A value changed in the table: store it; the open program follows."""
        before = st.value(self.prefs)
        st.set(self.prefs, value)
        if st.value(self.prefs) != before and self.main is not None \
                and hasattr(self.main, 'settings_changed'):
            self.main.settings_changed(us.effects([st.id]))
        self.refresh()

    def ticked(self):
        out = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            rid = item.data(Qt.UserRole) if item is not None else None
            if rid and not rid.startswith('group:') and item.checkState() == Qt.Checked:
                out.append(rid)
        return out

    # ------------------------------------------------------------- resetting
    def _confirm(self, title, names):
        listed = '\n'.join(f"• {n}" for n in names)
        return QMessageBox.question(
            self, title, f"Reset to the default:\n\n{listed}\n\nYour saved items are not changed.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

    def _names(self, ids):
        by_id = {st.id: st for st in us.SETTINGS}
        out = []
        for i in ids:
            if i in by_id:
                st = by_id[i]
                out.append(st.label if st.label == st.group else
                           f"{st.group.split(' (')[0]}: {st.label}")
            else:
                out.append(f"{i[len('other:'):]} (not used by this version)")
        return out

    def reset_selected(self):
        ids = self.ticked()
        if not ids:
            QMessageBox.information(self, "Reset selected", "Tick the settings to reset first.")
            return []
        if not self._confirm("Reset selected settings", self._names(ids)):
            return []
        return self._reset([i for i in ids if not i.startswith('other:')],
                           [i[len('other:'):] for i in ids if i.startswith('other:')])

    def reset_all(self):
        ids = [r[0] for r in self.rows() if r[4]]
        if not ids or not self._confirm("Reset all settings", self._names(ids)):
            return []
        return self._reset(None, ())

    def _reset(self, settings, other):
        done = us.reset(self.prefs, settings, other)
        if self.main is not None and hasattr(self.main, 'settings_changed'):
            self.main.settings_changed(us.effects(done))
        for r in range(self.table.rowCount()):           # untick everything
            item = self.table.item(r, 0)
            if item is not None:
                item.setCheckState(Qt.Unchecked)
        self.refresh()
        return done

    # ------------------------------------------------------------- saved items
    def delete_items(self, kind):
        names = kind.names()
        if not names:
            return []
        if kind.id == 'recent':
            if QMessageBox.question(self, "Clear Open recent",
                                    f"Remove all {len(names)} files from the Open recent list?\n"
                                    "(Only the list is cleared; the files themselves stay.)",
                                    QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) != QMessageBox.Yes:
                return []
            chosen = names
        else:
            pick = _PickDialog(self, kind, names)
            if pick.exec_() != QDialog.Accepted:
                return []
            chosen = pick.chosen()
            if not chosen or QMessageBox.question(
                    self, "Delete", f"Delete {len(chosen)} of the {kind.label.split(' (')[0].lower()}?\n"
                    "This cannot be undone.",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return []
        kind.delete(chosen)
        self.refresh()
        return chosen

    def open_folder(self, path):
        os.makedirs(path, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
