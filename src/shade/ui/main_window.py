"""Normal window mode (meant for a second monitor)."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMainWindow

from shade.ui.capture_guard import CaptureExcluded
from shade.ui.hint_view import HintView
from shade.ui.theme import window_stylesheet


class MainWindow(CaptureExcluded, QMainWindow):
    def __init__(self, theme: str = "day") -> None:
        super().__init__()
        self.setWindowTitle("Shade")
        self.view = HintView(transcript_lines=None, show_history=True)
        self.setCentralWidget(self.view)
        self.apply_theme(theme)
        self.resize(560, 760)
        geometry = QSettings("Shade", "Shade").value("main_window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def apply_theme(self, theme: str) -> None:
        self.setStyleSheet(window_stylesheet(theme))

    def closeEvent(self, event):  # noqa: N802
        QSettings("Shade", "Shade").setValue("main_window/geometry", self.saveGeometry())
        event.ignore()  # closing the window just hides it; the app lives in the tray
        self.hide()
