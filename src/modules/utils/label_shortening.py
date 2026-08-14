# src/modules/utils/label_shortening.py
"""
Shared "shorten names" algorithm — display-only label shortening used
consistently everywhere the app shows a list of spectrum names: the main
spectra list widget, plot legends/titles, Cluster Analysis, 2D
Correlation, Reference Matching, and every operation dialog's own spectra
list.

This is the single canonical implementation — originally written for the
main spectra list widget (see main_controller.py's checkBox_shorten_names
/ _DistinguishingNameDelegate) and extracted here so every other caller
shares the exact same behavior instead of reimplementing it slightly
differently.

CRITICAL: this is a DISPLAY-ONLY transformation. It must never be used to
rename an actual spectrum['label'], never written back into a spectrum
dict, and never used as a lookup/identity key anywhere (see
spectrum_identity.py's spectrum_key/spectrum_id and developer_guide_help.py's
"Golden Rule: Spectrum Identity" — labels are already the wrong thing to
use as identity; a shortened, ambiguous label is worse). Any place that
creates NEW spectra (Apply, Add as New, Send to main list, etc.) must
build their names from the original, full label — never from whatever
happened to be displayed with shortening turned on.
"""


def compute_distinguishing_labels(labels):
    """
    For a list of spectrum labels, strip whatever text carries no
    distinguishing information, returning {full_label: shortened_label}
    for display only.

    A single global common-prefix/common-suffix strip across the WHOLE
    list (an earlier, simpler version of this function) only works when
    every item in the list shares one common lead-in/trail-out. In
    practice a list very often holds SEVERAL distinct groups — e.g. one
    "Add" import's worth of CD spectra ("CD spectra with header : ...")
    sitting alongside a separate "Add" import's worth of Raman spectra
    ("Raman spectra - no header : ...") — and those two groups share
    NOTHING with each other, so a single global strip finds a common
    prefix/suffix of zero length and silently does nothing for the
    entire list, not just the mismatched pair. Confirmed directly: this
    was exactly the reported failure the first time this was built for
    the main spectra list.

    Fixed by clustering: if the current group of labels has no shared
    prefix/suffix at all, split it into sub-groups by first character
    (guaranteed to make each sub-group strictly smaller, since "no
    shared prefix" means at least two labels already differ at
    position 0) and recurse on each sub-group independently. A label's
    final shortened form only ever reflects text shared within its OWN
    group — a different group's spectra never influence it. This
    naturally reproduces the single-global-strip behaviour whenever the
    whole list genuinely is one group, and correctly falls back to
    per-group stripping otherwise.

    Purely a character-level comparison (not word/token-aware) — simple,
    deterministic, and it already does the right thing for this app's
    own "<file> : <column>" label convention, which is what motivated
    this in the first place.

    Returns {} (no shortening for anything) when there are fewer than 2
    labels — nothing to distinguish one item from. Any single label
    whose entire text would be stripped away (unusual: it would mean
    that label consists of exactly its group's shared prefix immediately
    followed by its group's shared suffix, nothing else) is left
    un-shortened individually, so a list item is never left blank.

    Note: if *labels* contains duplicates, only one {full_label: ...}
    entry can exist per unique string — callers that need to shorten
    labels for a list of spectrum DICTS where two spectra might
    legitimately share a label should build the input list from unique
    labels, or accept that duplicates collapse to the same shortened
    text (they were already visually indistinguishable by name before
    shortening, so this doesn't lose any information a reader had).
    """
    if len(labels) < 2:
        return {}
    return _shorten_label_group([(lbl, lbl) for lbl in labels])


