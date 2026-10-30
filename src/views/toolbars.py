# src/views/toolbars.py
"""The buttons under the menu bar, in groups as in other scientific programs
(e.g. Origin): each group is a tool bar of its own that can be hidden -
View > Toolbars, or a right-click on the buttons - and the buttons can show
their text or only the icon. "Text on the buttons: Automatic" (the default)
leaves the text out group by group (Analysis first) when the window is too
narrow for all buttons, so no button is hidden behind the "»" of a tool bar.
The choices are remembered.

  Main:                     Import data, Open snapshot, Save, Help | Copy plot
  Spectra processing:       Data range, Smoothing, Baseline, Normalization
  Analysis & visualization: Peak list, Peak Fitting, SVD analysis, 2D map,
                            Group Statistics, Data table

Every button is the same QAction as its menu entry, so both always do the
same. The menus of Spectra processing and Analysis & Visualization get
icons for all their entries (menu_icons)."""
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QAction, QActionGroup, QLabel, QMenu, QStyle, QToolBar, QToolButton

from src.views import icons

PREFERENCES_KEY = 'toolbars'
HIDEABLE = ('main', 'processing', 'analysis')
TEXT_MODES = (('auto', "Automatic (when there is room)"), ('always', "Always"),
              ('never', "Never - only the icons"))

STYLE = """
QToolBar { spacing: 3px; padding: 2px 4px; border: none; }
QToolBar QToolButton {
    border: 1px solid #b9c0c8; border-radius: 4px; padding: 3px 8px; margin: 1px;
    background: #f7f8fa; }
QToolBar QToolButton:hover { background: #e7f0fb; border-color: #5b9bd5; }
QToolBar QToolButton:pressed { background: #d4e4f7; }
QToolBar QToolButton:disabled { color: #9aa0a6; background: #f1f2f4; border-color: #dde1e5; }
QToolBar QToolButton[popupMode="1"] { padding-right: 18px; }
QToolBar QToolButton#qt_toolbar_ext_button { border: none; background: transparent;
    padding: 0px; margin: 0px 1px; }
QToolBar QLabel#toolbarGroupLabel { color: #6b7480; font-size: 8pt; padding: 0px 2px 0px 6px; }
"""

# (action attribute, button text, icon, tooltip) of the tool buttons
PROCESSING = (
    ('actionMenuOpsDataRange', "Data range", icons.data_range_icon,
     "Data range: keep a part of the x axis (cut the spectra)"),
    ('actionMenuOpsSGSmoothing', "Smoothing", icons.smoothing_icon,
     "Savitzky–Golay smoothing: less noise, the bands keep their shape"),
    ('actionMenuOpsAutomatedBaseline', "Baseline", icons.baseline_icon,
     "Baseline correction (automated): remove a sloping or curved background"),
    ('actionMenuOpsNormalization', "Normalization", icons.normalization_icon,
     "Normalization: bring the spectra to the same scale (maximum, area, a band, …)"),
)
ANALYSIS = (
    ('actionMenuPeakList', "Peak list", icons.peak_list_icon,
     "Peak list: every peak of the selected spectra in a table - positions, heights, widths; "
     "a band table and a plot through a series"),
    ('actionMenuPeakFitting', "Peak Fitting", icons.peak_fitting_icon,
     "Peak Fitting: split the spectra into bands (Gaussian, Lorentzian, …) - also "
     "overlapping bands and shoulders"),
    ('actionMenuSVDAnalysis', "SVD analysis", icons.svd_analysis_icon,
     "SVD analysis: how many independent components the spectra contain, and what they "
     "look like"),
    ('actionMenu2DMap', "2D map", icons.map2d_icon,
     "2D map: a value of every spectrum (pixel) as a map - intensity, a band, a fitted peak"),
    ('actionMenuGroupStatistics', "Group Statistics", icons.group_statistics_icon,
     "Group Statistics: do groups of spectra differ? A value per spectrum, the test, plots"),
    ('actionMenuDataTable', "Data table", icons.table_icon,
     "Data table: the selected spectra as a table - copy to Excel, formulas, values per "
     "spectrum and plots"),
)

