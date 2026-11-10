"""The program icon: a purple circle with a white "S"."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap


def make_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#3b3f8f"))
        p.setPen(Qt.PenStyle.NoPen)
        m = max(1, size // 32)
        p.drawEllipse(m, m, size - 2 * m, size - 2 * m)
        p.setPen(QColor("white"))
        f = QFont()
        f.setPixelSize(round(size * 0.6))
        f.setBold(True)
        p.setFont(f)
        p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "S")
        p.end()
        icon.addPixmap(pix)
    return icon
