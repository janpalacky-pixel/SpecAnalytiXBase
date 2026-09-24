
# src/views/dialogs/misc/spectra_selection_dialog.py
import re

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QSpinBox, QVBoxLayout, QHBoxLayout,
                           QLabel, QDialogButtonBox, QPushButton, QRadioButton,
                           QButtonGroup, QStackedWidget, QWidget, QLineEdit,
                           QCheckBox, QListWidget, QListWidgetItem, QMessageBox,
                           QAbstractItemView)


# ── Pure logic helpers — no Qt widgets involved, so these are unit-testable
#    without a running QApplication (see tests/test_spectra_selection_dialog.py) ──

def derive_root_name(label: str) -> str:
    """Best-effort "root name" for one spectrum label, stripping whatever
    looks like the varying per-spectrum suffix so that spectra belonging
    to the same series/map/dataset collapse onto the same root:

        "Chlorella [r23_c24]"          -> "Chlorella"
        "Raman_DNA_conc_dep : sp001"   -> "Raman_DNA_conc_dep"
        "sample_012"                   -> "sample"
        "spectrum-3"                   -> "spectrum"
        "plain_unique_name"            -> "plain_unique_name"  (unchanged)

    This is a heuristic over label-naming conventions already used
    elsewhere in the app (WITec MAT map import's "[rNN_cNN]" suffix,
    multi-spectrum file readers' "<file> : <sub-id>" suffix, and generic
    "<name><sep><number>" sequential naming) — not a guarantee every
    dataset's convention is recognized. A label that doesn't match any
    of these is its own root, so it still shows up (as a singleton group)
    rather than being silently dropped.
    """
    s = label.strip()

    # 1) Trailing bracketed group: "<root> [anything]" -> "<root>"
    stripped = re.sub(r'\s*\[[^\[\]]*\]\s*$', '', s)
    if stripped != s:
        return stripped.strip()

    # 2) Trailing " : <id>" segment, where <id> is an optional short
    #    alphabetic prefix followed by digits (e.g. "sp001", "3", "id42")
    m = re.match(r'^(.*\S)\s*:\s*[A-Za-z]*\d+\s*$', s)
    if m:
        return m.group(1).strip()

    # 3) Trailing "<sep><id>" where <sep> is a space/underscore/dash/hash
    #    and <id> is the same optional-prefix + digits shape as above
    #    (e.g. "sample_012", "spectrum-3", "run#7")
    m = re.match(r'^(.*\S)[\s_\-#]+[A-Za-z]*\d+\s*$', s)
    if m:
        return m.group(1).strip()

    # 4) Nothing recognizable to strip — the label is its own root
    return s


def group_by_root_name(labels):
    """Group label indices by derive_root_name(label).

    Returns an ordered dict-like list of (root, [indices]) tuples, sorted
    by group size (largest first) then alphabetically, so the most useful
    groupings surface at the top.
    """
    groups = {}
    order = []
    for idx, label in enumerate(labels):
        root = derive_root_name(label)
        if root not in groups:
            groups[root] = []
            order.append(root)
        groups[root].append(idx)
    order.sort(key=lambda r: (-len(groups[r]), r.lower()))
    return [(root, groups[root]) for root in order]


def compute_text_search_indices(labels, pattern, use_regex=False, case_sensitive=False):
    """Indices of labels matching `pattern`, as a plain substring or as a
    regular expression (re.search — matches anywhere in the label, not
    anchored). Raises re.error if use_regex and the pattern is invalid —
    callers should catch this and surface it to the user rather than
    silently returning no matches.
    """
    if not pattern:
        return []
    if use_regex:
        flags = 0 if case_sensitive else re.IGNORECASE
        compiled = re.compile(pattern, flags)
        return [i for i, lbl in enumerate(labels) if compiled.search(lbl)]
    needle = pattern if case_sensitive else pattern.lower()
    return [
        i for i, lbl in enumerate(labels)
        if needle in (lbl if case_sensitive else lbl.lower())
    ]


