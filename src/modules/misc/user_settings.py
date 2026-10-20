# src/modules/misc/user_settings.py
"""File -> Settings and saved items...: everything SpecAnalytiXBase remembers on
this computer between sessions, in one place (no Qt here; the window is
src/views/dialogs/misc/settings_dialog.py).

Two kinds, kept apart on purpose:
* Settings (preferences.json): each with its current and default value; they
  can be reset to the default, selected ones or all.
* Saved items the user built up: normalization presets, import profiles,
  batch pipelines, the Open recent list and automatic saves of earlier
  sessions. Resetting the settings never touches them; they are deleted only
  one by one, on purpose. Installing, updating or uninstalling the program
  does not touch either kind.

Both are shared by every copy of the program of this Windows user (installed
or run from source)."""

import os
import sys

from src.modules.misc.session_files import (DEFAULT_AUTOSAVE_MINUTES, Preferences,
                                            RecentFiles, app_data_dir)


# --- settings ------------------------------------------------------------------------

class Setting:
    """One row of the Settings table: one value the user can change.

    kind: 'choice' (options = [(value, text)]), 'bool', 'int' or 'float'
    (options = dict(minimum=, maximum=, step=, decimals=, suffix=)).
    get(prefs) / put(prefs, value) read and store it; `effect` names what the
    open program has to update when it changes (MainController.settings_changed)."""

    def __init__(self, sid, group, label, kind, default, get, put, options=None,
                 effect=None, note=''):
        self.id, self.group, self.label, self.kind = sid, group, label, kind
        self.default, self._get, self._put = default, get, put
        self.options, self.effect, self.note = options, effect, note

    def value(self, prefs):
        return self._get(prefs)

    def set(self, prefs, value):
        self._put(prefs, value)

    def changed(self, prefs):
        v, d = self.value(prefs), self.default
        if self.kind == 'float':
            return abs(float(v) - float(d)) > 1e-9
        return v != d

    def text(self, value):
        """A value as people read it."""
        if self.kind == 'bool':
            return 'on' if value else 'off'
        if self.kind == 'choice':
            return dict(self.options).get(value, str(value))
        if self.kind == 'float':
            return f"{float(value):g}{self.options.get('suffix', '')}"
        return f"{value}{self.options.get('suffix', '')}"

    def current_text(self, prefs):
        return self.text(self.value(prefs))

    @property
    def default_text(self):
        return self.text(self.default)


def _key(key, default, convert=lambda v: v):
    """get / put for a value stored under its own key."""
    def get(prefs):
        try:
            return convert(prefs.get(key, default))
        except (TypeError, ValueError):
            return default

    def put(prefs, value):
        if value == default:
            prefs.remove(key)
        else:
            prefs.set(key, value)
    return get, put


def _in_dict(key, sub, normalize, defaults):
    """get / put for one entry of a settings dictionary (e.g. the peak-fit
    map's Fit settings); the dictionary is removed when all are default."""
    def get(prefs):
        stored = prefs.get(key, {})
        return normalize(stored if isinstance(stored, dict) else {})[sub]

    def put(prefs, value):
        stored = prefs.get(key, {})
        s = normalize(stored if isinstance(stored, dict) else {})
        s[sub] = value
        s = normalize(s)
        if s == normalize({}):
            prefs.remove(key)
        else:
            prefs.set(key, {k: v for k, v in s.items() if k in defaults})
    return get, put


def _autosave_get(prefs):
    return prefs.autosave_minutes()


def _cd_limits(index):
    def get(prefs):
        return prefs.cd_quality_limits()[index]
    key = ('cd_ht_limit_V', 'cd_abs_limit')[index]
    from src.modules.data_io.cd_quality import DEFAULT_ABS_LIMIT, DEFAULT_HT_LIMIT_V
    default = (DEFAULT_HT_LIMIT_V, DEFAULT_ABS_LIMIT)[index]

    def put(prefs, value):
        if abs(float(value) - default) < 1e-9:
            prefs.remove(key)
        else:
            prefs.set(key, float(value))
    return get, put


