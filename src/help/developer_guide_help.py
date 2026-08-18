# src/help/developer_guide_help.py
import os

def get_developer_guide_help_title():
    return "SpecAnalytiXBase Developer Guide"

def get_developer_guide_help_content():
    # This file lives at src/help/developer_guide_help.py — repo root is
    # three levels up. Resolved here (dev-mode / running from source) so
    # the links below open the real, current files on disk. NOTE: these
    # two files are NOT bundled by BuildInstaller.bat (it only adds
    # "resources;resources"), so these links will not resolve in an
    # installed .exe — only when running from source. That's fine for a
    # developer-facing page; if this ever needs to also work in a built
    # installer, add these two files to that --add-data line, or copy
    # them into resources/ and link there instead.
    _repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _project_structure_url = "file:///" + os.path.join(_repo_root, "project_structure.txt").replace("\\", "/")
    _requirements_url = "file:///" + os.path.join(_repo_root, "requirements.txt").replace("\\", "/")
    _content = """
    <html>
    <head>
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #1976D2; margin-top: 28px; border-bottom: 1px solid #BBDEFB; padding-bottom: 4px; }
            h3    { color: #F57C00; margin-top: 18px; }
            h4    { color: #555; margin-top: 14px; }
            a     { color: #1976D2; }
            .tip      { background-color: #d4edda; border: 1px solid #c3e6cb; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .warning  { background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .danger   { background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .info     { background-color: #e3f2fd; padding: 10px; margin: 8px 0; border-left: 4px solid #2196f3; border-radius: 0 5px 5px 0; }
            .rule     { background-color: #FCE4EC; padding: 12px; margin: 10px 0; border-left: 4px solid #C2185B; border-radius: 0 5px 5px 0; }
            .scheme   { background-color: #F4F5F7; border: 1px solid #D0D3DA; border-radius: 6px;
                        padding: 16px; margin: 12px 0; font-family: 'Courier New', monospace;
                        font-size: 10pt; line-height: 1.7; white-space: pre; }
            .box      { background-color: #FFFFFF; border: 1px solid #B0B8C8; border-radius: 4px;
                        padding: 2px 10px; display: inline-block; }
            code      { background-color: #F4F5F7; padding: 1px 5px; border-radius: 3px; font-family: 'Courier New', monospace; }
            table { width: 100%; border-collapse: collapse; margin: 10px 0; }
            th    { background-color: #E3EAF4; color: #1976D2; padding: 7px 10px; text-align: left; }
            td    { padding: 6px 10px; border-bottom: 1px solid #E0E0E0; vertical-align: top; }
            tr:nth-child(even) { background-color: #F8F9FB; }
            ul, ol { padding-left: 22px; }
            li { margin: 4px 0; }
        </style>
    </head>
    <body>

        <h1>SpecAnalytiXBase Developer Guide</h1>

        <div class="info">
            This guide is for anyone reading, maintaining, or extending the source
            code — not for end users running the application (see the
            <strong>User Guide</strong> for that). It describes how the codebase is
            organised, the conventions every operation follows, and — most
            importantly — the one mistake this codebase has made repeatedly enough
            that it deserves its own section: see
            <a href="#identity">The Golden Rule: Spectrum Identity</a> below.
        </div>

        <!-- ═══════════════════════════════════════════════════════════
             ORIGIN, STACK, LICENSE, CONTACT
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="origin">Origin &amp; Purpose</h2>
        <p>SpecAnalytiXBase began as a collection of MATLAB scripts used internally
        for spectroscopic data analysis. This codebase is largely a new application
        built around that original idea — most of the GUI, workflow, and data
        management design here is new, not ported. Where a specific numerical
        algorithm (e.g. SVD) is used, it relies on the same standard, well-known
        methods in both the original MATLAB and this Python implementation, rather
        than a line-by-line translation.</p>

        <div class="info">
            A substantial part of this codebase's debugging and refinement —
            including the spectrum-identity investigation that motivated
            <a href="#identity">The Golden Rule</a> section below, and the fixes
            that followed from it across most of the operations listed in this
            guide — was carried out in collaboration with <strong>Claude, an AI
            model developed by Anthropic</strong>. Where this document explains
            <em>why</em> a particular convention exists, it is very often
            summarising that collaborative debugging process directly.
        </div>

        <h2 id="stack">Technology Stack</h2>
        <table>
            <tr><th>Component</th><th>Notes</th></tr>
            <tr><td>Python 3</td><td>Confirm the exact minimum/maximum supported
                version against this project's <code>requirements.txt</code> /
                <code>setup.py</code> — do not assume a specific point release from
                this document.</td></tr>
            <tr><td>PyQt5</td><td>All dialogs, the main window, and the application
                event loop. Again, check <code>requirements.txt</code> for the exact
                pinned version before assuming compatibility with a newer PyQt5
                release — Qt widget behaviour (see the <code>QDialog</code> note
                under Common Pitfalls below) has changed between versions in ways
                that matter here.</td></tr>
            <tr><td>NumPy / SciPy</td><td>Core numerical operations: array handling,
                interpolation, optimisation (<code>curve_fit</code>,
                <code>minimize</code>), signal processing.</td></tr>
            <tr><td>scikit-learn</td><td>NMF, PCA, KMeans / Agglomerative / DBSCAN
                clustering.</td></tr>
            <tr><td>pandas / openpyxl</td><td>Excel/CSV import and export.</td></tr>
            <tr><td>Matplotlib</td><td>All plotting, embedded via
                <code>FigureCanvasQTAgg</code>.</td></tr>
        </table>

        <h2 id="license">Using, Modifying &amp; Sharing This Code</h2>
        <div class="info">
            <p>In plain terms: anyone is welcome to use, modify, and extend this
            codebase, including for their own projects, on the condition that if a
            modified version is shared or distributed, its source code is made
            available too — the same way this code is made available to you. The
            intent is that improvements stay shareable rather than disappearing into
            a closed copy.</p>
            <p>This paragraph is a plain-language statement of intent, not formal
            license text. If a legally enforceable license is needed — for
            depositing the code in a public repository, for a publication's data/code
            availability statement, or for any other formal purpose — consider
            attaching a recognised open-source license whose terms match this intent,
            such as the
            <a href="https://www.gnu.org/licenses/gpl-3.0.html">GNU General Public
            License (GPL-3.0)</a>, which is built around the same "stays shareable"
            principle. Neither this paragraph nor the rest of this guide is legal
            advice; consult your institution's technology transfer office or a
            qualified advisor before formally licensing the project.</p>
        </div>

        <h2 id="contact">Questions &amp; Contact</h2>
        <p>For questions about this codebase, its scientific background, or
        collaboration:</p>
        <ul>
            <li>Email: <a href="mailto:janpalacky@ibp.cz">janpalacky@ibp.cz</a></li>
            <li>Research group page:
                <a href="https://www.ibp.cz/en/research/departments/biophysics-of-nucleic-acids/research-profile">
                Biophysics of Nucleic Acids — Institute of Biophysics</a></li>
        </ul>

        <!-- ═══════════════════════════════════════════════════════════
             ARCHITECTURE
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="architecture">Architecture at a Glance</h2>

        <p>Almost every feature in this application — each processing operation,
        each analysis/visualisation tool — follows the same three-layer split:</p>

        <div class="scheme">
┌─────────────────────────────────────────────────────────────────┐
│  DIALOG  (src/views/dialogs/...)                                 │
│  • Builds the Qt UI for one operation                            │
│  • Holds short-lived, UI-only state (current widget values)      │
│  • Knows about spectrum LABELS for display — list widgets, tabs, │
│    plot titles — never as a long-term identity key                │
│  • Calls into its Controller (or, for the simplest tools, its     │
│    Manager directly) to do real work                              │
└───────────────────────────┬───────────────────────────────────────┘
                            │  selected spectra, settings dict
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  CONTROLLER  (src/controllers/...)                                │
│  • Thin glue layer: owns one Manager instance                     │
│  • Translates between "what the Dialog has" (often spectrum       │
│    dicts or labels) and "what the Manager needs"                  │
│  • THE SEAM where _key_for(spectrum) translation belongs, if the  │
│    Manager's state must survive across multiple dialog sessions   │
│    (see "The Golden Rule" below)                                  │
└───────────────────────────┬───────────────────────────────────────┘
                            │  spectra, params
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  MANAGER  (src/modules/...)                                        │
│  • All real computation — numpy/scipy/sklearn, pure functions     │
│    of its inputs wherever possible                                │
│  • Some Managers hold NO state at all (stateless: Automated        │
│    Baseline, SNIP, FFT Denoising, Spectral Calculator, Band Ratio) │
│  • Others hold state that must survive across dialog sessions      │
│    (Baseline points, Spike Removal markings, SG-smoothing custom   │
│    deltas) — these are exactly the ones that need careful identity │
│    handling, see below                                            │
└─────────────────────────────────────────────────────────────────┘
        </div>

        <p>Not every operation has all three layers as separate files. Several of
        the simpler Analysis &amp; Visualization tools (NMF, PCA Scores &amp;
        Loadings) skip the Controller entirely — their Dialog talks straight to a
        freshly-created Manager instance. That's a deliberate, safe simplification
        for tools with no need to remember anything across sessions, not a missing
        piece — see <a href="#new-operation">Checklist</a> below for when it's
        appropriate.</p>

        <h3 id="component-map">Whole-Application Component Map</h3>

        <div class="info" style="margin-top:6px;">
            This is a whole-application view — which top-level pieces exist and who
            calls whom — not a folder listing. It complements, rather than repeats,
            the per-operation Dialog &rarr; Controller &rarr; Manager diagram above:
            that one zooms into a single feature; this one shows how <em>all</em>
            features plug into the same shell, history mechanism, and data model.
            Solid arrows are direct calls/ownership; dashed arrows are optional or
            read-mostly paths.
        </div>

        <div style="background:#FFFFFF; border:1px solid #D0D3DA; border-radius:6px; padding:10px; margin:12px 0; overflow-x:auto;">
        <svg viewBox="0 0 1180 970" xmlns="http://www.w3.org/2000/svg" style="width:100%; height:auto; font-family:Arial,sans-serif;">
            <defs>
                <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#555"/>
                </marker>
                <marker id="arrowBlue" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#1976D2"/>
                </marker>
            </defs>

            <!-- zone backgrounds -->
            <rect x="10" y="10" width="1160" height="130" rx="8" fill="#E8F5E9" stroke="#A5D6A7" stroke-dasharray="4,3"/>
            <text x="24" y="28" font-size="12" fill="#2E7D32" font-weight="bold">UI SHELL</text>

            <rect x="10" y="150" width="1160" height="110" rx="8" fill="#E3F2FD" stroke="#90CAF9" stroke-dasharray="4,3"/>
            <text x="24" y="168" font-size="12" fill="#1976D2" font-weight="bold">COORDINATION</text>

            <rect x="10" y="270" width="1160" height="200" rx="8" fill="#FFF3E0" stroke="#FFCC80" stroke-dasharray="4,3"/>
            <text x="24" y="288" font-size="12" fill="#E65100" font-weight="bold">DISPATCH &amp; HISTORY</text>

            <rect x="10" y="480" width="1160" height="200" rx="8" fill="#FCE4EC" stroke="#F48FB1" stroke-dasharray="4,3"/>
            <text x="24" y="498" font-size="12" fill="#C2185B" font-weight="bold">FEATURE LAYER (~40 tools total)</text>

            <rect x="10" y="690" width="1160" height="90" rx="8" fill="#F4F5F7" stroke="#B0B8C8" stroke-dasharray="4,3"/>
            <text x="24" y="708" font-size="12" fill="#555" font-weight="bold">DATA MODEL</text>

            <!-- ================= UI SHELL ================= -->
            <rect x="490" y="36" width="160" height="38" rx="6" fill="#2E7D32"/>
            <text x="570" y="60" font-size="13" fill="#fff" text-anchor="middle">main.py</text>

            <rect x="440" y="96" width="260" height="38" rx="6" fill="#2E7D32"/>
            <text x="570" y="115" font-size="13" fill="#fff" text-anchor="middle">MainWindow</text>
            <text x="570" y="129" font-size="10" fill="#DCEDC8" text-anchor="middle">menus &middot; spectra list &middot; plot canvas</text>

            <!-- ================= COORDINATION ================= -->
            <rect x="440" y="180" width="260" height="46" rx="6" fill="#1976D2"/>
            <text x="570" y="199" font-size="13" fill="#fff" text-anchor="middle">MainController</text>
            <text x="570" y="213" font-size="10" fill="#BBDEFB" text-anchor="middle">selection state &middot; wires menu actions</text>

            <!-- ================= DISPATCH &amp; HISTORY ================= -->
            <rect x="40" y="300" width="260" height="50" rx="6" fill="#1976D2"/>
            <text x="170" y="320" font-size="13" fill="#fff" text-anchor="middle">SpectrumManager</text>
            <text x="170" y="334" font-size="10" fill="#BBDEFB" text-anchor="middle">import / export (Excel, SPC, SPE, JWS, ...)</text>

            <rect x="440" y="300" width="260" height="50" rx="6" fill="#1976D2"/>
            <text x="570" y="320" font-size="13" fill="#fff" text-anchor="middle">OperationsController</text>
            <text x="570" y="334" font-size="10" fill="#BBDEFB" text-anchor="middle">dispatches every operation &amp; tool</text>

            <rect x="860" y="300" width="260" height="50" rx="6" fill="#7B1FA2"/>
            <text x="990" y="320" font-size="13" fill="#fff" text-anchor="middle">HelpWindow</text>
            <text x="990" y="334" font-size="10" fill="#E1BEE7" text-anchor="middle">renders help_*.py &rarr; opens in default browser</text>

            <rect x="360" y="400" width="280" height="50" rx="6" fill="#0D47A1"/>
            <text x="500" y="420" font-size="13" fill="#fff" text-anchor="middle">IncrementalOperationsManager</text>
            <text x="500" y="434" font-size="10" fill="#BBDEFB" text-anchor="middle">Operations History (append-only snapshots)</text>

            <rect x="700" y="400" width="240" height="50" rx="6" fill="#1976D2"/>
            <text x="820" y="420" font-size="13" fill="#fff" text-anchor="middle">BatchPipelineManager</text>
            <text x="820" y="434" font-size="10" fill="#BBDEFB" text-anchor="middle">captures &amp; replays History steps</text>

            <!-- ================= FEATURE LAYER ================= -->
            <rect x="40" y="516" width="520" height="150" rx="6" fill="none" stroke="#C2185B" stroke-width="1.5"/>
            <text x="300" y="534" font-size="11" fill="#C2185B" text-anchor="middle" font-weight="bold">Processing Operations</text>

            <rect x="60" y="548" width="140" height="38" rx="5" fill="#F57C00"/>
            <text x="130" y="571" font-size="12" fill="#fff" text-anchor="middle">Dialog</text>

            <rect x="240" y="548" width="140" height="38" rx="5" fill="#F57C00"/>
            <text x="310" y="571" font-size="12" fill="#fff" text-anchor="middle">Controller</text>

            <rect x="420" y="548" width="120" height="38" rx="5" fill="#F57C00"/>
            <text x="480" y="571" font-size="12" fill="#fff" text-anchor="middle">Manager</text>

            <text x="300" y="610" font-size="10" fill="#8E1339" text-anchor="middle">Normalization &middot; Baseline &middot; FFT Denoising &middot;</text>
            <text x="300" y="624" font-size="10" fill="#8E1339" text-anchor="middle">Smoothing &middot; Data Range &middot; Peak Fitting &middot; ...</text>
            <text x="300" y="650" font-size="10" fill="#8E1339" text-anchor="middle">always through IncrementalOperationsManager.apply_operation()</text>

            <rect x="620" y="516" width="520" height="150" rx="6" fill="none" stroke="#C2185B" stroke-width="1.5"/>
            <text x="880" y="534" font-size="11" fill="#C2185B" text-anchor="middle" font-weight="bold">Analysis &amp; Visualization Tools</text>

            <rect x="640" y="548" width="140" height="38" rx="5" fill="#F57C00"/>
            <text x="710" y="571" font-size="12" fill="#fff" text-anchor="middle">Dialog</text>

            <rect x="820" y="548" width="140" height="38" rx="5" fill="#F57C00"/>
            <text x="890" y="571" font-size="12" fill="#fff" text-anchor="middle">Manager</text>

            <rect x="1000" y="548" width="140" height="38" rx="5" fill="none" stroke="#F57C00" stroke-width="1.5" stroke-dasharray="4,3"/>
            <text x="1070" y="565" font-size="10" fill="#F57C00" text-anchor="middle">Controller</text>
            <text x="1070" y="578" font-size="8" fill="#F57C00" text-anchor="middle">(optional)</text>

            <text x="880" y="610" font-size="10" fill="#8E1339" text-anchor="middle">NMF &middot; MCR-ALS &middot; PCA &middot; SVD &middot; Band Ratio &middot;</text>
            <text x="880" y="624" font-size="10" fill="#8E1339" text-anchor="middle">Cluster &middot; Melting Curve &middot; Reference Matching &middot; ...</text>
            <text x="880" y="650" font-size="10" fill="#8E1339" text-anchor="middle">mostly stateless &mdash; Controller only where state/export needs it</text>

            <!-- ================= DATA MODEL ================= -->
            <rect x="260" y="716" width="660" height="50" rx="6" fill="#555"/>
            <text x="590" y="736" font-size="13" fill="#fff" text-anchor="middle">Spectrum data</text>
            <text x="590" y="750" font-size="10" fill="#ddd" text-anchor="middle">unique_id (identity) &middot; label (display only) &middot; x/y arrays &middot; metadata &middot; correction_history</text>

            <!-- ================= ARROWS ================= -->
            <line x1="570" y1="74" x2="570" y2="96" stroke="#555" stroke-width="1.5" marker-end="url(#arrow)"/>
            <line x1="570" y1="134" x2="570" y2="180" stroke="#555" stroke-width="1.5" marker-end="url(#arrow)"/>
            <line x1="470" y1="226" x2="220" y2="300" stroke="#555" stroke-width="1.5" marker-end="url(#arrow)"/>
            <line x1="570" y1="226" x2="570" y2="300" stroke="#555" stroke-width="1.5" marker-end="url(#arrow)"/>
            <line x1="670" y1="226" x2="960" y2="300" stroke="#7B1FA2" stroke-width="1.3" stroke-dasharray="5,4" marker-end="url(#arrow)"/>
            <line x1="540" y1="350" x2="510" y2="400" stroke="#555" stroke-width="1.5" marker-end="url(#arrow)"/>
            <line x1="660" y1="345" x2="780" y2="400" stroke="#555" stroke-width="1.5" marker-end="url(#arrow)"/>
            <line x1="770" y1="400" x2="650" y2="347" stroke="#555" stroke-width="1.2" stroke-dasharray="5,4" marker-end="url(#arrow)"/>
            <line x1="500" y1="350" x2="320" y2="516" stroke="#555" stroke-width="1.5" marker-end="url(#arrow)"/>
            <line x1="640" y1="350" x2="850" y2="516" stroke="#555" stroke-width="1.5" marker-end="url(#arrow)"/>
            <line x1="200" y1="567" x2="240" y2="567" stroke="#555" stroke-width="1.3" marker-end="url(#arrow)"/>
            <line x1="380" y1="567" x2="420" y2="567" stroke="#555" stroke-width="1.3" marker-end="url(#arrow)"/>
            <line x1="780" y1="567" x2="820" y2="567" stroke="#555" stroke-width="1.3" marker-end="url(#arrow)"/>
            <line x1="960" y1="567" x2="1000" y2="567" stroke="#555" stroke-width="1.2" stroke-dasharray="5,4" marker-end="url(#arrow)"/>
            <line x1="480" y1="586" x2="480" y2="716" stroke="#555" stroke-width="1.5" marker-end="url(#arrow)"/>
            <line x1="890" y1="586" x2="700" y2="716" stroke="#555" stroke-width="1.2" stroke-dasharray="5,4" marker-end="url(#arrow)"/>
            <!-- Analysis optional Controller -> IncrementalOperationsManager (register_copy_operation),
                 routed via the right margin and the gap above OperationsController/HelpWindow to
                 avoid crossing the HelpWindow and BatchPipelineManager boxes -->
            <path d="M 1070 548 L 1150 548 L 1150 260 L 780 260 L 780 320 L 660 340 L 640 415" fill="none" stroke="#1976D2" stroke-width="1.3" stroke-dasharray="5,4" marker-end="url(#arrowBlue)"/>
            <!-- SpectrumManager -> Data model (elbow, hugs left margin to avoid the Processing box and the zone label) -->
            <path d="M 170 350 L 170 495 L 25 495 L 25 730 L 260 730" fill="none" stroke="#555" stroke-width="1.5" marker-end="url(#arrow)"/>
            <!-- IncrementalOperationsManager -> Data model (elbow, drops through the gap between the two feature boxes) -->
            <path d="M 500 450 L 500 480 L 590 480 L 590 716" fill="none" stroke="#555" stroke-width="1.5" marker-end="url(#arrow)"/>

            <!-- legend -->
            <rect x="30" y="800" width="1120" height="150" rx="6" fill="#FAFAFA" stroke="#E0E0E0"/>
            <text x="46" y="820" font-size="11" fill="#333" font-weight="bold">Legend</text>

            <line x1="46" y1="840" x2="86" y2="840" stroke="#555" stroke-width="1.5" marker-end="url(#arrow)"/>
            <text x="94" y="844" font-size="10" fill="#333">direct call / ownership</text>
            <line x1="46" y1="862" x2="86" y2="862" stroke="#555" stroke-width="1.2" stroke-dasharray="5,4" marker-end="url(#arrow)"/>
            <text x="94" y="866" font-size="10" fill="#333">optional / read-mostly path</text>
            <line x1="46" y1="884" x2="86" y2="884" stroke="#1976D2" stroke-width="1.3" stroke-dasharray="5,4" marker-end="url(#arrowBlue)"/>
            <text x="94" y="888" font-size="10" fill="#333">register_copy_operation()</text>
            <text x="94" y="902" font-size="9" fill="#666">(2D Map ROI export, NMF/MCR-ALS Export Components)</text>

            <rect x="640" y="833" width="16" height="14" fill="#F57C00"/>
            <text x="664" y="845" font-size="10" fill="#333">per-tool Dialog / Controller / Manager (one of ~40 features)</text>
            <rect x="640" y="857" width="16" height="14" fill="#1976D2"/>
            <text x="664" y="869" font-size="10" fill="#333">app-wide singleton-ish coordinators (one instance each)</text>
            <rect x="640" y="881" width="16" height="14" fill="#555"/>
            <text x="664" y="893" font-size="10" fill="#333">shared data / infrastructure</text>

            <text x="46" y="930" font-size="10" fill="#666" font-style="italic">Not shown: every Processing/Analysis Dialog also has its own "?"/Help button that opens HelpWindow directly (omitted for clarity &mdash; see the dashed MainController &rarr; HelpWindow arrow as the representative case).</text>
        </svg>
        </div>

        <h3 id="sequence">Concretely: What Happens When the User Clicks "Apply"</h3>
        <p>The three-layer split above is the static picture. Here's the same
        thing as a single, real, runtime sequence — using Normalization as a
        stand-in for "any processing operation," since they're all wired the same
        way:</p>
        <div class="scheme">
User clicks "Apply" in NormalizationDialog
        │
        ▼
NormalizationDialog.on_apply_clicked()
        │  reads widget values into a settings dict
        │  calls self.commit_callback(settings)
        ▼
OperationsController.commit_normalization(settings)
        │  selected_spectra = self.controller.selected_spectra
        │  result = NormalizationManager().normalize(selected_spectra, settings)
        │  current_state = self.operations_manager.get_current_spectra()
        │  output_spectra = [unaffected spectra from current_state] + result
        ▼
IncrementalOperationsManager.apply_operation(
    'Normalization', settings, affected_spectra=result,
    new_state_spectra=output_spectra)
        │  appends a new frozen entry to self.operations_chain
        │  self.active_operation_index = len(operations_chain) - 1
        ▼
back in commit_normalization():
        │  self.controller.original_spectra = output_spectra
        │  rebuild spectra_list_widget from it
        │  self.controller.plot_spectra()
        ▼
Dialog closes · plot and list now reflect the new state
· a new entry appears in Operations History
        </div>
        <p>Every processing operation in this codebase follows this exact shape.
        Once you've traced it through for one operation, you've traced it through
        for all of them — the only things that differ between operations are what
        happens inside the Manager call in the middle.</p>

        <h3 id="paradigms">Design Paradigms in Use (and Why)</h3>
        <p>None of this is bespoke invention. Naming the actual patterns helps —
        both for relating this codebase to general software engineering knowledge,
        and for knowing what <em>not</em> to reach for instead.</p>
        <table>
            <tr><th>Pattern</th><th>Where it shows up here</th></tr>
            <tr><td><strong>Layered architecture</strong> (a relative of MVC)</td>
                <td>Dialog (View) → Controller → Manager (Model/business logic).
                Each layer only talks to its immediate neighbour.</td></tr>
            <tr><td><strong>Command pattern</strong></td>
                <td>Each call to <code>apply_operation()</code> packages "what
                happened" (type, parameters, affected spectra) as a self-contained
                record — the same shape every time, regardless of which actual
                operation it represents.</td></tr>
            <tr><td><strong>Persistent / immutable data structures</strong>
                <br>(also: <strong>append-only log</strong>, the same idea behind
                Git commits and event-sourcing)</td>
                <td><code>operations_chain</code> never edits an existing entry —
                every change produces a brand new one, leaving every previous
                entry untouched forever. This is precisely why the rename redesign
                (below) is simpler and more robust than the retroactive version it
                replaced: nothing is ever mutated after the fact, so there's
                nothing for two changes to collide over.</td></tr>
            <tr><td><strong>Entity vs. value object</strong>
                <br>(a Domain-Driven Design distinction)</td>
                <td>A spectrum's <code>unique_id</code> is its entity identity —
                permanent, never displayed, never chosen by the user. Its
                <code>label</code> is a value — freely replaceable, and never a
                safe key for anything meant to outlive one dialog session. See
                <a href="#identity">The Golden Rule</a> below.</td></tr>
        </table>

        <h3 id="apply-pattern">The Apply / Add as New Convention</h3>
        <p>Every processing operation's dialog has its own <strong>Apply</strong>
        and <strong>Add as New</strong> buttons built directly into the dialog,
        wired to a <code>commit_callback</code> passed in when the dialog is
        constructed (almost always a method on <code>OperationsController</code>
        named <code>commit_&lt;operation&gt;</code>). There is no separate
        application-wide "Run" step for these — the dialog commits its own result
        the moment one of those buttons is clicked, after a <strong>local Yes/No
        confirmation prompt</strong> (<code>QMessageBox.question</code>, defaulting
        to No) that names exactly what's about to happen — e.g. "replace the
        selected spectra with their normalized result" or "add the normalized
        result as new spectra." This confirmation is part of the standard pattern,
        present in every one of these dialogs' shared <code>_on_commit_clicked</code>
        handler — not something specific to any one operation. The dialog still
        closes itself on success, and answering No (or Close without committing) is
        always non-destructive: it remembers the dialog's current settings (see
        below) but changes nothing in the actual spectra.</p>

        <div class="warning">
            <strong>Known inconsistency: SVD Interpolation's Add as New skips the
            confirmation prompt.</strong> Unlike every other operation, SVD
            Interpolation doesn't share one <code>_on_commit_clicked(add_as_new)</code>
            handler — it has two separate methods, <code>_on_apply_clicked</code> and
            <code>_on_add_as_new_clicked</code>. Apply confirms before committing, the
            same as everywhere else; Add as New currently does not. This is drift, not
            a deliberate design choice — worth fixing by adding the same confirmation
            to <code>_on_add_as_new_clicked</code> the next time that dialog is
            touched.
        </div>

        <h3 id="history-scope">What Belongs in Operations History</h3>
        <div class="rule">
            <strong>Operations History exists to track changes to the spectra
            themselves — additions, removals, and data transformations. It is
            not a log of every analysis a user has run.</strong> A tool that only
            computes and displays a derived characteristic (Band Ratio, Reference
            Matching, SVD Analysis, PCA Scores &amp; Loadings, NMF, Cluster
            Analysis) should never call <code>apply_operation()</code> — there is
            nothing about the spectra list for "jump to a previous state" to
            meaningfully undo. Saving the result into the relevant spectrum's own
            <code>metadata</code> (and syncing that via
            <code>update_original_spectra_with_processed()</code>, which only
            touches the live list, never the history chain) is fine and often
            useful — it just isn't a history step.
        </div>
        <p>The exceptions are genuine, and fall into two mechanisms depending on
        which is the more natural fit:</p>
        <ul>
            <li><strong><code>apply_operation()</code>, conditionally</strong> —
                Peak Fitting's Output Options (<em>add fit / add residual / add
                individual peaks</em>) and Melting Curve Analysis's Output Options
                both <em>can</em> add real new spectra to the list, and only
                register a history step when they actually do so — the
                metadata-only path (no Output Option checked) deliberately skips
                <code>apply_operation()</code> entirely, for the same reason Band
                Ratio always does.</li>
            <li><strong><code>OperationsController.register_copy_operation()</code></strong>
                — 2D Map's ROI export, and NMF's and MCR-ALS's <em>Export
                Components&hellip;</em> (which always adds spectra the moment the
                user confirms the export, so there's no "did nothing" branch to
                guard against) all go through this instead of
                <code>apply_operation()</code>, since what they're recording is
                closer to "copy these existing/derived spectra into the list"
                than "transform the current spectra in place."</li>
        </ul>
        <p>If a future tool gains a similar "optionally export results as new
        spectra" feature, follow whichever of these two shapes fits: a
        conditional <code>apply_operation()</code> call if the new spectra are a
        state transition of the current selection, or
        <code>register_copy_operation()</code> if they're better described as
        additions copied/derived from it.</p>

        <div class="warning">
            Peak Fitting, Band Ratio, and Reference Matching predate this
            convention and still use an older two-step design: their "OK" button
            only <em>saves</em> settings into
            <code>OperationsController.current_parameters</code>; a second,
            separate <code>handle_&lt;operation&gt;()</code> method is what
            actually executes them. When these three tools were moved from the main
            Spectra-processing combobox into their own Analysis &amp; Visualization
            menu entries, the second step stopped being reachable from anywhere —
            <code>OperationsController.operations</code>, the dict that used to map
            each name to its handler, was never actually wired into the new menu
            dispatch path. The result: clicking OK silently did nothing beyond
            saving settings, for an unknown amount of time, with no error of any
            kind. This has since been fixed by calling the handler directly from
            the settings-save branch, but the lesson generalises: <strong>if a
            dialog's only externally visible action is "this thing got recorded
            somewhere," verify by tracing the call chain that something downstream
            actually reads it back out</strong> — don't assume a handler method
            existing means it's being called.
        </div>

        <h3 id="settings-cache">Remembering Dialog Settings: The Selection-Hash Guard</h3>
        <p><code>OperationsController</code> keeps three pieces of bookkeeping used
        by almost every operation that goes through the generic Run dispatch
        (<code>show_parameters_dialog</code>):</p>
        <table>
            <tr><th>Attribute</th><th>Purpose</th></tr>
            <tr><td><code>self.current_parameters[operation]</code></td>
                <td>The settings most recently <em>applied</em> for this operation
                name.</td></tr>
            <tr><td><code>self.last_op_settings[operation]</code></td>
                <td>The settings most recently <em>shown</em> in the dialog, whether
                applied or not — lets Close-without-Apply still be remembered.</td></tr>
            <tr><td><code>self.last_selection_hash</code></td>
                <td>A single hash (sorted, comma-joined spectrum labels — see
                <code>_get_selection_hash</code>) describing which selection those
                settings belong to. Shared globally across all operations, updated
                every time any one of them saves its settings.</td></tr>
        </table>
        <p>The correct pattern, used by every properly-guarded operation, is:</p>
        <div class="scheme">
last_settings = {}
if (operation in self.current_parameters and
        self.last_selection_hash == current_selection_hash):
    last_settings = self.last_op_settings.get(operation, {}).copy()
        </div>
        <div class="danger">
            <strong>This guard has been missing more often than it should be.</strong>
            It was absent for Peak Fitting, Combine Spectra, Spectral Calculator,
            Band Ratio, Reference Matching, and PCA Scores &amp; Loadings at various
            points — in each case, switching to a completely unrelated selection and
            reopening the dialog silently pre-loaded it with whatever the
            <em>previous, unrelated</em> selection had used. For Spectral
            Calculator specifically this is worse than cosmetic: the stale formula
            text references spectrum labels that may not even exist in the new
            selection. <strong>Any new operation added to the generic Run dispatch
            must include this guard from the start.</strong>
        </div>

        <!-- ═══════════════════════════════════════════════════════════
             OPERATIONS HISTORY
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="history-internals">Operations History (<code>IncrementalOperationsManager</code>)</h2>
        <p>One instance of <code>IncrementalOperationsManager</code>, owned by
        <code>OperationsController</code>, tracks the entire session as a linear
        chain:</p>
        <ul>
            <li><code>self.original_spectra</code> — a deep-copied snapshot of the
                very first imported state. This is what "Original State" (#0 in the
                History dialog) restores.</li>
            <li><code>self.operations_chain</code> — a list of operation records,
                each with (at least) <code>type</code>, <code>parameters</code>,
                <code>affected_labels</code>, and <code>output_spectra</code> (a
                full, deep-copied snapshot of every spectrum as it existed
                immediately after that step).</li>
            <li><code>self.active_operation_index</code> — which step is currently
                "live"; <code>-1</code> means Original State.</li>
            <li><code>get_current_spectra()</code> — the single chokepoint every
                consumer reads spectra state through. Returns a deep copy of either
                <code>original_spectra</code> or the active step's
                <code>output_spectra</code>, and — since a real, previously-shipped
                bug — also runs a final de-duplication pass (see below) before
                returning.</li>
        </ul>

        <h3 id="snapshot-vs-delta">Why Full Snapshots, Not Diffs</h3>
        <p>There are two standard ways to build an undo/history system. This
        codebase deliberately picked the simpler of the two:</p>
        <table>
            <tr><th></th><th>Snapshot-based (used here)</th><th>Delta-based (e.g. Git)</th></tr>
            <tr><td>What's stored per step</td>
                <td>A full, independent copy of every spectrum's complete state</td>
                <td>Only what changed since the previous step</td></tr>
            <tr><td>Reconstructing any historical state</td>
                <td>Direct — just read that step's stored copy</td>
                <td>Requires replaying deltas from some earlier known state</td></tr>
            <tr><td>Memory cost</td>
                <td>Scales with (spectra count × steps), regardless of how much
                    actually changed each time</td>
                <td>Scales with how much actually changed each time</td></tr>
            <tr><td>Implementation complexity</td>
                <td>Low — every consumer just reads a list of dicts</td>
                <td>Higher — needs diff/patch logic and a replay mechanism</td></tr>
        </table>
        <p>The memory cost is the real trade-off, and it's worth knowing the actual
        numbers rather than assuming it matters: a spectrum with 2000 points is two
        float64 arrays, roughly 32KB. 100 spectra × 10 operations ≈ 32MB for an
        entire session. Even an extreme case — 10,000 Raman spectra, 10 operations
        — is roughly 3GB, which is large but unremarkable on hardware that's
        already running SVD or NMF on that same dataset. <strong>If a future
        version of this application needs to handle session sizes where that
        stops being true, that's the point to revisit this decision — not
        before.</strong> Don't introduce delta-based storage speculatively; it's
        meaningfully more code for a problem that doesn't currently exist.</p>

        <h3>Renaming Is Forward-Only — and Why That Replaced an Earlier, More
        "Clever" Design</h3>
        <p>Renaming a spectrum creates a new entry in <code>operations_chain</code>,
        exactly like any other operation — <code>RenameSpectraController</code>
        builds the new state from <code>get_current_spectra()</code>, applies the
        rename to it, and calls <code>apply_operation('Rename', ...)</code> with the
        renamed spectra as <code>affected_spectra</code>. <strong>It never reaches
        backward to modify an earlier snapshot.</strong> An older entry simply keeps
        showing whichever name was genuinely true at that point in time, forever.</p>
        <div class="tip">
            This is deliberately the simplest possible design, and it was arrived at
            <em>after</em> a more sophisticated alternative — not instead of one out
            of laziness. Worth understanding why, since the temptation to rebuild the
            retroactive version will come up again.
        </div>
        <p>An earlier version tried to be cleverer: renaming would reach backward
        and update every old snapshot's label too, so history always displayed a
        spectrum under its <em>current</em> name rather than whatever it was called
        at the time. This required: matching each historical snapshot's entries
        against the rename request, refusing to write a name that would collide
        with another spectrum already in that same snapshot (since a label freed up
        by deletion can later be reused by an unrelated spectrum), evaluating an
        entire batch of renames atomically so a genuine swap wasn't mistaken for a
        collision, and a separate chain-tracking dictionary so renaming the same
        spectrum a second time would still find it correctly.</p>
        <div class="danger">
            <strong>Every one of those pieces shipped, individually tested, and
            individually turned out to have a real bug</strong> — found one at a
            time, each only by testing actual application behaviour, not by reading
            the code:
            <ul>
                <li>The collision check covered <code>output_spectra</code> but not
                    the separate <code>affected_labels</code> string list, so a
                    spectrum could silently disappear from "Spectra List" views even
                    though its underlying data was untouched.</li>
                <li>The chain-tracking dictionary updated itself sequentially while
                    processing a batch, so a genuine simultaneous swap
                    (<code>{'A': 'B', 'B': 'A'}</code>) was misread as a sequential
                    chain looping back on itself, collapsing to a no-op and silently
                    discarding one half of the swap.</li>
                <li>Even after fixing both of those: matching a historical snapshot's
                    entry by label string alone — with no permanent identity to
                    disambiguate — meant an unrelated spectrum that happened to share
                    a label in some old, never-deleted snapshot could be renamed by
                    mistake, while the spectrum actually being renamed stayed stuck.</li>
                <li>A separate, leftover hook (<code>_hook_into_rename_controller</code>,
                    now removed) called the rename-registration function a
                    <em>second</em> time after every rename, without the identity
                    info the first call had — silently undoing a correct rename
                    immediately after it succeeded. This is the reason several
                    "verified" fixes kept failing in the real application despite
                    passing isolated tests: the test never exercised the second,
                    redundant call.</li>
            </ul>
            Four real bugs, found one at a time, each by a human running the actual
            application — not by code review, not by unit tests written in
            isolation. That track record is the actual reason this was rebuilt as
            forward-only rather than fixed a fifth time. A system whose correctness
            depends on the cumulative result of every rename ever performed in a
            session has an enormous number of paths to verify; a system where each
            action only ever looks at its own immediate input has very few.
        </div>
        <p>If a future requirement specifically needs old history to show a
        spectrum's <em>current</em> name rather than its name-at-the-time, treat
        that as a deliberate, scoped feature request — re-introduce the
        identity-based matching <em>and</em> keep the forward-only history entry as
        the baseline behaviour, rather than reaching for retroactive rewriting again
        as the default.</p>

        <!-- ═══════════════════════════════════════════════════════════
             THE GOLDEN RULE
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="identity">⭐ The Golden Rule: Spectrum Identity</h2>

        <div class="rule">
            <strong>A spectrum's <code>label</code> is a display string the user
            can change at any time. It is never a stable identity. Any dictionary
            that remembers something about a specific spectrum across more than one
            dialog session must be keyed by that spectrum's permanent identifier —
            <code>spectrum['metadata']['unique_id']</code> — not by its label.</strong>
        </div>

        <div class="scheme">
spectrum = {
    'label':    'Sample 3'        ← VALUE. Cosmetic. User-editable.
                                     Can collide, change, get reused.
                                     Fine for UI display. Never a key.

    'metadata': {
        'unique_id': 'f3a9c1...'  ← IDENTITY. Permanent. Invisible to
                                     the user. Assigned once at import,
                                     never changes. The only safe key.
    },
    'x_scale': [...],
    'y_scale': [...],
}
        </div>

        <p>This single mistake, in different files, was responsible for nearly
        every bug found during the most recent maintenance pass on this codebase:
        Baseline Correction, Interactive Subtraction, Spike Removal,
        Savitzky-Golay's custom delta values, and the Operations History
        duplicate-name issue described above all trace back to it. It is worth
        understanding precisely, because it is easy to reintroduce.</p>

        <div class="rule">
            <strong>Status: unified.</strong> A full codebase sweep converted every
            remaining label-keyed identity/selection site to
            <code>spectrum_key()</code> / <code>spectrum_id()</code> (defined once,
            centrally, in <code>src/modules/utils/spectrum_identity.py</code> — the
            same <code>metadata.get('unique_id') or spectrum['label']</code> logic
            every Manager's own <code>_key_for</code> already implemented locally,
            now with one canonical implementation new code should import instead of
            reinventing). This includes the main spectra list widget itself
            (<code>main_controller.py</code>, <code>operations_controller.py</code>,
            <code>spectrum_selector_controller.py</code>, and every operation
            controller's post-Apply/Add-as-New selection restore), which for a long
            time was the one conspicuous holdout — it tracked selection and
            rename-sync by matching <code>QListWidgetItem.text()</code> against
            <code>spectrum['label']</code> directly, the exact anti-pattern this
            section warns about, just not yet caught. Every
            <code>QListWidgetItem</code> representing a spectrum now also carries
            that spectrum's <code>unique_id</code> as <code>Qt.UserRole</code> data,
            set once when the row is created, independent of whatever text is
            displayed (see the <code>_DistinguishingNameDelegate</code> docstring
            above for why display text and identity are two separate things even on
            the very same row). <code>CustomPlotPropertiesManager</code>'s
            per-spectrum color/style dict, the reference-matching dialog's saved
            selection, and <code>BaselinePointsStorage</code>'s cross-dialog cache
            were fixed the same way. Verified with headless PyQt runtime tests:
            rename-preserves-selection, reorder-preserves-selection, and both
            combined, at the main list widget level.
        </div>

        <h3>Why it happens</h3>
        <p>A spectrum's label is convenient to use as a dictionary key — it's a
        string, it's exactly what's shown in the UI, and for a quick first
        implementation it just works. The bug only appears later, through either of
        two paths:</p>
        <table>
            <tr><th>Failure mode</th><th>What happens</th></tr>
            <tr><td><strong>Orphaning</strong></td>
                <td>Spectrum "Sample_A" has settings stored under key
                <code>"Sample_A"</code>. The user renames it to "Sample_A_v2".
                Nothing updates the dictionary key. The settings are still in
                memory, now permanently unreachable under a name nothing matches
                anymore.</td></tr>
            <tr><td><strong>Cross-contamination</strong></td>
                <td>The same spectrum is later deleted. A completely unrelated file
                is imported and happens to receive the same auto-generated label
                (very plausible — re-importing the same source file, or just an
                import counter landing on the same number). It now silently
                inherits "Sample_A"'s old settings, despite having never been
                touched by that operation.</td></tr>
        </table>

        <h3>The fix pattern</h3>
        <p>Every Manager that needs to remember something about a spectrum across
        more than one dialog session should define:</p>
        <div class="scheme">
@staticmethod
def _key_for(spectrum):
    metadata = spectrum.get('metadata') or {}
    return metadata.get('unique_id') or spectrum['label']
        </div>
        <p>...and use <code>self._key_for(spectrum)</code> — never
        <code>spectrum['label']</code> directly — for every read and write of that
        persistent dictionary. The label fallback exists only for spectra that
        genuinely have no <code>unique_id</code> (this shouldn't normally happen
        for anything that went through the standard import path, but is a safe
        fallback for, e.g., externally-loaded reference library spectra that were
        never assigned one).</p>

        <div class="warning">
            <strong>One subtlety that has caused a real regression: don't
            over-apply this.</strong> A Dialog that creates its own short-lived
            Manager instance, uses it consistently with
            <code>spectrum['label']</code> as the key throughout its own internal
            methods, and is modal (so no rename can happen while it's open) does
            <em>not</em> need <code>_key_for</code> internally — it's already safe,
            because nothing can change the label mid-session and nothing else reads
            that same dictionary. Spike Removal's manager was changed to use
            <code>_key_for</code> inside <code>detect_spikes()</code> at one point,
            while every other method the interactive dialog calls on its own local
            manager instance still used the raw label — this made detection write
            results under one kind of key while every lookup read a different kind,
            so nothing was ever found. The fix was to revert the manager's own
            internal methods back to plain labels, and instead do the
            label-to-unique_id translation only at the one seam that actually needs
            it: the boundary in the Controller where state crosses from one dialog
            session's manager into the long-lived one (or vice versa). <strong>The
            translation belongs at the boundary where state crosses a session gap —
            not inside methods that are also used self-consistently within a single,
            already-safe session.</strong>
        </div>

        <h3>Recognising which Managers are at risk</h3>
        <p>Not every Manager needs this. The actual risk factor is: <strong>does
        the operation let different spectra in the same selection carry different,
        individually-remembered settings that persist across a dialog
        close/reopen</strong> (or, for interactive tools, across an editing
        session)? That's the shape that produces a label-keyed persistence
        dictionary. By contrast, a Manager that applies one uniform setting to the
        whole batch every time (Automated Baseline, SNIP, FFT Denoising,
        Resolution Enhancement, Spectral Calculator, Combine Spectra, Band Ratio)
        has nothing per-spectrum to orphan in the first place — there's no
        dictionary, just scalar settings reused identically. SVD-family tools
        (SVD Background, SVD Analysis, Map2D's SVD mode) sit in between: they keep
        per-<em>component</em> state (not per-spectrum), but stay safe as long as
        the decomposition is fully recomputed — and the per-component state fully
        reset — every time the dialog opens or the underlying spectra selection
        changes. Check that the reset actually happens unconditionally before
        assuming a recompute-based tool is safe by default.</p>

        <h3 id="label-shortening">Display-Only Label Shortening (<code>label_shortening.py</code>)</h3>
        <p>A separate, purely cosmetic transformation lives in
        <code>src/modules/utils/label_shortening.py</code>: a <strong>Shorten
        names</strong> checkbox which strips whatever text is common across the
        currently-shown spectrum names (usually a shared file-name prefix/suffix)
        so only the distinguishing part is displayed. The core algorithm
        (<code>compute_distinguishing_labels</code>) was originally written inline
        inside <code>main_controller.py</code>'s private
        <code>_DistinguishingNameDelegate</code>, then extracted here so every
        <em>other</em> caller shares one implementation instead of reimplementing
        it slightly differently. It is wired into the main window's plot legends
        (via the main window's own checkbox), and separately into Cluster
        Analysis, 2D Correlation, Reference Matching, Band Ratio, NMF/MCR-ALS
        concentration and scores plots, Melting Curve Analysis, SVD Analysis's
        "Spectrum labels" x-axis mode, and every processing-operation dialog's
        own spectra list.</p>
        <div class="info">
            <strong>Each dialog gets its own checkbox, not the main window's.</strong>
            Every dialog listed above uses
            <code>make_shorten_names_checkbox()</code> to build a checkbox that is
            entirely independent of <code>main_controller.checkBox_shorten_names</code>
            — its own <code>QCheckBox</code>, its own on/off state, defaulting to
            unchecked every time the dialog opens regardless of the main window's
            current setting. Toggling the main window's checkbox does not touch
            an open dialog's checkbox or its displayed labels, and vice versa.
            The one deliberate exception is <code>external_figure.py</code> (the
            main plot's "open in external window" mirror), which still reads
            <code>main_controller.checkBox_shorten_names</code> directly since it
            is a live view of the main plot rather than an independent dialog.
            When adding a new dialog that shows spectrum names, use
            <code>make_shorten_names_checkbox()</code> rather than reaching for
            the main window's checkbox.
        </div>
        <div class="warning">
            <strong><code>main_controller.py</code>'s own
            <code>_DistinguishingNameDelegate</code> was NOT itself replaced by
            <code>make_shortened_name_delegate()</code> — it still exists as a
            separately-maintained duplicate delegate class</strong> (its own
            docstring says so explicitly), just now calling the shared
            <code>compute_distinguishing_labels()</code> algorithm internally
            instead of reimplementing that part too. This is exactly the kind of
            drift risk <a href="#dont-duplicate-tracked-mutations">the section
            below on duplicated code paths</a> warns about in general: it was
            already the reason one hardening fix (an unguarded exception inside
            <code>initStyleOption()</code>, which PyQt5 turns into an immediate
            <code>abort()</code> with no traceback — see
            <code>make_shortened_name_delegate</code>'s own try/except) had to be
            applied to this copy separately, after already being fixed in the
            shared one. If touching this area again, consider finishing the
            consolidation — replacing <code>_DistinguishingNameDelegate</code>
            with a direct call to <code>make_shortened_name_delegate()</code> —
            rather than assuming it already happened.
        </div>
        <table>
            <tr><th>Function</th><th>Use</th></tr>
            <tr><td><code>compute_distinguishing_labels(labels)</code></td>
                <td>Core algorithm: <code>{full_label: shortened_label}</code> for a
                list of labels, handling several unrelated groups independently rather
                than assuming one global common prefix/suffix.</td></tr>
            <tr><td><code>shorten_spectra_labels(spectra, enabled)</code></td>
                <td>Convenience wrapper over a list of spectrum dicts; returns the
                labels unchanged when <code>enabled</code> is False.</td></tr>
            <tr><td><code>make_shortened_name_delegate(list_widget, is_enabled, parent=None)</code></td>
                <td>Paint-only <code>QStyledItemDelegate</code> for a
                <code>QListWidget</code>/<code>QTableWidget</code> — substitutes display
                text at paint time without ever touching <code>item.text()</code> or the
                underlying model.</td></tr>
            <tr><td><code>make_display_text_delegate(get_display_map, parent=None)</code></td>
                <td>Same idea for a single table column, driven by a caller-supplied
                <code>{full_label: display_text}</code> map (used e.g. for a table's
                "Spectrum" column while other columns stay untouched).
                <b>Always pass <code>parent=&lt;the table/view&gt;</code></b> — Qt's
                <code>setItemDelegateForColumn()</code> does NOT take ownership of the
                delegate, so a call like
                <code>table.setItemDelegateForColumn(0, make_display_text_delegate(m))</code>
                with no parent (and no Python reference kept) leaves the delegate
                object with nothing keeping it alive. Python garbage-collects it
                right after the call returns; the table still points at it
                internally, and the next repaint segfaults the whole process —
                confirmed as the real root cause of a "Reference Matching just
                closes with no error" crash report (fixed by adding
                <code>parent=self._table</code>).</td></tr>
            <tr><td><code>make_shorten_names_checkbox(text='Shorten names')</code></td>
                <td>Factory for a dialog's own independent Shorten Names
                <code>QCheckBox</code> — unchecked by default, with a standard
                tooltip explaining it's separate from the main window's setting.
                Use this instead of reading
                <code>main_controller.checkBox_shorten_names</code> in any new
                dialog.</td></tr>
        </table>
        <div class="rule">
            <strong>Never confuse this with identity.</strong> Shortening must never be
            written back into <code>spectrum['label']</code>, never used as a lookup key,
            and never baked into a name for a newly created spectrum (Apply, Add as New,
            Send to main list, export, ...) — those always build from the full, original
            label. See <a href="#identity">The Golden Rule</a> above; a shortened,
            potentially ambiguous label is strictly worse than a full one as an identity
            key.
        </div>
        <p>Toggling the checkbox re-plots the main window immediately
        (<code>main_controller.toggle_shorten_names()</code> calls
        <code>plot_spectra()</code> unconditionally after swapping the list delegate) —
        legend text and axis labels are baked into matplotlib <code>Text</code> objects
        at plot time, so unlike the list widget's paint-time delegate, the plot itself
        has to be redrawn to pick up the change, regardless of the Interactive Update
        setting.</p>

        <!-- ═══════════════════════════════════════════════════════════
             CHECKLIST
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="qt-batch-ops">Qt Widget Operations: Batch, Don't Loop</h2>

        <div class="rule">
            <strong>Any Qt widget-state change repeated once per spectrum in a loop
            — selection, item flags, anything touching the widget's internal
            model — costs real, measurable time per call, independent of
            <code>blockSignals()</code>. At a few hundred spectra this is invisible.
            At a few thousand it is the entire performance problem.</strong>
        </div>

        <p>Found via a real <code>cProfile</code> trace of a ~90-second Apply on
        4675 spectra: <strong>83 of those 90 seconds</strong> were spent in
        <code>QListWidgetItem.setSelected(True)</code>, called once per spectrum
        inside <code>_rebuild_spectra_list_with_selection()</code>. The surrounding
        code already wrapped the whole rebuild in
        <code>widget.blockSignals(True)</code> — which stops <em>signals</em> from
        firing, but does nothing about the real internal Qt cost each individual
        call still pays. Every per-spectrum manager computation in this codebase
        was independently profiled and confirmed fast even at this scale; this one
        widget call, called the naive way, was the actual bottleneck the whole time.</p>

        <div class="scheme">
# SLOW — real, measured cost that scales with N, even with signals blocked
for i, spectrum in enumerate(original_spectra):
    item = QListWidgetItem(spectrum['label'])
    item.setData(Qt.UserRole, spectrum_id(spectrum))   # identity, not just display text
    widget.addItem(item)
    if spectrum_key(spectrum) in highlight_ids:         # match by identity — see the
        item.setSelected(True)          # ← paid once PER SPECTRUM   Golden Rule above

# FAST — one atomic operation regardless of how many rows are selected
rows_to_select = [...]
selection = QItemSelection()
for row in rows_to_select:
    idx = model.index(row, 0)
    selection.select(idx, idx)
widget.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)
        </div>

        <p>Confirmed by direct benchmark: <strong>0.032s vs. a profiled 83.2s</strong>
        at 4675 items, for both a contiguous block and a scattered selection. The
        general lesson: before assuming a per-spectrum <em>computation</em> is the
        bottleneck for a slow operation, check what happens to the UI afterward too
        — a rebuild-and-reselect step that "just" touches Qt widgets is not free at
        scale, and won't show up if you only profile the numerical part.</p>

        <h2 id="deepcopy-pitfall">Avoid <code>copy.deepcopy()</code> on Spectrum Dicts</h2>

        <div class="rule">
            <strong><code>copy.deepcopy()</code> on a spectrum dict is 10-18x
            slower than a targeted copy once <code>metadata['correction_history']</code>
            has accumulated entries — which is after literally any prior operation,
            not an edge case. Never reach for it here; use the targeted-copy
            pattern instead.</strong>
        </div>

        <div class="scheme">
# SLOW — walks and reconstructs every nested object via Python's generic
# copy protocol, including numpy arrays (no special-casing) and the
# entire correction_history list
copied = copy.deepcopy(spectrum)

# FAST — the same independence guarantee (arrays and metadata are real,
# separate copies), without the generic-protocol overhead
copied = {k: (v.copy() if hasattr(v, 'copy') else v) for k, v in spectrum.items() if k != 'metadata'}
copied['metadata'] = dict(spectrum.get('metadata') or {})
# NOTE: dict(...) is only a SHALLOW copy of metadata — nested mutable
# values (like correction_history, a list) are still the SAME object
# across copies at this point. Safe today only because nothing in this
# codebase mutates that list in place (see correction_history.py:
# append_correction_history always builds and reassigns a fresh list).
# If independence of a nested value actually matters, copy it explicitly:
copied['metadata']['correction_history'] = list(spectrum.get('metadata', {}).get('correction_history', []))
        </div>

        <p>This surfaced in <code>register_copy_operation()</code> (the function
        every Add as New commit calls) and cost real time specifically in that
        mode — which is also why Add as New was measured as disproportionately
        slower than Apply, beyond what the batch-selection fix above explains on
        its own. A second, related fix in the same function: if the caller already
        computed the current spectrum state a few lines earlier (every
        <code>commit_&lt;operation&gt;()</code> does), pass it in via the optional
        <code>pre_state</code> parameter instead of letting
        <code>register_copy_operation()</code> call
        <code>get_current_spectra()</code> again — that method does its own full
        per-spectrum copy on every call, so a second call for data the caller
        already has is pure waste.</p>

        <h2 id="progress-callback">Long-Running Operations: the <code>progress_callback</code> Hook</h2>

        <p>Every <code>commit_&lt;operation&gt;()</code> method wraps its work in
        an indeterminate <code>QProgressDialog</code> (see
        <code>OperationsController._show_busy_progress</code>), shown only above a
        spectra-count threshold (200) so small, fast operations aren't interrupted
        by a dialog that would just flash and vanish. The dialog's label text
        updates at each phase boundary ("Applying... → Updating spectrum list...
        → Redrawing plot...").</p>

        <div class="warning">
            <strong>The busy animation does not spin during a single long call on
            its own.</strong> Qt's event loop is frozen for the duration of any one
            blocking Python call — <code>QApplication.processEvents()</code> called
            once before/after a phase makes the label text update, but doesn't make
            anything animate <em>during</em> that phase. To get real animation
            during a per-spectrum loop, the loop itself needs to periodically hand
            control back to the event loop.
        </div>

        <p>The pattern used throughout this codebase: any Manager or Controller
        method with a per-spectrum loop that can run long accepts an optional
        <code>progress_callback=None</code> parameter, and calls
        <code>notify_progress(progress_callback, i)</code> —
        <code>src/modules/utils/progress_utils.py</code> — once per iteration:</p>

        <div class="scheme">
from src.modules.utils.progress_utils import notify_progress

def apply_correction(self, spectra, settings, progress_callback=None):
    for i, spectrum in enumerate(spectra):
        notify_progress(progress_callback, i)
        ...actual per-spectrum work...
        </div>

        <div class="tip">
            <code>notify_progress()</code> is a small, deliberately shared
            helper — before it existed, the 3-line check it wraps
            (<code>if progress_callback is not None and i % 50 == 0:
            progress_callback()</code>) was hand-copied into 10+ methods
            across 8+ files. Confirmed still the single implementation in
            use: every current caller (16 files, spanning Managers,
            Controllers, and <code>plotting.py</code>'s
            <code>overlay_plot_mode</code>/<code>grid_plot_mode</code>) goes
            through this one function — there is no remaining hand-copied
            <code>% 50</code> check anywhere else in the codebase. Call the
            shared helper for any new operation; don't reintroduce the
            inline version.
        </div>

        <p>The caller (a <code>commit_&lt;operation&gt;()</code> method) passes
        <code>lambda: QApplication.processEvents()</code> only when its own
        progress dialog is actually showing, <code>None</code> otherwise — so a
        Manager/Controller method never needs to know or care whether a dialog
        exists.</p>

        <div class="tip">
            When adding this to a new operation, check whether the loop actually
            lives in the Manager or in the Controller that calls it — several
            Controllers in this codebase (Manual Baseline, Spike Removal,
            Interactive Subtraction) do their own per-spectrum work directly rather
            than delegating a whole-list call to the Manager, and the hook needs to
            go wherever the loop actually is, not reflexively in the Manager.
        </div>

        <h2 id="run-id">Linking Sibling Spectra: the <code>run_id</code> Pattern</h2>

        <p>Several operations create more than one output spectrum from a
        single computation — NMF and MCR-ALS export several components from
        one decomposition; Peak Fitting can create a total-fit spectrum, a
        residual spectrum, and one spectrum per individual peak, all from one
        fit. Each of these spectra gets its own <code>correction_history</code>
        entry describing how <em>it specifically</em> was produced — but
        nothing in that alone tells you whether two spectra came from the
        <strong>same</strong> run, or from two separate runs that happened to
        produce similarly-named or similarly-indexed results.</p>

        <div class="rule">
            <strong>Generate one <code>uuid.uuid4()</code> per computation,
            before the loop that builds each output spectrum, and include it
            (as <code>run_id</code>, or a more specific name like
            <code>fit_run_id</code>) in every one of that computation's
            output spectra's <code>correction_history</code> entries.</strong>
        </div>

        <div class="scheme">
def export_components_to_main_list(self, base_label, source_spectra, which=None):
    ...
    # ONE id for every component this call produces — generated once,
    # outside the loop, not per-component.
    run_id = str(uuid.uuid4())
    for k in indices:
        ...
        new_spectrum['metadata']['correction_history'] = append_correction_history(
            None, 'NMF',
            {'run_id': run_id, 'component_index': k + 1, ...}
        )
        </div>

        <p>Two components with the same <code>run_id</code> are provably
        siblings from one decomposition; two components with different
        <code>run_id</code>s are provably from separate runs, even if their
        component indices happen to coincide (e.g. "component 1" from two
        different runs of the same tool). This is now used by NMF, MCR-ALS,
        and Peak Fitting (as <code>fit_run_id</code>, linking the total fit,
        residual, and every individual peak from one fit) — reach for the
        same pattern for any future operation that can produce more than one
        related output spectrum per invocation.</p>

        <h2 id="fresh-metadata">Build Derived-Spectrum Metadata Fresh — Don't Inherit the Source's Whole Dict</h2>

        <div class="warning">
            <strong>Confirmed real bug:</strong> Peak Fitting's total-fit and
            residual spectra were built via
            <code>{k: v.copy() ... for k, v in original_spectrum.items()}</code>
            — copying <em>every</em> key from the source spectrum, including
            its entire import metadata (file path, column index, import
            parameters, valid point count). A computed curve that was never
            imported from anywhere ended up showing a file path in its own
            Metadata panel, taken from a spectrum it happens to be derived
            from.
        </div>

        <p>Individual peak spectra, in the same file, were already built the
        other way — starting from an empty dict and adding only what's
        actually true of the new spectrum:</p>

        <div class="scheme">
# WRONG for a genuinely new, computed spectrum — inherits everything,
# including fields that describe how the SOURCE was imported, not how
# this new spectrum came to exist
derived = {k: v.copy() if hasattr(v, 'copy') else v for k, v in source.items()}

# RIGHT — only x_scale (needed for the plot) and the new y_scale carry
# over; metadata starts empty and gets exactly what's relevant added
# (unique_id, correction_history) — nothing inherited by accident
derived = {
    'x_scale': source['x_scale'].copy(),
    'y_scale': new_y_scale,
    'label': "",  # set by the caller
    'metadata': {},
}
        </div>

        <p>The general rule: if a new spectrum is <strong>computed</strong>
        from another (a fit, a combination, a decomposition result) rather
        than being a <strong>copy</strong> of it (Copy spectra, Add as New),
        build its dict from scratch. Blanket-copying the source's dict is
        only correct when the new spectrum genuinely inherits the source's
        provenance — which a computed result does not.</p>

        <h2 id="dont-duplicate-tracked-mutations">Never Duplicate a Tracked Mutation in a Second Code Path</h2>

        <div class="warning">
            <strong>Confirmed real bug, and the reason it's worth its own
            section:</strong> Rename's previous-name tracking
            (<code>RenameSpectraManager.apply_renamed_labels</code>, which
            correctly writes a <code>correction_history</code> entry) was
            called once, correctly, on the UI-facing spectrum list. But a
            <em>second</em>, separate block of code — building the snapshot
            actually stored in Operations History — did its own, independent
            <code>spectrum['label'] = new_label</code> with no tracking at
            all. As long as both blocks happened to operate on the exact same
            spectrum objects, this was invisible. The moment any other
            operation ran in between two renames (creating genuinely new
            spectrum copies, as every operation in this app correctly does),
            the two code paths were mutating <em>different</em> objects —
            and the untracked one is what actually persisted. Previous names
            silently vanished from history, but only when interleaved with
            another operation — exactly the kind of bug that looks fine in
            the simple case and only breaks in a slightly less common one.
        </div>

        <div class="rule">
            <strong>If a manager method already correctly applies some
            mutation with tracking/side effects, every code path that needs
            that same mutation must call that <em>same</em> method — never
            re-implement the raw operation a second time nearby, even if it
            looks like "just one line" to duplicate.</strong> Two
            implementations of the same idea will drift out of sync the
            moment either one changes, and the bug that results is often
            invisible until a specific ordering of other operations exposes
            it.
        </div>

        <h2 id="pyqtsignal-dict-order">pyqtSignal(list)/(dict) Silently Reorders Nested Dict Keys — Use pyqtSignal(object)</h2>

        <div class="warning">
            <strong>Confirmed real bug, found by direct isolated reproduction (a
            minimal QObject/pyqtSignal test built specifically to confirm this,
            not inferred from reading the code):</strong> a spectrum's
            <code>metadata</code> dict — and nested dicts inside it, like
            <code>import_parameters</code> and <code>duplicate_x_merge</code> —
            appeared with its keys fully alphabetised, at every nesting level,
            but <strong>only</strong> for spectra imported via <strong>File →
            Import data → add</strong>. The exact same file imported via
            <strong>new</strong> showed the correct, original insertion order.
            Python dicts have guaranteed insertion order since 3.7 — nothing in
            this codebase's own code sorts them — so two import paths producing
            different key order for identical input pointed at something outside
            plain Python entirely.
        </div>

        <div class="rule">
            <strong>The cause: <code>ImportController.spectra_added</code> was
            declared <code>pyqtSignal(list)</code>.</strong> A typed PyQt signal
            argument is marshalled through Qt's C++ container types on its way
            from emitter to receiver — a Python <code>dict</code> nested inside
            a typed <code>list</code>/<code>dict</code> payload gets converted to
            <code>QVariantMap</code>, which is a <code>QMap</code>, and
            <code>QMap</code> is <strong>always</strong> kept sorted by key at
            the C++ level. "Add spectra" was the only place in this codebase
            that sent spectrum dicts through a <em>typed</em> signal rather than
            passing them directly (e.g. as a plain Python list/dict argument to
            a normal method call) — which is exactly why only that one path was
            affected, and why it took a targeted debug-print bisection across
            three pipeline checkpoints (<code>_store_spectrum_dict</code> →
            <code>spectra_added.emit(...)</code> → the receiving slot) to
            actually pin the boundary down, rather than being obvious from
            reading either side of the signal on its own.
        </div>

        <div class="scheme">
# WRONG — PyQt marshals the payload through QVariantMap, alphabetising
# every dict's keys (and every nested dict's keys) along the way
spectra_added = pyqtSignal(list)

# RIGHT — tells PyQt to treat the payload as an opaque Python object:
# no C++ container conversion, no reordering. The exact same list/dict
# objects come out the receiving end that went in on the emit() side.
spectra_added = pyqtSignal(object)
        </div>

        <p>Confirmed directly, not just reasoned about: with <code>pyqtSignal(list)</code>,
        emitting a dict and reading it back in the connected slot showed different
        key order than the dict had before <code>emit()</code> was called; with
        <code>pyqtSignal(object)</code>, the order survived unchanged. The general
        rule for this codebase: <strong>any signal that carries a spectrum dict, or
        anything containing one, must be declared <code>pyqtSignal(object)</code>,
        never a typed container signature</strong> — the moment a typed signature
        is used, PyQt's C++ marshalling becomes an invisible, silent transformation
        applied to your data that nothing in the Python-level code chose or can see
        happening.</p>

        <div class="info">
            <strong>Why this was a real bug worth fixing, not just cosmetic:</strong>
            display order in the Metadata dialog is the whole point of that dialog —
            it reflects the order fields were actually recorded (import parameters
            first, correction history in the order corrections happened, etc.).
            Silently re-alphabetising it doesn't lose any data, but it does quietly
            break the one thing that view exists to show accurately.
        </div>

        <h2 id="natural-sort">The Master Spectra List Is Always Re-sorted — <code>order_spectra()</code> Is the One Place That Controls It</h2>

        <div class="rule">
            <strong><code>MainController.order_spectra()</code> is the single
            source of "default order" for the entire app.</strong> It's called
            after essentially every operation that adds, renames, or replaces
            spectra — import, copy, rename, and the post-Apply/Add-as-New
            commit of every processing dialog (over 25 call sites, all
            following the same <code>self.original_spectra =
            self.order_spectra(self.original_spectra)</code> + rebuild-the-
            list-widget pattern). Anything downstream that reads "spectrum
            order" with no explicit sort of its own — SVD/NMF/MCR-ALS
            concentration-profile x-axes, SVD Background Correction, the
            default row order in export tables, etc. — is really just reading
            whatever <code>self.original_spectra</code> currently is, i.e.
            whatever <code>order_spectra()</code> last put it in. There is no
            way to import spectra and have them simply keep file order; they
            are always re-sorted by label immediately.
        </div>

        <div class="warning">
            <strong>Confirmed real bug (2026-08-18): plain alphabetical sort
            silently broke temperature-series ordering.</strong>
            <code>order_spectra()</code> originally sorted with
            <code>key=lambda s: s['label'].lower()</code> — plain text
            comparison. SpecOrd-imported melting-curve labels embed an
            unpadded temperature (e.g. <code>"...run3_heating T=8.60C"</code>),
            and as plain text <code>"T=8.60"</code> sorts <em>after</em>
            <code>"T=79.70"</code> (comparing character by character,
            <code>'8' &gt; '7'</code>) — so a strictly-increasing-temperature
            run displayed as 4.60, 5.60, &hellip;, 79.70, <strong>8.60</strong>,
            80.70, &hellip;, 98.65 in the main list, and every "default order"
            consumer downstream inherited the same corruption.
        </div>

        <div class="scheme">
# Digit run, optionally signed — but the '-' only counts as a sign when
# it's NOT glued onto a preceding letter/digit (distinguishes a real
# negative value from a "sample-1" style separator hyphen).
_NATSORT_CHUNK_RE = re.compile(r'((?&lt;![A-Za-z0-9])-?\d+)')

@classmethod
def _natural_sort_key(cls, label):
    return tuple(
        (0, int(chunk)) if re.fullmatch(r'-?\d+', chunk) else (1, chunk.lower())
        for chunk in cls._NATSORT_CHUNK_RE.split(label) if chunk != ''
    )
        </div>

        <p><strong>How it works:</strong> a label is split into alternating
        text/number chunks; each chunk is tagged <code>(0, int)</code> for a
        number or <code>(1, str)</code> for text, so two labels can always be
        compared even when their chunk patterns differ in length or type at
        some position — the leading 0/1 tag never lets the comparison reach a
        point where Python would try to compare an <code>int</code> to a
        <code>str</code> directly (which raises in Python&nbsp;3). Digit runs
        compare as integers, so <code>"8"</code> vs <code>"79"</code> vs
        <code>"80"</code> compare correctly regardless of how many characters
        each one has, and a label with several embedded numbers (run index
        <em>and</em> temperature, say) nests correctly because each chunk is
        compared in turn, left to right — exactly like comparing version
        numbers segment by segment.</p>

        <div class="info">
            <strong>The sign heuristic exists because hyphens are more often
            separators than minus signs in spectrum labels.</strong> Without
            the negative-lookbehind guard, a naive "digit run with optional
            leading <code>-</code>" pattern would read <code>sample-1</code>,
            <code>sample-2</code>, <code>sample-10</code> as the signed
            integers &minus;1, &minus;2, &minus;10 and sort them 10, 2, 1 —
            backwards from what anyone naming files that way would expect,
            and this pattern (a hyphen used as an index/field separator) is
            far more common in this codebase's labels than an actual signed
            quantity. The lookbehind <code>(?&lt;![A-Za-z0-9])</code> only
            allows a <code>-</code> to attach to a number when the character
            immediately before it is <em>not</em> alphanumeric — so
            <code>"sample-1"</code> (<code>-</code> preceded by the letter
            <code>e</code>) keeps the hyphen as plain text and sorts 1, 2, 10
            as intended, while <code>"T=-5.00C"</code> (<code>-</code>
            preceded by <code>=</code>) is read as the number &minus;5 and
            sorts correctly relative to other signed temperatures. Both
            behaviors were verified directly against test cases covering
            each pattern, together and separately, before this was
            considered done — not just reasoned about.
        </div>

        <p>Purely non-numeric labels (no digits at all) are completely
        unaffected — every chunk is a text chunk, so the result is the exact
        same case-insensitive alphabetical order the old sort already gave.
        This was verified explicitly: sorting a pure-text label set with the
        old <code>.lower()</code> key and the new natural-sort key produces
        identical output.</p>

        <h2 id="new-operation">Checklist: Adding a New Operation</h2>
        <ol>
            <li>Decide whether settings are uniform-for-the-whole-batch (most
                operations) or genuinely per-spectrum. If per-spectrum and the
                Manager needs to remember them <em>across</em> dialog sessions, plan
                for <code>_key_for</code> from the start — see
                <a href="#identity">above</a>.</li>
            <li>Give the Manager a <code>prune_to_current_spectra(current_spectra)</code>
                method if it holds any persistent per-spectrum dictionary, and call
                it whenever the dialog opens — otherwise entries for deleted spectra
                accumulate forever and become available for a re-imported spectrum
                to silently inherit.</li>
            <li>Build the Dialog with its own <strong>Apply</strong> /
                <strong>Add as New</strong> buttons and a <code>commit_callback</code>
                parameter — follow the established pattern, not the older two-step
                Run/Configure design.</li>
            <li>If the Dialog is launched through <code>show_parameters_dialog</code>'s
                generic Run dispatch and remembers settings across sessions, include
                the selection-hash guard from <a href="#settings-cache">above</a> —
                copy it verbatim from a recently-added operation rather than
                rewriting it from scratch.</li>
            <li>If launched via its own menu action instead (like the Analysis
                &amp; Visualization tools), trace the actual call chain end to end
                before assuming a "save settings" step also triggers execution —
                see the Peak Fitting cautionary tale above.</li>
            <li>If the operation creates new spectra, assign each one a fresh
                <code>metadata['unique_id']</code> — never let a copy inherit its
                source's id — and use <code>find_unique_name</code>-style suffixing
                against the full current label set before assigning a name.</li>
            <li>If the operation can plausibly run on hundreds or thousands of
                spectra, add a <code>progress_callback</code> hook to its
                per-spectrum loop — see <a href="#progress-callback">above</a> —
                and never build a per-spectrum result by looping a Qt widget
                selection call one item at a time — see
                <a href="#qt-batch-ops">above</a>.</li>
            <li>Write the test the way this codebase's bugs have actually been
                found: select A, configure something, close/apply; switch to an
                unrelated B; come back to A (or a spectrum that reused A's old
                name) and confirm nothing leaked either direction.</li>
            <li>If the Dialog shows a spectrum name anywhere (its own list, a table
                column, a plot legend/axis), wire in
                <a href="#label-shortening"><code>label_shortening.py</code></a> the same
                way every existing dialog does — give it its own
                <code>make_shorten_names_checkbox()</code> checkbox (unchecked by
                default, independent of the main window's), and drive a paint-only
                delegate or display-map for widgets,
                <code>compute_distinguishing_labels</code>/
                <code>shorten_spectra_labels</code> for plot text, off that local
                checkbox's state. Never let the shortened text leak into an exported
                file name or a newly created spectrum's label.</li>
        </ol>

        <!-- ═══════════════════════════════════════════════════════════
             PROJECT STRUCTURE
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="structure">Project Structure</h2>
        <p>The codebase follows the three-layer split consistently across
        directories:</p>
        <table>
            <tr><th>Path</th><th>Contains</th></tr>
            <tr><td><code>src/controllers/core/</code></td>
                <td><code>main_controller.py</code> (top-level wiring, menu
                connections) and <code>operations_controller.py</code> (the
                generic Run dispatch, commit_* methods, Operations History
                signal handling)</td></tr>
            <tr><td><code>src/controllers/data_analysis/</code></td>
                <td>One controller per Spectra-processing operation</td></tr>
            <tr><td><code>src/controllers/visualization_analysis/</code></td>
                <td>One controller per Analysis &amp; Visualization tool (where one
                exists — several skip this layer, see above)</td></tr>
            <tr><td><code>src/controllers/misc/</code></td>
                <td>Rename, Copy, Delete, Spectrum Metadata, Import Settings,
                Spectrum Selector — the operations that act on the spectrum list
                itself rather than spectral data</td></tr>
            <tr><td><code>src/modules/data_analysis/</code></td>
                <td>Managers for Spectra-processing operations, plus
                <code>incremental_operations_manager.py</code> and
                <code>spectrum_utils.py</code></td></tr>
            <tr><td><code>src/modules/visualization_analysis/</code></td>
                <td>Managers for Analysis &amp; Visualization tools</td></tr>
            <tr><td><code>src/modules/core/</code></td>
                <td><code>spectrum_manager.py</code> — the importer-facing spectrum
                store (label/unique_id mapping at import time)</td></tr>
            <tr><td><code>src/modules/data_io/</code></td>
                <td>One reader/writer module per file format:
                <code>table_data_converter.py</code> (delimited text, delimiter
                auto-detection), <code>row_data_converter.py</code>,
                <code>interlaced_data_converter.py</code>,
                <code>spe_data_converter.py</code> (LightField/WinSpec, optional
                calibrated x-axis), <code>spc_data_converter.py</code> /
                <code>spc_data_writer.py</code> (Thermo/GRAMS, read + write), and
                <code>jasco_jws_reader.py</code> (JASCO SpectraManager OLE2 compound-file
                format, dependency-free — own CFB/directory-tree walk, no
                <code>olefile</code> requirement — with value-range heuristics to
                classify CD/HT/Absorbance channels, since the format stores no channel-type
                string).</td></tr>
            <tr><td><code>src/modules/utils/</code></td>
                <td><code>spectrum_identity.py</code> (<code>spectrum_key</code>/
                <code>spectrum_id</code> — see <a href="#identity">The Golden Rule</a>),
                <code>label_shortening.py</code> (see
                <a href="#label-shortening">above</a>), plus
                <code>app_logger.py</code>, <code>correction_history.py</code>,
                <code>progress_utils.py</code>, <code>resource_path.py</code>,
                <code>spectra_validation.py</code></td></tr>
            <tr><td><code>src/views/dialogs/data_analysis/</code></td>
                <td>Dialogs for Spectra-processing operations</td></tr>
            <tr><td><code>src/views/dialogs/visualization_analysis/</code></td>
                <td>Dialogs for Analysis &amp; Visualization tools</td></tr>
            <tr><td><code>src/views/dialogs/misc/</code></td>
                <td>Rename, Copy, Import, Spectra Selection, Metadata dialogs</td></tr>
            <tr><td><code>src/help/</code></td>
                <td>This file and every other in-app help page — one
                <code>get_&lt;name&gt;_help_title()</code> /
                <code>get_&lt;name&gt;_help_content()</code> pair per topic, wired up
                in <code>main_controller.connect_help_menu_signals()</code></td></tr>
        </table>

        <div class="tip">
            For the full, current directory listing, see
            <a href="__PROJECT_STRUCTURE_URL__"><code>project_structure.txt</code></a>
            at the repository root. Dependencies to install are listed in
            <a href="__REQUIREMENTS_URL__"><code>requirements.txt</code></a>, also at
            the repository root, alongside <code>main.py</code> — install with
            <code>pip install -r requirements.txt</code>. Both links open the real,
            current file on disk when running from source; they will not resolve in
            a built installer (see note in this file's source).
        </div>

        <!-- ═══════════════════════════════════════════════════════════
             TESTING
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="testing">Running the Tests</h2>
        <p>The test suite lives in <code>tests/</code> and runs with
        <code>pytest</code> (config in <code>pytest.ini</code> at the repo root,
        which sets <code>testpaths = tests</code>). From a terminal opened at the
        repo root:</p>
        <div class="scheme">
pytest tests/ -v
        </div>
        <p>What each test file actually covers, how the shared fixtures in
        <code>conftest.py</code> work, and — importantly — a frank note on what
        is <em>not</em> covered yet, all live in <code>tests/README.md</code>
        rather than being duplicated here. In short: pure-Python/numpy fixtures
        with no Qt dependency, one file per import/export/snapshot concern, plus
        <code>test_regression_bugs.py</code> (specific bugs that were found and
        fixed by hand, pinned down so they can't silently come back) and
        <code>test_ground_truth_correctness.py</code> (NMF and MCR-ALS checked
        against known synthetic decompositions — did it recover the right
        answer, not just "did it run").</p>
        <div class="tip">
            When adding a new operation (see the <a href="#new-operation">Checklist</a>
            above), add its regression test the same way this suite's existing ones
            were built: reproduce the specific bug as a minimal synthetic case,
            confirm the test actually fails against the old, buggy code, then confirm
            it passes against the fix. A test that was never seen to fail hasn't
            actually verified anything.
        </div>

        <!-- ═══════════════════════════════════════════════════════════
             BUILD, PACKAGING & REPO HYGIENE
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="build-packaging">Build, Packaging &amp; Repository Hygiene</h2>
        <p><code>BuildInstaller.bat</code> (repo root) does a full release build in
        one step:</p>
        <ol>
            <li>Runs <code>pyinstaller</code> directly from the command line —
                <code>--name</code>, <code>--windowed</code>, <code>--onedir</code>,
                <code>--add-data</code>, <code>--icon</code> are all baked into the
                <code>.bat</code> file itself — against <code>main.py</code>.
                PyInstaller writes <code>SpecAnalytiXBase.spec</code> and the
                <code>build/</code> and <code>dist/</code> folders as a side effect
                of that command. None of the three are hand-maintained recipes;
                all are fully reproducible by rerunning the script.</li>
            <li>Runs Inno Setup (<code>installer.iss</code>) against
                <code>dist/SpecAnalytiXBase/</code> to produce
                <code>installer/Setup_for_SpecAnalytiXBase_ver_&lt;version&gt;.exe</code>.</li>
            <li>On success, deletes <code>build/</code> and <code>dist/</code> —
                both are pure intermediate output at that point and get recreated
                from scratch on the next run. If either step fails, the script
                stops and leaves them in place for debugging instead of silently
                deleting a broken build.</li>
        </ol>
        <p><code>project_structure.txt</code> (linked above) is generated the same
        way, on demand rather than automatically: run
        <code>python generate_project_structure.py</code> from the repo root any
        time the tree changes. It writes a fresh tree with a line count (or file
        size, for binaries) next to every entry, skipping the same build/cache
        folders listed in <code>.gitignore</code>.</p>
        <div class="info">
            <strong>What not to commit:</strong> <code>.gitignore</code> (repo
            root) excludes <code>build/</code>, <code>dist/</code>,
            <code>installer/*.exe</code>, <code>__pycache__/</code>,
            <code>.pytest_cache/</code>, and <code>*.pstats</code> — all
            regenerable output, never source. <code>clean_pycache.bat</code> /
            <code>clean_pycache.sh</code> (repo root) do a one-time sweep of any
            <code>__pycache__</code>/<code>.pytest_cache</code> folders already on
            disk; safe to run any time since Python recreates them automatically
            as needed.
        </div>
    </body>
    </html>
"""
    _content = _content.replace("__PROJECT_STRUCTURE_URL__", _project_structure_url)
    _content = _content.replace("__REQUIREMENTS_URL__", _requirements_url)
    return _content
