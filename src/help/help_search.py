# src/help/help_search.py
"""Help › Search the help…: find a word in all help pages at once (the
browser's Ctrl+F searches only the page that is open). Every page is cut
into its sections (an element with an id - a heading, or a paragraph marked
so); a section that contains every typed word is a hit, those whose heading
or page title contains them first. A hit opens its page at the section."""

import html
import importlib
import re

# pages not for users of the program (its source code, the licence text)
SKIPPED = {'developer_guide', 'license'}

_TAG = re.compile(r'<[^>]+>')
_ID = re.compile(r'<(h[1-6]|p|li|div|section|tr|td|span|a)\b[^>]*\bid="([^"]+)"[^>]*>', re.I)
_DROP = re.compile(r'<(script|style|svg)\b.*?</\1>', re.I | re.S)
_index = None


def _text(fragment):
    t = _TAG.sub(' ', _DROP.sub(' ', fragment))
    return re.sub(r'\s+', ' ', html.unescape(t)).strip()


def _heading(tag, fragment):
    """The section's heading: the heading text, or the start of the text."""
    if tag.lower().startswith('h'):
        m = re.search(r'^(.*?)</%s>' % tag, fragment, re.I | re.S)
        if m:
            return _text(m.group(1))
    words = _text(fragment).split()
    return ' '.join(words[:8]) + (' …' if len(words) > 8 else '')


def sections(content):
    """[(anchor, heading, text)] of a help page; text before the first id:
    anchor None."""
    content = _DROP.sub(' ', content)
    marks = list(_ID.finditer(content))
    out = []
    start = 0
    body = re.search(r'<body[^>]*>', content, re.I)
    if body:
        start = body.end()
    first = marks[0].start() if marks else len(content)
    head = _text(content[start:first])
    if head:
        out.append((None, '', head))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(content)
        fragment = content[m.end():end]
        text = _text(fragment)
        if text:
            out.append((m.group(2), _heading(m.group(1), fragment), text))
    return out


def build_index(registry=None):
    """[(key, page title, anchor, heading, text)] of every help page."""
    if registry is None:
        from src.help.help_window import _REGISTRY as registry
    index = []
    for key, (module, title_fn, content_fn) in registry.items():
        if key in SKIPPED:
            continue
        try:
            mod = importlib.import_module(module)
            title = getattr(mod, title_fn)()
            content = getattr(mod, content_fn)()
        except Exception:
            continue
        for anchor, heading, text in sections(content):
            index.append((key, title, anchor, heading, text))
    return index


def index():
    global _index
    if _index is None:
        _index = build_index()
    return _index


def _snippet(text, word, width=150):
    i = text.lower().find(word)
    if i < 0:
        return text[:width] + ('…' if len(text) > width else '')
    a = max(0, i - width // 3)
    b = min(len(text), a + width)
    return ('…' if a else '') + text[a:b] + ('…' if b < len(text) else '')


def search(query, entries=None, limit=60):
    """The sections that contain every word of `query` (case ignored), best
    first: [{'key', 'title', 'anchor', 'heading', 'snippet'}]."""
    words = [w for w in re.split(r'\s+', query.lower().strip()) if w]
    if not words:
        return []
    found = []
    for n, (key, title, anchor, heading, text) in enumerate(entries if entries is not None
                                                           else index()):
        low = text.lower()
        if not all(w in low or w in heading.lower() or w in title.lower() for w in words):
            continue
        score = 0
        for w in words:
            score += 10 * (w in heading.lower()) + 4 * (w in title.lower())
            score += min(low.count(w), 5)
        found.append((-score, n, {'key': key, 'title': title, 'anchor': anchor,
                                  'heading': heading, 'snippet': _snippet(text, words[0])}))
    found.sort(key=lambda t: (t[0], t[1]))
    return [f for _, _, f in found[:limit]]