def _whats_new():
    from src.version import __version__

    def get(prefs):
        return prefs.get('whats_new_hidden_for') != __version__

    def put(prefs, show):
        if show:
            prefs.remove('whats_new_hidden_for')
        else:
            prefs.set('whats_new_hidden_for', __version__)
    return get, put


def _build_settings():
    from src.modules.visualization import large_selection as ls
    from src.modules.visualization_analysis import peak_fit_map as pf
    from src.modules.utils.parallel_utils import max_worker_count
    from src.modules.data_io.cd_quality import DEFAULT_ABS_LIMIT, DEFAULT_HT_LIMIT_V
    from src.views.theme import THEMES
    large = lambda sub: _in_dict('large_plot_settings', sub, ls.normalized_settings,
                                 ls.DEFAULT_SETTINGS)
    shared = ('processing_mode', 'max_workers')       # -> Parallel processing (all tools)

    def pf_norm(d):
        return {k: v for k, v in pf.normalized_settings(d).items() if k not in shared}
    pf_defaults = {k: v for k, v in pf.DEFAULT_SETTINGS.items() if k not in shared}
    peak = lambda sub: _in_dict('peak_fit_map_settings', sub, pf_norm, pf_defaults)
    g_many = 'Plotting many spectra (View \u203a Plotting many spectra\u2026)'
    g_cd = 'CD data quality (View \u203a CD data quality)'
    g_pf = '2D Map peak-fit maps (Fit settings\u2026)'
    g_mr = 'Methods report for publications (File \u203a Methods report for publication)'
    g_par = 'Parallel processing (all tools that use several processor cores)'
    return [
        Setting('autosave', 'Automatic saving (File \u203a Automatic saving)',
                'Automatic saving (File \u203a Automatic saving)',
                'choice', DEFAULT_AUTOSAVE_MINUTES, _autosave_get,
                _key('autosave_minutes', DEFAULT_AUTOSAVE_MINUTES)[1],
                options=[(0, 'off')] + [(m, f'every {m} minutes') for m in (5, 10, 20)],
                effect='autosave'),
        Setting('large_max_drawn', g_many, 'Overlay, Grid and Waterfall plots draw at most',
                'int', ls.DEFAULT_SETTINGS['max_drawn'], *large('max_drawn'),
                options=dict(minimum=10, maximum=10_000_000, step=100, suffix=' spectra'),
                effect='large_plot'),
        Setting('large_mode', g_many, 'With more spectra selected, draw', 'choice',
                ls.DEFAULT_SETTINGS['mode'], *large('mode'),
                options=[('preview', 'that many, evenly spread'), ('all', 'all of them')],
                effect='large_plot'),
        Setting('large_dialog_count', g_many, 'Tool windows draw at most', 'int',
                ls.DEFAULT_DIALOG_COUNT,
                *_key('large_plot_dialog_count', ls.DEFAULT_DIALOG_COUNT, ls.normalized_dialog_count),
                options=dict(minimum=10, maximum=10_000_000, step=10, suffix=' spectra'),
                effect='large_plot'),
        Setting('cd_shading', g_cd, 'Shade unreliable CD regions', 'bool', True,
                *_key('cd_quality_shading', True, bool), effect='cd_quality'),
        Setting('cd_ht', g_cd, 'HT (detector voltage) limit', 'float', DEFAULT_HT_LIMIT_V,
                *_cd_limits(0), options=dict(minimum=100, maximum=2000, step=10, decimals=0,
                                             suffix=' V'), effect='cd_quality'),
        Setting('cd_abs', g_cd, 'Absorbance limit', 'float', DEFAULT_ABS_LIMIT, *_cd_limits(1),
                options=dict(minimum=0.1, maximum=10, step=0.1, decimals=2), effect='cd_quality'),
        Setting('import_preview', 'Import dialog: plot preview', 'Import dialog: plot preview',
                'bool', True,
                *_key('import_plot_preview', True, bool)),
        Setting('pf_shape', g_pf, 'Peak shape', 'choice', pf.DEFAULT_SETTINGS['shape'],
                *peak('shape'), options=[(v, v) for v in pf.SHAPES]),
        Setting('pf_baseline', g_pf, 'Background', 'choice', pf.DEFAULT_SETTINGS['baseline'],
                *peak('baseline'), options=[(v, v) for v in pf.BASELINES]),
        Setting('pf_min_r2', g_pf, 'Hide fits with R\u00b2 below (0 = show all)', 'float',
                pf.DEFAULT_SETTINGS['min_r2'], *peak('min_r2'),
                options=dict(minimum=0, maximum=1, step=0.05, decimals=2)),
        Setting('pf_min_band_points', g_pf, 'Reject bands narrower than', 'choice',
                float(pf.DEFAULT_SETTINGS['min_band_points']), *peak('min_band_points'),
                options=[(float(n), 'off' if n == 0 else f'{n} data points')
                         for n in pf.MIN_BAND_POINTS_CHOICES]),
        Setting('parallel_mode', g_par, 'Processing', 'choice', 'auto',
                *_key('parallel_processing_mode', 'auto',
                      lambda v: v if v in ('auto', 'serial', 'parallel') else 'auto'),
                options=[('auto', 'automatic'), ('serial', 'serial (one core)'),
                         ('parallel', 'parallel (several cores)')]),
        Setting('parallel_workers', g_par, 'Parallel workers (0 = all cores)', 'int', 0,
                *_key('parallel_max_workers', 0, lambda v: max(0, int(v))),
                options=dict(minimum=0, maximum=max_worker_count(), step=1)),
        Setting('mr_table', g_mr, 'Include the parameter table when the report is copied or saved',
                'bool', True,
                *_key('methods_report_include_table', True, bool)),
        Setting('mr_refs', g_mr, 'Include the references when the report is copied or saved',
                'bool', True,
                *_key('methods_report_include_references', True, bool)),
        Setting('theme', 'Theme (View \u203a Theme)', 'Theme (View \u203a Theme)', 'choice', 'light',
                *_key('theme', 'light', lambda v: v if v in THEMES else 'light'),
                options=[('light', 'light'), ('dark', 'dark')], effect='theme',
                note='used from the next start'),
        Setting('whats_new', "What's New window at the start (Help \u203a What's New)",
                "What's New window at the start (Help \u203a What's New)", 'bool', True,
                *_whats_new()),
    ]


