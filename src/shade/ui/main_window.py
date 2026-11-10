"""Normal window mode (meant for a second monitor).

The window lives only in the tray, not on the taskbar: it is owned by a hidden
widget (Windows never gives owned windows a taskbar button) and keeps the
standard minimize / maximize / close buttons. Minimize and close both hide it
to the tray; the tray icon or "Show" brings it back.
"""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QMainWindow, QWidget

from shade.ui.capture_guard import CaptureExcluded
from shade.ui.ui_state import ui_state
from shade.ui.hint_view import HintView
from shade.ui.icon import make_icon
from shade.ui.theme import window_stylesheet

SW_SHOW = 5
SW_RESTORE = 9
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040

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
    def __init__(self, theme: str = "day", font_size: int = 14) -> None:
        super().__init__(_taskbar_owner(), WINDOW_FLAGS)
        self.setWindowTitle("Shade")
        self.setWindowIcon(make_icon())
        self.view = HintView(transcript_lines=None, show_history=True, font_size=font_size)
        self.setCentralWidget(self.view)
        self.apply_theme(theme)
        self.resize(560, 760)
        geometry = ui_state().value("main_window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def apply_theme(self, theme: str) -> None:
        self.setStyleSheet(window_stylesheet(theme))

    def show(self) -> None:
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        super().show()

    def bring_to_front(self) -> None:
        """Show, restore and activate. An owned window restored from the tray
        otherwise comes back behind the other windows and looks "not shown"."""
        self.show()
        self.raise_()
        self.activateWindow()
        if sys.platform == "win32":
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            user32.ShowWindow(hwnd, SW_RESTORE if user32.IsIconic(hwnd) else SW_SHOW)
            # Topmost on/off moves it above other windows even if Windows
            # refuses to hand over keyboard focus.
            flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
            # Windows only lets the foreground thread change the foreground
            # window; briefly share input with it so the switch is allowed.
            fg = user32.GetForegroundWindow()
            fg_thread = user32.GetWindowThreadProcessId(fg, None)
            our_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            attached = fg_thread and fg_thread != our_thread and user32.AttachThreadInput(our_thread, fg_thread, True)
            try:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
            finally:
                if attached:
                    user32.AttachThreadInput(our_thread, fg_thread, False)

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
        ui_state().setValue("main_window/geometry", self.saveGeometry())
        event.ignore()  # closing the window just hides it; the app lives in the tray
        self.hide()
