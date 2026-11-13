"""Every picture a help page shows exists. The Band markers page showed four
empty frames from the start (its pictures were never made) and no test
noticed: a help page builds its <img> tags from file names, also of files
that are not there."""
import os
import re
import urllib.parse
import urllib.request

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


def _pages():
    from src.help import help_window
    for key, (module, _title, content) in help_window._REGISTRY.items():
        yield key, module, content


@pytest.mark.parametrize('key,module,content', list(_pages()), ids=lambda v: str(v))
def test_every_picture_of_the_help_page_exists(key, module, content):
    mod = __import__(module, fromlist=[content])
    html = getattr(mod, content)()
    missing = []
    for src in re.findall(r'<img[^>]*\ssrc="([^"]+)"', html):
        if src.startswith(('data:', 'http:', 'https:')):
            continue
        path = urllib.request.url2pathname(urllib.parse.urlparse(src).path) \
            if src.startswith('file:') else src
        if not os.path.isfile(path):
            missing.append(os.path.basename(path))
    assert not missing, f"help page {key!r}: pictures missing: {missing}"
