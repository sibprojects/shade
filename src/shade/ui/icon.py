"""The program icon: a faceted gem seen from above (an octagon with a table
and crown facets) in black and gray, with the white "S" on the table."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

APOTHEM_OUTER = 0.48  # half-width of the gem (flat sides touch the icon edge)
APOTHEM_TABLE = 0.36  # half-width of the flat top facet (fits the big S)
LIGHT_FROM = math.radians(225)  # light comes from the top-left


def _octagon(apothem: float) -> list[tuple[float, float]]:
    r = apothem / math.cos(math.radians(22.5))
    return [
        (0.5 + r * math.cos(math.radians(22.5 + 45 * k)), 0.5 + r * math.sin(math.radians(22.5 + 45 * k)))
        for k in range(8)
    ]


def _gray(points: list[tuple[float, float]]) -> QColor:
    """Facets facing the light are lighter gray, the rest darker."""
    cx = sum(x for x, _ in points) / len(points) - 0.5
    cy = sum(y for _, y in points) / len(points) - 0.5
    facing = math.cos(math.atan2(cy, cx) - LIGHT_FROM)  # -1..1
    v = int(70 + 55 * facing)  # 15..125: black to mid gray
    return QColor(v, v, v)


def _facets() -> list[tuple[list[tuple[float, float]], QColor]]:
    outer, table = _octagon(APOTHEM_OUTER), _octagon(APOTHEM_TABLE)
    facets = []
    for k in range(8):
        v0, v1 = outer[k], outer[(k + 1) % 8]
        t0, t1 = table[k], table[(k + 1) % 8]
        mid = ((v0[0] + v1[0]) / 2, (v0[1] + v1[1]) / 2)
        for pts in ([t0, t1, mid], [v0, mid, t0], [mid, v1, t1]):
            facets.append((pts, _gray(pts)))
    facets.append((table, QColor("#141414")))
    return facets


def _poly(points, size: int) -> QPolygonF:
    return QPolygonF([QPointF(x * size, y * size) for x, y in points])


def _draw(size: int) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    facets = _facets()
    for points, color in facets:
        p.setBrush(color)
        p.drawPolygon(_poly(points, size))
    if size >= 24:  # facet edges only where they stay crisp
        p.setPen(QPen(QColor(210, 210, 210, 90), max(1.0, size / 80)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for points, _ in facets:
            p.drawPolygon(_poly(points, size))
    # The letter as a vector path: no ClearType color fringes, stays gray.
    f = QFont()
    f.setPixelSize(round(size * 0.92))
    f.setBold(True)
    path = QPainterPath()
    path.addText(0, 0, f, "S")
    box = path.boundingRect()
    path.translate(size / 2 - box.center().x(), size / 2 - box.center().y())
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#ededed"))
    p.drawPath(path)
    p.end()
    return pix


def make_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_draw(size))
    return icon