SETTINGS = _build_settings()

# What each setting does, for people (tooltip in the window, and the table in
# the User Guide, section "Settings and Saved Items"), and where to read more.
HELP = {
    'autosave': ("How often the program saves your current work in the background, so that it "
                 "can be restored after a crash or power cut (the next start offers it). Off: "
                 "never. Saving a snapshot yourself (File \u203a Save) is not affected.",
                 'help://user_guide#autosave'),
    'large_max_drawn': ("Drawing is slow (about 5 s per 1 000 spectra), so the Overlay, Grid and "
                        "Waterfall plots draw at most this many spectra. Up to this many "
                        "selected: all are drawn. More selected: this many, evenly spread (a "
                        "preview). Operations and analyses always use all selected spectra.",
                        'help://plot_controls#many-spectra'),
    'large_mode': ("When more spectra are selected: a preview of that many evenly spread spectra "
                   "(quick), or all of them \u2014 the Overlay plot then in portions, with a "
                   "progress window and Stop.", 'help://plot_controls#many-spectra'),
    'large_dialog_count': ("Tool windows (FFT Denoising, X-axis alignment, Isosbestic points, "
                           "Normalization, Data range, \u2026) draw at most this many spectra, "
                           "evenly spread; their calculations always use all of them.",
                           'help://plot_controls#many-spectra'),
    'cd_shading': ("After importing JASCO CD data, wavelengths where the detector got too little "
                   "light are shaded grey in the plots: the CD signal there is unreliable.",
                   'help://import#cd-quality'),
    'cd_ht': ("A wavelength counts as unreliable where the detector voltage (HT) is above this "
              "limit.", 'help://import#cd-quality'),
    'cd_abs': ("\u2026 or where the absorbance is above this limit.", 'help://import#cd-quality'),
    'import_preview': ("The Import dialog draws the spectra exactly as they will be imported with "
                       "the current settings. Switch it off to make the dialog quicker with very "
                       "large files.", 'help://import#plot-preview'),
    'pf_shape': ("The band shape fitted in every pixel for the fitted metrics of the 2D Map "
                 "(Fitted peak position, FWHM, height, area, R\u00b2).", 'help://map2d#peak-fit'),
    'pf_baseline': ("The background fitted under the band: none, constant or linear (sloping).",
                    'help://map2d#peak-fit'),
    'pf_min_r2': ("Pixels whose fit describes the data worse than this (R\u00b2 from 0 to 1) are "
                  "left blank. 0 shows every fit.", 'help://map2d#peak-fit'),
    'pf_min_band_points': ("Fits narrower than this many data points are taken as spikes (cosmic "
                           "rays, single noisy points), not as bands, and set aside.",
                           'help://map2d#peak-fit'),
    'parallel_mode': ("How the tools that can use several processor cores compute: Automated "
                      "Baseline, X-axis alignment, the 2D Map's peak-fit maps and bootstrap "
                      "uncertainty (NMF, MCR-ALS). Automatic: several cores only when it saves "
                      "time. Serial: one core (e.g. to keep the computer free for other work). "
                      "Parallel: always several cores. A tool's own window can change it for the "
                      "session; this is where the tools start from.",
                      'help://user_guide#parallel-workers'),
    'parallel_workers': ("How many processor cores (worker processes) may be used at most; 0 = "
                         "all cores. Fewer leave the computer more responsive and need less "
                         "memory.", 'help://user_guide#parallel-workers'),
    'mr_table': ("File \u203a Methods report for publication drafts the paragraph about the data "
                 "processing for a paper's Methods section. On: when you copy the report or save "
                 "it (Word, HTML, Markdown, text), the parameter table (every operation with its "
                 "settings) is included.", 'help://methods_report'),
    'mr_refs': ("On: when you copy or save the Methods report, the list of references (the "
                "original papers of the methods used) is included.", 'help://methods_report'),
    'theme': ("Light or dark colours for the program's windows; plots stay white. Used from the "
              "next start.", 'help://user_guide#theme'),
    'whats_new': ("At the start of a new version, a small window lists what is new. Off: not "
                  "shown again for this version (Help \u203a What's New opens it any time).",
                  'help://whats_new'),
}