# icons of the other menu entries (object name -> icon)
MENU_ICONS = {
    'actionMenuOpsManualBaseline': icons.manual_baseline_icon,
    'actionMenuOpsAutomatedBaseline': icons.baseline_icon,
    'actionMenuOpsSNIPBaseline': icons.snip_baseline_icon,
    'actionMenuOpsSVDBackground': icons.svd_background_icon,
    'actionMenuOpsSGSmoothing': icons.smoothing_icon,
    'actionMenuOpsFFTDenoising': icons.fft_denoising_icon,
    'actionMenuOpsDataRange': icons.data_range_icon,
    'actionMenuOpsCombineSpectra': icons.combine_spectra_icon,
    'actionMenuOpsInteractiveSubtraction': icons.interactive_subtraction_icon,
    'actionMenuOpsXAxisAlignment': icons.x_alignment_icon,
    'actionMenuOpsSVDInterpolation': icons.svd_interpolation_icon,
    'actionMenuOpsSpectralCalculator': icons.spectral_calculator_icon,
    'actionMenuOpsNormalization': icons.normalization_icon,
    'actionMenuOpsCDUnitConversion': icons.cd_conversion_icon,
    'actionMenuOpsXAxisUnitConversion': icons.x_unit_conversion_icon,
    'actionMenuOpsMeanCentering': icons.mean_centering_icon,
    'actionMenuOpsSpikeRemoval': icons.spike_removal_icon,
    'actionMenuOpsCosmicRayRemoval': icons.cosmic_ray_icon,
    'actionMenuOpsResolutionEnhancement': icons.resolution_icon,
    'actionMenuOpsRunBatchPipeline': icons.run_pipeline_icon,
    'actionMenuOpsSaveBatchPipeline': icons.save_pipeline_icon,
    'actionMenuSVDAnalysis': icons.svd_analysis_icon,
    'actionMenuPCAScores': icons.pca_icon,
    'actionMenuNMF': icons.nmf_icon,
    'actionMenuMCRALS': icons.mcr_icon,
    'actionMenuClusterAnalysis': icons.cluster_icon,
    'actionMenuSOM': icons.som_icon,
    'actionMenu2DMap': icons.map2d_icon,
    'actionMenu2DCorrelation': icons.correlation2d_icon,
    'actionMenuPLS': icons.pls_icon,
    'actionMenuPeakList': icons.peak_list_icon,
    'actionMenuPeakFitting': icons.peak_fitting_icon,
    'actionMenuBandRatio': icons.band_ratio_icon,
    'actionMenuReferenceMatching': icons.reference_matching_icon,
    'actionMenuMeltingCurve': icons.melting_curve_icon,
    'actionMenuIsosbesticPoint': icons.isosbestic_icon,
    'actionMenuKineticsFitting': icons.kinetics_icon,
    'actionMenuQCOutlier': icons.qc_outlier_icon,
    'actionMenuGroupStatistics': icons.group_statistics_icon,
    'actionMenuDataTable': icons.table_icon,
    'actionMenuMixtureAnalysis': icons.mixture_icon,
}
# the sub-menus get the icon of a typical entry
SUBMENU_ICONS = {
    'Baseline Correction': icons.baseline_icon, 'Smoothing': icons.smoothing_icon,
    'Data Manipulation': icons.data_range_icon,
    'Axis && Unit Conversion': icons.x_unit_conversion_icon,
    'Spike Removal': icons.spike_removal_icon, 'Resolution': icons.resolution_icon,
    'Batch Pipeline': icons.pipeline_icon, 'Visualization': icons.map2d_icon,
    'Data Analysis': icons.peak_fitting_icon,
}


# ----------------------------------------------------------------- remembered
def saved():
    out = {k: True for k in HIDEABLE}
    out['text'] = 'auto'
    try:
        from src.modules.misc.session_files import Preferences
        stored = Preferences().get(PREFERENCES_KEY, {}) or {}
        out.update({k: bool(v) for k, v in stored.items() if k in HIDEABLE})
        text = stored.get('text', 'auto')
        out['text'] = text if text in dict(TEXT_MODES) else 'auto'
    except Exception:
        pass
    return out


def save(choice):
    try:
        from src.modules.misc.session_files import Preferences
        Preferences().set(PREFERENCES_KEY, dict(choice))
    except Exception:
        pass


# ----------------------------------------------------------------- building
def _toolbar(view, name, title):
    tb = QToolBar(title, view)
    tb.setObjectName(name)
    tb.setMovable(False)
    tb.setFloatable(False)
    tb.setIconSize(QSize(16, 16))
    tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    tb.setStyleSheet(STYLE)
    view.addToolBar(Qt.TopToolBarArea, tb)
    return tb


def _group_label(tb, text):
    label = QLabel(text)
    label.setObjectName("toolbarGroupLabel")
    tb.addWidget(label)
    return label


