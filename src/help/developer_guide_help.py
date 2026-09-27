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

        <div class="info">
            <strong>Naming collision, not two concepts.</strong>
            <code>MainController</code> also has an attribute called
            <code>original_spectra</code> — but it is a completely different thing
            that just happens to share this name. <code>MainController.
            original_spectra</code> is the full list of spectra currently in
            memory (as opposed to <code>selected_spectra</code>, whichever subset
            is checked in the list widget), and it gets overwritten every time an
            operation runs — right after Baseline Correction, for instance, it
            holds the corrected result, not the raw import. Only
            <code>IncrementalOperationsManager.original_spectra</code> (this one)
            is the frozen, never-overwritten baseline. When reading or writing
            code that touches <code>original_spectra</code>, check which object
            owns it before assuming which behavior applies — see also the comment
            at its definition in <code>MainController.initialize_attributes()</code>.
        </div>

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

        <h3 id="revision-counter">Reopening a Dialog: "Remember Unless Something
        Changed" (<code>revision</code> and <code>revision_tracking.py</code>)</h3>
        <p>Several controllers keep <strong>one persistent Manager instance alive
        for the controller's own lifetime</strong>, reused every time its dialog is
        closed and reopened, rather than creating a fresh Manager per dialog session
        &mdash; <code>Map2DController</code>, <code>BaselineCorrectionController</code>,
        <code>NMFController</code>, <code>MCRALSController</code>,
        <code>ClusterAnalysisController</code>, <code>PcaScoresController</code>,
        <code>SOMController</code>, <code>TwoDCorrelationController</code>,
        <code>QCOutlierController</code>, <code>InteractiveSubtractionController</code>,
        <code>SpikeRemovalController</code>, and others. That Manager may be holding a
        previous fit, previously picked baseline points, previously detected spikes, or
        a previously stored subtraction factor &mdash; real, potentially expensive-to-
        reproduce work the user did last time this dialog was open.</p>
        <p>Naively, there are two wrong ways to handle that on the next reopen:</p>
        <ul>
            <li><strong>Never reset.</strong> Reopen the dialog after running a
                completely unrelated operation (SNIP Baseline on a different tab, say)
                and it silently shows a fit/selection computed from spectra that no
                longer look like that &mdash; a real, shipped bug on
                <code>Map2DManager</code> before this existed (see its own
                <code>reset()</code> docstring).</li>
            <li><strong>Always reset.</strong> <code>NMFController</code>/
                <code>MCRALSController</code>'s <code>show_dialog()</code> used to call
                <code>self.manager.reset()</code> unconditionally on every open &mdash;
                correct, but it throws away a perfectly good, possibly slow-to-recompute
                result every single time the dialog is reopened, even when literally
                nothing happened in between.</li>
        </ul>
        <p>The right behavior is in between: keep the Manager's state across a reopen
        <em>unless</em> an operation actually ran, or history navigation moved to a
        different point, or new spectra were imported, since the dialog was last open.
        <code>IncrementalOperationsManager.revision</code> is a plain integer, incremented
        by:</p>
        <ul>
            <li><code>apply_operation()</code> &mdash; every committed operation,
                <strong>except</strong> <code>'Rename'</code> (see below).</li>
            <li><code>set_active_operation()</code> &mdash; any undo/redo navigation to a
                <em>different</em> index than the one already active.</li>
            <li><code>add_spectra_to_original()</code> &mdash; only when spectra were
                actually newly added (a no-op call, e.g. re-importing something already
                present, does not bump it).</li>
        </ul>
        <div class="tip">
            It is a plain monotonic counter, <strong>not</strong> a state identifier.
            Jumping <em>back</em> to a history index a dialog had already cached results
            for still bumps it to a new, higher number &mdash; it does not restore that
            index's earlier value. "Equal" only ever means "provably nothing happened
            since"; it never means "we're back to a state I've cached before". That is
            the right tradeoff for every current caller (each just wants "always re-check
            on any navigation"), and it keeps the implementation simple. A future caller
            that specifically wants "restore my cache for this exact history state even
            across undo/redo" needs a real per-state identifier instead, not an
            assumption about this counter.
        </div>
        <div class="info">
            <strong>Rename is the deliberate exception.</strong> A committed rename goes
            through <code>apply_operation('Rename', ...)</code> exactly like any other
            operation (see <a href="#history-internals">above</a>) &mdash; but it never
            touches a spectrum's actual <code>x_scale</code>/<code>y_scale</code>, only
            its label. Every cache this counter protects is already keyed by
            <code>metadata['unique_id']</code> rather than by label specifically so it
            survives a rename (<code>BaselineManager._key_for</code>,
            <code>SpikeRemovalManager._key_for</code>,
            <code>InteractiveSubtractionManager._key_for</code>, ... &mdash; see
            <a href="#identity">The Golden Rule: Spectrum Identity</a>). Bumping
            <code>revision</code> for a Rename would throw all of that away for no
            reason, on every single rename &mdash; <code>apply_operation()</code>
            explicitly skips the bump when <code>operation_type == 'Rename'</code>.
            Plain spectrum deletion/removal isn't routed through
            <code>apply_operation()</code> at all &mdash; no Operations History entry is
            created for it &mdash; so it never bumps this either, for the same reason.
        </div>
        <p><code>src/modules/utils/revision_tracking.py</code> is the one shared helper
        every one of these controllers uses, rather than each hand-rolling the same
        comparison:</p>
        <div class="scheme">
from src.modules.utils.revision_tracking import revision_changed

class SomeController:
    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = SomeManager()
        self._last_seen_revision = None   # nothing trusted yet

    def show_dialog(self, ...):
        should_reset, self._last_seen_revision = revision_changed(
            self.controller, self._last_seen_revision)
        if should_reset:
            self.manager.reset()   # or a scoped, per-spectrum clear -- see below
        ...
        </div>
        <p><code>revision_changed(main_controller, last_seen_revision)</code> returns
        <code>(should_reset, current_revision)</code>: <code>should_reset</code> is
        <code>True</code> when the current revision differs from what was last seen,
        <strong>or</strong> when the current revision can't even be determined (no
        <code>operations_controller</code> reachable yet, say) &mdash; when in doubt,
        forget rather than risk showing stale computed/picked state. The caller always
        stores <code>current_revision</code> as its new <code>_last_seen_revision</code>
        regardless of <code>should_reset</code>, so the very next comparison is against
        whatever was actually current this time.</p>
        <p>Not every controller resets its Manager wholesale. Some Managers mix
        long-lived <em>settings</em> (correction mode, default thresholds, ...) with
        genuinely stale-prone <em>computed/picked results</em> (a fit, baseline points,
        detected spikes) in the same instance &mdash; for those, clear only the
        computed/picked part, following the same idea as
        <code>BaselineManager.clear_baseline(key)</code>:</p>
        <table>
            <tr><th>Controller</th><th>What a revision change clears</th></tr>
            <tr><td><code>Map2DController</code>, <code>NMFController</code>,
                <code>MCRALSController</code>, <code>ClusterAnalysisController</code>,
                <code>PcaScoresController</code>, <code>SOMController</code>,
                <code>TwoDCorrelationController</code>, <code>QCOutlierController</code></td>
                <td>The whole Manager, via its own <code>reset()</code> &mdash; these
                Managers hold nothing but one fit/result, so a full reset is the whole
                job.</td></tr>
            <tr><td><code>BaselineCorrectionController</code></td>
                <td>Only the affected spectra's own baseline points, via
                <code>self.manager.clear_baseline(key)</code> per spectrum &mdash; other
                spectra's points, and the Manager's own settings, are untouched.</td></tr>
            <tr><td><code>InteractiveSubtractionController</code></td>
                <td>Only <code>self.manager.stored_factors</code> &mdash;
                <code>file_subtrahends</code> (spectra loaded from an external file) are
                untouched, since they don't depend on the main spectrum list's data at
                all.</td></tr>
            <tr><td><code>SpikeRemovalController</code></td>
                <td>Only the currently-shown spectra's own entries, via
                <code>self.manager.reset_for_spectrum(key)</code> per spectrum &mdash;
                mirrors <code>_sync_manager</code>'s own reasoning for why a scoped clear
                matters (a global reset would erase an unrelated, still-valid
                spectrum's markings too).</td></tr>
        </table>
        <div class="info">
            <strong>This is a different mechanism from the selection-hash guard
            above.</strong> <a href="#settings-cache">Remembering Dialog Settings</a>
            governs whether cached <em>settings</em> (the values shown in the dialog's
            own controls) are restored, keyed by whether the <em>selection</em> changed.
            <code>revision</code> governs whether cached <em>results</em> (a fit,
            picked/detected points, a stored factor) are kept, keyed by whether any
            <em>operation</em> ran. A dialog can use either, both, or neither &mdash;
            <code>NMFController</code> uses both (<code>last_op_settings</code> for its
            controls, <code>revision</code> for the Manager's fit); most of the "always
            reset"/"never reset" Manager-holding controllers only needed the latter.
            Selection changing alone, with no operation applied, does not bump
            <code>revision</code> at all &mdash; whether that's actually safe depends on
            the dialog: NMF/MCR-ALS/PCA Scores/2D Correlation always recompute fresh from
            the current selection the moment they're shown (see their own
            <code>_initial_run_pending</code>/<code>showEvent</code>), so a selection
            change is reflected correctly regardless; Cluster Analysis/SOM/QC Outlier
            show a blank "press Run" state until the user acts, for the same reason;
            Manual Baseline/Interactive Subtraction/Spike Removal look up each
            spectrum's own stored state by its own identity, so a different selection
            just shows whatever is (or isn't) stored for <em>those</em> spectra,
            correctly, either way.
        </div>
        <p>Adding a new controller with this same "one persistent Manager across dialog
        reopens" shape? Wire it into <code>revision_tracking.py</code> the same way
        rather than reaching for either extreme again &mdash; and if the Manager mixes
        settings with computed/picked results, clear only the latter, scoped to the
        spectra actually affected, the same way <code>BaselineCorrectionController</code>/
        <code>InteractiveSubtractionController</code>/<code>SpikeRemovalController</code>
        do above.</p>

        <!-- ═══════════════════════════════════════════════════════════
             SNAPSHOT FILE SAVE/LOAD PIPELINE
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="snapshot-pipeline">Snapshot Files (.snapx): Save/Load Pipeline</h2>

        <div class="info">
            <strong>Naming collision to watch for:</strong> "snapshot" is used in
            two unrelated senses on this page. Above (see
            <a href="#history-internals">Operations History</a> and
            <a href="#snapshot-vs-delta">Why Full Snapshots, Not Diffs</a>) it means
            one saved copy of a spectrum's state at one step in
            <code>operations_chain</code> — an in-memory concept, never written to
            disk on its own. Here it means the <em>other</em> sense: a
            <code>.snapx</code> <strong>file</strong>, written by
            <code>SaveManager.save_snapshot()</code> and read back by
            <code>SaveManager.load_snapshot()</code>, that captures the
            <em>entire</em> application state — including every one of those
            in-memory operations-chain entries — in one JSON file. The rest of
            this section is about the file.
        </div>

        <p>A <code>.snapx</code> file is a JSON dump of everything
        <code>_build_state()</code> can reach: <code>original_spectra</code>,
        <code>selected_spectra</code>, plot/UI settings, and — when present — the
        operations-history block (<code>operations_chain</code>,
        <code>active_operation_index</code>, <code>current_parameters</code>,
        <code>import_batches</code>, and a deduplicated operations-baseline copy of
        <code>original_spectra</code>; see
        <a href="#snapshot-vs-delta">Why Full Snapshots, Not Diffs</a> for the
        dedup logic). <code>load_snapshot()</code> is the reverse: read the file,
        then restore each of those pieces back onto a live
        <code>main_controller</code>.</p>

        <div style="background:#FFFFFF; border:1px solid #D0D3DA; border-radius:6px; padding:10px; margin:12px 0; overflow-x:auto;">
        <svg viewBox="0 0 900 1100" xmlns="http://www.w3.org/2000/svg" style="width:100%; height:auto; font-family:Arial,sans-serif;">
            <defs>
                <marker id="snapArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#555"/>
                </marker>
            </defs>

            <rect x="250" y="16" width="400" height="44" rx="6" fill="#2E7D32"/>
            <text x="450" y="43" font-size="13" fill="#fff" text-anchor="middle">User: File &rarr; Import Snapshot</text>

            <line x1="450" y1="60" x2="450" y2="92" stroke="#555" stroke-width="1.5" marker-end="url(#snapArrow)"/>

            <rect x="150" y="92" width="600" height="64" rx="6" fill="#1976D2"/>
            <text x="450" y="116" font-size="13" fill="#fff" text-anchor="middle">SaveSpectraController.load_snapshot()</text>
            <text x="450" y="132" font-size="10" fill="#BBDEFB" text-anchor="middle">shows Yes/No confirmation, with an orange "?" HelpRole button</text>
            <text x="450" y="146" font-size="10" fill="#BBDEFB" text-anchor="middle">"?" re-asks this same question after showing the info &mdash; see the tip below</text>

            <line x1="450" y1="156" x2="450" y2="185" stroke="#555" stroke-width="1.5" marker-end="url(#snapArrow)"/>
            <polygon points="450,185 530,215 450,245 370,215" fill="#FFF3E0" stroke="#E65100" stroke-width="1.5"/>
            <text x="450" y="219" font-size="12" fill="#E65100" text-anchor="middle" font-weight="bold">Yes?</text>

            <line x1="530" y1="215" x2="620" y2="215" stroke="#555" stroke-width="1.3" stroke-dasharray="5,4" marker-end="url(#snapArrow)"/>
            <rect x="620" y="190" width="240" height="50" rx="6" fill="#F4F5F7" stroke="#B0B8C8"/>
            <text x="740" y="211" font-size="11" fill="#555" text-anchor="middle">No &rarr; return False</text>
            <text x="740" y="225" font-size="10" fill="#555" text-anchor="middle">workspace untouched</text>

            <line x1="450" y1="245" x2="450" y2="275" stroke="#555" stroke-width="1.5" marker-end="url(#snapArrow)"/>
            <rect x="120" y="275" width="660" height="64" rx="6" fill="#1976D2"/>
            <text x="450" y="299" font-size="13" fill="#fff" text-anchor="middle">Show QProgressDialog (range 0..LOAD_SNAPSHOT_STAGE_COUNT+1) &middot; call</text>
            <text x="450" y="315" font-size="11.5" fill="#fff" text-anchor="middle" font-family="monospace">SaveManager.load_snapshot(main_controller, file_path, progress_callback)</text>
            <text x="450" y="330" font-size="10" fill="#BBDEFB" text-anchor="middle">old workspace stays exactly as it was &mdash; nothing is cleared before this returns</text>

            <line x1="450" y1="339" x2="450" y2="369" stroke="#555" stroke-width="1.5" marker-end="url(#snapArrow)"/>

            <rect x="70" y="369" width="760" height="430" rx="8" fill="none" stroke="#C2185B" stroke-width="1.5"/>
            <text x="450" y="391" font-size="12" fill="#C2185B" text-anchor="middle" font-weight="bold">SaveManager.load_snapshot() &mdash; internal stages, each reporting progress</text>

            <rect x="100" y="405" width="700" height="34" rx="5" fill="#FCE4EC"/>
            <text x="120" y="427" font-size="11" fill="#8E1339">1. Reading snapshot file &mdash; parse JSON, sanity-check keys, reject duplicate labels</text>

            <rect x="100" y="447" width="700" height="34" rx="5" fill="#FCE4EC"/>
            <text x="120" y="469" font-size="11" fill="#8E1339">2. Restoring plot settings &mdash; _restore_ui_state()</text>

            <rect x="100" y="489" width="700" height="34" rx="5" fill="#FCE4EC"/>
            <text x="120" y="511" font-size="11" fill="#8E1339">3. Restoring spectra &mdash; assign original_spectra/selected_spectra; _resync_spectrum_manager()</text>

            <rect x="100" y="531" width="700" height="46" rx="5" fill="#FCE4EC"/>
            <text x="120" y="549" font-size="11" fill="#8E1339">4. Restoring Operations History &mdash; _restore_operations()</text>
            <text x="120" y="563" font-size="9.5" fill="#AD1457">operations_chain + active_operation_index restored as ONE atomic, validated pair &mdash; see below</text>

            <rect x="100" y="587" width="700" height="34" rx="5" fill="#FCE4EC"/>
            <text x="120" y="609" font-size="11" fill="#8E1339">5. Restoring spectrum selection &mdash; _restore_spectrum_selection()</text>

            <rect x="100" y="629" width="700" height="34" rx="5" fill="#FCE4EC"/>
            <text x="120" y="651" font-size="11" fill="#8E1339">6. Rendering plot &mdash; plot_spectra(); the bar stays just under 100% for the whole render, reaching true 100% only after this returns</text>

            <text x="450" y="687" font-size="10" fill="#555" text-anchor="middle">each stage above calls _report_progress(stage, label) &rarr; progress_callback(stage, label)</text>
            <text x="450" y="701" font-size="10" fill="#555" text-anchor="middle">&rarr; the controller's closure does progress.setValue(stage); progress.setLabelText(label); QApplication.processEvents()</text>

            <rect x="100" y="723" width="700" height="60" rx="6" fill="#FFF3E0" stroke="#E65100" stroke-width="1.3"/>
            <text x="450" y="745" font-size="11" fill="#E65100" text-anchor="middle" font-weight="bold">Fault tolerance: independent try/except per field&#8230;</text>
            <text x="450" y="761" font-size="10" fill="#8E1339" text-anchor="middle">&#8230;EXCEPT stage 4's chain/index pair, which is computed, shape-validated, and</text>
            <text x="450" y="775" font-size="10" fill="#8E1339" text-anchor="middle">assigned together, or both reset to ([], -1) together &mdash; never left mismatched.</text>

            <line x1="450" y1="799" x2="450" y2="829" stroke="#555" stroke-width="1.5" marker-end="url(#snapArrow)"/>

            <rect x="80" y="829" width="330" height="82" rx="6" fill="#2E7D32"/>
            <text x="245" y="851" font-size="12" fill="#fff" text-anchor="middle">Success: return True</text>
            <text x="245" y="867" font-size="10" fill="#DCEDC8" text-anchor="middle">progress dialog closed &middot;</text>
            <text x="245" y="881" font-size="10" fill="#DCEDC8" text-anchor="middle">"Snapshot Loaded" info shown</text>
            <text x="245" y="895" font-size="9" fill="#DCEDC8" text-anchor="middle">(progress reaches its true 100% only now)</text>

            <rect x="490" y="829" width="330" height="82" rx="6" fill="#C62828"/>
            <text x="655" y="851" font-size="12" fill="#fff" text-anchor="middle">Any exception: raise RuntimeError</text>
            <text x="655" y="867" font-size="10" fill="#FFCDD2" text-anchor="middle">progress dialog closed &middot;</text>
            <text x="655" y="881" font-size="10" fill="#FFCDD2" text-anchor="middle">"Error Loading Snapshot" critical shown</text>
            <text x="655" y="895" font-size="9" fill="#FFEBEE" text-anchor="middle">old workspace was never touched &mdash; there was nothing to recover</text>

            <rect x="30" y="927" width="840" height="150" rx="6" fill="#FAFAFA" stroke="#E0E0E0"/>
            <text x="46" y="947" font-size="11" fill="#333" font-weight="bold">Legend</text>
            <line x1="46" y1="967" x2="86" y2="967" stroke="#555" stroke-width="1.5" marker-end="url(#snapArrow)"/>
            <text x="94" y="971" font-size="10" fill="#333">normal flow</text>
            <line x1="46" y1="989" x2="86" y2="989" stroke="#555" stroke-width="1.3" stroke-dasharray="5,4" marker-end="url(#snapArrow)"/>
            <text x="94" y="993" font-size="10" fill="#333">declined / aborted path</text>
            <text x="46" y="1017" font-size="10" fill="#666">This diagram covers the current implementation (progress_callback + atomic chain/index-pair validation).</text>
            <text x="46" y="1033" font-size="10" fill="#666">If you change the stage sequence, update SaveManager.LOAD_SNAPSHOT_STAGE_COUNT and this diagram together.</text>
            <text x="46" y="1053" font-size="10" fill="#666">See the table and callouts below for exactly which fields fail independently vs. as an atomic pair.</text>
        </svg>
        </div>

        <p>The stage numbers in the diagram match
        <code>SaveManager.LOAD_SNAPSHOT_STAGE_COUNT</code> (currently 6) and the
        six <code>self._report_progress(progress_callback, N, "...")</code> calls
        inside <code>load_snapshot()</code>. This <code>progress_callback</code>
        is a different shape from the
        <a href="#progress-callback">per-spectrum progress_callback hook</a>
        described above — it's called once per named stage with
        <code>(stage, label)</code> arguments, not once per spectrum with no
        arguments, because a snapshot load has a handful of coarse phases rather
        than one big per-spectrum loop. Don't assume the two
        <code>progress_callback</code> conventions are interchangeable if you're
        touching either one.</p>

        <p>Stage 6 specifically needs both conventions at once: a large 2D map's
        Grid render can itself run long enough to need pumping <em>during</em> it,
        not just before/after, and that pumping is <code>plot_spectra()</code>'s
        own no-arg <code>progress_callback</code> (forwarded straight into
        <code>grid_plot_mode()</code> / <code>overlay_plot_mode()</code>'s
        per-item <code>notify_progress()</code> calls). So
        <code>load_snapshot()</code> builds a tiny no-arg adapter around its own
        <code>(stage, label)</code> callback — <code>render_progress_callback()</code>
        in the code — and passes <em>that</em> to <code>plot_spectra()</code>,
        rather than either passing its own callback straight through (wrong
        shape) or leaving the render unpumped (freezes visibly for a big grid).</p>

        <p>Stage 5 (<code>_restore_spectrum_selection()</code>) also makes the
        spectrum-selection panel (<code>main_controller.view.spectrum_selection_frame</code>)
        visible, right after it repopulates the list &mdash; deliberately
        <em>before</em> stage 6's render, not after it.
        <code>ImportController.import_snapshot()</code> used to be the
        <em>only</em> place that showed this panel, and only once
        <code>load_snapshot()</code> had returned &mdash; i.e. after the
        render <em>and</em> after the user dismissed the "Snapshot Loaded"
        dialog. That panel starts hidden on a fresh app session (nothing to
        select yet), so the very first time it's ever shown, Qt pays a
        one-time layout/paint cost for it. Landing that cost after
        everything else made a large snapshot look "frozen twice" in a row
        &mdash; once for the render, then again, separately, for the panel
        to pop in. Moving the call to stage 5 pays that one-time cost while
        the progress dialog is still up and already accounting for the
        time being spent, instead of stacking it on top afterwards. The
        call in <code>import_snapshot()</code> is now a harmless,
        idempotent safety net rather than the only place this happens.</p>

        <div class="tip">
            <strong>Adding a stage?</strong> Bump
            <code>LOAD_SNAPSHOT_STAGE_COUNT</code>, add the new
            <code>_report_progress(...)</code> call at the right point, and update
            this diagram together — the controller's <code>QProgressDialog</code>
            range is set from that constant, so a stale count just makes the bar
            finish early or never reach full, not crash.
        </div>

        <div class="danger">
            <strong>Real Qt gotcha #1 — a custom button's role does not stop
            <code>QMessageBox</code> from closing on it.</strong> An earlier
            version of the confirmation dialog assumed
            <code>QMessageBox.HelpRole</code> meant a button added with that role
            wouldn't close the box when clicked — reasonable-sounding, and wrong.
            Every button added to a <code>QMessageBox</code> (via
            <code>addButton()</code>, whatever role) shares the same internal
            <code>QDialogButtonBox</code>, whose <code>clicked</code> signal
            <code>QMessageBox</code> connects, internally, straight to closing
            itself — role plays no part in that. Clicking the orange "?" was
            closing the still-unanswered "replace workspace?" question along with
            the info box, every time. Confirmed by actually running this dialog,
            not by re-reading the docs more carefully — the fix
            (<code>SaveSpectraController.load_snapshot()</code>) doesn't fight
            this behaviour; it works with it: <code>msg_box.exec_()</code> runs
            in a loop, and a click identified as the help button
            (<code>msg_box.clickedButton() is help_button</code>) shows the info
            and then simply calls <code>exec_()</code> again on the same
            instance, which Qt allows any number of times. Only a real Yes/No
            click breaks the loop. If you add a second custom button anywhere in
            this codebase, assume it will close its <code>QMessageBox</code> too,
            and design for that instead of trying to prevent it.
        </div>

        <div class="danger">
            <strong>Real Qt gotcha #2 — <code>QProgressDialog</code> auto-closes
            itself the instant <code>setValue()</code> reaches the maximum.</strong>
            <code>autoClose</code> and <code>autoReset</code> both default to
            <code>True</code>: reaching the maximum value triggers an internal
            <code>reset()</code>, which (with <code>autoClose</code> still
            <code>True</code>) hides the dialog — regardless of whether the work
            that value is supposed to represent has actually finished. Stage 6
            ("Rendering plot…") reports itself by calling
            <code>progress.setValue(6)</code>, which <em>is</em> this dialog's
            configured maximum (<code>progress.setRange(0,
            SaveManager.LOAD_SNAPSHOT_STAGE_COUNT)</code>) — so the dialog was
            vanishing the instant the label changed to "Rendering plot…",
            <em>before</em> the actual (potentially slow, for a large Grid plot)
            render underneath it had even started. The app then looked frozen
            with no progress feedback at all for however long that render took,
            followed eventually by the "Snapshot Loaded" message appearing on its
            own. Fixed by calling <code>progress.setAutoClose(False)</code> and
            <code>progress.setAutoReset(False)</code> right after creating the
            dialog — <code>load_snapshot()</code> already closes it explicitly on
            every exit path, so the automatic behaviour was never needed, only
            harmful. Any new <code>QProgressDialog</code> in this codebase whose
            last reported value equals its maximum needs the same two lines,
            unless it genuinely wants the auto-close.
            <br><br>
            <strong>Addendum:</strong> disabling auto-close alone does not fix a
            second, separate visual problem &mdash; a bar whose <em>reported</em>
            value equals the dialog's configured maximum sits at a literal 100%
            for the entire duration of whatever work that value represents,
            which still reads as "stuck" even once the dialog stops vanishing.
            Stage 6 hit this too: <code>progress.setValue(6)</code> against
            <code>progress.setRange(0, 6)</code> is 100% the moment the label
            changes, not when the render actually finishes. Fixed by widening
            the range to <code>(0, LOAD_SNAPSHOT_STAGE_COUNT + 1)</code> &mdash;
            one step past the real stage count &mdash; so stage 6's reported
            value is always below the maximum, and only calling
            <code>progress.setValue(LOAD_SNAPSHOT_STAGE_COUNT + 1)</code> (the
            true 100%) once the whole load has actually returned successfully.
        </div>

        <div class="danger">
            <strong>Real Qt gotcha #3 &mdash; clearing a widget can silently
            change application state through a signal you forgot was
            connected.</strong> An earlier version of this controller called
            <code>main_controller.spectra_list_widget.clear()</code> right after
            confirmation, before the load even started, purely to avoid showing
            stale spectra while a slow load ran. <code>QListWidget.clear()</code>
            fires <code>itemSelectionChanged</code>, which is connected (see
            <code>SpectrumSelectorController.on_item_selection_changed()</code>)
            straight to recomputing <code>main_controller.selected_spectra</code>
            from whatever is currently selected in the widget &mdash; which,
            right after a <code>.clear()</code>, is nothing. So the very act of
            "just tidying the list" was silently wiping the real selection
            before <code>SaveManager.load_snapshot()</code> had even been
            called, every single time. It went unnoticed until a user tested a
            <em>failed</em> load and reported that everything came back
            correctly except the selection &mdash; which, by then, had already
            been destroyed by this codebase's own cleanup, not by the failure
            itself. <code>_restore_spectrum_selection()</code> (stage 5, in
            <code>save_spectra_manager.py</code>) already knew to
            <code>blockSignals(True)</code> around its own
            <code>clear()</code>/repopulate for exactly this reason &mdash; the
            bug was a second, unguarded <code>.clear()</code> call outside that
            method entirely. Lesson: a widget's <code>.clear()</code> (or any
            bulk mutation) is never purely cosmetic once something is connected
            to its change signals &mdash; check what's listening before adding
            one, especially outside code that already knows to guard it.
        </div>

        <h3>Fault Tolerance, Field By Field</h3>
        <p>Every consumer of the operations history — starting with
        <code>IncrementalOperationsManager.get_current_spectra()</code>, which
        does a direct, unbounds-checked
        <code>self.operations_chain[self.active_operation_index]</code> — trusts
        that <code>active_operation_index</code> is always a valid position in
        <code>operations_chain</code>, or <code>-1</code>. That's the reason
        stage&nbsp;4 is the one exception to the "restore each field
        independently" rule used everywhere else in <code>_restore_operations()</code>:</p>
        <table>
            <tr><th>Field</th><th>Restored by</th><th>On failure</th></tr>
            <tr><td>Plot/UI settings</td><td><code>_restore_ui_state()</code></td>
                <td>Warning logged; that one setting stays at its pre-load value —
                    the rest of the load continues</td></tr>
            <tr><td><code>original_spectra</code> / <code>selected_spectra</code></td>
                <td>Direct assignment, after <code>_validate_unique_labels()</code></td>
                <td>Duplicate labels raise <code>ValueError</code> before
                    assignment — this specific failure aborts the <strong>whole</strong>
                    load (see the danger box below), unlike everything else in this
                    table</td></tr>
            <tr><td><code>operations_chain</code> + <code>active_operation_index</code></td>
                <td><code>_restore_operations()</code>'s atomic block</td>
                <td>Any shape or range problem in <strong>either</strong> resets
                    <strong>both</strong> to <code>([], -1)</code> together</td></tr>
            <tr><td><code>current_parameters</code>, <code>import_batches</code>,
                    per-operation <code>original_spectra</code> baseline</td>
                <td><code>_restore_operations()</code>, independent try/except each</td>
                <td>Warning logged; that one field is skipped, the rest of
                    <code>_restore_operations()</code> continues</td></tr>
            <tr><td>Spectrum selection</td>
                <td><code>_restore_spectrum_selection()</code></td>
                <td>Warning logged; selection left at whatever
                    <code>_resync_spectrum_manager()</code> produced</td></tr>
        </table>

        <div class="warning">
            <strong>Two different failure classes — easy to conflate when reading
            the code quickly.</strong> The per-entry/per-field defensiveness inside
            <code>_restore_operations()</code> only kicks in once
            <code>load_snapshot()</code>'s own outer structure is intact — the
            outer <code>try/except Exception</code> around the <em>entire</em>
            method (reading the file, validating labels, restoring UI, resyncing
            <code>SpectrumManager</code>, restoring operations, restoring
            selection, and the final render) converts <strong>any</strong>
            unhandled exception, at <strong>any</strong> of those stages, into one
            generic <code>RuntimeError</code>. So a truly malformed file (bad
            JSON, duplicate labels, a missing required key) aborts the whole load
            before anything is restored — but a well-formed file with one bad
            <em>piece</em> inside an otherwise-good operations-history block does
            <strong>not</strong> abort the load; only that one piece is skipped.
        </div>

        <div class="warning">
            <strong>Why there's no proactive "clear the old workspace" step
            anymore.</strong> An earlier version of
            <code>SaveSpectraController.load_snapshot()</code> cleared the
            graphics view and the spectra list widget <em>before</em> calling
            <code>SaveManager.load_snapshot()</code>, purely so a slow load
            wouldn't leave the previous workspace's spectra sitting on screen
            while it ran. That single line caused the bug described in
            "Real Qt gotcha #3" above (a silent, connected-signal wipe of
            <code>selected_spectra</code>), and it complicated failure handling
            for no real benefit: <code>SaveManager.load_snapshot()</code> already
            replaces every piece of the workspace itself once it succeeds
            &mdash; stage&nbsp;3 assigns <code>original_spectra</code> /
            <code>selected_spectra</code> directly, stage&nbsp;5 rebuilds the
            spectra list widget from scratch (with signals blocked,
            correctly), and stage&nbsp;6 redraws the plot. Nothing beyond
            those stages was ever needed to make a successful load's contents
            appear; the extra clear only existed to hide the <em>previous</em>
            contents while waiting, at the cost of the bug above and of
            leaving the workspace genuinely empty (not merely stale) if the
            load then failed. It was removed rather than patched, matching
            this codebase's stated preference (see "Renaming Is Forward-Only")
            for the design with the fewest states to reason about over a
            cleverer one with more edge cases. The one real trade-off: on a
            failed load, whatever was on screen before
            <strong>Import Snapshot</strong> was clicked stays on screen,
            completely unchanged &mdash; not because anything was deliberately
            preserved, but because nothing ever touched it. This also makes
            snapshot loading match the shape of a regular data import
            (<strong>File &rarr; Import data &rarr; new</strong> only clears
            existing spectra once a new file has actually loaded), instead of
            being the one exception to it.
        </div>

        <h3 id="snapshot-file-size">The .snapx File Size: Deduplication and Compression</h3>
        <p>A real 95&nbsp;MB text file (an 85&times;55 Raman 2D map &mdash;
        4675 spectra) produced an 837&nbsp;MB <code>.snapx</code> file after
        just two operations (a SNIP baseline correction, then cosmic-ray
        removal). That's not a JSON/base64 encoding problem &mdash;
        <code>_json_encode()</code>'s base64-encoded numpy arrays are already
        an efficient binary representation. It's <strong>logical
        duplication</strong>: before the fix described here,
        <code>_build_state()</code> could write out <em>five</em> full copies
        of the same spectra data, when only three are ever genuinely
        distinct.</p>

        <table>
            <tr><th>Slot</th><th>Genuinely distinct?</th><th>Handling</th></tr>
            <tr><td>Top-level <code>original_spectra</code></td>
                <td>Yes &mdash; the canonical copy</td>
                <td>Always stored</td></tr>
            <tr><td><code>selected_spectra</code></td>
                <td>No &mdash; always reconstructable as
                    <code>original_spectra</code> filtered by
                    <code>selected_indices</code>, in ascending order (exactly
                    what <code>SpectrumSelectorController.get_selected_spectra()</code>
                    itself builds)</td>
                <td>Omitted whenever it matches that reconstruction; stored
                    only when it doesn't (see below)</td></tr>
            <tr><td><code>operations.original_spectra</code> (pre-operations
                    baseline)</td>
                <td>Only when operations have actually been applied</td>
                <td>Omitted when identical to the top-level copy (existing
                    dedup &mdash; see
                    <a href="#snapshot-vs-delta">Why Full Snapshots, Not Diffs</a>)</td></tr>
            <tr><td>Each <code>operations_chain[i]['output_spectra']</code></td>
                <td>Yes, for every entry <strong>except</strong> whichever one
                    is currently active</td>
                <td>Every other entry is a genuinely distinct frozen copy
                    (intended design &mdash; see
                    <a href="#history-scope">What Belongs in Operations History</a>);
                    only the <strong>active</strong> entry is checked, because
                    <code>main_controller.original_spectra</code> always
                    mirrors <code>get_current_spectra()</code>'s output (see
                    <code>operations_controller.jump_to_operation_state()</code>)
                    &mdash; so that one entry is always a second copy of data
                    already saved at the top level</td></tr>
        </table>

        <p>Whether the two new dedup cases fire is decided the same way the
        existing baseline dedup already did: by comparing actual content with
        <code>_spectra_lists_equal()</code> (every field, including nested
        metadata &mdash; not just label/x_scale/y_scale), never by checking
        which entry <em>should</em> be active or assuming the chain's shape.
        <code>_spectra_lists_equal</code> fails toward <strong>not
        equal</strong> on anything it can't be fully sure about &mdash; the
        safe direction here, since the only thing riding on the answer is
        whether a second copy gets kept. A deduped
        <code>operations_chain</code> entry doesn't just drop its
        <code>output_spectra</code> key; it's marked
        <code>output_spectra_omitted: True</code> so
        <code>_restore_operations()</code> knows to backfill it on load, using
        <code>_deep_copy_spectra_list()</code> to give that entry its own
        independent copy &mdash; never a second reference to
        <code>main_controller.original_spectra</code>, or a later edit to one
        would silently corrupt the other. The <code>output_spectra_omitted</code>
        flag is deleted immediately after a successful backfill: leaving it
        behind would let a <em>future</em> save-then-reload cycle
        misinterpret it, overwriting that entry's by-then-legitimately-different
        data with whatever <code>original_spectra</code> happens to be at that
        later load.</p>

        <div class="info">
            <strong>A more aggressive option was tried and rejected.</strong>
            A content-addressed array-pooling prototype &mdash; deduplicating
            <code>x_scale</code> by content hash across all 4675 spectra,
            since every pixel in a 2D map shares the same wavenumber axis
            &mdash; got a single copy's JSON size from 161.8&nbsp;MB down to
            81.8&nbsp;MB. But gzip alone on that same single copy (see below)
            already reaches 44.0&nbsp;MB &mdash; capturing nearly all of that
            benefit without introducing shared, pooled objects that every
            future piece of code touching a spectrum dict would need to know
            not to mutate in place. Not implemented, on a risk/benefit call.
        </div>

        <p>On top of the deduplication, <code>save_snapshot()</code> now
        gzip-compresses the JSON before writing it, at
        <code>SNAPSHOT_GZIP_LEVEL = 6</code> by default &mdash; the same idea
        as a <code>.docx</code> or <code>.xlsx</code> file really being a zip
        archive under a familiar extension. The <code>.snapx</code> extension
        and the Save/Load dialogs' file filters are completely unchanged;
        only the bytes on disk differ. <code>_load_state()</code> checks for
        gzip's own 2-byte magic number (<code>b'\x1f\x8b'</code>) before
        falling back to the plain <code>'{'</code>-byte check it always used
        &mdash; so every <code>.snapx</code> file saved before this change,
        which is plain UTF-8 JSON text with no magic number, keeps loading
        exactly as before, forever. A file that starts with the gzip magic
        number but isn't actually a valid gzip stream (a truncated or
        corrupted copy) raises the same friendly "not a valid snapshot"
        error as any other unreadable file, rather than a raw
        <code>gzip.BadGzipFile</code>.</p>

        <p><code>save_snapshot()</code> takes an optional
        <code>compression_level</code> argument overriding
        <code>SNAPSHOT_GZIP_LEVEL</code> for that one save. Any caller
        (not the GUI &mdash; see below) can in principle pass a value
        outside gzip's valid 1-9 range; rather than raising and failing
        the whole save over that, the manager <strong>clamps</strong> it
        &mdash; quietly caps it to the nearest valid value instead of
        rejecting it (15 becomes 9, -3 becomes 1) &mdash; via
        <code>max(1, min(9, int(compression_level)))</code>. The GUI
        itself can never trigger this: <code>SaveOptionsDialog</code>
        exposes three named presets
        rather than the raw number &mdash; "Fast" / "Balanced (default)" /
        "Maximum" mapping to levels 1 / 6 / 9
        (<code>SaveOptionsDialog._COMPRESSION_PRESETS</code>) &mdash; visible
        only when Snapshot is the selected format, and passed through
        <code>SaveController._save_snapshot()</code> from
        <code>settings['compression_level']</code>. "Balanced" is
        deliberately kept equal to <code>SNAPSHOT_GZIP_LEVEL</code>, so
        leaving the control at its default behaves identically to before it
        existed.</p>

        <p>Real numbers, measured end-to-end on the same 85&times;55 Raman
        map, after both fixes and verified with an actual
        <code>save_snapshot()</code> / <code>load_snapshot()</code> round trip
        (including confirming the backfilled operations-chain entry matches
        exactly and isn't an aliased object). These specific numbers use
        SYNTHETIC stand-ins for SNIP Baseline and Cosmic Ray Removal (a
        shared linear ramp; one shared replacement row) &mdash; they
        demonstrate the dedup + gzip mechanism cleanly, but see
        <a href="#chain-entry-order-independent">A Second Bug</a> below for
        the number confirmed with the real algorithms, on a real user's
        machine:</p>

        <table>
            <tr><th>Stage</th><th>Size</th></tr>
            <tr><td>5 stored copies, plain JSON (the old behaviour)</td>
                <td>811&nbsp;MB &mdash; matches the ~837&nbsp;MB originally
                    reported</td></tr>
            <tr><td>3 distinct copies, deduplicated, still plain JSON</td>
                <td>487&nbsp;MB</td></tr>
            <tr><td>3 distinct copies, deduplicated <strong>and</strong>
                    gzip-compressed (level 6) &mdash; the shipped result</td>
                <td>226&nbsp;MB &mdash; a 3.6&times; reduction, 72% smaller
                    than the original 811&nbsp;MB</td></tr>
        </table>

        <p>Gzip's compression level is a real time/size trade-off, measured
        on this same ~487&nbsp;MB deduplicated payload: level 1 compresses in
        about 4&nbsp;s to roughly 155&nbsp;MB; level 6 (the level used) takes
        roughly 8&ndash;13&nbsp;s and reaches the sizes above. Decompression
        on load is fast regardless of the level it was saved at (roughly
        1.5&nbsp;s for this file), since gzip's decompression cost doesn't
        depend on the compression level used to create the stream &mdash;
        only the save side pays for the extra squeeze.</p>

        <div class="warning">
            <strong>These exact ratios are specific to this file, not a
            guarantee.</strong> How much dedup and gzip help depends on how
            many genuinely-redundant copies a given session's operations
            history happens to contain, and how compressible the actual
            spectral data is. A session with many distinct operations kept
            deliberately (the intended "frozen copy per operation" design)
            will still produce a large file &mdash; that growth with the
            number of operations was never the bug being fixed here.
        </div>

        <h3 id="chain-entry-order-independent">A Second Bug: The Active Chain Entry's Dedup Check Was Order-Sensitive</h3>
        <p>The numbers above (3 distinct copies &rarr; 226&nbsp;MB) were
        measured with the real algorithms and the real 85&times;55 data
        file, and the dedup logic worked exactly as intended &mdash; in a
        hand-built test. In actual GUI use, real users kept seeing files
        around 328&nbsp;MB instead: the active <code>operations_chain</code>
        entry's dedup (see the table above) was silently never firing.</p>

        <p>The cause: <code>_spectra_lists_equal()</code> originally
        compared its two lists <strong>positionally</strong> &mdash;
        <code>zip(a, b)</code>, item by item. <code>MainController.
        original_spectra</code> gets re-sorted into natural label order by
        <code>order_spectra()</code> after every operation (see
        <a href="#natural-sort">The Master Spectra List Is Always
        Re-sorted</a>). The matching <code>operations_chain</code> entry's
        own <code>output_spectra</code>, however, is built as "unaffected
        spectra in their current order, then the processed spectra
        appended at the end" (see <code>SNIPBaselineController.
        commit_snip_baseline()</code> / <code>CosmicRayController.
        commit_cosmic_ray_removal()</code>) and is never sorted. Both lists
        end up holding the exact same spectra, genuinely identical content
        &mdash; just in a different order &mdash; and a purely positional
        comparison reported that as "not equal," keeping a second full
        copy that should have been dropped.</p>

        <p><code>_spectra_lists_equal()</code> now tries the positional
        comparison first (unchanged, and still the only comparison used
        when it already succeeds), and only when that fails does it fall
        back to matching spectra by their <code>label</code> instead of
        their position &mdash; sorting both lists by label onto temporary
        copies used only for this one comparison, never touching the real,
        in-memory lists or anything written to the file. This fallback
        only runs when every label is unique on both sides; if either list
        has a duplicate or missing label, it stays with "not equal" (the
        same fail-safe direction as everywhere else in this function
        &mdash; at worst a second copy is kept, never data lost). See
        <code>TestSpectraListsEqual.test_same_spectra_in_different_order_is_equal</code>
        and the sibling tests around it for the exact cases covered,
        including one confirming a genuine content difference still isn't
        masked by reordering.</p>

        <p>Confirmed fixed on a real user's machine, real data, real GUI
        session (load 2D map &rarr; SNIP Baseline &rarr; Cosmic Ray Removal
        &rarr; Save as compressed Snapshot, Balanced preset): <strong>328
        &rarr; 233&nbsp;MB</strong>. The remaining size is the two things
        this dedup was never meant to remove: the SNIP-only intermediate
        step kept in the operations history (real, intentional undo data),
        and the pre-operations baseline (kept so the whole chain can be
        reverted) &mdash; see the table above.</p>

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

        <h2 id="mcr-als-nnls-hybrid">MCR-ALS's Per-Column <code>nnls</code> Solves: Skip the
        Constraint When It Isn't Binding</h2>

        <div class="rule">
            <strong>Before assuming <code>scipy.optimize.nnls()</code> itself is slow,
            check whether the constraint it enforces (x &ge; 0) is even active for a
            given row/column. When the plain, UNCONSTRAINED least-squares solution
            already comes out non-negative everywhere, it IS the exact
            <code>nnls</code> solution — <code>nnls</code>'s own definition guarantees
            this, so there is nothing left for the constrained solver to find that the
            cheap unconstrained one didn't already find.</strong>
        </div>

        <p><code>MCRALSManager.compute()</code>'s alternating-least-squares loop calls
        <code>nnls()</code> once per spectrum row (the C-step) and once per wavelength
        column (both branches of the ST-step) — a plain Python <code>for</code> loop,
        since each row/column is an independent least-squares problem sharing the same
        constraint matrix. For a 2D map with thousands of pixels, that's thousands of
        individual <code>nnls()</code> calls per iteration.</p>

        <p><code>MCRALSManager._hybrid_nnls_columns(A, B)</code> replaces all three
        loops. It first solves the WHOLE batch's unconstrained least-squares problem
        in one shot (<code>np.linalg.pinv(A) @ B</code>, one matrix multiply regardless
        of how many columns), then only calls the real <code>nnls()</code> for the
        columns whose unconstrained answer actually went negative somewhere.</p>

        <div class="scheme">