def help_table_html():
    """The table of all settings for the User Guide (section Settings and
    Saved Items), from the same texts as the tooltips in the window."""
    out = ['<table><tr><th>Setting</th><th>What it does</th><th>Default</th></tr>']
    for title, settings in groups():
        if len(settings) > 1:
            out.append(f'<tr><td colspan="3"><b>{title}</b></td></tr>')
        for st in settings:
            text, link = HELP.get(st.id, ('', ''))
            more = f' <a href="{link}">More&hellip;</a>' if link else ''
            out.append(f'<tr><td>{st.label}</td><td>{text}{more}</td><td>{st.default_text}</td></tr>')
    out.append('</table>')
    return '\n'.join(out)

KNOWN_KEYS = {'autosave_minutes', 'large_plot_settings', 'large_plot_dialog_count',
              'cd_quality_shading', 'cd_ht_limit_V', 'cd_abs_limit', 'import_plot_preview',
              'peak_fit_map_settings', 'methods_report_include_table',
              'methods_report_include_references', 'theme', 'whats_new_hidden_for',
              'parallel_processing_mode', 'parallel_max_workers'}


def groups():
    """[(group name, [settings])] in the order of the table."""
    out = []
    for s in SETTINGS:
        if not out or out[-1][0] != s.group:
            out.append((s.group, []))
        out[-1][1].append(s)
    return out


def other_keys(prefs):
    """Stored values this version of the program does not use: left over from
    an earlier version, or written by a newer one (the settings are shared by
    every copy of the program on this computer)."""
    return sorted(k for k in prefs.all() if k not in KNOWN_KEYS)


def reset(prefs, setting_ids=None, other=()):
    """Set these settings (all when setting_ids is None) back to their
    defaults, and forget these other stored values (all when setting_ids is
    None). Returns the ids of the settings that changed and the other keys
    forgotten."""
    done = []
    for s in SETTINGS:
        if (setting_ids is None or s.id in setting_ids) and s.changed(prefs):
            s.set(prefs, s.default)
            done.append(s.id)
    keys = other_keys(prefs) if setting_ids is None else [k for k in other if k in prefs.all()]
    if keys:
        prefs.remove(*keys)
        done.extend(keys)
    return done