def _add_tools(view, tb, tools):
    for attr, text, icon, tip in tools:
        action = getattr(view, attr)
        action.setIconText(text)
        action.setIcon(icon())
        action.setToolTip(tip)
        action.setStatusTip(tip)
        tb.addAction(action)
        name = ''.join(w[:1].upper() + w[1:] for w in text.split())   # DataRange, PeakList
        tb.widgetForAction(action).setObjectName(f"toolbar{name}Button")


def build(view):
    """The four tool bars, the menu icons and View > Toolbars."""
    # Main: Import data (click: New; the arrow: New / Add to current), Open
    # snapshot, Save (Copy plot is added by the controller, which makes it)
    tb = _toolbar(view, "mainToolBar", "Main buttons (Import, Open snapshot, Save, Help, Copy plot)")
    view.mainToolBar = tb
    imp = QToolButton(view)
    imp.setObjectName("toolbarImportButton")
    imp.setText("Import data")
    imp.setIcon(view.style().standardIcon(QStyle.SP_DirOpenIcon))
    imp.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    imp.setToolTip("Import data files instead of the current spectra  [Ctrl+I]\n"
                   "The arrow: New… or Add to current…  [Ctrl+Shift+I]")
    imp.setMenu(view.menuImport)
    imp.setPopupMode(QToolButton.MenuButtonPopup)
    imp.clicked.connect(view.actionImport_new.trigger)
    tb.addWidget(imp)
    view.toolbarImportButton = imp
    for action, text, key in ((view.actionImport_Snapshot, "Open snapshot", "Ctrl+O"),
                              (view.actionSave, "Save", "Ctrl+S")):
        action.setIconText(text)                   # the button: without the menu's "…"
        action.setToolTip(f"{action.statusTip()}  [{key}]")
        tb.addAction(action)
        tb.widgetForAction(action).setObjectName(f"toolbar{text.replace(' ', '')}Button")

    # Help right after Save: near the eyes (the Help menu)
    help_btn = QToolButton(view)
    help_btn.setObjectName("toolbarHelpButton")
    help_btn.setText("Help")
    help_btn.setIcon(icons.help_icon())
    help_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    help_btn.setMenu(view.menuHelp)
    help_btn.setPopupMode(QToolButton.InstantPopup)
    help_btn.setToolTip("User Guide, Quick Start, the help of every tool, test datasets, "
                        "What's New, Run tests, About")
    view.toolbarHelpAction = tb.addWidget(help_btn)
    view.toolbarHelpButton = help_btn
    view.helpToolBar = None                        # (Help is one of the main buttons)

    view.processingToolBar = _toolbar(view, "processingToolBar", "Spectra processing")
    view.processingGroupLabel = _group_label(view.processingToolBar, "Processing")
    _add_tools(view, view.processingToolBar, PROCESSING)

    view.analysisToolBar = _toolbar(view, "analysisToolBar", "Analysis && visualization")
    view.analysisGroupLabel = _group_label(view.analysisToolBar, "Analysis")
    _add_tools(view, view.analysisToolBar, ANALYSIS)

    apply_menu_icons(view)
    _build_toolbars_menu(view)
    apply_help_icons(view)
    view.menuHelp.aboutToShow.connect(lambda: apply_help_icons(view))


def apply_menu_icons(view):
    for name, make in MENU_ICONS.items():
        action = getattr(view, name, None)
        if action is not None:
            action.setIcon(make())
    for menu in (getattr(view, 'menuSpectraProcessingOps', None),
                 getattr(view, 'menuAnalysisVisualization', None)):
        if menu is None:
            continue
        for action in menu.actions():
            sub = action.menu()
            if sub is not None and sub.title() in SUBMENU_ICONS:
                action.setIcon(SUBMENU_ICONS[sub.title()]())


# the Help menu: its own entries, and the help of each tool with the icon
# of that tool (found by its name in the menus)
HELP_ICONS = {
    'actionUserGuide': icons.book_icon, 'actionQuickStart': icons.quick_start_icon,
    'actionWhatsNew': icons.whats_new_icon, 'actionKeyboardShortcuts': icons.keyboard_icon,
    'actionInstallationHelp': icons.installation_icon,
    'actionDeveloperGuide': icons.developer_icon, 'actionOur_Group': icons.group_icon,
    'actionOur_Institute': icons.institute_icon, 'actionLicense': icons.license_icon,
    'actionRunTests': icons.run_tests_icon, 'actionAbout': icons.about_icon,
    'actionOpenSyntheticFolder': icons.folder_icon, 'actionOpenRealFolder': icons.folder_icon,
    'actionDownloadLargeDatasets': icons.download_icon,
    'actionBatchPipelineHelp': icons.pipeline_icon,
}
DATASET_ICONS = {'Synthetic': icons.synthetic_data_icon,
                 'Real (measured)': icons.measured_data_icon}
