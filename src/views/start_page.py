# src/views/start_page.py
"""The start page: shown over the empty plot while no spectra are loaded,
so that a new user sees at once what to do - Import data, Open snapshot,
the files used recently, a test dataset to try, the Quick start - and that
files can simply be dropped onto the window. It disappears as soon as
spectra are loaded and comes back when all are deleted."""

import os

from PyQt5.QtCore import QEvent, QObject, Qt
from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                             QVBoxLayout, QWidget)

RECENT_SHOWN = 5


class StartPage(QFrame):
    """Over `host` (the plot area): big buttons, the recent files, a hint.
    `actions`: {'import', 'snapshot', 'quick_start'} -> QAction to trigger;
    `test_menu`: the menu of the test datasets; `recent`: a callable giving
    the recent entries ({'path', 'kind'}); `open_recent(entry)`."""

    def __init__(self, host, actions, test_menu=None, recent=None, open_recent=None):
        super().__init__(host)
        self.setObjectName('start_page')
        self.host = host
        self._actions = actions
        self._test_menu = test_menu
        self._recent = recent or (lambda: [])
        self._open_recent = open_recent
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            "#start_page { background: palette(base); }"
            "QPushButton#start_big { font-size: 11pt; padding: 10px 16px; text-align: left; }"
            "QPushButton#start_recent { border: none; background: transparent; color: #1565C0;"
            "  text-align: left; padding: 2px 4px; }"
            "#start_column { background: transparent; }"
            "QPushButton#start_recent:hover { text-decoration: underline; }")
        outer = QVBoxLayout(self)
        outer.addStretch(2)
        middle = QHBoxLayout()
        middle.addStretch(1)
        column = QVBoxLayout()
        column.setSpacing(8)
        title = QLabel("Start")
        title.setStyleSheet("font-size: 18pt; font-weight: bold;")
        column.addWidget(title)
        sub = QLabel("No spectra loaded yet. Begin with one of these:")
        sub.setStyleSheet("font-size: 10.5pt;")
        column.addWidget(sub)
        column.addSpacing(6)
        from src.views import icons
        self.buttons = {}
        for key, text, tip, icon in (
                ('import', "Import data…",
                 "Import data: your measured spectra (text, Excel, JASCO, SPC, ...)\n"
                 "- the same as File › Import data › New… (Ctrl+I).",
                 icons.standard('SP_DialogOpenButton', self)),
                ('snapshot', "Open snapshot…",
                 "Open snapshot: work saved earlier with Save (spectra, history,\n"
                 "settings) - the same as File › Open snapshot… (Ctrl+O).",
                 icons.standard('SP_DirOpenIcon', self)),
                ('test', "Try a test dataset ▾",
                 "Try a test dataset: spectra that come with the program (synthetic\n"
                 "series and measured data) - to try every tool without own data.\n"
                 "The same as Help › Test datasets.",
                 icons.standard('SP_FileDialogContentsView', self)),
                ('quick_start', "Quick start",
                 "Quick start: a one-page introduction to the program\n"
                 "(the same as Help › Quick start).",
                 icons.standard('SP_MessageBoxQuestion', self))):
            b = QPushButton(text)
            b.setObjectName('start_big')
            b.setIcon(icon)
            b.setToolTip(tip)
            b.setAutoDefault(False)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _c=False, k=key: self._clicked(k))
            column.addWidget(b)
            self.buttons[key] = b
        column.addSpacing(10)
        self.recent_title = QLabel("Open recent:")
        self.recent_title.setStyleSheet("font-weight: bold;")
        column.addWidget(self.recent_title)
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(0)
        column.addLayout(self.recent_box)
        column.addSpacing(10)
        hint = QLabel("Or drag files from File Explorer and drop them onto this window.")
        hint.setStyleSheet("color: #666;")
        column.addWidget(hint)
        holder = QWidget()
        holder.setObjectName('start_column')
        holder.setLayout(column)
        holder.setMinimumWidth(320)
        holder.setMaximumWidth(460)
        middle.addWidget(holder)
        middle.addStretch(1)
        outer.addLayout(middle)
        outer.addStretch(3)
        self.recent_buttons = []
        host.installEventFilter(self)
        self._fit()

    # ------------------------------------------------------------------
    def _clicked(self, key):
        if key == 'test':
            if self._test_menu is not None:
                b = self.buttons['test']
                self._test_menu.popup(b.mapToGlobal(b.rect().bottomLeft()))
            return
        action = self._actions.get(key)
        if action is not None:
            action.trigger()

    def refresh_recent(self):
        """The recent files, at most RECENT_SHOWN, newest first."""
        for b in self.recent_buttons:
            self.recent_box.removeWidget(b)
            b.deleteLater()
        self.recent_buttons = []
        try:
            entries = list(self._recent() or [])[:RECENT_SHOWN]
        except Exception:
            entries = []
        for entry in entries:
            path = entry.get('path', '')
            name = os.path.basename(path)
            folder = os.path.basename(os.path.dirname(path))
            if entry.get('kind') == 'snapshot':
                name += "   (snapshot)"
            if folder:
                name += f"   \u2013 in {folder}"     # two files of the same name told apart
            b = QPushButton(name)
            b.setObjectName('start_recent')
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(entry.get('path', ''))
            b.setAutoDefault(False)
            b.clicked.connect(lambda _c=False, e=entry: self._open_recent and self._open_recent(e))
            self.recent_box.addWidget(b)
            self.recent_buttons.append(b)
        self.recent_title.setVisible(bool(entries))

    def show_if(self, empty):
        """Shown while no spectra are loaded."""
        if empty:
            self.refresh_recent()
            self._fit()
            self.show()
            self.raise_()
        else:
            self.hide()

    def _fit(self):
        self.setGeometry(self.host.rect())

    def eventFilter(self, obj, event):
        if obj is self.host and event.type() in (QEvent.Resize, QEvent.Show):
            self._fit()
        return False
