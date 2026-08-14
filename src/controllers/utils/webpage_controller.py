
# src/controllers/webpage_controller.py

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices

class WebpageController:
    def __init__(self):
        pass

    def open_url(self, url: str):
        """Opens the provided URL in the default web browser."""
        QDesktopServices.openUrl(QUrl(url))
