"""Drag a rectangle on any screen; emits the selected area as PNG bytes.

Each screen is captured first (Shade's own windows are hidden by the caller),
then shown frozen and dimmed in a full-screen selector on that screen. The
crop is taken from the frozen capture at its physical resolution, so mixed
DPI setups work without coordinate conversion between monitors.
"""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QRect, Qt, Signal, QObject
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from shade.ui.capture_guard import CaptureExcluded


def selection_rect(a: QPoint, b: QPoint) -> QRect:
    return QRect(min(a.x(), b.x()), min(a.y(), b.y()), abs(a.x() - b.x()), abs(a.y() - b.y()))


def physical_rect(r: QRect, dpr: float) -> QRect:
    return QRect(round(r.x() * dpr), round(r.y() * dpr), round(r.width() * dpr), round(r.height() * dpr))


def png_bytes(pix: QPixmap) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pix.save(buf, "PNG")
    return bytes(data)


class _ScreenSelector(CaptureExcluded, QWidget):
    done = Signal(object)  # bytes | None

    def __init__(self, screen, shot: QPixmap) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool,
        )
        self.shot = shot
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._a: QPoint | None = None
        self._b: QPoint | None = None

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.shot)
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))
        if self._a and self._b:
            r = selection_rect(self._a, self._b)
            p.drawPixmap(r, self.shot, physical_rect(r, self.shot.devicePixelRatio()))
            p.setPen(QPen(QColor("#4c8dff"), 2))
            p.drawRect(r)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.RightButton:
            self.done.emit(None)
            return
        self._a = self._b = e.position().toPoint()
        self.update()

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._a:
            self._b = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e):  # noqa: N802
        if not self._a:
            return
        r = selection_rect(self._a, e.position().toPoint())
        if r.width() < 5 or r.height() < 5:
            self.done.emit(None)
            return
        crop = self.shot.copy(physical_rect(r, self.shot.devicePixelRatio()))
        self.done.emit(png_bytes(crop))

    def keyPressEvent(self, e):  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self.done.emit(None)


class RegionSelector(QObject):
    selected = Signal(bytes)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._widgets: list[_ScreenSelector] = []

    def start(self) -> None:
        if self._widgets:
            return
        for screen in QGuiApplication.screens():
            shot = screen.grabWindow(0)
            w = _ScreenSelector(screen, shot)
            w.done.connect(self._finish)
            self._widgets.append(w)
            w.showFullScreen()
            w.activateWindow()

    def _finish(self, png) -> None:
        for w in self._widgets:
            w.close()
            w.deleteLater()
        self._widgets = []
        if png:
            self.selected.emit(png)
        else:
            self.cancelled.emit()
