# src/help/license_help.py
import os

"""
Help content for the License page. There are three places license
information lives in this project, each for a different audience — this
page explains all three and links to each:

  - LICENSE (repo root) — the full, formal GPL-3.0 legal text. This is
    the actual license governing the software.
  - installer_assets/license.txt — a plain-language summary shown inside
    the Windows installer wizard ("I Agree" screen), for someone who
    just wants to know the terms without reading the full legal text.
  - developer_guide_help.py's "Using, Modifying & Sharing This Code"
    section (id="license") — explains the licensing *intent* and why
    GPL-3.0 was chosen, for anyone extending the source.

Keep this page's summary consistent with those three if any of them change.
"""


def get_license_help_title():
    return "License"


def get_license_help_content():
    # Resolved here (dev-mode / running from source) so the links below
    # open the real, current files on disk. Same caveat as
    # developer_guide_help.py: these links won't resolve in a built
    # installer, only when running from source.
    _repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _license_url = "file:///" + os.path.join(_repo_root, "LICENSE").replace("\\", "/")
    _license_txt_url = "file:///" + os.path.join(_repo_root, "installer_assets", "license.txt").replace("\\", "/")

    _content = """
    <html>
    <head>
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #1976D2; margin-top: 28px; border-bottom: 1px solid #BBDEFB; padding-bottom: 4px; }
            a     { color: #1976D2; }
            .info     { background-color: #e3f2fd; padding: 10px; margin: 8px 0; border-left: 4px solid #2196f3; border-radius: 0 5px 5px 0; }
            .tip      { background-color: #d4edda; border: 1px solid #c3e6cb; padding: 10px; border-radius: 5px; margin: 8px 0; }
            code { background-color: #f1f1f1; padding: 2px 4px; border-radius: 3px; font-family: monospace; }
            ul, ol { padding-left: 22px; }
            li { margin: 4px 0; }
        </style>
    </head>
    <body>

        <h1>License</h1>

        <p>SpecAnalytiXBase is free, open-source software, licensed under
        the <b>GNU General Public License, version 3 (GPL-3.0)</b>. In
        plain terms: you are free to use, copy, and modify this software
        &mdash; including for your own projects &mdash; and to share or
        redistribute it or any modified version of it, on the condition
        that if you share a modified version, its source code must be
        made available too, under these same terms. The intent is that
        improvements stay shareable rather than disappearing into a
        closed copy.</p>

        <div class="info">
            This software is provided "as-is," without warranty of any
            kind, express or implied, including but not limited to
            warranties of merchantability or fitness for a particular
            purpose. In no event shall the authors, the Institute of
            Biophysics of the Czech Academy of Sciences, or its
            affiliates be liable for any damages arising from the use
            of, or inability to use, this software.
        </div>

        <h2 id="where">Where the License Text Lives</h2>
        <p>There are three places license information appears in this
        project, for three different audiences:</p>
        <ul>
            <li><a href="__LICENSE_URL__"><code>LICENSE</code></a> (repository
                root) &mdash; the full, formal GPL-3.0 legal text. This is
                the actual license governing the software.</li>
            <li><a href="__LICENSE_TXT_URL__"><code>installer_assets/license.txt</code></a>
                &mdash; a plain-language summary shown on the "I Agree"
                screen of the Windows installer, for anyone who wants the
                terms without reading the full legal text.</li>
            <li>The <a href="help://developer_guide#license">Developer
                Guide</a>'s licensing section &mdash; explains why
                GPL-3.0 was chosen, for anyone extending the source.</li>
        </ul>
        <p>All three describe the same license; they differ in length and
        audience, not in substance. If anything here ever seems to
        conflict, the formal <code>LICENSE</code> file at the repository
        root is the one that actually governs.</p>

        <h2 id="official">Official License Text</h2>
        <p>The canonical, authoritative version of GPL-3.0 is published by
        the Free Software Foundation:</p>
        <p><a href="https://www.gnu.org/licenses/gpl-3.0.html">gnu.org/licenses/gpl-3.0.html</a></p>

        <h2 id="contact">Questions</h2>
        <ul>
            <li>Email: <a href="mailto:janpalacky@ibp.cz">janpalacky@ibp.cz</a></li>
            <li>Research group page:
                <a href="https://www.ibp.cz/en/research/departments/biophysics-of-nucleic-acids/research-profile">
                Biophysics of Nucleic Acids &mdash; Institute of Biophysics</a></li>
        </ul>
        <div class="tip">
            This paragraph and the rest of this page are a plain-language
            summary, not legal advice. For anything requiring precision
            &mdash; a publication's code-availability statement, formal
            redistribution questions, etc. &mdash; refer to the actual
            <a href="__LICENSE_URL__">LICENSE</a> file or consult a
            qualified advisor.
        </div>

    </body>
    </html>
"""
    _content = _content.replace("__LICENSE_URL__", _license_url)
    _content = _content.replace("__LICENSE_TXT_URL__", _license_txt_url)
    return _content
