"""Hide Shade windows from screen capture and screen sharing."""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtWidgets import QWidget

WDA_EXCLUDEFROMCAPTURE = 0x11


def exclude_from_capture(w: QWidget) -> bool:
    """Apply WDA_EXCLUDEFROMCAPTURE to the widget's top-level window."""
    if sys.platform != "win32":
        return False
    hwnd = int(w.window().winId())
    return bool(ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))


class CaptureExcluded:
    """Mixin for top-level widgets: re-applies exclusion every time the window is shown
    (changing window flags recreates the native window)."""

    capture_ok: bool = True

    def showEvent(self, event):  # noqa: N802 (Qt naming)
        super().showEvent(event)
        self.capture_ok = exclude_from_capture(self)