class SpectraSelectionDialog(QDialog):
    """
    A reusable dialog for selecting spectra, in three ways:

      * Index range  — start/end/step over the spectrum list's own order
        (the original functionality of this dialog).
      * Text search   — a substring or regular-expression match against
        every spectrum's label.
      * Common root name — spectra are grouped by a shared "root" (e.g.
        every pixel of one imported 2-D map, or every sub-spectrum of one
        multi-spectrum file); pick one or more groups to select all of
        their members at once.

    Can be used for both spectrum selector and rename operations. Callers
    must now pass `labels` (the actual spectrum labels, in list order) —
    it's required for the text-search and root-name modes, and is also
    used as the authoritative spectrum count for range mode.
    """

    def __init__(self, parent=None, total_spectra=0, title="Select Spectra", labels=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.labels = list(labels) if labels else []
        # total_spectra is kept as an explicit fallback for any caller that
        # doesn't (yet) pass labels — range mode still works from a bare
        # count, it just can't offer the text-search/root-name modes
        # without labels to match against.
        self.total_spectra = len(self.labels) if self.labels else total_spectra
        self.selection_result = {
            'indices': [],
            'action': None,  # Will be set based on which button is clicked
        }

        self.init_ui()

    # ------------------------------------------------------------------ #
    # UI construction                                                     #
    # ------------------------------------------------------------------ #

    def init_ui(self):
        """Initialize the dialog UI."""
        layout = QVBoxLayout()

        # ── Mode selector row, with a single context-help button covering
        #    all three modes (same small orange "?" convention used
        #    throughout the rest of the app, e.g. the 2-D Map dialog's
        #    section-header info buttons) ──
        mode_row = QHBoxLayout()
        self._radio_range = QRadioButton("Index range")
        self._radio_search = QRadioButton("Text search")
        self._radio_root = QRadioButton("Common root name")
        self._radio_range.setChecked(True)
        self._mode_group = QButtonGroup(self)
        for btn in (self._radio_range, self._radio_search, self._radio_root):
            self._mode_group.addButton(btn)
            mode_row.addWidget(btn)
        mode_row.addStretch()
        mode_row.addWidget(self._make_info_button(
            "About Select Spectra",
            "Three ways to pick which spectra the Select / Add to Selection /\n"
            "Remove from Selection buttons below act on:\n\n"
            "Index range — start/end/step over the spectrum list's own order,\n"
            "1-based and inclusive (e.g. 1-10 step 2 selects spectra 1, 3, 5,\n"
            "7, 9).\n\n"
            "Text search — matches every spectrum's label against a plain\n"
            "substring, or (with 'Regular expression' checked) a full regex\n"
            "searched anywhere in the label. Case-insensitive unless 'Case\n"
            "sensitive' is checked.\n\n"
            "Common root name — groups spectra that look like they belong to\n"
            "the same series (e.g. every pixel of one imported 2-D map, or\n"
            "every sub-spectrum of one multi-spectrum file) by stripping the\n"
            "varying part of the label — a trailing [bracketed] tag, a\n"
            "': id' suffix, or a trailing '_number'/'-number' — and shows\n"
            "each detected group with its spectrum count. Tick one or more\n"
            "groups to select every spectrum in them at once. A label that\n"
            "doesn't match any of those conventions still shows up as its\n"
            "own one-spectrum group, rather than being left out."))
        layout.addLayout(mode_row)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_range_panel())
        self._stack.addWidget(self._build_search_panel())
        self._stack.addWidget(self._build_root_panel())
        layout.addWidget(self._stack)

        self._radio_range.toggled.connect(
            lambda checked: checked and self._stack.setCurrentIndex(0))
        self._radio_search.toggled.connect(
            lambda checked: checked and self._stack.setCurrentIndex(1))
        self._radio_root.toggled.connect(
            lambda checked: checked and self._stack.setCurrentIndex(2))

        # Add selection buttons — shared across all three modes
        button_layout = QHBoxLayout()

        self.select_button = QPushButton("Select")
        self.select_button.clicked.connect(lambda: self.handle_button_click("select"))
        button_layout.addWidget(self.select_button)

        self.add_button = QPushButton("Add to Selection")
        self.add_button.clicked.connect(lambda: self.handle_button_click("add"))
        button_layout.addWidget(self.add_button)

        self.remove_button = QPushButton("Remove from Selection")
        self.remove_button.clicked.connect(lambda: self.handle_button_click("remove"))
        button_layout.addWidget(self.remove_button)

        layout.addLayout(button_layout)

        # Add standard Cancel button
        self.button_box = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.setLayout(layout)

    def _build_range_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        start_layout = QHBoxLayout()
        start_layout.addWidget(QLabel("Start:"))
        self.start_spinbox = QSpinBox()
        self.start_spinbox.setMinimum(1)
        self.start_spinbox.setMaximum(self.total_spectra if self.total_spectra > 0 else 1)
        start_layout.addWidget(self.start_spinbox)

        end_layout = QHBoxLayout()
        end_layout.addWidget(QLabel("End:"))
        self.end_spinbox = QSpinBox()
        self.end_spinbox.setMinimum(1)
        self.end_spinbox.setMaximum(self.total_spectra if self.total_spectra > 0 else 1)
        self.end_spinbox.setValue(self.total_spectra if self.total_spectra > 0 else 1)
        end_layout.addWidget(self.end_spinbox)

        step_layout = QHBoxLayout()
        step_layout.addWidget(QLabel("Step:"))
        self.step_spinbox = QSpinBox()
        self.step_spinbox.setMinimum(1)
        self.step_spinbox.setMaximum(self.total_spectra if self.total_spectra > 0 else 1)
        step_layout.addWidget(self.step_spinbox)

        layout.addLayout(start_layout)
        layout.addLayout(end_layout)
        layout.addLayout(step_layout)
        layout.addStretch()
        return panel

    def _build_search_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Contains / matches:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("e.g. Raman  or  Chlor")
        self.search_edit.textChanged.connect(self._update_search_count)
        search_row.addWidget(self.search_edit)
        layout.addLayout(search_row)

        opts_row = QHBoxLayout()
        self.regex_cb = QCheckBox("Regular expression")
        self.regex_cb.setToolTip(
            "Unchecked (default): plain substring match anywhere in the\n"
            "label. Checked: the text above is a regular expression,\n"
            "matched anywhere in the label (re.search).")
        self.regex_cb.stateChanged.connect(self._update_search_count)
        opts_row.addWidget(self.regex_cb)
        self.case_sensitive_cb = QCheckBox("Case sensitive")
        self.case_sensitive_cb.stateChanged.connect(self._update_search_count)
        opts_row.addWidget(self.case_sensitive_cb)
        opts_row.addStretch()
        layout.addLayout(opts_row)

        self.search_count_label = QLabel("")
        self.search_count_label.setStyleSheet("font-size:8pt; color:#555;")
        layout.addWidget(self.search_count_label)
        layout.addStretch()

        self._update_search_count()
        return panel

    def _build_root_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self._root_groups = group_by_root_name(self.labels)

        self.root_list = QListWidget()
        self.root_list.setSelectionMode(QAbstractItemView.NoSelection)
        for root, indices in self._root_groups:
            item = QListWidgetItem(f"{root}  ({len(indices)})")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, indices)
            self.root_list.addItem(item)
        self.root_list.itemChanged.connect(self._update_root_count)
        layout.addWidget(self.root_list)

        mini_row = QHBoxLayout()
        btn_check_all = QPushButton("Check All")
        btn_check_all.clicked.connect(lambda: self._set_all_root_checks(Qt.Checked))
        mini_row.addWidget(btn_check_all)
        btn_uncheck_all = QPushButton("Uncheck All")
        btn_uncheck_all.clicked.connect(lambda: self._set_all_root_checks(Qt.Unchecked))
        mini_row.addWidget(btn_uncheck_all)
        mini_row.addStretch()
        layout.addLayout(mini_row)

        self.root_count_label = QLabel("")
        self.root_count_label.setStyleSheet("font-size:8pt; color:#555;")
        layout.addWidget(self.root_count_label)

        self._update_root_count()
        return panel

    # ------------------------------------------------------------------ #
    # Live feedback                                                        #
    # ------------------------------------------------------------------ #

    def _update_search_count(self, *_args):
        pattern = self.search_edit.text()
        try:
            indices = compute_text_search_indices(
                self.labels, pattern,
                use_regex=self.regex_cb.isChecked(),
                case_sensitive=self.case_sensitive_cb.isChecked())
            self.search_count_label.setStyleSheet("font-size:8pt; color:#555;")
            self.search_count_label.setText(
                f"{len(indices)} of {len(self.labels)} spectra match"
                if pattern else "")
        except re.error as exc:
            self.search_count_label.setStyleSheet("font-size:8pt; color:#B71C1C;")
            self.search_count_label.setText(f"Invalid regular expression: {exc}")

    def _set_all_root_checks(self, state):
        self.root_list.blockSignals(True)
        for i in range(self.root_list.count()):
            self.root_list.item(i).setCheckState(state)
        self.root_list.blockSignals(False)
        self._update_root_count()

    def _update_root_count(self, *_args):
        total = 0
        n_groups = 0
        for i in range(self.root_list.count()):
            item = self.root_list.item(i)
            if item.checkState() == Qt.Checked:
                n_groups += 1
                total += len(item.data(Qt.UserRole))
        self.root_count_label.setText(
            f"{total} spectra in {n_groups} group(s) checked" if n_groups else "")

    # ------------------------------------------------------------------ #
    # Selection resolution                                                 #
    # ------------------------------------------------------------------ #

    def _compute_matched_indices(self):
        """Resolve the active mode to a sorted list of 0-based indices, or
        return None (after showing a message) if the current mode's input
        isn't valid yet (e.g. a broken regex)."""
        if self._radio_range.isChecked():
            start = self.start_spinbox.value() - 1
            end = self.end_spinbox.value() - 1
            step = self.step_spinbox.value()
            return list(range(start, end + 1, step))

        if self._radio_search.isChecked():
            pattern = self.search_edit.text()
            if not pattern:
                QMessageBox.warning(self, "No search text",
                                     "Type some text (or a regular expression) to search for.")
                return None
            try:
                return compute_text_search_indices(
                    self.labels, pattern,
                    use_regex=self.regex_cb.isChecked(),
                    case_sensitive=self.case_sensitive_cb.isChecked())
            except re.error as exc:
                QMessageBox.warning(self, "Invalid regular expression", str(exc))
                return None

        # Common root name
        indices = set()
        for i in range(self.root_list.count()):
            item = self.root_list.item(i)
            if item.checkState() == Qt.Checked:
                indices.update(item.data(Qt.UserRole))
        if not indices:
            QMessageBox.warning(self, "Nothing checked",
                                 "Check one or more root-name groups to select.")
            return None
        return sorted(indices)

    def handle_button_click(self, action):
        """Handle clicks on the selection action buttons."""
        indices = self._compute_matched_indices()
        if indices is None:
            return
        self.selection_result = {'indices': indices, 'action': action}
        self.accept()

    def get_selection_parameters(self):
        """Return the selection parameters: {'indices': [0-based ints], 'action': str}."""
        return self.selection_result

    def _make_info_button(self, title, text):
        """Small orange '?' button — same style used throughout the rest
        of the app (e.g. the 2-D Map dialog's and standalone NMF/MCR-ALS
        dialogs' section-header info buttons)."""
        btn = QPushButton('?')
        btn.setFixedSize(24, 24)
        btn.setStyleSheet(
            'QPushButton { background-color:#F57C00; color:white; '
            'font-weight:bold; border:none; border-radius:4px; }'
            'QPushButton:hover { background-color:#EF6C00; }')
        btn.setToolTip('About this dialog')
        btn.clicked.connect(lambda: QMessageBox.information(self, title, text))
        return btn
