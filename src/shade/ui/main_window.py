"""Normal window mode (meant for a second monitor)."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMainWindow

from shade.ui.capture_guard import CaptureExcluded
from shade.ui.hint_view import HintView


class MainWindow(CaptureExcluded, QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Shade")
        self.view = HintView(transcript_lines=None, show_history=True)
        self.setCentralWidget(self.view)
        self.resize(560, 760)
        geometry = QSettings("Shade", "Shade").value("main_window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):  # noqa: N802
        QSettings("Shade", "Shade").setValue("main_window/geometry", self.saveGeometry())
        event.ignore()  # closing the window just hides it; the app lives in the tray
        self.hide()
