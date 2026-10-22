"""A single backslash in ordinary program text is read by Python as a special
character: in the User Guide "%LOCALAPPDATA%\\SpecAnalytiXBase\\autosave" the
"\\a" became an invisible bell character, so the guide showed "...utosave",
and Python printed "SyntaxWarning: invalid escape sequence" at start-up.
Every program file must compile without such a warning."""
import pathlib
import warnings

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
FILES = sorted(ROOT.glob('src/**/*.py')) + sorted(ROOT.glob('tests/*.py'))


@pytest.mark.skipif(not list(ROOT.glob('src/**/*.py')),
                    reason="the installed version has no program source files")
def test_no_invalid_backslash_in_program_text():
    problems = []
    for path in FILES:
        text = path.read_text(encoding='utf-8')
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            compile(text, str(path), 'exec')
        problems += [f'{path.relative_to(ROOT)} line {w.lineno}: {w.message}'
                     for w in caught if issubclass(w.category, (SyntaxWarning, DeprecationWarning))]
    assert not problems, '\n'.join(problems)


def test_user_guide_shows_the_autosave_folder():
    from src.help.user_guide_help import get_user_guide_help_content
    text = get_user_guide_help_content()
    assert '\a' not in text
    assert r'%LOCALAPPDATA%\SpecAnalytiXBase\autosave' in text
