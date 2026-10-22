# src/views/dialogs/misc/whats_new_dialog.py
"""The small window shown when a new version starts: the "in brief" list
of resources/whats_new/<version>.md, a button for the full list (Help ->
What's New) and "Don't show this again" (for this version; the next version
shows its own list again). Below it the "in brief" lists of all earlier
versions, newest first (e.g. 1.6.0, 1.5.0 under 1.7.0), the same for
everyone."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton,
                             QTextBrowser, QVBoxLayout)

from src.help import whats_new_help

_STYLE = """
<style>
  body { font-family: Arial, sans-serif; line-height: 1.45; }
  li   { margin-bottom: 6px; }
  a    { color: #1976D2; }
</style>
"""


class WhatsNewDialog(QDialog):

    def __init__(self, parent, version):
        super().__init__(parent)
        self.version = version
        self.earlier = whats_new_help.earlier_versions(version)
        self.setWindowTitle(f"What's new in SpecAnalytiXBase {version}")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.resize(720, 560)
        layout = QVBoxLayout(self)
        title = QLabel(f"<h2 style='color:#2E7D32; margin:0'>What's new in {version}</h2>")
        layout.addWidget(title)
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        self.text.anchorClicked.connect(self._open_link)
        md = whats_new_help.brief_markdown(version)
        for earlier in self.earlier:          # all earlier versions, newest first
            brief = whats_new_help.brief_markdown(earlier)
            if brief:
                md += f"\n### Earlier: what was new in {earlier}\n\n" + brief
        self.text.setHtml(_STYLE + whats_new_help.markdown_to_html(md))
        layout.addWidget(self.text, 1)
        self.dont_show = QCheckBox("Don't show this again")
        self.dont_show.setToolTip("At the start of the program, for this version. Untick it here "
                                  "(Help \u203a What's New) to see this window at every start again;\n"
                                  "the next version shows what is new in it in any case.")
        row = QHBoxLayout()
        row.addWidget(self.dont_show)
        row.addStretch(1)
        self.all_button = QPushButton("Show all changes…")
        self.all_button.setToolTip("Help › What's New: the full list")
        self.all_button.clicked.connect(lambda: self._open_help('whats_new', None))
        self.close_button = QPushButton("Close")
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)
        row.addWidget(self.all_button)
        row.addWidget(self.close_button)
        layout.addLayout(row)

    def _open_help(self, key, anchor):
        from src.help.help_window import open_help_topic
        open_help_topic(self, key, anchor)

    def _open_link(self, url):
        text = url.toString()
        if text.startswith('help://'):
            key, _, anchor = text[len('help://'):].partition('#')
            self._open_help(key, anchor or None)
        elif text.startswith('#'):
            self._open_help('whats_new', text[1:])