# SLOW — one nnls() call per column, even for columns that don't need the constraint
ST = np.zeros((n_components, n))
for j in range(n):
    st_j, _ = nnls(C, D[:, j])
    ST[:, j] = st_j

# FAST — same result, fewer nnls() calls
unconstrained = np.linalg.pinv(A) @ B     # whole batch, one shot
result = unconstrained.copy()
needs_nnls = ~np.all(unconstrained >= 0, axis=0)
for j in np.flatnonzero(needs_nnls):      # only the columns that actually need it
    x_j, _ = nnls(A, B[:, j])
    result[:, j] = x_j
        </div>

        <p>Confirmed identical to the original per-column loop's output (relative
        difference ~1e-15 against real <code>scipy.optimize.nnls</code> on a real
        85&times;55 Raman map — ordinary floating-point roundoff between two
        different-but-exact linear algebra routes, not an approximation). Measured
        with a controlled, repeated A/B comparison on realistic C/ST states drawn from
        an actual alternating fit: a consistent <strong>1.2&times;&ndash;2.1&times;</strong>
        per call. Confirmed by the user on their own real, baseline-corrected 55&times;85
        map with "Run N times, keep best": <strong>20s &rarr; 10s</strong> at 10 runs,
        <strong>105s &rarr; 48s</strong> at 50 runs — close to the top of the measured
        range once per-run noise averages out over many runs.</p>

        <p>How much this helps is entirely data-dependent — it's proportional to how
        many rows/columns already come out non-negative unconstrained, which tends to
        be more likely for cleaner (e.g. already baseline-corrected), well-separated,
        lower-component-count fits. In the worst case (every column still needs the
        real solve) it costs one extra cheap <code>pinv()</code> call and is never
        slower than the original loop, never different.</p>

        <p>NMF does <strong>not</strong> have an equivalent bottleneck: its standard
        path calls scikit-learn's own compiled <code>NMF</code> solver directly, and
        its hand-written "with references" multiplicative-update loop
        (<code>_fit_with_references()</code>) already updates the entire W/H matrices
        at once per iteration, with no per-row/per-column <code>nnls</code>-style loop
        to hybridize. Confirmed directly in <code>nmf_manager.py</code> before ruling
        this out — the two managers don't share this code, so this optimization was
        MCR-ALS-only by necessity, not by oversight.</p>

        <h2 id="best-of-n-parallelization-attempt">"Run N Times, Keep Best": Why It's Still a
        Sequential Loop (Investigated, Not Skipped by Oversight)</h2>

        <div class="rule">
            <strong>Before parallelizing a loop of numpy/scipy calls, measure — don't assume
            more workers means more speed. This codebase's own OpenBLAS is already
            internally multi-threaded, so naive Python-level parallelism can easily make
            things SLOWER by fighting itself for the same cores.</strong>
        </div>

        <p>Both <code>Map2DManager.compute_mcr_map()</code>/<code>compute_nmf_map()</code>
        (n_runs &gt; 1) and the standalone MCR-ALS/NMF dialogs' own "Run N times, keep best"
        button run every trial in a plain sequential <code>for</code> loop, on the main GUI
        thread (the map dialog's version has no progress dialog at all — just a wait cursor,
        by deliberate design; the standalone dialogs pump <code>QApplication.processEvents()</code>
        between trials to keep a real, cancellable <code>QProgressDialog</code> responsive).
        Each trial is fully independent (its own fresh manager instance, its own random
        seed, no shared state) — an "embarrassingly parallel" shape — so parallelizing it
        looks, on paper, like a bigger win than the per-column <code>nnls</code> shortcut
        above. It was investigated directly, on a real 85&times;55 map, before deciding not
        to build it (yet):</p>

        <ol>
            <li><strong>Plain <code>ThreadPoolExecutor</code> made it slower, not faster:</strong>
                10.4s sequential &rarr; 15.2s with 2 threads &rarr; 18.1s with 4 threads, for 6
                MCR-ALS trials. OpenBLAS here is already internally multi-threaded
                (<code>OpenBLAS 0.3.29 ... MAX_THREADS=64</code>, no
                <code>OPENBLAS_NUM_THREADS</code> cap set anywhere in this codebase) — running
                several trials as Python threads at once just makes several already-
                multi-threaded BLAS calls fight over the same physical cores. Python-level
                threading is not a safe default speed-up for numpy-heavy code without capping
                BLAS's own thread count first.</li>
            <li><strong>Real multiprocessing, done carefully, only helped marginally on the
                dev sandbox:</strong> with each worker's <code>OPENBLAS_NUM_THREADS</code> /
                <code>OMP_NUM_THREADS</code> explicitly capped to 1 (to avoid repeating the
                oversubscription problem above across processes instead of threads),
                <code>ProcessPoolExecutor(max_workers=2)</code> measured 9.4s vs. a
                10.3s BLAS-capped sequential baseline for the same 6 trials — roughly 10%,
                not the ~2x you'd hope for from 2 cores. Process start-up and pickling the
                whole spectra dataset to each worker ate a real chunk of the theoretical
                gain at this trial count and data size. This was measured on a 2-core
                sandbox; it was <em>not</em> measured on a real, likely-more-multicore
                desktop, so don't treat "marginal" as the final word for every machine —
                only for this one.</li>
            <li><strong>A real blocker, found independently of the timing result:</strong>
                this app is packaged with PyInstaller (<code>SpecAnalytiXBase.spec</code>),
                and <code>main.py</code> does not call
                <code>multiprocessing.freeze_support()</code>. Without it, spawning worker
                processes from a frozen Windows <code>.exe</code> is a known way for each
                worker to re-launch the whole GUI instead of just running its trial — this
                needs to be added to <code>main.py</code>, right after its existing
                <code>if __name__ == "__main__":</code> guard, and tested against an actual
                frozen build, before any <code>ProcessPoolExecutor</code>/
                <code>multiprocessing.Pool</code> use could ship safely.</li>
        </ol>

        <p>Given a measured ~10% gain (on this sandbox), an unmeasured payoff on real
        hardware, and real added complexity (per-worker BLAS thread capping, the
        <code>freeze_support()</code> fix, and redesigning the standalone dialogs' Cancel
        button for a parallel loop instead of a sequential one it can just stop between
        iterations of), this was deliberately <strong>not</strong> built. The decision:
        keep "Run N times, keep best" sequential for now, and revisit parallelizing it only
        as its own dedicated piece of work — profiled on a real, target machine first — if
        a future feature (e.g. bootstrap resampling, which needs the same "refit many times
        independently" shape) makes the sequential cost actually painful in practice.</p>

        <h2 id="mcr-als-bootstrap-uncertainty">MCR-ALS Bootstrap Uncertainty: Residual
        Resampling With a Warm-Started Refit</h2>

        <div class="rule">
            <strong>Two different kinds of "how much should I trust this MCR-ALS result"
            question exist, and answering one does not answer the other. Conflating them
            &mdash; e.g. re-fitting from random inits and calling the spread "uncertainty" &mdash;
            silently mixes rotational-ambiguity noise into what should be a pure
            measurement-noise-sensitivity estimate, or vice versa.</strong>
        </div>

        <p><strong>"Run N times, keep best"</strong> (see its own section above) answers
        "did this fit land in the wrong local optimum, or a solution that fits equally well
        but is chemically wrong?" by re-fitting from different random starting points ON THE
        SAME DATA. <strong>"Bootstrap Uncertainty"</strong> (<code>MCRALSController.
        compute_bootstrap_uncertainty()</code>) answers a different question: "how much would
        THIS specific, already-chosen result change if I'd collected this data with a
        different noise realization?" That needs the opposite discipline: every replicate
        must be refit from the SAME starting point (the result being bootstrapped), on
        DIFFERENT synthetic data built from that result's own residual noise.</p>

        <h3>The method</h3>
        <ol>
            <li>Fit once normally (or via "Run N times, keep best") to get a reference
                C0, ST0, and the aligned data matrix D0 the fit was run on
                (<code>MCRALSManager.D</code> &mdash; stored specifically so this doesn't
                need to rebuild it from spectra and re-run the whole alignment/interpolation
                pipeline a second time).</li>
            <li>Compute residuals: <code>residuals = D0 - C0 @ ST0</code>.</li>
            <li>For each of B resamples: resample whole residual ROWS (each spectrum's own
                residual vector, kept intact) with replacement, and build
                <code>D_b = C0 @ ST0 + residuals[row_idx, :]</code>. Resampling whole rows
                rather than individual points preserves whatever wavelength-to-wavelength
                correlation the real noise has within one spectrum &mdash; a per-point i.i.d.
                assumption would be a stronger (and less defensible) claim than this method
                needs to make.</li>
            <li>Refit D_b <strong>warm-started from ST0</strong> (<code>init_ST=ST0</code> on
                <code>MCRALSManager.compute()</code> &mdash; see below), under the exact same
                constraints (c_nonneg, st_nonneg, normalize_spectra, closure, references,
                fix_references) the reference fit used.</li>
            <li>Collect every replicate's ST/C, take pointwise percentiles (2.5%/97.5% for a
                95% band) across replicates.</li>
        </ol>

        <h3>init_ST: the warm-start hook, and why it also disables reordering</h3>
        <p><code>MCRALSManager.compute()</code> gained an <code>init_ST</code> parameter:
        when given, it skips 'init' (svd/random), the sign-orientation fix-up, and reference-
        row seeding entirely, and uses that array as the starting ST directly. This is
        deliberately NOT exposed as a user-facing "initialization" option &mdash; it exists
        for exactly one caller, this bootstrap.</p>
        <p>It ALSO skips the end-of-fit "reorder components by explained variance" step that
        every normal fit does. This is not an oversight-turned-workaround &mdash; it's
        necessary for correctness. Without it, two bootstrap replicates whose two components'
        explained variances happen to come out in a slightly different order (easily possible
        when EVs are close and noise varies between replicates) would silently swap which
        physical component occupies slot 0 vs. slot 1 &mdash; and averaging/percentile-ing slot 0
        across replicates would then mix two DIFFERENT components' distributions together,
        producing a nonsensical band. Confirmed directly with a test constructed so a plain
        (non-warm-started) fit's own reordering would have flipped the slots: warm-started
        fits keep <code>init_ST</code>'s own order (see
        <code>tests/test_mcr_als_bootstrap.py::TestInitSTWarmStart::
        test_warm_start_skips_reorder_by_explained_variance</code>).</p>
        <p>A genuinely converged reference fit warm-starts back to itself in as few as 2
        iterations (the ALS loop always runs at least 2 before it can compare consecutive
        lack-of-fit values) with the same result to ~1e-12 &mdash; confirmed directly. An
        UNDER-converged "reference" (one that merely exhausted max_iterations while still
        slowly improving, rather than actually reaching tol) does NOT warm-start back to
        itself, because it wasn't at a fixed point to begin with; this surfaced as a genuine
        test-writing mistake during development (assuming a 200-iteration, tol=1e-8 run had
        converged when it had not) before being caught and fixed with a properly converged
        reference (tol=1e-10, ~900 iterations for that particular synthetic case) &mdash; worth
        remembering before assuming any "warm start didn't reproduce the reference" report is
        this feature's bug rather than an under-converged reference.</p>

        <h3>A deliberate simplification: display-only band normalization</h3>
        <p>The Concentrations tab's "Normalize to 100% per spectrum" toggle, when active,
        normalizes the bootstrap band using the REFERENCE fit's own row sums, not each
        individual bootstrap replicate's own row sum. Re-normalizing every one of the B
        replicates independently would be more statistically rigorous, but adds real
        complexity for what is a display-only band (it doesn't feed into any saved/exported
        number) &mdash; this is a deliberate, documented simplification, not an oversight.</p>

        <h3>Orchestration lives on the controller, not the dialog</h3>
        <p>Unlike "Run N times, keep best" (whose trial loop and near-best consensus logic
        live in the DIALOG, calling the controller's single-trial <code>compute_trial()</code>
        repeatedly), the entire bootstrap loop &mdash; resampling, refitting, percentile
        aggregation &mdash; lives in one method,
        <code>MCRALSController.compute_bootstrap_uncertainty()</code>. The dialog's job is
        just UI: prompt for a resample count, drive a <code>QProgressDialog</code> with
        Cancel (via a <code>cancel_check</code> callback checked before each replicate, same
        "plain sequential loop with real Cancel support" pattern as "Run N times, keep best" &mdash;
        see the parallelization section above for why this stayed sequential), and redraw the
        Pure Spectra / Concentrations tabs afterward. Putting the loop on the controller
        (rather than duplicating it in the dialog, best-of-n-style) was a deliberate choice
        here specifically because the loop's correctness (residual resampling, warm start,
        percentile math) has real statistical content worth unit-testing directly without a
        GUI in the way &mdash; see <code>tests/test_mcr_als_bootstrap.py</code>.</p>
        <p><strong>See also:</strong> the MCR-ALS help page's own
        <a href="help://mcr_als#bootstrap-uncertainty">Bootstrap Uncertainty section</a> for
        the user-facing explanation this technical section backs up, and the User Guide's
        MCR-ALS entry for the short version.</p>

        <h2 id="nmf-bootstrap-uncertainty">NMF Bootstrap Uncertainty: the Same Method,
        One Genuinely New Wrinkle</h2>

        <p>NMF's own <strong>"Bootstrap Uncertainty&hellip;"</strong>
        (<code>NMFController.compute_bootstrap_uncertainty()</code>) is the direct port of
        the MCR-ALS feature described just above &mdash; same residual-row resampling, same
        warm-started refit from the reference's own converged result
        (<code>init_H</code> on <code>NMFManager.compute()</code>, mirroring
        <code>init_ST</code>), same skip of the end-of-fit reorder-by-explained-variance
        step, same display-only band-normalization simplification, same
        controller-owns-the-loop/dialog-is-just-UI split. Rather than repeat all of that,
        this section only covers what's genuinely different for NMF.</p>

        <h3>The one real difference: NMF has two fitting algorithms, MCR-ALS has one</h3>
        <p>MCR-ALS always fits via alternating NNLS, whatever the caller asked for &mdash;
        the reference fit and every bootstrap replicate go through the exact same code.
        NMF does not: a cold fit with no reference spectra goes through scikit-learn's own
        <code>NMF</code> class, while a fit anchored to reference spectra (or, now, a
        warm-started bootstrap replicate) goes through <code>NMFManager.
        _fit_with_references()</code>, a hand-written Lee &amp; Seung multiplicative-update
        (MU) loop &mdash; written out by hand specifically because scikit-learn's NMF cannot
        hold individual rows of H fixed, which reference-anchoring needs. <code>init_H</code>
        is only usable by that hand-written loop (scikit-learn has no supported way to
        warm-start from an arbitrary externally-chosen H), so every bootstrap replicate
        ALWAYS goes through <code>_fit_with_references()</code>, regardless of whether the
        reference itself came from scikit-learn or not.</p>
        <p>Is that safe? Yes, for the thing that actually matters here (component identity
        staying put, not rotating between replicates): any genuine local minimum of the
        Frobenius NMF objective is <em>also</em> a fixed point of the Lee &amp; Seung MU
        update rule, since both are just alternative iterative schemes for finding
        stationary points of the same objective under the same non-negativity constraints.
        A replicate warm-started from a real local minimum can only refine toward it (or a
        point immediately next to it), never jump to some unrelated rotation.</p>
        <p>Is it as FAST as MCR-ALS's warm start, which stabilizes back to the reference in
        as few as 2 iterations? Only sometimes &mdash; and this was a genuine surprise
        during development, worth recording so it doesn't get mistaken for a bug later.
        Warm-starting the MU loop from a reference that was ITSELF fit through the MU loop
        (e.g. via a trivial, non-fixed reference spectrum) reproduces that reference in 2
        iterations, atol&nbsp;&asymp;&nbsp;1e-4 &mdash; exactly like MCR-ALS. But warm-starting from a
        REAL scikit-learn cold fit (the common case: no reference spectra at all) typically
        does NOT stabilize quickly. Confirmed directly on a synthetic test mixture:
        scikit-learn's default convergence tolerance (<code>tol=1e-4</code>, not exposed
        through <code>NMFManager.compute()</code>) let it call itself "converged" at a
        reconstruction error of ~0.0068, while tightening that same tolerance to 1e-6/1e-8/
        1e-10 kept driving the SAME fit's reconstruction error down by orders of magnitude
        further (0.0068 &rarr; 0.000068 &rarr; 0.0000007 &rarr; ...), at what is still the
        same fixed point &mdash; scikit-learn was simply stopping early relative to how
        precisely the MU loop's own convergence check (a tighter, ~1e-6 relative-change
        threshold) demands. A bootstrap replicate warm-started from such an
        under-converged reference has real further downhill progress available and will
        use up to its whole <code>max_iter</code> budget doing it, landing at a MORE
        precise, but still non-rotated, nearby optimum. See
        <code>tests/test_nmf_bootstrap.py::TestInitHWarmStart</code> for both cases side by
        side: <code>test_warm_start_from_own_converged_result_is_stable</code> (same
        algorithm throughout, near-instant) and
        <code>test_warm_start_from_sklearn_cold_fit_stays_in_same_basin</code> (the
        realistic case &mdash; asserts the two guarantees that actually hold there:
        reconstruction error never gets WORSE than the reference it started from, since
        plain multiplicative updates are monotonically non-increasing by construction, and
        every replicate stays strongly correlated with, i.e. not rotated away from, the
        reference's own components).</p>
        <p>Practical upshot: this is not a correctness problem &mdash; the shipped
        end-to-end tests (<code>TestComputeBootstrapUncertainty</code>) confirm real
        bootstrap runs still preserve component identity across replicates and produce
        sane, monotonic-bounded bands. But does the width of the reported band actually
        depend on how far each replicate got to converge, given all this? Checked directly
        (not just assumed) by computing the same bootstrap band at several
        <code>max_iter</code> budgets on two independent synthetic mixtures: from the
        app's own default (500) up to 10&times; that (5000), the mean band width barely
        moved (well under 1% relative change) &mdash; the SPREAD across replicates, which is
        what the band actually measures, stabilizes early even while each replicate's own
        absolute reconstruction error keeps slowly improving underneath it. Dropping well
        BELOW the default, to 150, did measurably narrow the concentration (W) band by
        about 9% in one of the two checks (the component/H band barely moved, under 1%,
        even there) &mdash; so an unusually tight iteration budget can make the reported
        uncertainty look a little smaller than it really is, though the effect was modest
        and only showed up once iterations were cut well below what the app already uses
        by default. No evidence this is a problem at the app's normal settings; worth
        knowing about rather than assuming away if <code>max_iter</code> is ever driven
        very low for other reasons.</p>
        <p><strong>See also:</strong> the NMF help page's own
        <a href="help://nmf#bootstrap-uncertainty">Bootstrap Uncertainty section</a> for the
        user-facing explanation this technical section backs up, and the User Guide's NMF
        entry for the short version.</p>

        <h2 id="rgb-overlay-export">2D Map RGB Overlay Mode</h2>

        <p><code>Map2DDialog</code>'s <b>RGB overlay</b> is an 8th Map Type radio button
        (alongside Intensity/SVD/PCA/NMF/MCR-ALS/Map arithmetic/Cluster overlay) that composes
        up to three already-computed component maps into one false-color composite, shown
        inline in the main map canvas. It started as a standalone modal dialog
        (<code>_RGBOverlayDialog</code>, reachable from an <b>Export ▾</b> menu item) and was
        converted into a full mode with its own inline right-side panel (<code>_rgb_panel</code>)
        specifically so it could reuse the dialog's existing ROI-selection and spectrum-inspection
        machinery "as in other modes" rather than duplicating it inside a second dialog. The
        standalone dialog and its menu item are gone; everything below describes the current,
        only architecture. A few decisions worth recording for future maintenance:</p>

        <p><b>Gated like any other decomposition-dependent control.</b>
        <code>self._radio_rgb</code> starts disabled (<code>setEnabled(False)</code>, id 7 in
        <code>self._radio_group</code>) and is flipped on by <code>_update_rgb_radio_enabled()</code>,
        called right after every successful SVD/PCA/NMF/MCR-ALS compute (both the normal
        <code>_compute_map()</code> path and the "Run N times, keep best" trial-result path).
        Once enabled it stays enabled for the rest of the dialog's life &mdash;
        <code>Map2DManager</code>'s per-kind caches are only ever replaced, never cleared back to
        empty once populated, so there's no scenario where RGB overlay would need to become
        unavailable again.</p>

        <p><b>Any computed kind, per channel, independently.</b> Rather than requiring one active
        decomposition (the single-component map view's own model, driven by the four radio
        buttons and <code>_decomp_kind()</code>), each of the three channel boxes in
        <code>_rgb_panel</code> (<code>_rgb_channel_widgets</code>, one dict of
        enable/kind/comp widgets per channel) reads
        <code>Map2DManager.get_component_coefficients(kind, index)</code> directly for whichever
        kind that channel's own combo currently names (<code>_rgb_channel_array()</code>). This
        works because <code>Map2DManager</code> already keeps SVD, PCA, NMF and MCR-ALS results in
        separate, independently-populated caches (<code>_U</code>/<code>_s</code>,
        <code>_pca_U</code>, <code>_nmf_manager</code>, <code>_mcr_manager</code> respectively)
        that computing one kind does not clear for the others &mdash; verified directly
        (<code>grep</code> for where each is reset to <code>None</code> turns up only
        <code>__init__</code> and that kind's own failure path). So if the user has, say, run both
        NMF and MCR-ALS for the same map dimensions, both are simultaneously available and mixable
        across R/G/B (<code>_compose_rgb_overlay()</code>) &mdash; nothing here recomputes
        anything; a channel with nothing computed for its selected kind simply leaves that
        channel's Component combo empty (<code>_refresh_rgb_component_combo()</code>), and an
        unchecked or empty channel contributes exactly zero, not a fallback component.</p>

        <p><b>Fully live &mdash; no explicit first build, ever.</b> Unlike NMF/MCR-ALS,
        composing an RGB overlay never requires an "Update Map" press: re-reading cached
        coefficients and renormalizing is cheap, unlike a fit. Every panel control
        (Enable/Source/Component per channel, and the percentile spinboxes) is wired to
        <code>_on_rgb_panel_changed()</code>, which calls <code>_compute_rgb_overlay_map()</code>
        unconditionally whenever <code>_radio_rgb.isChecked()</code> &mdash; including the very
        first <b>Enable</b> checkbox toggle, while <code>self._rgb_overlay_array</code> is still
        <code>None</code>. An earlier version of this method guarded on
        <code>self._rgb_overlay_array is not None</code>, requiring one explicit "Compute
        Map"/"Update Map" press before the panel would respond to anything &mdash; that guard was
        removed because it silently blocked exactly the case a user hits first (checking
        <b>Enable</b> on a fresh panel), leaving them looking at an unchanged placeholder with no
        obvious next step. <code>_compute_map()</code> still dispatches to
        <code>_compute_rgb_overlay_map()</code> when <b>Update Map</b> is pressed directly, so the
        button keeps working, but nothing in this mode depends on it ever being pressed.</p>

        <p><b>Auto-restore on mode entry.</b> <code>_on_mode_changed()</code>'s RGB branch calls
        <code>_compute_rgb_overlay_map(quiet=True)</code> immediately on entering RGB overlay if
        any channel is already enabled (typically: switching away and back), so a previously-built
        composite reappears with no button press and none of the two informational/warning
        <code>QMessageBox</code> popups that the same method shows on an explicit press
        (<code>quiet=True</code> suppresses "Invalid Dimensions" and "Nothing to show"/"No data
        for enabled channel(s)"; a genuine exception still raises <code>QMessageBox.critical</code>
        unconditionally regardless of <code>quiet</code> &mdash; that dialog exists to surface a
        real bug, not to explain an expected result to someone who just clicked a button). Before
        attempting this the branch resets <code>self._rgb_overlay_array = None</code> and only
        calls <code>_refresh_rgb_component_combo()</code> for a channel whose combo's item count no
        longer matches its Source kind's real component count &mdash; refreshing every channel
        unconditionally on every mode entry was an early bug caught during this feature's own
        testing: it silently reset each channel's Component selection back to index 0 on every
        switch, discarding whatever the user had actually picked.</p>

        <p><b>SVD/PCA/NMF/MCR-ALS: redraw from cache on mode re-entry instead of refitting.</b>
        <code>self._decomp_needs_refit</code> is a per-kind dict (<code>{'svd': False, 'pca':
        False, 'nmf': False, 'mcr': False}</code>) tracking whether a kind's cached fit is stale
        relative to its current settings. It is set <code>True</code> only by the things that
        actually invalidate a fit &mdash; the "Configure {kind} range&hellip;" dialog's acceptance
        handler, the NMF/MCR-ALS <b>Components to fit</b> spinner's change handler
        (<code>_on_decomp_n_changed</code>), and <code>_on_reference_settings_changed</code> when
        references change without auto-recompute &mdash; and cleared in <code>_compute_map()</code>'s
        decomposition branch right after a successful fit. <code>_on_mode_changed()</code>'s
        decomposition branch checks both that the kind has <code>n_components &gt; 0</code> and
        that it isn't marked dirty; if so, <code>_redraw_cached_decomp_map(kind)</code> reshapes
        <code>Map2DManager.get_component_coefficients(kind, 0)</code> straight from the cache
        (the same read-only mechanism the RGB channels use) and redraws, skipping
        <code>compute_svd_map()</code>/<code>compute_pca_map()</code>/<code>compute_nmf_map()</code>/
        <code>compute_mcr_map()</code> entirely. Only when the dirty flag is set (or nothing has
        been fitted yet for that kind) does the mode fall back to its usual "Press 'Update Map' to
        compute&hellip;" placeholder. This now extends to every fit setting, not just range/count/
        references: NMF's <b>Init.</b>/<b>Max iter.</b> and MCR-ALS's <b>Max iter.</b>/<b>Non-neg. C</b>/
        <b>Non-neg. ST</b>/<b>Closure</b> controls are wired to <code>_on_fit_settings_changed(kind)</code>,
        which does exactly what <code>_on_decomp_n_changed</code> and
        <code>_on_reference_settings_changed</code> already did: set <code>self._decomp_needs_refit[kind]
        = True</code> and put up the same red "&hellip; changed &mdash; press 'Update Map' to refit&hellip;"
        status text. These controls only exist (are only visible/enabled) while their own kind is the
        active Map Type, so <code>_on_fit_settings_changed</code> also guards on
        <code>self._decomp_kind() == kind</code> before touching anything, purely defensively against a
        signal firing while that kind isn't current. Changing one of these settings, then switching Map
        Type away and back without touching anything else, now correctly requires 'Update Map' instead
        of silently redrawing a fit computed under the old settings.</p>

        <p><b>Hover-tooltip artists don't survive <code>ax.cla()</code> &mdash; reset the
        reference, don't just hide it.</b> Found while testing the two features above, but the bug
        itself is general, not RGB-specific: every full map redraw (<code>_MapCanvas.update_map()</code>,
        <code>_draw_rgb_overlay_map()</code>, <code>_draw_cluster_map()</code>) calls
        <code>self.ax.cla()</code>, which removes the existing hover-tooltip
        <code>Annotation</code> (<code>self._tooltip</code>, created by <code>ax.annotate()</code>
        in <code>_make_tooltip()</code>) from the axes' own artist list. The Python object survives
        &mdash; <code>self._tooltip</code> is still a valid reference &mdash; but it is now
        orphaned: no longer in <code>ax.texts</code>, and <code>.axes</code> no longer points at
        the current axes. <code>enable_hover()</code>, called right after every redraw via
        <code>_on_map_computed()</code>, only creates a fresh tooltip when
        <code>self._tooltip is None</code>; otherwise it just calls
        <code>self._tooltip.set_visible(False)</code> on whatever it already has &mdash; which, on
        the second and every subsequent redraw, is that same orphaned object. Confirmed directly:
        after a second redraw, <code>tooltip.get_visible()</code> still reports whatever was last
        set (no exception, no visible symptom in code), but <code>tooltip in ax.texts</code> is
        <code>False</code> and <code>tooltip.axes is ax</code> is <code>False</code> &mdash; it is
        never actually drawn again no matter what <code>set_visible()</code> is called with. Fixed
        by setting <code>self._tooltip = None</code> (or <code>self._map_canvas._tooltip = None</code>
        from the dialog) immediately after each of those three <code>ax.cla()</code> calls, so
        <code>enable_hover()</code>'s <code>is None</code> check is always true right after a
        redraw and a fresh, correctly-attached tooltip gets created every time.</p>

        <p><b>Percentile stretch is display/export-only.</b> One shared pair of spinboxes
        (<code>_rgb_lo_pct_spin</code>/<code>_rgb_hi_pct_spin</code>) feeds all three channels, but
        each enabled channel is independently rescaled to <code>[0, 1]</code> from <i>its own</i>
        data's <code>[lo%, hi%]</code> percentile range (<code>_rgb_normalize_channel()</code>)
        &mdash; same percentage, different absolute cutoff per channel, since each channel is
        usually a different component with a different value range. This is purely for compositing
        into the displayed/exported image, the same convention as the single map's manual colorbar
        clipping (<code>_apply_clim</code>). It never writes back into the manager's cached arrays,
        unlike <code>invert_component()</code> (see the single-component map view), which flips
        <code>_U</code>/<code>_pca_U</code> in place &mdash; the wording here was tightened after a
        user question conflated the two ("doesn't touch your fit results" needed to say explicitly
        that it never mutates the underlying decomposition, the way Invert deliberately does).</p>

        <p><b><code>_last_map_data</code> gets a grayscale proxy, not <code>None</code>.</b>
        Dozens of existing methods across the file (ROI drawing/toggling, the hover tooltip,
        colorbar clim, CSV export, click-to-inspect, "Clear all ROIs" redraw) all gate on
        <code>self._last_map_data is not None</code> and assume a real, finite
        <code>(n_rows, n_cols)</code> scalar array. Leaving it <code>None</code> in RGB mode would
        have silently broken ROI tool activation and click-to-inspect, which the user specifically
        wanted to keep working "as in other modes". Instead, <code>_compute_rgb_overlay_map()</code>
        stores a synthetic scalar proxy in <code>_last_map_data</code>
        (<code>rgb.mean(axis=2)</code>, a grayscale luma average) while the real
        <code>(n_rows, n_cols, 3)</code> composite lives separately in
        <code>self._rgb_overlay_array</code>. Consumers that would misuse the proxy meaningfully
        are explicitly special-cased instead of left to operate on it silently: <code>_on_map_click</code>
        checks <code>_radio_rgb.isChecked()</code> first and reports real
        <code>R=.. G=.. B=..</code> values from <code>_rgb_overlay_array</code> rather than the
        proxy's averaged scalar; <code>_export_map()</code> (CSV/Excel) and
        <code>_show_roi_statistics()</code> (ROI comparison stats) both guard on
        <code>_radio_rgb.isChecked()</code> and refuse with an explanatory message rather than
        exporting or comparing the meaningless grayscale average &mdash; use the panel's own
        <b>Export as PNG…</b> (<code>_export_rgb_overlay_png()</code>) instead, which composes and
        writes the real RGB array.</p>

        <p><b>Native resolution, no cmap/norm.</b> The composite is written at exactly
        <code>n_rows &times; n_cols</code> — one image pixel per map pixel, matching
        <code>_export_map()</code>'s own convention of exporting raw data rather than whatever
        on-screen "Equal aspect ratio" stretching is active (equal aspect, and interpolation, only
        affect <code>_draw_rgb_overlay_map()</code>'s on-screen preview canvas, never the exported
        file). Because the array passed to <code>plt.imsave()</code> is already an
        <code>(n_rows, n_cols, 3)</code> float array in <code>[0, 1]</code>, matplotlib writes it
        as literal RGB and ignores <code>cmap</code>/<code>norm</code> entirely (those only apply
        to scalar 2-D arrays) &mdash; no manual uint8 conversion needed, and no new dependency:
        this uses matplotlib's own PNG writer, not Pillow, consistent with "matplotlib: all
        plotting" already covering this codebase's plotting/export needs. For the same reason
        <code>_draw_rgb_overlay_map()</code> never attaches a colorbar (unlike, say,
        <code>_draw_cluster_map()</code>'s discrete tab10 colorbar) &mdash; the pixel colors here
        are literal data, not a colormap-encoded scalar, so there's nothing for a colorbar to
        show.</p>

        <h2 id="roi-persistence">2D Map: ROI Regions Survive Mode Switches</h2>

        <p>Drawing an ROI region, then switching Map Type (SVD &rarr; NMF, Intensity &rarr;
        RGB overlay, ...), used to silently delete every region. Root cause: <code>_on_mode_changed()</code>
        unconditionally calls a shared <code>_invalidate_map()</code> helper at its top, used for
        many unrelated reasons (mode switch, a metric change with nothing computed yet, a
        decomposition setting that forces a refit) &mdash; and that helper's job description
        ("clear the displayed map and show a recompute-needed placeholder") had, for no principled
        reason, grown a <code>self._clear_all_rois()</code> call inside it. Every one of
        <code>_invalidate_map()</code>'s callers inherited that side effect whether or not it made
        sense for them.</p>

        <p><b>The fix is a scope correction, not a feature bolt-on.</b> An ROI region's identity is
        a set of <code>(row, col)</code> grid positions (<code>bounds</code> in each region dict) &mdash;
        nothing about which <i>kind</i> of map is being viewed or computed, or what its computed
        values are, is part of that identity. The only thing that can actually invalidate a
        region's positions is the grid itself changing shape: <code>n_rows</code>/<code>n_cols</code>
        are shared, dialog-wide state (not per-mode), so a region drawn in SVD mode is exactly as
        valid in NMF or RGB overlay mode as it was where it was drawn &mdash; right up until Rows &times;
        Cols is actually edited, at which point a 25&times;25 region's bounds may no longer even be
        inside a reshaped 5&times;125 grid. So <code>self._clear_all_rois()</code> was removed from
        <code>_invalidate_map()</code> entirely and moved to the top of <code>_on_dims_changed()</code>
        &mdash; the sole handler for both dimension spinboxes' <code>valueChanged</code> signals &mdash;
        unconditionally, before the existing is_fast/dims_ok branch. This also fixes a latent
        asymmetry that predates this change: the "fast" modes (Intensity/Arithmetic/Cluster) took
        the <code>_compute_map()</code> branch on a dims change and never called
        <code>_invalidate_map()</code> at all, so a dims change previously left stale ROI regions in
        place for those modes specifically while clearing them for SVD/PCA/NMF/MCR-ALS/RGB &mdash;
        now both branches clear unconditionally, resolving the inconsistency rather than
        preserving it.</p>

        <p><b>Data surviving isn't the same as being visible &mdash; the same orphaned-artist bug as
        the hover tooltip, generalized.</b> Not clearing <code>self._roi_regions</code> only fixes
        half the problem: every full map redraw (<code>_MapCanvas.update_map()</code>,
        <code>_draw_rgb_overlay_map()</code>, <code>_draw_cluster_map()</code>, all three calling
        <code>ax.cla()</code>) destroys every existing ROI <code>Rectangle</code>/<code>Ellipse</code>/
        <code>PathPatch</code>/<code>Line2D</code> artist the exact same way it was found to destroy
        the hover-tooltip <code>Annotation</code> (see the RGB overlay section above) &mdash; the
        region dict's <code>'patch'</code> reference survives as a Python object, but it's no
        longer part of the axes' artist list and <code>set_visible()</code>/redrawing it changes
        nothing on screen. <code>_redraw_roi_patches()</code> fixes this the same way
        <code>_draw_ref_markers()</code> already fixed it for NMF/MCR-ALS reference-pixel markers:
        rebuild a fresh artist for every region from its OWN stored data (<code>bounds</code>, plus
        <code>cx</code>/<code>cy</code>/<code>a</code>/<code>b</code> for an ellipse) and reassign
        <code>reg['patch']</code> to point at it &mdash; except for a <code>'lasso'</code> region,
        which has no separate vertex store in the dict, so its vertices are read off the existing
        (orphaned but still perfectly readable as a plain Python object) <code>PathPatch</code> via
        <code>.get_path().vertices</code> before building its replacement. <code>_last_rect_patch</code>/
        <code>_last_ellipse_patch</code> (used by <code>_on_roi_selected</code>/
        <code>_on_ellipse_roi_selected</code> to tell "resize the just-drawn region's handles" apart
        from "start a new one") are updated to the fresh artist too, in the same loop &mdash; otherwise
        dragging a handle right after a mode switch would silently mutate an orphaned patch nobody
        can see instead of the one actually on screen.</p>

        <p><b>Wiring: a canvas-level hook, not a dialog-level afterthought bolted onto six call
        sites.</b> <code>_MapCanvas.update_map()</code> is called from six different places in the
        dialog; rather than adding a <code>self._redraw_roi_patches()</code> call after each one
        (guaranteed to be missed by whichever call site gets added next), <code>_MapCanvas</code>
        gained a generic <code>self._post_redraw_hook</code> callable (<code>None</code> by default,
        set once via <code>set_post_redraw_hook()</code> right after dialog construction), invoked
        at the end of both <code>update_map()</code> and <code>_draw_stale()</code> (the "Settings
        changed" placeholder) right before the final <code>draw_idle()</code>. The dialog wires
        <code>self._map_canvas.set_post_redraw_hook(self._redraw_roi_patches)</code> once in
        <code>__init__</code>, immediately after constructing <code>_map_canvas</code>. This keeps
        <code>_MapCanvas</code> ignorant of what an "ROI region" even is (same separation of
        concerns as the existing <code>_ref_pixel_by_component</code> mechanism) while guaranteeing
        every current AND future <code>update_map()</code>/<code>_draw_stale()</code> call site gets
        the hook for free. <code>_draw_rgb_overlay_map()</code> and <code>_draw_cluster_map()</code>
        don't go through <code>update_map()</code> at all (they draw directly on
        <code>self._map_canvas.ax</code>), so each calls <code>self._redraw_roi_patches()</code>
        directly, right before its own final <code>draw()</code>.</p>

        <div class="rule">
            <strong>Take-home: a matplotlib artist does not survive <code>ax.cla()</code>, and
            "the reference still isn't <code>None</code>" is not evidence that it does.</strong>
            <code>ax.cla()</code> removes every artist from the axes' internal container lists
            (<code>ax.texts</code>, <code>ax.patches</code>, <code>ax.lines</code>, ...) but does
            nothing to whatever external variable still points at one of those artist objects
            &mdash; the object stays alive, its attributes stay readable and even individually
            settable, and no exception is ever raised for touching it. It has simply stopped being
            part of what gets drawn. This codebase hit this same bug twice in one session (the
            hover-tooltip <code>Annotation</code>, then every ROI patch/line type) precisely
            because the failure mode looks like nothing at all: no traceback, no visibly-wrong
            state in a debugger (<code>get_visible()</code> still returns whatever was last set),
            just a UI element that silently stops appearing after the second redraw and not the
            first. Any future full-canvas redraw path in this dialog that adds its own persistent
            overlay artist (on <code>self.ax</code>, surviving across redraws by design) needs
            either its own re-attach-after-<code>cla()</code> step or a subscription to
            <code>_post_redraw_hook</code> &mdash; there is no default in matplotlib that does this
            automatically, and "I didn't touch that code" is exactly how this bug hides for a long
            time in a path that isn't exercised by an automated test with real Qt widgets and a
            second real redraw in sequence (a single-redraw test, which is the easy one to write,
            cannot catch it at all).
        </div>

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

        <h2 id="redraw-after-operation">Interactive Update Must Survive Apply / Add as New</h2>

        <p>Every <code>commit_*</code> method used to end by calling
        <code>self.controller.plot_spectra(...)</code> directly, and
        <code>_rebuild_spectra_list_with_selection()</code> (called just before that,
        by every one of them) forced <code>interactive_mode_checkbox.setChecked(True)</code>
        right before it &mdash; the reasoning being that a redraw was about to happen
        regardless, so the checkbox should stay "honest" about what the user was about
        to see.</p>

        <div class="rule">
            <strong>That reasoning was backwards, and it was a real reported bug, not a
            style choice.</strong> Interactive Update off means "don't redraw until I
            press Refresh Plot" &mdash; a deliberate choice for large datasets/slow
            machines, or simply not wanting to watch a big 2D map's source spectra
            redraw. Applying an operation (SNIP baseline, normalization, Data range,
            etc.) is just another way the selected/displayed spectra change &mdash; it
            has no more claim to override that setting than clicking a different row in
            the spectrum list does, and clicking a row already respects it (see
            <code>spectrum_selector_controller.py</code>'s <code>isChecked()</code> checks).
            Forcing the checkbox back to checked and drawing anyway silently took away
            the user's choice on every single Apply/Add as New, with the checkbox itself
            lying about having done so.
        </div>

        <p><b>Fix:</b> <code>OperationsController._redraw_after_operation(progress=None,
        context='operation')</code> is now the ONE place this decision is made. Every
        <code>commit_*</code> method calls <code>self.oc._redraw_after_operation(progress,
        "&lt;description&gt;")</code> instead of calling <code>plot_spectra()</code> directly
        (20 call sites across <code>src/controllers/data_analysis/</code> plus one inside
        <code>OperationsController</code> itself, for jumping to an Operations History step
        &mdash; same bug, same fix). It checks
        <code>self.controller.interactive_mode_checkbox.isChecked()</code> first: unchecked is
        a no-op (the spectra list, selection, and <code>self.controller.selected_spectra</code>
        are already updated by the caller before this runs, so nothing about the operation's
        result is lost &mdash; the user just sees it after pressing Refresh Plot instead);
        checked runs exactly the old progress-label-plus-<code>plot_spectra()</code>-plus-
        error-logging sequence every caller used to hand-roll individually. The forced
        <code>setChecked(True)</code> calls are gone &mdash; there are now zero places in this
        codebase that flip that checkbox on the user's behalf.</p>

        <div class="note">
            The per-caller exception handling this replaced was itself inconsistent &mdash;
            some caught only <code>ValueError</code>, most caught <code>Exception</code>, two
            (<code>combine_spectra_controller.py</code>, <code>interactive_subtraction_controller.py</code>)
            had no <code>try</code>/<code>except</code> at all. <code>_redraw_after_operation</code>
            catches <code>Exception</code> uniformly and logs
            <code>f"Error plotting after {context}: {exc}"</code> &mdash; strictly safer than any
            individual caller's previous coverage, never narrower.
        </div>

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
            <li>If the Controller keeps one persistent Manager instance alive across
                dialog close/reopen (rather than a fresh one per dialog session), wire
                it into the <a href="#revision-counter"><code>revision_tracking.py</code></a>
                helper — don't hand-write "always reset" (throws away good state for no
                reason) or "never reset" (shows a stale fit/selection after an unrelated
                operation runs) again.</li>
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
            <li>Call <code>self.oc._redraw_after_operation(progress, "&lt;description&gt;")</code>
                right after <code>_rebuild_spectra_list_with_selection()</code> and setting
                <code>self.controller.selected_spectra</code> &mdash; never call
                <code>self.controller.plot_spectra(...)</code> directly, and never re-check
                <code>interactive_mode_checkbox</code> yourself. See
                <a href="#redraw-after-operation">above</a>.</li>
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
