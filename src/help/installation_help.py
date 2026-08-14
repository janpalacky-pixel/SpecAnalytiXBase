# src/help/installation_help.py

"""
Help content for the Installation page — how to get/run SpecAnalytiXBase
itself (as opposed to how to use it once it's running, which is Quick
Start / User Guide). Mirrors INSTALLATION.txt at the project root; keep
the two in sync if either changes.
"""


def get_installation_help_title():
    return "Installation"


def get_installation_help_content():
    return """
    <html>
    <head>
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #1976D2; margin-top: 28px; border-bottom: 1px solid #BBDEFB; padding-bottom: 4px; }
            h3    { color: #F57C00; margin-top: 18px; }
            a     { color: #1976D2; }
            .tip      { background-color: #d4edda; border: 1px solid #c3e6cb; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .info     { background-color: #e3f2fd; padding: 10px; margin: 8px 0; border-left: 4px solid #2196f3; border-radius: 0 5px 5px 0; }
            .warning  { background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; border-radius: 5px; margin: 8px 0; }
            code { background-color: #f1f1f1; padding: 2px 4px; border-radius: 3px; font-family: monospace; }
            pre  { background-color: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto; }
            ul, ol { padding-left: 22px; }
            li { margin: 4px 0; }
        </style>
    </head>
    <body>

        <h1>Installation</h1>

        <p>This page covers getting SpecAnalytiXBase itself set up and
        running — if the application is already open and showing you
        this help page, you obviously already have it running one way or
        another. It's here for reference: for reinstalling, for setting
        up a development copy from source, for building your own
        installer, or for passing along to someone else. The plain-text
        version of this same page, <code>INSTALLATION.txt</code>, sits at
        the root of the source tree.</p>

        <p>Once the application itself is running, see
        <a href="help://quick_start">Quick Start</a> for how to use it.</p>

        <div class="info">
            The installer-based method (sections 1 and 3 below) is
            Windows-only. Running from Python source (section 2) also
            works on macOS and Linux — the application itself (PyQt5) is
            cross-platform; only the packaging tools (PyInstaller / Inno
            Setup) target Windows here.
        </div>

        <h2 id="installer">1. Install Using the Installer <small>(Windows, recommended for most users)</small></h2>
        <p>The installer is a single file, named
        <code>Setup_for_SpecAnalytiXBase_ver_&lt;version&gt;.exe</code>,
        found in the project's <code>installer</code> folder once it has
        been built.</p>
        <p>You have two options for getting that file:</p>
        <ul>
            <li>Use an installer you were already given, or</li>
            <li>Build a brand-new one yourself from the source code —
                useful if you'd rather not trust a pre-built <code>.exe</code>
                from someone else and want to compile it yourself. See
                <a href="#building">section 3</a> below.</li>
        </ul>
        <p>Either way, once you have the <code>.exe</code>, run it and
        follow the setup wizard. It installs the application, creates a
        Start Menu entry, and offers an optional desktop shortcut.</p>

        <div class="warning">
            <b>The installer is not digitally signed</b>, so Windows
            SmartScreen or your antivirus software may flag it or show a
            warning when you run it. This is expected for an installer
            from a small, independent project &mdash; a code-signing
            certificate costs money that isn't currently in the budget
            &mdash; and isn't a sign that anything is actually wrong with
            the file. If you see a SmartScreen prompt, choose
            <b>More info</b>, then <b>Run anyway</b>. If your antivirus
            blocks or removes the file outright, you may need to allow it
            manually or add an exception. As always, only do this for an
            installer you trust the source of; if you'd rather not, build
            your own from the source code instead (see
            <a href="#building">section 3</a>), which avoids the issue
            entirely.
        </div>

        <h2 id="from-source">2. Run From the Python Source Code <small>(Windows / macOS / Linux)</small></h2>
        <p>Do this if you want to inspect, modify, or debug the
        application, or if you simply prefer not to run a pre-built
        <code>.exe</code> at all.</p>

        <h3>Requirements</h3>
        <ul>
            <li>Python 3.9&ndash;3.12 recommended, from
                <a href="https://www.python.org/downloads/">python.org/downloads</a>.
                PyQt5 5.15.x — this application's GUI toolkit — has the
                most reliable pre-built wheels in that range; a very new
                Python version may not yet have a matching PyQt5 wheel
                available. If installation fails, try a slightly older
                Python version from that range.</li>
            <li>The packages listed in <code>requirements.txt</code> at
                the project root — see that file for exactly which ones,
                and why each is needed.</li>
        </ul>

        <h3>Steps</h3>
        <p>From a command prompt/terminal opened in the project folder
        (the one containing <code>main.py</code>):</p>
        <ol>
            <li>Create a virtual environment — recommended, so these
                packages are kept separate from anything else on your
                system:
                <pre>python -m venv venv</pre>
            </li>
            <li>Activate it:
                <pre>venv\\Scripts\\activate            (Windows)
source venv/bin/activate         (macOS / Linux)</pre>
            </li>
            <li>Install the required packages:
                <pre>pip install -r requirements.txt</pre>
            </li>
            <li>Run the application:
                <pre>python main.py</pre>
            </li>
        </ol>

        <h2 id="building">3. Building the Installer From Source <small>(Windows)</small></h2>
        <p>Do this to produce your own installer <code>.exe</code>
        instead of using a pre-built one, or after making changes to the
        source code that you want to package up.</p>
        <p>In addition to the Python environment set up above, you need:</p>
        <ul>
            <li><b>PyInstaller</b>, installed into the same environment:
                <pre>pip install pyinstaller</pre>
            </li>
            <li><b>Inno Setup 6</b> (free), which turns the PyInstaller
                output into a proper Windows installer. Download from the
                official site:
                <a href="https://jrsoftware.org/isdl.php">jrsoftware.org/isdl.php</a>
            </li>
        </ul>
        <div class="warning">
            <b><code>BuildInstaller.bat</code> currently expects Inno
            Setup at its default install location for version 6</b> —
            <code>C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe</code>.
            If you install a newer major version (7 or later) instead,
            either install Inno Setup 6 alongside it, or edit that path
            in <code>BuildInstaller.bat</code> to point at wherever
            <code>ISCC.exe</code> actually is on your machine.
        </div>
        <p>Then, from the project root, simply run:</p>
        <pre>BuildInstaller.bat</pre>
        <p>This does two things in sequence:</p>
        <ol>
            <li>Runs PyInstaller to bundle the application
                (<code>main.py</code> plus the <code>resources</code>
                folder) into a standalone folder under <code>dist\\</code>.</li>
            <li>Runs Inno Setup (<code>installer.iss</code>) to package
                that folder into a single installer <code>.exe</code>,
                written to the <code>installer</code> folder.</li>
        </ol>
        <p>The resulting <code>.exe</code> is exactly the same kind of
        file described in <a href="#installer">section 1</a> — copy it
        anywhere, or hand it to someone else to install the application
        without them needing Python at all.</p>

        <h2 id="contact">Questions &amp; Contact</h2>
        <p>Collaboration, bug reports, installation problems, etc.</p>
        <ul>
            <li>Email: <a href="mailto:janpalacky@ibp.cz">janpalacky@ibp.cz</a></li>
            <li>Research group page:
                <a href="https://www.ibp.cz/en/research/departments/biophysics-of-nucleic-acids/research-profile">
                Biophysics of Nucleic Acids &mdash; Institute of Biophysics</a></li>
        </ul>
        <div class="tip">
            This is open-source software — see
            <code>installer_assets/license.txt</code> for the terms, or
            the <a href="help://developer_guide#license">Developer
            Guide</a> for the fuller explanation.
        </div>

    </body>
    </html>
    """
