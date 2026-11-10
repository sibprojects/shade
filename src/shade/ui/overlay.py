"""Semi-transparent always-on-top overlay mode."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from shade.ui.capture_guard import CaptureExcluded
from shade.ui.ui_state import ui_state
from shade.ui.hint_view import HintView
from shade.ui.theme import overlay_stylesheet

BASE_FLAGS = (
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool
)


class Overlay(CaptureExcluded, QWidget):
    def __init__(
        self,
        opacity: float = 0.85,
        click_through: bool = False,
        bg_color: str = "#101218",
        text_color: str = "#f2f2f2",
        font_size: int = 12,
    ) -> None:
        super().__init__(None, BASE_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("overlay")
        self.apply_style(bg_color, text_color, opacity)
        self.view = HintView(transcript_lines=3, show_history=False, font_size=font_size, compact=True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.resize(560, 470)
        pos = ui_state().value("overlay/pos")
        if pos is not None:
            self.move(pos)
        self._drag_from: QPoint | None = None
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

    # Drag anywhere to move (when not click-through).
    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_from = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._drag_from is not None:
            self.move(e.globalPosition().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, e):  # noqa: N802
        self._drag_from = None
        ui_state().setValue("overlay/pos", self.pos())