HELP_SUBMENU_ICONS = {
    'Spectra Processing': icons.smoothing_icon,
    'Spectra Analysis && Visualization': icons.map2d_icon,
    'Test datasets': icons.datasets_icon,
}


def _plain(text):
    return ''.join(ch for ch in text.lower() if ch.isalnum())


def apply_help_icons(view):
    """Icons in the Help menu (also its sub-menus made later, e.g. the test
    datasets): set when the menu opens, only where an entry has none."""
    help_menu = getattr(view, 'menuHelp', None)
    if help_menu is None:
        return
    by_name = {}                                  # tool name -> its menu icon
    for menu in (getattr(view, 'menuSpectraProcessingOps', None),
                 getattr(view, 'menuAnalysisVisualization', None)):
        stack = [menu] if menu is not None else []
        while stack:
            m = stack.pop()
            for a in m.actions():
                if a.menu() is not None:
                    stack.append(a.menu())
                elif not a.icon().isNull():
                    by_name.setdefault(_plain(a.text()), a.icon())
    cache = view.__dict__.setdefault('_help_icon_cache', {})

    def make(fn):
        if fn not in cache:
            cache[fn] = fn()
        return cache[fn]

    def walk(menu, in_datasets):
        for a in menu.actions():
            if a.isSeparator():
                continue
            sub = a.menu()
            title = sub.title() if sub is not None else ''
            if a.icon().isNull():
                fn = HELP_ICONS.get(a.objectName())
                if fn is None and sub is not None:
                    fn = (DATASET_ICONS.get(title) if in_datasets else
                          HELP_SUBMENU_ICONS.get(title) or SUBMENU_ICONS.get(title))
                if fn is not None:
                    a.setIcon(make(fn))
                elif sub is None and not in_datasets and _plain(a.text()) in by_name:
                    a.setIcon(by_name[_plain(a.text())])
                # (the datasets themselves and their groups: no icons - a long
                # list reads better without them)
            if sub is not None:
                walk(sub, in_datasets or title == 'Test datasets')
    walk(help_menu, False)


def tool_bars(view):
    """{key: tool bar} of the tool bars that can be hidden."""
    return {'main': view.mainToolBar, 'processing': view.processingToolBar,
            'analysis': view.analysisToolBar}


def _build_toolbars_menu(view):
    """View > Toolbars: one tick per group, and the text on the buttons."""
    menu = QMenu("Toolbars", view.menuView)
    menu.setObjectName("menuToolbars")
    choice = saved()
    for key, tb in tool_bars(view).items():
        act = tb.toggleViewAction()
        act.setText({'main': "Main buttons (Import, Open snapshot, Save, Help, Copy plot)",
                     'processing': "Spectra processing",
                     'analysis': "Analysis && visualization"}[key])
        tb.setVisible(choice[key])
        act.triggered.connect(lambda on, k=key: _remember(view, k, on))
        menu.addAction(act)
    menu.addSeparator()
    text_menu = QMenu("Text on the buttons", menu)
    text_menu.setObjectName("menuToolbarText")
    group = QActionGroup(text_menu)
    view.toolbarTextActions = {}
    for mode, label in TEXT_MODES:
        act = QAction(label, text_menu, checkable=True)
        act.setObjectName(f"actionToolbarText_{mode}")
        act.setChecked(mode == choice['text'])
        group.addAction(act)
        text_menu.addAction(act)
        act.triggered.connect(lambda _on=False, m=mode: set_text_mode(view, m, remember=True))
        view.toolbarTextActions[mode] = act
    menu.addMenu(text_menu)
    view.menuToolbarText = text_menu
    menu.addSeparator()
    reset = QAction("Back to the default (all groups, text: Automatic)", menu)
    reset.setObjectName("actionToolbarsDefault")
    reset.triggered.connect(lambda _on=False: reset_to_default(view))
    menu.addAction(reset)
    view.actionToolbarsDefault = reset
    view.menuToolbars = menu
    view.menuView.addMenu(menu)
    view.toolbarTextMode = choice['text']
    for tb in tool_bars(view).values():
        tb.visibilityChanged.connect(lambda *_: fit(view))
    fit(view)


def reset_to_default(view):
    """All groups shown, text Automatic; the stored choice is forgotten."""
    try:
        from src.modules.misc.session_files import Preferences
        Preferences().remove(PREFERENCES_KEY)
    except Exception:
        pass
    for tb in tool_bars(view).values():
        tb.setVisible(True)
    set_text_mode(view, 'auto')