def _shorten_label_group(pairs):
    """
    Worker for compute_distinguishing_labels. *pairs* is a list of
    (full_label, text_remaining_to_shorten) — 'text' starts equal to the
    full label and only ever shrinks as recursion strips shared prefixes/
    suffixes within successively smaller groups. Returns
    {full_label: shortened_label}.
    """
    if len(pairs) == 1:
        full, text = pairs[0]
        return {full: text if text else full}

    texts = [t for _, t in pairs]
    shortest = min(len(t) for t in texts)

    prefix_len = 0
    while prefix_len < shortest and all(t[prefix_len] == texts[0][prefix_len] for t in texts):
        prefix_len += 1

    suffix_len = 0
    while suffix_len < shortest and all(t[-1 - suffix_len] == texts[0][-1 - suffix_len] for t in texts):
        suffix_len += 1

    # Clamp so prefix + suffix trimming can never overlap or exceed the
    # shortest text in this group — keep the prefix trim as computed and
    # shrink the suffix trim if the two would otherwise collide.
    if prefix_len + suffix_len > shortest:
        suffix_len = max(0, shortest - prefix_len)

    if prefix_len > 0 or suffix_len > 0:
        # This group shares SOMETHING — strip it and stop; the remaining
        # middles are already what gets displayed for this group (not
        # recursed into further, so a nested second layer of commonality
        # within the stripped middles is left alone — deliberately: it
        # already achieved a real reduction, and stopping here keeps the
        # algorithm simple and its output predictable).
        result = {}
        for full, t in pairs:
            end = len(t) - suffix_len
            middle = t[prefix_len:end] if end > prefix_len else ''
            result[full] = middle if middle else full
        return result

    # Nothing at all shared across this whole group — it's actually
    # several distinct groups mixed together (see the screenshot case in
    # the docstring above). Split by first character — guaranteed to
    # produce strictly smaller sub-groups, since prefix_len==0 means at
    # least two texts already differ at position 0 — and recurse on each
    # independently.
    #
    # EXCEPT when the shortest text in this group is already empty (""):
    # that happens either because a spectrum's actual label IS the empty
    # string (e.g. imported from a file with an unnamed/blank header
    # column), or because two labels are identical and nothing remains
    # to bucket. There's no character at position 0 to bucket an empty
    # string on — indexing t[0] on it raised
    # "IndexError: string index out of range" (a real, confirmed crash:
    # e.g. compute_distinguishing_labels(['', 'bb', 'bb', 'a', 'aa'])).
    # Bail out safely for the WHOLE group in that case, falling back to
    # each pair's original full label rather than guessing a partial
    # shortening — correctness over cleverness for this rare edge case.
    if shortest == 0:
        return {full: full for full, _ in pairs}

    buckets = {}
    for full, t in pairs:
        buckets.setdefault(t[0], []).append((full, t))
    result = {}
    for bucket in buckets.values():
        result.update(_shorten_label_group(bucket))
    return result


def make_shortened_name_delegate(list_widget, is_enabled, parent=None):
    """
    Build a reusable paint-only "shorten names" delegate for any
    QListWidget whose items' text() is the full/original spectrum label —
    for dialogs other than the main window (which has its own, separately
    maintained _DistinguishingNameDelegate in main_controller.py, swapped
    in/out by its checkbox). The PyQt import lives inside this function so
    this module stays importable in contexts (like plotting.py) that never
    touch Qt.

    Like the main window's delegate, the returned delegate NEVER touches
    the underlying item text — only initStyleOption() is overridden, so
    painting-critical behavior (selection highlight, hover, fonts) is
    unaffected, and list.item(i).text() everywhere else keeps returning
    the full, original label. Safe to use on any list whose selection is
    read back via Qt.UserRole (identity) rather than by matching displayed
    text — exactly the pattern already used throughout this app (see
    spectrum_identity.py's Golden Rule).

    is_enabled: a zero-arg callable returning whether shortening should
    currently be applied, typically
    `lambda: main_controller.checkBox_shorten_names.isChecked()`. Checked
    live on every paint — install once at dialog-build time (via
    list_widget.setItemDelegate(...)) and it tracks the main window's
    checkbox for as long as the dialog stays open, no swapping needed.

    parent defaults to list_widget itself — Qt's setItemDelegate() does
    NOT take ownership of the delegate, so without a parent (or a kept
    Python reference) the delegate object could be garbage-collected out
    from under the view. Parenting it to the list it decorates keeps it
    alive for exactly as long as that list exists, with no extra
    bookkeeping required from callers.
    """
    from PyQt5.QtWidgets import QStyledItemDelegate

    if parent is None:
        parent = list_widget

    class _ShortenedNameDelegate(QStyledItemDelegate):
        def __init__(self):
            super().__init__(parent)
            self._cache_key = None
            self._cache = {}

        def _shortened_map(self):
            labels = tuple(
                list_widget.item(i).text()
                for i in range(list_widget.count())
            )
            if labels != self._cache_key:
                self._cache = compute_distinguishing_labels(list(labels))
                self._cache_key = labels
            return self._cache

        def initStyleOption(self, option, index):
            super().initStyleOption(option, index)
            if not is_enabled():
                return
            # try/except is deliberate and load-bearing here, not
            # defensive decoration: initStyleOption() is a Qt virtual
            # method override, called directly by Qt's C++ paint
            # machinery -- NOT a plain Python function call. PyQt5's
            # documented behavior for an unhandled Python exception
            # raised inside a virtual method override (or a signal/slot
            # callback) is to report it via sys.excepthook and then
            # abort() the ENTIRE application (SIGABRT) -- with no error
            # dialog, and no visible traceback at all if the app has no
            # attached console (a normal windowed launch). That matches
            # a real, confirmed report of exactly this symptom -- "no
            # error message, the whole app just closes" -- while
            # switching to a tab that made this table paint for the
            # first time. A regular try/except anywhere in the normal
            # Python call chain (e.g. around _compute_results()) cannot
            # catch this, because painting is driven by Qt itself, not
            # by any of this app's own function calls. Falling back to
            # the untouched original text on any failure here is a
            # purely cosmetic degradation -- one paint's worth of
            # display-only shortening not applying -- compared to that.
            try:
                full_text = option.text
                option.text = self._shortened_map().get(full_text, full_text)
            except Exception:
                pass

    return _ShortenedNameDelegate()


