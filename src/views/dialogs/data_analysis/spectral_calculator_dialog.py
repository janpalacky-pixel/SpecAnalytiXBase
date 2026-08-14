# src/views/dialogs/data_analysis/spectral_calculator_dialog.py

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QDialogButtonBox,
    QSplitter, QTextEdit, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy,
    QAbstractItemView, QWidget, QMenu, QActionGroup, QAction, QApplication,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QTextCursor
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import numpy as np
import re

from src.modules.data_analysis.spectral_calculator_manager import SpectralCalculatorManager
from src.modules.utils.label_shortening import shorten_spectra_labels, make_shorten_names_checkbox


class SpectralCalculatorDialog(QDialog):
    """Dialog for the spectral calculator.

    The user types a formula using spectrum labels as variable names.
    A live reference panel on the right lists available spectra and
    built-in functions. A live preview below the formula shows the
    resulting spectrum/spectra as they're typed. The formula is validated
    before Apply/Add as New is accepted.

    Apply and Add as New are this dialog's OWN buttons (see __init__
    below), not a main-window checkbox — same commit_callback pattern
    used by every other refined operation dialog in this app (Manual
    Baseline, SG-Smoothing, FFT Denoising, etc.). The dialog closes
    itself once a commit succeeds (see _on_commit_clicked) — this
    matters more here than for most other operations: Apply replaces
    the source spectra, so if the dialog stayed open afterward,
    self.selected_spectra would keep pointing at spectra that no longer
    exist in the main list, and any further action taken in the same
    still-open dialog would fail with "One or more source spectra could
    not be found."
    """

    def __init__(self, parent=None, selected_spectra=None, current_settings=None,
                 commit_callback=None, main_controller=None):
        super().__init__(parent)
        self.setWindowTitle('Spectral Calculator')
        self.setModal(True)
        self.resize(1100, 780)
        # Allow maximizing (e.g. for long formulas / many spectra), but not
        # minimizing — a modal dialog minimized to the taskbar has no way
        # back without alt-tabbing, which is confusing.
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowMaximizeButtonHint
        )

        self._main_controller = main_controller
        self.selected_spectra = selected_spectra or []
        self.current_settings = current_settings or {}
        self.manager = SpectralCalculatorManager()
        # Bound method (SpectralCalculatorController.commit_spectral_calculator)
        # passed in by whatever opened this dialog, so Apply / Add as New
        # can commit the result directly, without a separate Run step.
        self.commit_callback = commit_callback

        # Alias map: short "sp1", "sp2", ... names standing in for the real
        # (possibly long) spectrum labels, purely for typing/reading
        # formulas in THIS dialog. Built once, in selection order, so an
        # alias means the same spectrum for the whole time this dialog is
        # open. The real labels are what the manager evaluates against and
        # what ends up in any saved settings or output metadata — aliases
        # never leave this dialog.
        self.alias_to_label = {}
        self.label_to_alias = {}
        for i, s in enumerate(self.selected_spectra):
            alias = f'sp{i + 1}'
            self.alias_to_label[alias] = s['label']
            self.label_to_alias[s['label']] = alias

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._do_update_preview)

        self._setup_ui()
        self._load_settings()
        self._update_preview()



    # =================================================================
    # Alias translation
    # =================================================================
    def _aliased_formula_to_real(self, formula: str) -> str:
        """Translate a formula written with aliases (sp1, sp2, ...) into
        one using the real spectrum labels, for evaluation. Longest-alias-
        first replacement avoids "sp1" wrongly matching inside "sp10"."""
        result = formula
        for alias in sorted(self.alias_to_label, key=len, reverse=True):
            result = re.sub(rf'\b{re.escape(alias)}\b', self.alias_to_label[alias], result)
        return result

    def _real_formula_to_aliased(self, formula: str) -> str:
        """Translate a formula written with real spectrum labels into one
        using this session's aliases — used when loading a previously
        saved formula (written before this dialog session existed, so it
        necessarily used real labels) back into the editable alias form."""
        result = formula
        for label in sorted(self.label_to_alias, key=len, reverse=True):
            if label in result:
                result = result.replace(label, self.label_to_alias[label])
        return result

    # =================================================================
    # UI construction
    # =================================================================
    def _setup_ui(self):
        root = QVBoxLayout(self)

        # Top info bar — kept to one short line so it doesn't eat space the
        # Preview panel needs; full detail is in the tooltip and Help.
        info = QLabel(
            'Use aliases (sp1, sp2, ...) shown on the right as variables. '
            'Click <b>Help</b> below for the full guide.'
        )
        info.setWordWrap(True)
        # QLabel's sizeHint() for word-wrapped text is unreliable — it does
        # not consistently use heightForWidth() at the label's actual
        # assigned width, and can report (and sometimes actually render) a
        # height suggesting several wrapped lines even when only one line
        # of text is showing. QSizePolicy.Fixed alone only stops a PARENT
        # from stretching this label beyond its sizeHint; it does nothing
        # if sizeHint() itself is wrong. So this caps the label directly,
        # using its own font metrics (not a guessed constant) plus the
        # padding from its stylesheet below — this scales correctly if the
        # font or padding ever changes, rather than a number that would
        # silently go stale.
        info.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        _info_padding = 6 + 6  # matches the top/bottom padding in the stylesheet below
        info.setMaximumHeight(info.fontMetrics().height() + _info_padding + 6)
        info.setToolTip(
            'These aliases stand in for the real spectrum names, which can be '
            'long. Click an alias or function on the right to insert it at the '
            'cursor.\n\n'
            'All selected spectra must share an identical x-axis — use Define '
            'Spectral Range \u2192 Apply linearisation first if needed.\n\n'
            'A formula can return a list of results (e.g. "[sp1 - sp2, sp1 + '
            'sp2]") to produce several output spectra at once.\n\n'
            'Whether the result replaces the source spectra or is added as new '
            'ones is controlled by the "Add as new" checkbox in the main '
            'window, not here.'
        )
        info.setStyleSheet(
            'background-color: #E3F2FD; color: #1976D2; '
            'padding: 6px; border-radius: 3px; font-style: italic;'
        )
        root.addWidget(info)

        # Main splitter: left (formula + output) | right (reference)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([560, 340])
        root.addWidget(splitter)

        # Button box
        self.button_box = QDialogButtonBox()
        help_btn = QPushButton('Help')
        validate_btn = QPushButton('Validate formula')
        save_btn = QPushButton('Save\u2026')
        save_btn.setToolTip(
            'Save the current preview result(s) to a file, without closing '
            'this dialog or applying the operation to the main spectrum list.'
        )
        self.apply_button = QPushButton('Apply')
        self.apply_button.setToolTip(
            'Replace the source spectra with the formula result(s).'
        )
        self.add_as_new_button = QPushButton('Add as New')
        self.add_as_new_button.setToolTip(
            'Keep the source spectra unchanged and add the formula result(s) '
            'to the list under new names.'
        )
        self.close_button = QPushButton('Close')
        self.button_box.addButton(help_btn, QDialogButtonBox.HelpRole)
        self.button_box.addButton(validate_btn, QDialogButtonBox.ActionRole)
        self.button_box.addButton(save_btn, QDialogButtonBox.ActionRole)
        self.button_box.addButton(self.apply_button, QDialogButtonBox.ActionRole)
        self.button_box.addButton(self.add_as_new_button, QDialogButtonBox.ActionRole)
        self.button_box.addButton(self.close_button, QDialogButtonBox.RejectRole)
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        self.button_box.rejected.connect(self.reject)
        help_btn.clicked.connect(self._show_help)
        validate_btn.clicked.connect(self._on_validate)
        save_btn.clicked.connect(self._save_preview_spectra)
        root.addWidget(self.button_box)

    def _build_left_panel(self):
        widget = QWidget()
        outer_layout = QVBoxLayout(widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # Top section (Formula + Output + Examples) and the Preview section
        # are placed in a vertical splitter so the user can drag to resize
        # how much room the preview gets, rather than a fixed split.
        left_splitter = QSplitter(Qt.Vertical)

        top_widget = QWidget()
        top_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout = QVBoxLayout(top_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self._top_widget = top_widget

        # Formula + Output merged into one box: a single-line name field
        # never needed its own separate groupbox, and keeping them apart
        # meant Output had nothing useful to do with extra splitter room.
        # The formula field is a multi-line QTextEdit rather than a
        # QLineEdit specifically so that extra room IS useful — a long
        # formula gets more visible lines instead of the box just growing
        # empty space around a single line of text.
        formula_group = QGroupBox('Formula')
        formula_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        formula_layout = QVBoxLayout(formula_group)

        self.formula_edit = QTextEdit()
        self.formula_edit.setFont(QFont('Courier New', 11))
        self.formula_edit.setPlaceholderText(
            'e.g.  2*sp1 + sp2 - sp3   or   [sp1 - sp2, sp1 + sp2]'
        )
        self.formula_edit.setTabChangesFocus(True)  # Tab moves focus, doesn't insert a tab
        self.formula_edit.setLineWrapMode(QTextEdit.WidgetWidth)
        # A few lines tall by default — enough for a genuinely long
        # formula to be readable without scrolling, but not so tall it
        # dominates the box when the formula is short (the common case).
        _line_h = self.formula_edit.fontMetrics().height()
        self.formula_edit.setMinimumHeight(_line_h * 3 + 16)
        self.formula_edit.textChanged.connect(self._on_formula_text_changed)
        formula_layout.addWidget(self.formula_edit)

        # Validation feedback gets its own full-width row right below the
        # editor.
        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        formula_layout.addWidget(self.validation_label)

        # Output name + Clear share one row: Clear acts on the formula
        # above, but visually pairing it with the name field keeps both
        # "supporting" controls together on a single compact line rather
        # than Clear sitting alone under the editor.
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel('New spectrum name:'))
        self.name_edit = QLineEdit('Calculator_result')
        self.name_edit.setToolTip(
            'Base name for the result spectrum. If the formula produces more '
            'than one output spectrum, they are numbered automatically '
            '(e.g. "Calculator_result_1", "Calculator_result_2", ...).'
        )
        self.name_edit.textChanged.connect(self._update_preview)
        name_row.addWidget(self.name_edit)

        clear_formula_btn = QPushButton('Clear')
        clear_formula_btn.setToolTip('Clear the formula and start from scratch')
        clear_formula_btn.setFixedWidth(55)
        clear_formula_btn.clicked.connect(self._clear_formula)
        name_row.addWidget(clear_formula_btn)
        formula_layout.addLayout(name_row)

        layout.addWidget(formula_group, 1)

        # Examples — collapsed by default: this is by far the largest
        # single piece of the top section, and least needed once the
        # formula syntax is familiar, so collapsing it leaves much more
        # room for Preview without an oversized window.
        #
        # Uses QGroupBox's own native checkable mode (setCheckable +
        # toggled signal) rather than a custom collapsible widget — a
        # custom widget with manual sizeHint/updateGeometry bookkeeping is
        # exactly where real-vs-headless-testing Qt rendering diverged
        # last time, so this sticks to the plainest built-in mechanism:
        # hide a normal child widget, let Qt's own layout engine do
        # whatever it always does for a hidden widget, nothing custom.
        ex_group = QGroupBox('\u25b6  Formula examples  (click to insert)')
        ex_group.setCheckable(True)
        ex_group.setChecked(False)
        ex_group.setStyleSheet(
            'QGroupBox { margin-top: 0px; padding-top: 18px; }'
            'QGroupBox::title { subcontrol-origin: margin; left: 7px; top: 0px; }'
            # Hide the actual checkbox square — the arrow embedded in the
            # title text (updated on toggle, below) serves as the visual
            # indicator instead. The toggle behavior itself is unchanged,
            # still QGroupBox's own native checkable mode.
            'QGroupBox::indicator { width: 0px; height: 0px; }'
        )
        ex_layout = QVBoxLayout(ex_group)
        ex_layout.setContentsMargins(8, 0, 8, 4)
        ex_layout.setSpacing(0)
        examples = [
            ('Linear combination',      '2*sp1 + 0.5*sp2 - sp3'),
            ('Ratio spectrum',           'sp1 / sp2'),
            ('Normalised difference',    '(sp1 - sp2) / (sp1 + sp2)'),
            ('Transmittance → Abs.',    'absorbance(sp1)'),
            ('Absorbance → Trans.',     'transmittance(sp1)'),
            ('Kubelka-Munk',            'kubelka_munk(sp1)'),
            ('First derivative',        'derivative(sp1)'),
            ('Second derivative',       'second_deriv(sp1)'),
            ('SNV normalisation',       'snv(sp1)'),
            ('Min-max normalisation',   'normalise(sp1)'),
            ('Multiple outputs at once', '[sp1 - mean_val(sp1), sp2 - mean_val(sp2)]'),
        ]
        self.example_list = QListWidget()
        self.example_list.setSelectionMode(QAbstractItemView.SingleSelection)
        for label, formula in examples:
            item = QListWidgetItem(f'{label}:   {formula}')
            item.setData(Qt.UserRole, formula)
            item.setToolTip(formula)
            self.example_list.addItem(item)
        self.example_list.itemClicked.connect(self._insert_example)
        # Size to fit all rows without extra blank space below them, and
        # without being resizable taller than that — any extra vertical
        # room in the dialog should go to the Preview panel instead, via
        # the splitter below, not be absorbed here.
        row_height = self.example_list.sizeHintForRow(0) if self.example_list.count() else 18
        content_height = row_height * self.example_list.count() + 2 * self.example_list.frameWidth()
        self.example_list.setFixedHeight(content_height)
        self.example_list.setVisible(False)  # matches ex_group.setChecked(False) above
        ex_layout.addWidget(self.example_list)

        def _resize_ex_group(checked):
            # Derive the title-row height from the groupbox's own sizeHint
            # while its content is hidden, rather than a hardcoded pixel
            # constant — this stays correct regardless of font, DPI
            # scaling, or Qt style/theme on whatever machine runs it.
            was_visible = self.example_list.isVisible()
            self.example_list.setVisible(False)
            title_bar_height = ex_group.sizeHint().height()
            self.example_list.setVisible(was_visible)

            margins = ex_layout.contentsMargins()
            if checked:
                target = title_bar_height + content_height + margins.top() + margins.bottom()
                ex_group.setFixedHeight(target)
            else:
                ex_group.setFixedHeight(title_bar_height)

            # The diagnostic dump showed every widget's geometry is
            # already correct and tightly packed after a resize like this
            # — the visible gaps reported are very likely stale painted
            # pixels left behind because nothing told Qt to actually
            # repaint the freed-up screen area, not a real layout error.
            # Forcing it explicitly costs nothing and directly addresses
            # that, regardless of platform/theme.
            self.repaint()
            QApplication.processEvents()

        def _flip_ex_arrow(checked):
            arrow = '\u25bc' if checked else '\u25b6'
            title = ex_group.title().split('  ', 1)[-1]
            ex_group.setTitle(f'{arrow}  {title}')

        ex_group.toggled.connect(self.example_list.setVisible)
        ex_group.toggled.connect(_resize_ex_group)
        ex_group.toggled.connect(_flip_ex_arrow)
        ex_group.toggled.connect(self._on_examples_toggled)
        _resize_ex_group(False)
        layout.addWidget(ex_group)

        left_splitter.addWidget(top_widget)

        # Live preview — recomputes (debounced) as the formula changes,
        # showing every output spectrum the current formula would produce.
        preview_group = QGroupBox('Preview')
        preview_layout = QVBoxLayout(preview_group)

        self.preview_canvas = SpectralCalculatorPlotCanvas(self)
        self.preview_canvas.setContextMenuPolicy(Qt.CustomContextMenu)
        self.preview_canvas.customContextMenuRequested.connect(self._show_preview_context_menu)
        self.preview_toolbar = NavigationToolbar(self.preview_canvas, preview_group)
        preview_layout.addWidget(self.preview_toolbar)
        preview_layout.addWidget(self.preview_canvas)

        left_splitter.addWidget(preview_group)
        # Stretch factors make Preview absorb all extra space on resize (0
        # for the top section, 1 for Preview). For the INITIAL split, ask
        # for top_widget's real sizeHint and a deliberately oversized
        # number for Preview — QSplitter clamps an oversized request down
        # to whatever's actually left, which is the standard, robust way
        # to say "give the first pane exactly what it needs and everything
        # else to the second one."
        #
        # Deliberately NOT using preview_group.setMinimumHeight() here: a
        # widget's minimum height contributes directly to the whole
        # dialog's minimumSizeHint, so setting a generous floor on Preview
        # was forcing the dialog to grow taller than its requested 700px
        # just to satisfy that floor — the opposite of what was needed.
        top_height = top_widget.sizeHint().height()
        left_splitter.setSizes([top_height, 10000])
        left_splitter.setStretchFactor(0, 0)
        left_splitter.setStretchFactor(1, 1)
        self._left_splitter = left_splitter

        outer_layout.addWidget(left_splitter)

        return widget

    def _build_right_panel(self):
        widget = QGroupBox('Reference')
        layout = QVBoxLayout(widget)

        # Spectrum labels — shown as short aliases (sp1, sp2, ...) since
        # real spectrum names can be long; clicking inserts the alias, not
        # the real name. The real name is shown alongside and in the
        # tooltip so it's never actually ambiguous which spectrum sp1 is.
        sp_label = QLabel('Available spectra  (click to insert alias at cursor):')
        sp_label.setStyleSheet('font-weight: bold;')
        layout.addWidget(sp_label)

        self.spectra_list = QListWidget()
        self.spectra_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.spectra_list.itemClicked.connect(self._insert_label)
        self.spectra_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Display-only "shorten names" — this dialog's own, independent
        # checkbox (see make_shorten_names_checkbox). The composite
        # "alias — label" item text is rebuilt (not paint-delegated) each
        # time the checkbox is toggled, via _populate_reference_list —
        # clicking reads item.data(Qt.UserRole) (the alias), never this
        # text (see _insert_label), and the tooltip always shows the full
        # name regardless, so it's never actually ambiguous.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(self._populate_reference_list)
        self._populate_reference_list()
        layout.addWidget(self.spectra_list, stretch=1)
        layout.addWidget(self.checkBox_shorten_names)

        alias_note = QLabel(
            'Write simple expressions like sp1 + sp2, or multiple ones in '
            'a Python-style list: [sp1 + sp2, sp1 - sp2].'
        )
        alias_note.setWordWrap(True)
        alias_note.setStyleSheet(
            'color: #E65100; font-style: italic; font-size: 11px; '
            'background-color: #FFF3E0; padding: 5px; border-radius: 3px;'
        )
        layout.addWidget(alias_note)

        # Function reference table
        fn_label = QLabel('Built-in functions  (click to insert):')
        fn_label.setStyleSheet('font-weight: bold; margin-top: 6px;')
        layout.addWidget(fn_label)

        self.fn_table = QTableWidget()
        self.fn_table.setColumnCount(2)
        self.fn_table.setHorizontalHeaderLabels(['Function', 'Description'])
        self.fn_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.fn_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.fn_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.fn_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.fn_table.verticalHeader().setVisible(False)
        self.fn_table.setAlternatingRowColors(True)

        functions = SpectralCalculatorManager.available_functions()
        self.fn_table.setRowCount(len(functions))
        for row, (name, desc) in enumerate(functions):
            self.fn_table.setItem(row, 0, QTableWidgetItem(name))
            self.fn_table.setItem(row, 1, QTableWidgetItem(desc))

        self.fn_table.itemClicked.connect(self._insert_function)
        self.fn_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.fn_table, stretch=2)

        return widget

    # =================================================================
    # Settings persistence
    # =================================================================
    def _load_settings(self):
        if not self.current_settings:
            return
        formula = self.current_settings.get('formula', '')
        if formula:
            # A previously saved formula was stored using REAL spectrum
            # labels (aliases never leave this dialog), so translate it
            # into this session's aliases before displaying it for editing.
            self.formula_edit.setPlainText(self._real_formula_to_aliased(formula))
        name = self.current_settings.get('new_spectrum_name', '')
        if name:
            self.name_edit.setText(name)

    def get_settings(self):
        formula = self.formula_edit.toPlainText().strip()
        name = self.name_edit.text().strip()
        if not formula or not name:
            return None
        return {
            # Stored and handed to the controller/manager using REAL
            # spectrum labels — aliases are a this-dialog-only typing
            # convenience and must never leak into saved settings, output
            # metadata, or anything outside this dialog.
            'formula': self._aliased_formula_to_real(formula),
            'new_spectrum_name': name,
        }

    # =================================================================
    # Slots
    # =================================================================
    def _on_examples_toggled(self, checked: bool):
        """Connected to ex_group.toggled (passes the new checked state,
        unused here directly — example_list's own visibility is wired to
        the same signal separately).

        top_widget's sizeHint() changes automatically once example_list is
        hidden/shown (Qt computes this from its currently-visible
        children, no manual height bookkeeping needed for that part). What
        Qt does NOT do on its own is reflect that new sizeHint in the
        splitter's already-allocated sizes, since nothing forces a
        relayout just because a sizeHint changed passively.

        Querying sizeHint() synchronously, still inside this same signal
        handler, returns the STALE pre-toggle value — Qt doesn't finish
        propagating the visibility-driven layout change until the current
        event is done being handled. Deferring via QTimer.singleShot(0, ...)
        lets that settle first.

        Deliberately NOT calling setMaximumHeight() anywhere here: a
        permanent cap set at toggle time would block the user from ever
        dragging the splitter to give top_widget more room again.
        """
        if not hasattr(self, '_top_widget') or not hasattr(self, '_left_splitter'):
            return
        self._top_widget.updateGeometry()
        QTimer.singleShot(0, self._apply_examples_resize)

    def _apply_examples_resize(self):
        """Deferred half of _on_examples_toggled — see its docstring."""
        if not hasattr(self, '_top_widget') or not hasattr(self, '_left_splitter'):
            return
        new_height = self._top_widget.sizeHint().height()
        self._left_splitter.setSizes([new_height, 10000])
        self.repaint()

    def _clear_formula(self):
        """Clear the formula and reset validation label."""
        self.formula_edit.clear()
        self.validation_label.setText('')
        self.formula_edit.setFocus()

    def _populate_reference_list(self, *_):
        """(Re)build the Reference panel's spectra_list item text — the
        composite "alias — label" text is baked directly into each item
        (unlike other dialogs' paint-only shortened-name delegate) since
        the alias, not this text, is what clicking reads (see
        _insert_label). Called once at dialog-build time and again every
        time checkBox_shorten_names is toggled, so the displayed labels
        stay in sync with this dialog's own shorten-names state."""
        shorten_enabled = self.checkBox_shorten_names.isChecked()
        display_labels = shorten_spectra_labels(self.selected_spectra, shorten_enabled)
        self.spectra_list.clear()
        for s in self.selected_spectra:
            alias = self.label_to_alias[s['label']]
            display_name = display_labels.get(s['label'], s['label'])
            item = QListWidgetItem(f'{alias}   —   {display_name}')
            item.setData(Qt.UserRole, alias)
            item.setToolTip(f'{alias} stands for "{s["label"]}" in this dialog only.')
            self.spectra_list.addItem(item)

    def _insert_label(self, item):
        """Insert the clicked spectrum's alias (sp1, sp2, ...) at the
        current cursor position — not its real, possibly long, name."""
        alias = item.data(Qt.UserRole)
        self.formula_edit.insertPlainText(alias)
        self.formula_edit.setFocus()

    def _insert_function(self, item):
        """Insert 'funcname()' at cursor with cursor placed inside the parens."""
        row = item.row()
        func_name = self.fn_table.item(row, 0).text()
        # Strip any argument placeholder like (x) — insert just the bare name + ()
        bare = func_name.split('(')[0] + '()'
        self.formula_edit.insertPlainText(bare)
        # Move cursor back inside the parentheses
        cursor = self.formula_edit.textCursor()
        cursor.movePosition(QTextCursor.PreviousCharacter)
        self.formula_edit.setTextCursor(cursor)
        self.formula_edit.setFocus()

    def _insert_example(self, item):
        """Replace formula with the clicked example."""
        formula = item.data(Qt.UserRole)
        self.formula_edit.setPlainText(formula)
        self.formula_edit.setFocus()

    def _clear_validation_label(self):
        self.validation_label.setText('')

    def _on_formula_text_changed(self):
        self._clear_validation_label()
        self._update_preview()

    def _update_preview(self, *_args):
        """Request a preview recompute, debounced so rapid typing doesn't
        trigger a recompute on every keystroke."""
        if not hasattr(self, 'preview_canvas'):
            return
        self._preview_timer.start()  # restarts if already running

    def _do_update_preview(self):
        """Recompute the formula result and redraw the preview canvas with
        every output spectrum the current formula would produce."""
        formula = self.formula_edit.toPlainText().strip()
        if not formula:
            self.preview_canvas.show_message('Enter a formula to see a preview here.')
            return

        real_formula = self._aliased_formula_to_real(formula)
        try:
            results = self.manager.evaluate(real_formula, self.selected_spectra)
        except Exception as exc:
            self.preview_canvas.show_message(f'Cannot preview:\n{exc}')
            return

        base_name = self.name_edit.text().strip() or 'Calculator_result'
        preview_spectra = []
        for idx, res in enumerate(results):
            label = base_name if len(results) == 1 else f'{base_name}_{idx + 1}'
            preview_spectra.append({**res, 'label': label})

        self.preview_canvas.plot_spectra(preview_spectra)

    def _show_preview_context_menu(self, pos):
        """Right-click menu on the preview canvas: plot style, log scales,
        and opening the same preview in a separate, non-modal window."""
        canvas = self.preview_canvas
        menu = QMenu(self)

        style_menu = menu.addMenu('Plot style')
        style_group = QActionGroup(self)
        style_group.setExclusive(True)
        for label, value in (('Line', canvas.STYLE_LINE),
                              ('Points', canvas.STYLE_POINTS),
                              ('Points + line', canvas.STYLE_BOTH)):
            action = QAction(label, self, checkable=True)
            action.setChecked(canvas.plot_style == value)
            action.triggered.connect(lambda checked, v=value: canvas.set_plot_style(v))
            style_group.addAction(action)
            style_menu.addAction(action)

        menu.addSeparator()
        log_x_action = QAction('Log scale (X axis)', self, checkable=True)
        log_x_action.setChecked(canvas.log_x)
        log_x_action.triggered.connect(lambda checked: canvas.set_log_x(checked))
        menu.addAction(log_x_action)

        log_y_action = QAction('Log scale (Y axis)', self, checkable=True)
        log_y_action.setChecked(canvas.log_y)
        log_y_action.triggered.connect(lambda checked: canvas.set_log_y(checked))
        menu.addAction(log_y_action)

        menu.addSeparator()
        external_action = QAction('Open preview in external window', self)
        external_action.triggered.connect(self._open_preview_externally)
        menu.addAction(external_action)

        menu.exec_(canvas.mapToGlobal(pos))

    def _open_preview_externally(self):
        """Open the current preview in a separate, non-modal, resizable
        window — useful for comparing against other windows or just having
        more room than the dialog's own splitter allows."""
        if not self.preview_canvas._last_spectra:
            QMessageBox.information(
                self, 'Nothing to show',
                'There is no valid preview to open right now.'
            )
            return
        win = ExternalPreviewWindow(self, self.preview_canvas)
        win.show()
        # Keep a reference so it isn't garbage-collected while open.
        if not hasattr(self, '_external_preview_windows'):
            self._external_preview_windows = []
        self._external_preview_windows.append(win)

    def _save_preview_spectra(self):
        """
        Export the current preview result(s) — whatever the formula
        currently produces, computed in self.preview_canvas._last_spectra
        — using the existing save pipeline (SaveOptionsDialog +
        SaveManager), the same one used by Normalization's "Save selected
        spectra..." and by File > Save in the main window. This does not
        apply the operation or close the dialog; it's purely a way to
        export the preview result(s) to a file directly.
        """
        to_save = list(self.preview_canvas._last_spectra)
        if not to_save:
            QMessageBox.information(
                self, 'Nothing to save',
                'There is no valid preview result to save right now. '
                'Enter a formula that produces a valid result first.'
            )
            return

        from src.views.dialogs.misc.save_spectra_dialog import SaveOptionsDialog
        from src.modules.misc.save_spectra_manager import SaveManager
        from PyQt5.QtWidgets import QFileDialog

        # Snapshot format saves the whole application state, not a
        # spectrum list — irrelevant here, so it's hidden for this flow,
        # same as Normalization's save dialog.
        dialog = SaveOptionsDialog(self)
        dialog.setWindowTitle('Save Calculator Result')
        dialog.fmt_snapshot.setVisible(False)

        if dialog.exec_() != QDialog.Accepted:
            return

        settings = dialog.get_settings()
        save_manager = SaveManager()

        if settings['mode'] == 'table':
            if settings['use_common_scale'] and not save_manager.validate_common_scale(to_save):
                QMessageBox.warning(
                    self, 'Scale Mismatch',
                    'The result spectra have different x-scales.\n'
                    'Cannot use the common x-scale option.\n\n'
                    "Uncheck 'Use common x-scale' to save with individual x-scales."
                )
                return

            ext = '.xlsx' if settings['format'] == 'excel' else '.txt'
            file_filter = (
                'Excel Files (*.xlsx);;All Files (*.*)' if settings['format'] == 'excel'
                else 'Text Files (*.txt);;CSV Files (*.csv);;All Files (*.*)'
            )
            file_path, _ = QFileDialog.getSaveFileName(
                self, 'Save Calculator Result', '', file_filter
            )
            if not file_path:
                return
            import os
            root_path, current_ext = os.path.splitext(file_path)
            if not current_ext:
                file_path = root_path + ext

            try:
                save_manager.save_table(to_save, file_path, settings)
                QMessageBox.information(
                    self, 'Save Successful',
                    f'Saved {len(to_save)} result spectrum(s) to:\n{file_path}'
                )
            except Exception as e:
                QMessageBox.critical(self, 'Save Error', f'Failed to save spectra:\n{e}')

        else:  # individual files
            directory = QFileDialog.getExistingDirectory(
                self, 'Select Directory for Individual Files'
            )
            if not directory:
                return

            try:
                saved_files = save_manager.save_individual(to_save, directory, settings)
                QMessageBox.information(
                    self, 'Save Successful',
                    f'Saved {len(saved_files)} file(s) to:\n{directory}'
                )
            except Exception as e:
                QMessageBox.critical(self, 'Save Error', f'Failed to save files:\n{e}')

    def _on_validate(self):
        formula = self.formula_edit.toPlainText().strip()
        if not formula:
            self._set_validation('No formula entered.', ok=False)
            return
        real_formula = self._aliased_formula_to_real(formula)
        error = self.manager.validate_formula(real_formula, self.selected_spectra)
        if error:
            self._set_validation(f'✗  {error}', ok=False)
        else:
            try:
                results = self.manager.evaluate(real_formula, self.selected_spectra)
                n = len(results)
                suffix = '' if n == 1 else f' ({n} output spectra)'
                self._set_validation(f'✓  Formula is valid.{suffix}', ok=True)
            except Exception:
                # Already validated above; this is just for the output count
                # in the message, so fall back gracefully if it changes
                # between the two calls for any reason.
                self._set_validation('✓  Formula is valid.', ok=True)

    def _set_validation(self, msg: str, ok: bool):
        colour = '#2E7D32' if ok else '#C62828'
        self.validation_label.setText(msg)
        self.validation_label.setStyleSheet(f'color: {colour}; font-weight: bold;')

    def _on_commit_clicked(self, add_as_new):
        """Apply or Add as New — validates the formula (same checks the
        old OK button used), then commits directly via commit_callback.
        Feedback is shown right here next to the buttons that triggered
        it, instead of a separate Run step in the main window.
        """
        formula = self.formula_edit.toPlainText().strip()
        if not formula:
            QMessageBox.warning(self, 'Empty formula', 'Please enter a formula.')
            return
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, 'No name', 'Please enter a name for the result spectrum.')
            return
        real_formula = self._aliased_formula_to_real(formula)
        error = self.manager.validate_formula(real_formula, self.selected_spectra)
        if error:
            self._set_validation(f'✗  {error}', ok=False)
            QMessageBox.warning(
                self, 'Invalid formula',
                f'The formula could not be evaluated:\n\n{error}'
            )
            return

        if self.commit_callback is None:
            QMessageBox.critical(
                self, 'Not Available',
                'This dialog was opened without a way to apply changes. '
                'Please reopen it via Configure.'
            )
            return

        action = 'add the result(s) as new spectra' if add_as_new else 'replace the source spectra with the result(s)'
        confirm = QMessageBox.question(
            self, 'Confirm', f'{action[0].upper() + action[1:]}?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        settings = self.get_settings()
        settings['source_labels'] = [s['label'] for s in self.selected_spectra]
        success, message = self.commit_callback(settings, add_as_new, list(self.selected_spectra))
        if success:
            QMessageBox.information(self, 'Done', message)
            # Close after a successful commit — same pattern every other
            # refined operation dialog in this app already uses. Matters
            # more here than most: Apply REPLACES the source spectra, so
            # self.selected_spectra (and this whole dialog's state, e.g.
            # the live preview) would otherwise keep referencing spectra
            # that no longer exist in the main list. Confirmed reachable:
            # without this, any further action in the same still-open
            # dialog (another Apply, the live preview re-rendering, etc.)
            # fails with "One or more source spectra could not be found."
            # Add as New doesn't corrupt anything the same way (sources
            # are left untouched), but closes too for consistency with
            # every other operation dialog's Apply/Add as New behavior.
            self.accept()
        else:
            QMessageBox.warning(self, 'Could Not Apply', message)

    def _show_help(self):
        try:
            from src.help.spectral_calculator_help import (
                get_spectral_calculator_help_content,
                get_spectral_calculator_help_title,
            )
            from src.help.help_window import show_help_window
            show_help_window(
                self,
                get_spectral_calculator_help_title(),
                get_spectral_calculator_help_content(),
            )
        except Exception:
            QMessageBox.information(self, 'Help', 'Help is not available.')


class SpectralCalculatorPlotCanvas(FigureCanvas):
    """Plot canvas for the live formula preview.

    Keeps the last-plotted spectra and current style settings (line/points,
    log scales) so the right-click context menu can change how the same
    data is drawn without needing to re-evaluate the formula.
    """

    STYLE_LINE = 'line'
    STYLE_POINTS = 'points'
    STYLE_BOTH = 'both'

    def __init__(self, parent=None):
        self.fig = Figure(tight_layout=True)
        self.axes = self.fig.add_subplot(111)
        super().__init__(self.fig)

        self.axes.set_xlabel('X')
        self.axes.set_ylabel('Intensity')
        self.axes.grid(True, linestyle='--', alpha=0.6)

        self.fig.patch.set_facecolor('#f0f0f0')
        self.axes.set_facecolor('#ffffff')
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._last_spectra = []
        self.plot_style = self.STYLE_LINE
        self.log_x = False
        self.log_y = False
        # Defaults to True so the calculator's existing behaviour (legend
        # shown automatically whenever more than one spectrum is plotted)
        # is unchanged; Combine Spectra explicitly sets this False and
        # wires its own checkbox, since one result line rarely needs a
        # legend by default there.
        self.legend_visible = True

    def plot_spectra(self, spectra_list):
        self._last_spectra = spectra_list
        self._render()

    def _render(self):
        """Redraw using the last-plotted spectra and current style/scale
        settings — called both after new data arrives and after a style
        change from the context menu."""
        spectra_list = self._last_spectra
        self.axes.clear()

        if not spectra_list:
            self.show_message('No result to preview.', keep_data=True)
            return

        colors = ['#1f77b4', '#d62728', '#2ca02c', '#ff7f0e',
                  '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        x_all = []
        plotted = 0

        if self.plot_style == self.STYLE_LINE:
            marker, linestyle = '', '-'
        elif self.plot_style == self.STYLE_POINTS:
            marker, linestyle = 'o', 'None'
        else:  # STYLE_BOTH
            marker, linestyle = 'o', '-'

        for i, s in enumerate(spectra_list):
            x = np.asarray(s.get('x_scale', []), dtype=float)
            y = np.asarray(s.get('y_scale', []), dtype=float)
            if len(x) == 0 or len(y) == 0:
                continue
            if self.log_x:
                keep = x > 0
                x, y = x[keep], y[keep]
            if self.log_y:
                keep = y > 0
                x, y = x[keep], y[keep]
            if len(x) == 0:
                continue
            self.axes.plot(x, y, color=colors[i % len(colors)],
                           marker=marker, markersize=4, linestyle=linestyle,
                           lw=1.2, label=s.get('label', f'Output_{i}'), alpha=0.9)
            x_all.extend(x)
            plotted += 1

        if plotted == 0:
            self.show_message(
                'No valid result to preview'
                + (' (no positive values for the selected log scale).' if (self.log_x or self.log_y) else '.'),
                keep_data=True
            )
            return

        self.axes.set_xlabel('X')
        self.axes.set_ylabel('Intensity')
        self.axes.set_xscale('log' if self.log_x else 'linear')
        self.axes.set_yscale('log' if self.log_y else 'linear')
        self.axes.grid(True, linestyle='--', alpha=0.6)
        if plotted > 1 and self.legend_visible:
            self.axes.legend(loc='best', fontsize='small')
        if x_all and not self.log_x:
            xlo, xhi = np.min(x_all), np.max(x_all)
            pad = (xhi - xlo) * 0.02 if xhi > xlo else 1.0
            self.axes.set_xlim(xlo - pad, xhi + pad)
        self.axes.autoscale(axis='y')
        self.draw()

    def set_plot_style(self, style: str):
        self.plot_style = style
        self._render()

    def set_log_x(self, enabled: bool):
        self.log_x = enabled
        self._render()

    def set_log_y(self, enabled: bool):
        self.log_y = enabled
        self._render()

    def set_legend_visible(self, visible: bool):
        self.legend_visible = visible
        self._render()

    def show_message(self, message: str, keep_data: bool = False):
        """Clear the canvas and show a centered placeholder message —
        used when there's nothing to preview yet, or the formula errored.

        keep_data=False (default) also clears _last_spectra, since an
        empty-formula or error message means there's genuinely nothing to
        re-render with a different style. keep_data=True is used internally
        by _render() itself, where _last_spectra must NOT be wiped out —
        otherwise switching to a log scale that happens to filter out all
        points would permanently forget the underlying data.
        """
        if not keep_data:
            self._last_spectra = []
        self.axes.clear()
        self.axes.text(0.5, 0.5, message, transform=self.axes.transAxes,
                       ha='center', va='center', color='#1976D2', fontsize=10,
                       wrap=True)
        self.axes.set_xticks([])
        self.axes.set_yticks([])
        self.draw()


class ExternalPreviewWindow(QDialog):
    """A separate, non-modal, resizable window showing the same preview
    plot — opened via the preview canvas's right-click context menu. It
    has its own copy of the data and its own independent style settings
    (changing style here does not affect the dialog's own preview, and
    vice versa), since the whole point is comparing layouts side by side
    without one view fighting the other for control.
    """

    def __init__(self, parent, source_canvas):
        super().__init__(parent)
        self.setWindowTitle('Spectral Calculator — Preview')
        self.setModal(False)
        self.resize(800, 600)
        self.setWindowFlags(
            (self.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint)
        )

        layout = QVBoxLayout(self)

        self.canvas = SpectralCalculatorPlotCanvas(self)
        self.canvas.plot_style = source_canvas.plot_style
        self.canvas.log_x = source_canvas.log_x
        self.canvas.log_y = source_canvas.log_y
        self.canvas.plot_spectra(list(source_canvas._last_spectra))

        self.canvas.setContextMenuPolicy(Qt.CustomContextMenu)
        self.canvas.customContextMenuRequested.connect(self._show_context_menu)

        toolbar = NavigationToolbar(self.canvas, self)
        layout.addWidget(toolbar)
        layout.addWidget(self.canvas)

    def _show_context_menu(self, pos):
        """Same style/scale options as the embedded preview's menu, minus
        the 'open externally' entry — this window already IS that."""
        canvas = self.canvas
        menu = QMenu(self)

        style_menu = menu.addMenu('Plot style')
        style_group = QActionGroup(self)
        style_group.setExclusive(True)
        for label, value in (('Line', canvas.STYLE_LINE),
                              ('Points', canvas.STYLE_POINTS),
                              ('Points + line', canvas.STYLE_BOTH)):
            action = QAction(label, self, checkable=True)
            action.setChecked(canvas.plot_style == value)
            action.triggered.connect(lambda checked, v=value: canvas.set_plot_style(v))
            style_group.addAction(action)
            style_menu.addAction(action)

        menu.addSeparator()
        log_x_action = QAction('Log scale (X axis)', self, checkable=True)
        log_x_action.setChecked(canvas.log_x)
        log_x_action.triggered.connect(lambda checked: canvas.set_log_x(checked))
        menu.addAction(log_x_action)

        log_y_action = QAction('Log scale (Y axis)', self, checkable=True)
        log_y_action.setChecked(canvas.log_y)
        log_y_action.triggered.connect(lambda checked: canvas.set_log_y(checked))
        menu.addAction(log_y_action)

        menu.exec_(canvas.mapToGlobal(pos))
