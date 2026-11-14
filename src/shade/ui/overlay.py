"""Semi-transparent always-on-top overlay mode.

Frameless, so it draws its own thin frame: drag an edge or corner to resize,
drag the status line at the bottom, or anywhere with Ctrl held, to move.
Position, size and the hint/transcript border are remembered.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget

from shade.ui.capture_guard import CaptureExcluded
from shade.ui.hint_view import HintView
from shade.ui.theme import overlay_stylesheet
from shade.ui.ui_state import ui_state

BASE_FLAGS = (
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool
)
RESIZE_MARGIN = 6  # px of frame around the content that resizes the overlay
CORNER_EXTENT = 16  # px along an edge near a corner that grab the corner
DEFAULT_SIZE = QSize(560, 470)

_CURSORS = {
    Qt.Edge.LeftEdge: Qt.CursorShape.SizeHorCursor,
    Qt.Edge.RightEdge: Qt.CursorShape.SizeHorCursor,
    Qt.Edge.TopEdge: Qt.CursorShape.SizeVerCursor,
    Qt.Edge.BottomEdge: Qt.CursorShape.SizeVerCursor,
}


def edges_at(pos: QPoint, size: QSize, margin: int = RESIZE_MARGIN) -> Qt.Edge:
    """Which window edges a point inside the overlay is close enough to grab."""
    x, y, w, h = pos.x(), pos.y(), size.width(), size.height()
    on_frame = x < margin or x >= w - margin or y < margin or y >= h - margin
    if not on_frame:
        return Qt.Edge(0)
    # Near a corner, a wider zone along either edge grabs the corner.
    reach_x = CORNER_EXTENT if (y < CORNER_EXTENT or y >= h - CORNER_EXTENT) else margin
    reach_y = CORNER_EXTENT if (x < CORNER_EXTENT or x >= w - CORNER_EXTENT) else margin
    edges = Qt.Edge(0)
    if x < reach_x:
        edges |= Qt.Edge.LeftEdge
    elif x >= w - reach_x:
        edges |= Qt.Edge.RightEdge
    if y < reach_y:
        edges |= Qt.Edge.TopEdge
    elif y >= h - reach_y:
        edges |= Qt.Edge.BottomEdge
    return edges


def _cursor_for(edges: Qt.Edges) -> Qt.CursorShape:
    diag_main = (Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.Edge.RightEdge | Qt.Edge.BottomEdge)
    diag_anti = (Qt.Edge.RightEdge | Qt.Edge.TopEdge, Qt.Edge.LeftEdge | Qt.Edge.BottomEdge)
    if edges in diag_main:
        return Qt.CursorShape.SizeFDiagCursor
    if edges in diag_anti:
        return Qt.CursorShape.SizeBDiagCursor
    for edge, cursor in _CURSORS.items():
        if edges == edge:
            return cursor
    return Qt.CursorShape.ArrowCursor


class Overlay(CaptureExcluded, QWidget):
    def __init__(
        self,
        opacity: float = 0.85,
        click_through: bool = False,
        bg_color: str = "#101218",
        text_color: str = "#f2f2f2",
        font_size: int = 12,
        code_font_size: int | None = None,
    ) -> None:
        super().__init__(None, BASE_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("overlay")
        self.setMouseTracking(True)
        self.setMinimumSize(240, 140)
        self.apply_style(bg_color, text_color, opacity)
        self.view = HintView(
            transcript_lines=3, show_history=False, font_size=font_size, compact=True, code_font_size=code_font_size
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(RESIZE_MARGIN, RESIZE_MARGIN, RESIZE_MARGIN, RESIZE_MARGIN)
        layout.addWidget(self.view)
        # The status line doubles as the title bar: drag it to move the overlay.
        # With Ctrl held, a drag anywhere moves it.
        for child in self.findChildren(QWidget):
            child.installEventFilter(self)
        self.view._status.setCursor(Qt.CursorShape.SizeAllCursor)
        self.view.remember_split("overlay/split")

        state = ui_state()
        size = state.value("overlay/size")
        self.resize(size if isinstance(size, QSize) else DEFAULT_SIZE)
        pos = state.value("overlay/pos")
        if pos is not None:
            self.move(pos)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.save_geometry)
        self.click_through = False
        self.set_click_through(click_through)

    def apply_style(self, bg_color: str, text_color: str, opacity: float) -> None:
        # Opacity applies to the background only, so text stays crisp.
        self.setStyleSheet(overlay_stylesheet(bg_color, text_color, opacity))

    def set_click_through(self, on: bool) -> None:
        self.click_through = on
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, on)
        if visible:
            self.show()  # flag changes hide the window and recreate it

    def save_geometry(self) -> None:
        state = ui_state()
        state.setValue("overlay/pos", self.pos())
        state.setValue("overlay/size", self.size())
        state.sync()

    # ---- frame ----------------------------------------------------------

    def paintEvent(self, event):  # noqa: N802
        # Fully transparent pixels don't receive the mouse on Windows, so the
        # resize frame is painted faintly (and doubles as a visible border).
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 30))  # every pixel, corners included
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def mouseMoveEvent(self, e):  # noqa: N802
        self.setCursor(_cursor_for(edges_at(e.position().toPoint(), self.size())))

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() != Qt.MouseButton.LeftButton:
            return
        edges = edges_at(e.position().toPoint(), self.size())
        handle = self.windowHandle()
        if edges and handle is not None:
            handle.startSystemResize(edges)
        elif handle is not None:
            handle.startSystemMove()

    def _start_move(self) -> None:
        handle = self.windowHandle()
        if handle is not None:
            handle.startSystemMove()

    def eventFilter(self, obj, event):  # noqa: N802
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
            and (obj is self.view._status or event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        ):
            self._start_move()
            return True
        return super().eventFilter(obj, event)

    def moveEvent(self, event):  # noqa: N802
        super().moveEvent(event)
        self._save_timer.start()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._save_timer.start()
