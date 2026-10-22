"""The drop-down lists of the program show their arrow: the main window style
sheet styles the drop-down part, which hides Qt's own arrow, so it gives a
picture for it (light and dark theme, also a paler one when switched off)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_the_arrow_pictures_exist():
    for name in ('combo_arrow.png', 'combo_arrow_disabled.png', 'combo_arrow_for_dark.png',
                 'combo_arrow_disabled_for_dark.png'):
        path = os.path.join(ROOT, 'resources', 'icons', name)
        assert os.path.isfile(path) and not QImage(path).isNull()


def test_the_style_sheet_points_to_them(monkeypatch):
    from src.controllers.core.main_controller import MainController
    from src.views import theme
    css = "a { image: url(@COMBO_ARROW@); } b { image: url(@COMBO_ARROW_DISABLED@); }"
    for name, suffix in (('light', ''), ('dark', '_for_dark')):
        monkeypatch.setattr(theme, 'saved_theme', lambda n=name: n)
        out = MainController._with_arrow_images(css)
        assert '@' not in out and '\\' not in out
        assert f'combo_arrow{suffix}.png' in out and f'combo_arrow_disabled{suffix}.png' in out
        for path in out.split('url(')[1:]:
            assert os.path.isfile(path.split(')')[0])
