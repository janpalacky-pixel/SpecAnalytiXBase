# src/help/whats_new_help.py
"""Help -> What's New: what changed in each version, newest first.

The text lives in resources/whats_new/<version>.md -- one file per version,
written once and used twice: shown here as a help page, and pasted as the
release notes on GitHub (print that version with
    python -m src.help.whats_new_help 1.5.0
which turns the help links into plain text). For a new version, add its
file; the page lists all files, newest on top.

Only the little Markdown the files use is understood: ## and ### headings,
"- " bullets (nested with two more spaces), paragraphs, **bold**, *italic*,
`code` and [text](link) links -- help://topic#anchor for another help page,
#anchor for a heading on this page."""

import glob
import html
import os
import re
import sys

from src.modules.utils.resource_path import resource_path

_DIR = os.path.join('resources', 'whats_new')


def _version_key(path):
    name = os.path.splitext(os.path.basename(path))[0]
    return tuple(int(p) if p.isdigit() else 0 for p in re.split(r'[.\-]', name))


def version_files(folder=None):
    """The resources/whats_new/*.md files, newest version first."""
    folder = folder or resource_path(_DIR)
    return sorted(glob.glob(os.path.join(folder, '*.md')), key=_version_key, reverse=True)


def slug(text):
    """Heading -> anchor, as GitHub makes it ("Changed results" -> changed-results)."""
    text = re.sub(r'[^\w\- ]', '', text.lower().replace('*', '').replace('`', ''))
    return re.sub(r'\s', '-', text.strip())


def _inline(text):
    out = html.escape(text, quote=False)
    out = re.sub(r'`([^`]+)`', r'<code>\1</code>', out)
    out = re.sub(r'\*\*(.+?)\*\*(?!\*)', r'<b>\1</b>', out)     # also **bold *italic***
    out = re.sub(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])', r'<i>\1</i>', out)
    out = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', r'<a href="\2">\1</a>', out)
    return out


def markdown_to_html(md):
    """The Markdown of a whats_new file -> HTML (see the module docstring)."""
    lines = md.replace('\r\n', '\n').split('\n')
    out, para, items = [], [], []          # items: [(level, text)]

    def flush_para():
        if para:
            out.append('<p>' + _inline(' '.join(para)) + '</p>')
            para.clear()

    def flush_items():
        if not items:
            return
        level = -1
        for lvl, text in items:
            if lvl > level:
                out.append('<ul>' * (lvl - level))
            elif lvl < level:
                out.append('</li>' + '</ul></li>' * (level - lvl))
            else:
                out.append('</li>')
            out.append('<li>' + _inline(text))
            level = lvl
        out.append('</li>' + '</ul></li>' * level + '</ul>')
        items.clear()

    for raw in lines:
        line = raw.rstrip()
        m = re.match(r'^(#{2,3}) (.+)$', line)
        bullet = re.match(r'^( *)- (.*)$', line)
        if m:
            flush_para(); flush_items()
            tag = 'h2' if len(m.group(1)) == 2 else 'h3'
            out.append(f'<{tag} id="{slug(m.group(2))}">{_inline(m.group(2))}</{tag}>')
        elif bullet:
            flush_para()
            items.append((len(bullet.group(1)) // 2, bullet.group(2)))
        elif not line.strip():
            flush_para(); flush_items()
        elif items and raw.startswith(' '):
            lvl, text = items[-1]
            items[-1] = (lvl, text + ' ' + line.strip())
        else:
            flush_items()
            para.append(line.strip())
    flush_para(); flush_items()
    return '\n'.join(out)


def notes_path(version):
    """resources/whats_new/<version>.md, or None if there is none."""
    path = resource_path(os.path.join(_DIR, f'{version}.md'))
    return path if os.path.isfile(path) else None


def earlier_versions(current, folder=None):
    """All versions with notes that are older than `current`, newest first
    (e.g. 1.6.0, 1.5.0 for 1.7.0). The start window shows their "in
    brief" lists below the new one, the same for everyone - so also someone
    who skipped versions sees what they brought."""
    def key(version):            # '1.6.0' (not a file name: no extension to cut off)
        return tuple(int(p) if p.isdigit() else 0 for p in re.split(r'[.\-]', str(version)))
    out = []
    for path in version_files(folder):             # newest first
        name = os.path.splitext(os.path.basename(path))[0]
        if key(name) < key(current):
            out.append(name)
    return out


def brief_markdown(version):
    """The "<version> in brief" section of a version's notes (without its
    heading), or '' if there is none."""
    path = notes_path(version)
    if path is None:
        return ''
    with open(path, encoding='utf-8') as f:
        md = f.read()
    m = re.search(r'(?ms)^### [^\n]*in brief[^\n]*\n(.*?)(?=^##|\Z)', md)
    return m.group(1).strip() + '\n' if m else ''


def github_markdown(path):
    """The file's text for the GitHub release notes: help links (which only
    work inside the program) are left out."""
    with open(path, encoding='utf-8') as f:
        md = f.read()
    md = re.sub(r'\s*\[[^\]]+\]\(help://[^)]*\)(\s*·)?', '', md)
    return re.sub(r'[ \t]+\n', '\n', md)


def get_whats_new_help_title():
    return "What's New"


def get_whats_new_help_content():
    parts = []
    for path in version_files():
        with open(path, encoding='utf-8') as f:
            parts.append(markdown_to_html(f.read()))
    body = '\n<hr>\n'.join(parts) or '<p>No notes found.</p>'
    return """
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; max-width: 1000px; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #2E7D32; border-bottom: 2px solid #2E7D32; margin-top: 10px; }
            h3    { color: #1976D2; margin-top: 26px; border-bottom: 1px solid #BBDEFB; padding-bottom: 4px; }
            a     { color: #1976D2; }
            code  { background: #F1F3F4; padding: 1px 4px; border-radius: 3px; }
            li    { margin-bottom: 4px; }
            hr    { margin: 36px 0; border: none; border-top: 2px solid #CFD8DC; }
            h3[id$="in-brief"] + ul {
                    background: #F1F8E9; border: 1px solid #C5E1A5; border-radius: 6px;
                    padding: 12px 12px 12px 34px; }
        </style>
    </head>
    <body>
    <h1>What's New</h1>
    <p>What changed in each version of SpecAnalytiXBase, newest first. Each version starts
    with a short summary; the full list follows.</p>
    """ + body + """
    </body>
    </html>
    """


if __name__ == '__main__':          # python -m src.help.whats_new_help 1.5.0
    wanted = sys.argv[1] if len(sys.argv) > 1 else None
    for p in version_files():
        if wanted is None or os.path.basename(p) == f'{wanted}.md':
            sys.stdout.write(github_markdown(p))
            break
