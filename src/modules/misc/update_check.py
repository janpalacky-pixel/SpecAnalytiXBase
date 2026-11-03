# src/modules/misc/update_check.py
"""Is there a newer version? (Qt-free.) Asks GitHub for the latest release
of SpecAnalytiXBase (one small HTTPS request to api.github.com, nothing
about the user or the computer is sent; the program's version is in the
User-Agent, as GitHub asks for one) and compares its version with the
running one. Used at the start (Settings: "Check for a new version at the
start", on by default) and by Help > Check for a new version... - the
window side is MainController.check_for_update()."""

import json
import re
import urllib.request

REPO = "janpalacky-pixel/SpecAnalytiXBase"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
TIMEOUT_S = 6


def parse_version(text):
    """'v1.7.0' / '1.7.0' / 'SpecAnalytiXBase 1.7' -> (1, 7, 0); None if no
    version number in it."""
    m = re.search(r'(\d+)(?:\.(\d+))?(?:\.(\d+))?', str(text or ''))
    if not m:
        return None
    return tuple(int(g) if g is not None else 0 for g in m.groups())


def is_newer(latest, current):
    """Is the version `latest` newer than `current` (texts)?"""
    a, b = parse_version(latest), parse_version(current)
    return a is not None and b is not None and a > b


def fetch_latest(current_version='', timeout=TIMEOUT_S, opener=None):
    """{'version': '1.7.0', 'url': <release page>, 'name': ..., 'notes': ...}
    of the latest release on GitHub, or None when it cannot be found out (no
    internet, a firewall, GitHub not answering - never an error)."""
    request = urllib.request.Request(
        API_URL, headers={'Accept': 'application/vnd.github+json',
                          'User-Agent': f'SpecAnalytiXBase/{current_version or "unknown"}'})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
            data = json.loads(response.read().decode('utf-8', 'replace'))
    except Exception:                       # offline, timeout, HTTP error, bad answer
        return None
    tag = data.get('tag_name') or data.get('name')
    if not tag or parse_version(tag) is None or data.get('draft') or data.get('prerelease'):
        return None
    version = '.'.join(str(n) for n in parse_version(tag))
    return {'version': version, 'url': data.get('html_url') or RELEASES_URL,
            'name': data.get('name') or f"SpecAnalytiXBase {version}",
            'notes': data.get('body') or ''}


def newer_release(current_version, fetch=fetch_latest):
    """(release, None) if a newer one exists, (None, 'newest') if this is the
    newest, (None, 'unknown') if it could not be found out."""
    release = fetch(current_version)
    if release is None:
        return None, 'unknown'
    if is_newer(release['version'], current_version):
        return release, None
    return None, 'newest'