def make_display_text_delegate(get_display_map, parent=None):
    """
    Generic paint-only text-substitution delegate for a single column of a
    QTableWidget/QTreeWidget (install via
    `table.setItemDelegateForColumn(col, delegate)`) or any other Qt item
    view. Unlike make_shortened_name_delegate (which derives its own map
    from a QListWidget's current items), this one is handed the map to
    use — the right shape for a results table whose "Spectrum" column
    isn't itself the full population being grouped (e.g. reference
    matching's Results table, where the group is self.selected_spectra,
    not the table rows).

    NEVER touches the underlying cell data — only initStyleOption() is
    overridden, so item.text() / item.data(Qt.DisplayRole) keep returning
    the original text. This is what makes it safe to use even on a table
    whose cell text is read back for Copy / CSV export: those read
    .text() directly, bypassing the delegate entirely, so exports always
    contain full/original labels regardless of what's currently painted
    on screen — exactly the "shorten names is display-only" contract the
    rest of this module maintains.

    get_display_map: zero-arg callable returning a
    {full_text: display_text} dict "right now" — called on every paint,
    so callers whose map depends on live state (e.g. the main window's
    shorten-names checkbox) don't need to reinstall the delegate when
    that state changes.
    """
    from PyQt5.QtWidgets import QStyledItemDelegate

    class _DisplayTextDelegate(QStyledItemDelegate):
        def __init__(self):
            super().__init__(parent)

        def initStyleOption(self, option, index):
            super().initStyleOption(option, index)
            # See the identical try/except in make_shortened_name_delegate
            # above for why this is load-bearing, not defensive
            # decoration: initStyleOption() is called directly by Qt's
            # C++ paint machinery, and PyQt5 aborts the whole application
            # (SIGABRT, no error dialog, no visible traceback without a
            # console) on an unhandled exception raised inside a virtual
            # method override like this one -- confirmed as the cause of
            # a real "app just closes, no error message" report on this
            # exact table (Reference Matching's Results table, columns 0
            # and 2, both painted through this delegate).
            try:
                full_text = option.text
                option.text = get_display_map().get(full_text, full_text)
            except Exception:
                pass

    return _DisplayTextDelegate()


def make_shorten_names_checkbox(text: str = 'Shorten names'):
    """
    Build a standard, unchecked-by-default "Shorten names" QCheckBox for a
    dialog's OWN, independent use.

    Every dialog that displays spectrum labels used to read its shortening
    on/off state from the main window's single shared
    `main_controller.checkBox_shorten_names` — meaning toggling it in the
    main window silently affected every currently-open dialog too, and no
    dialog could have its own setting. Each dialog now gets its own
    instance of this checkbox instead, with its own independent state,
    starting unchecked regardless of the main window's current setting.
    Centralizing the label text and tooltip here keeps wording consistent
    across every dialog using it rather than each one drifting slightly.

    The caller is responsible for adding the returned checkbox to its own
    layout and connecting its stateChanged signal to whatever refresh is
    needed (e.g. a QListWidget/table viewport repaint for a paint-only
    delegate consumer via make_shortened_name_delegate /
    make_display_text_delegate — usually near-instant already, an explicit
    .viewport().update() just avoids waiting on the next unrelated repaint
    — or a full replot() call for a matplotlib legend/axis-label consumer,
    which has no other trigger to notice the change).
    """
    from PyQt5.QtWidgets import QCheckBox

    cb = QCheckBox(text)
    cb.setChecked(False)
    cb.setToolTip(
        "Shorten this dialog's own spectrum labels, showing only the part "
        "that differs from every other spectrum listed here. Independent "
        "of the main window's Shorten Names setting — each dialog has its "
        "own on/off state. Purely cosmetic: the spectrum's actual name is "
        "never changed, and any new spectrum this dialog creates (Apply, "
        "Add as New, Save, etc.) always uses the full original name."
    )
    return cb


def shorten_spectra_labels(spectra, enabled):
    """
    Convenience wrapper for the common case: given a list of spectrum
    dicts and whether shortening is currently enabled (read this from
    the main window's checkBox_shorten_names.isChecked()), return a
    {full_label: display_label} map ready to use for plot legends, axis
    tick labels, table rows, etc.

    When enabled is False, or there are fewer than 2 spectra, returns
    {s['label']: s['label'] for s in spectra} — i.e. every label maps to
    itself, so callers can use this map unconditionally
    (`display_map.get(spectrum['label'], spectrum['label'])`) without an
    extra branch for the disabled case.
    """
    labels = [s.get('label', '') for s in spectra]
    if not enabled:
        return {label: label for label in labels}
    shortened = compute_distinguishing_labels(labels)
    return {label: shortened.get(label, label) for label in labels}