def effects(setting_ids):
    """What the open program must update after these settings changed."""
    by_id = {s.id: s for s in SETTINGS}
    return {by_id[i].effect for i in setting_ids if i in by_id and by_id[i].effect}


# --- saved items -----------------------------------------------------------------------

class SavedKind:
    """One kind of saved items: how to list them (names) and delete one."""

    def __init__(self, sid, label, folder, list_fn, delete_fn, note=''):
        self.id, self.label, self.note = sid, label, note
        self._folder, self._list, self._delete = folder, list_fn, delete_fn

    def folder(self):
        return self._folder()

    def names(self):
        try:
            return list(self._list())
        except Exception:
            return []

    def delete(self, names):
        for name in names:
            self._delete(name)


def _normalization():
    from src.modules.data_analysis.normalization_manager import NormalizationManager
    return NormalizationManager


def _profiles():
    from src.modules.misc.import_profile_manager import ImportProfileManager
    return ImportProfileManager()


def _pipelines():
    from src.modules.misc.pipeline_manager import PipelineManager
    return PipelineManager()


def _norm_folder():
    from src.modules.data_analysis import normalization_manager as nm
    return os.path.dirname(nm._PRESETS_FILE)


def _profiles_folder():
    from src.modules.misc import import_profile_manager as ipm
    return os.path.dirname(ipm._profiles_file())


def _pipelines_folder():
    from src.modules.misc import pipeline_manager as pm
    return os.path.dirname(pm._pipelines_file())


def _autosave_label(session):
    import datetime
    when = datetime.datetime.fromtimestamp(session['saved_at']).strftime('%Y-%m-%d %H:%M')
    size = session['size'] / 1e6
    return f"{when}  ({size:.1f} MB{', version ' + session['app_version'] if session.get('app_version') else ''})"


def saved_kinds(autosave_manager=None):
    """The kinds of saved items (autosave_manager: the running program's,
    so that its own session is never offered for deleting)."""
    from src.modules.misc.session_files import AutosaveManager
    manager = autosave_manager or AutosaveManager()

    def autosaves():
        return {_autosave_label(s): s for s in manager.find_recoverable()}
    return [
        SavedKind('normalization', 'Normalization presets (Normalization › region presets)',
                  _norm_folder, lambda: sorted(_normalization().list_region_presets()),
                  lambda n: _normalization().delete_region_preset(n)),
        SavedKind('import_profiles', 'Import profiles (Import dialog › Profiles)',
                  _profiles_folder, lambda: sorted(_profiles().list_profiles()),
                  lambda n: _profiles().delete_profile(n)),
        SavedKind('pipelines', 'Batch pipelines (Batch processing)', _pipelines_folder,
                  lambda: sorted(_pipelines().list_pipelines()),
                  lambda n: _pipelines().delete_pipeline(n)),
        SavedKind('recent', 'Open recent list (File › Open recent)', app_data_dir,
                  lambda: [e['path'] if isinstance(e, dict) else str(e)
                           for e in RecentFiles().items()],
                  lambda n: RecentFiles().remove(n)),
        SavedKind('autosaves', 'Automatic saves of earlier sessions (crash recovery)',
                  lambda: manager.folder, lambda: list(autosaves()),
                  lambda n: manager.discard(autosaves()[n]),
                  note='work that was not saved when the program ended unexpectedly'),
    ]


def folders():
    """Where everything is stored: [(what, path)], one entry per folder."""
    out = {}
    for what, path in (('settings, Open recent, automatic saves', app_data_dir()),
                       ('import profiles', _profiles_folder()),
                       ('batch pipelines', _pipelines_folder()),
                       ('normalization presets', _norm_folder())):
        key = os.path.normcase(os.path.abspath(path))
        if key in out:
            out[key] = (out[key][0] + ', ' + what, path)
        else:
            out[key] = (what, path)
    return [(what[0].upper() + what[1:], path) for what, path in out.values()]