def _remember(view, key, value):
    choice = saved()
    choice[key] = value
    save(choice)


def _set_style(view, tb, text):
    style = Qt.ToolButtonTextBesideIcon if text else Qt.ToolButtonIconOnly
    if tb.toolButtonStyle() != style:
        tb.setToolButtonStyle(style)
    for btn in (view.toolbarImportButton, view.toolbarHelpButton):
        if btn.parentWidget() is tb or tb.isAncestorOf(btn):
            btn.setToolButtonStyle(style)


def set_text_mode(view, mode, remember=False):
    """'auto', 'always' or 'never' (View > Toolbars > Text on the buttons)."""
    view.toolbarTextMode = mode if mode in dict(TEXT_MODES) else 'auto'
    for m, act in getattr(view, 'toolbarTextActions', {}).items():
        act.setChecked(m == view.toolbarTextMode)
    if remember:
        _remember(view, 'text', view.toolbarTextMode)
    fit(view)


def set_text(view, on):
    """Text beside the icons on every button (True) or only the icons."""
    set_text_mode(view, 'always' if on else 'never')


def _width(view, tb, text):
    """The width tool bar `tb` needs with or without the text (kept)."""
    cache = view.__dict__.setdefault('_toolbar_widths', {})
    key = (tb.objectName(), text, len(tb.actions()))       # (a button added: measure again)
    if key not in cache:
        before = tb.toolButtonStyle() == Qt.ToolButtonTextBesideIcon
        _set_style(view, tb, text)
        tb.layout().invalidate()                           # the size with this style, now
        cache[key] = tb.sizeHint().width()
        _set_style(view, tb, before)
        tb.layout().invalidate()
    return cache[key]


def fit(view):
    """Text on the buttons where there is room: in Automatic mode the
    groups lose their text one after another (Analysis, Processing, the
    main buttons) until all buttons fit in the window. Afterwards (when the
    tool bars are laid out) a group whose last buttons still went behind its
    "»" loses its text too - so the result is right even where the measured
    widths are not (e.g. before the window is first drawn)."""
    if getattr(view, 'analysisToolBar', None) is None:
        return
    bars = [view.analysisToolBar, view.processingToolBar, view.mainToolBar]
    shown = [tb for tb in bars if not tb.isHidden()]
    mode = getattr(view, 'toolbarTextMode', 'auto')
    if mode != 'auto':
        for tb in bars:
            _set_style(view, tb, mode == 'always')
        return
    if not view.isVisible():
        return                         # measured when shown (the style sheets applied)
    room = view.width() - 12
    text = {tb: True for tb in shown}
    for tb in shown:                         # drop the text group by group
        if sum(_width(view, b, text[b]) for b in shown) <= room:
            break
        text[tb] = False
    for tb in bars:
        _set_style(view, tb, text.get(tb, True))
    _check_later(view)


def _check_later(view, rounds=3):
    """After the tool bars are laid out again (a moment later)."""
    from PyQt5.QtCore import QTimer
    timer = getattr(view, '_toolbar_check', None)
    if timer is None:
        timer = view._toolbar_check = QTimer(view)
        timer.setSingleShot(True)
        timer.setInterval(80)
        timer.timeout.connect(lambda: _no_overflow(view, view._toolbar_check_rounds))
    view._toolbar_check_rounds = rounds
    timer.start()                              # (again: the last change counts)


def _overflowing(tb):
    """Some of its buttons do not fit (they are behind its "»")."""
    return tb.width() + 2 < tb.sizeHint().width()


def _no_overflow(view, rounds=3):
    """Automatic mode: while a group hides buttons behind its "»", the
    next group still with text shows only icons (the measured widths were
    off: measure again next time)."""
    try:
        if getattr(view, 'toolbarTextMode', 'auto') != 'auto' or not view.isVisible():
            return
        bars = [view.analysisToolBar, view.processingToolBar, view.mainToolBar]
    except RuntimeError:                     # the window is gone
        return
    if not any(_overflowing(tb) for tb in bars if not tb.isHidden()):
        return
    view.__dict__.pop('_toolbar_widths', None)
    for tb in bars:
        if not tb.isHidden() and tb.toolButtonStyle() == Qt.ToolButtonTextBesideIcon:
            _set_style(view, tb, False)
            break
    else:
        return
    if rounds > 1:
        _check_later(view, rounds - 1)


def popup_menu(view):
    """The right-click menu of the tool bars (QMainWindow.createPopupMenu)."""
    menu = QMenu(view)
    menu.addActions(view.menuToolbars.actions())
    return menu
