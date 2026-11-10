"""Normal window mode (meant for a second monitor).

The window lives only in the tray, not on the taskbar: it is owned by a hidden
widget (Windows never gives owned windows a taskbar button) and keeps the
standard minimize / maximize / close buttons. Minimize and close both hide it
to the tray; the tray icon or "Show" brings it back.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer
from PySide6.QtWidgets import QMainWindow, QWidget

from shade.ui.capture_guard import CaptureExcluded
from shade.ui.hint_view import HintView
from shade.ui.icon import make_icon
from shade.ui.theme import window_stylesheet

WINDOW_FLAGS = (
    Qt.WindowType.Window
    | Qt.WindowType.WindowTitleHint
    | Qt.WindowType.WindowSystemMenuHint
    | Qt.WindowType.WindowMinimizeButtonHint
    | Qt.WindowType.WindowMaximizeButtonHint
    | Qt.WindowType.WindowCloseButtonHint
)


_OWNER: QWidget | None = None


def _taskbar_owner() -> QWidget:
    """One hidden widget for the whole app run. It must outlive every window it
    owns, so it is never deleted (deleting it would delete the windows too)."""
    global _OWNER
    if _OWNER is None:
        _OWNER = QWidget()
    return _OWNER


class MainWindow(CaptureExcluded, QMainWindow):
    def __init__(self, theme: str = "day") -> None:
        super().__init__(_taskbar_owner(), WINDOW_FLAGS)
        self.setWindowTitle("Shade")
        self.setWindowIcon(make_icon())
        self.view = HintView(transcript_lines=None, show_history=True)
        self.setCentralWidget(self.view)
        self.apply_theme(theme)
        self.resize(560, 760)
        geometry = QSettings("Shade", "Shade").value("main_window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def apply_theme(self, theme: str) -> None:
        self.setStyleSheet(window_stylesheet(theme))

    def show(self) -> None:
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        super().show()

    def changeEvent(self, event):  # noqa: N802
        super().changeEvent(event)
        # An owned window has no taskbar button to restore from, so minimizing
        # sends it to the tray instead.
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            QTimer.singleShot(0, self._hide_to_tray)

    def _hide_to_tray(self) -> None:
        self.hide()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)

    def closeEvent(self, event):  # noqa: N802
        QSettings("Shade", "Shade").setValue("main_window/geometry", self.saveGeometry())
        event.ignore()  # closing the window just hides it; the app lives in the tray
        self.hide()
