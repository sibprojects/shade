"""The program icon: a faceted blue diamond that fills the whole icon square."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

# Shape in unit coordinates (0..1): flat table on top, girdle, point at the bottom.
TABLE_L, TABLE_R = (0.28, 0.08), (0.72, 0.08)
GIRDLE_Y = 0.34
GIRDLE = [(0.02, GIRDLE_Y), (0.36, GIRDLE_Y), (0.64, GIRDLE_Y), (0.98, GIRDLE_Y)]
TIP = (0.5, 0.97)

FACETS = [
    # crown
    ([TABLE_L, TABLE_R, GIRDLE[2], GIRDLE[1]], "#9fd3ff"),  # table / front crown
    ([GIRDLE[0], TABLE_L, GIRDLE[1]], "#5aa9ff"),
    ([TABLE_R, GIRDLE[3], GIRDLE[2]], "#3d8bfd"),
    # pavilion
    ([GIRDLE[0], GIRDLE[1], TIP], "#1f6fe5"),
    ([GIRDLE[1], GIRDLE[2], TIP], "#1552c2"),
    ([GIRDLE[2], GIRDLE[3], TIP], "#0d3a9a"),
]


def _poly(points, size: int) -> QPolygonF:
    return QPolygonF([QPointF(x * size, y * size) for x, y in points])


def _draw(size: int) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    for points, color in FACETS:
        p.setBrush(QColor(color))
        p.drawPolygon(_poly(points, size))
    if size >= 24:  # facet edges only where they stay crisp
        p.setPen(QPen(QColor(255, 255, 255, 110), max(1.0, size / 64)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for points, _ in FACETS:
            p.drawPolygon(_poly(points, size))
    p.end()
    return pix


def make_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_draw(size))
    return icon
