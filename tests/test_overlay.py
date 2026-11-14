from PySide6.QtCore import QPoint, QSize, Qt

from shade.config import Settings
from shade.ui.hotkeys import ACTIONS, HotkeyManager
from shade.ui.overlay import Overlay, edges_at
from shade.ui.settings_dialog import HOTKEY_LABELS

E = Qt.Edge
SIZE = QSize(500, 400)


def test_edges_in_the_middle_is_none():
    assert edges_at(QPoint(250, 200), SIZE) == Qt.Edge(0)
    assert not edges_at(QPoint(250, 200), SIZE)


def test_edges_at_sides_and_corners():
    assert edges_at(QPoint(2, 200), SIZE) == E.LeftEdge
    assert edges_at(QPoint(497, 200), SIZE) == E.RightEdge
    assert edges_at(QPoint(250, 1), SIZE) == E.TopEdge
    assert edges_at(QPoint(250, 398), SIZE) == E.BottomEdge
    assert edges_at(QPoint(498, 398), SIZE) == E.RightEdge | E.BottomEdge
    assert edges_at(QPoint(1, 1), SIZE) == E.LeftEdge | E.TopEdge


def test_overlay_remembers_its_size(qtbot):
    o = Overlay()
    qtbot.addWidget(o)
    o.resize(700, 333)
    o.save_geometry()
    o2 = Overlay()
    qtbot.addWidget(o2)
    assert o2.size() == QSize(700, 333)


def test_overlay_has_a_minimum_size(qtbot):
    o = Overlay()
    qtbot.addWidget(o)
    assert o.minimumWidth() >= 200 and o.minimumHeight() >= 120


def test_toggle_overlay_hotkey():
    assert "toggle_overlay" in ACTIONS
    assert Settings().hotkeys["toggle_overlay"] == "<ctrl>+<alt>+o"
    assert HOTKEY_LABELS["toggle_overlay"] == "Show / hide overlay"
    valid, errors = HotkeyManager.parse(Settings().hotkeys)
    assert errors == [] and "toggle_overlay" in valid


def test_corner_zone_is_larger_than_the_frame():
    # Near a corner, being on one edge is enough to grab both.
    assert edges_at(QPoint(490, 398), SIZE) == E.RightEdge | E.BottomEdge
    assert edges_at(QPoint(498, 388), SIZE) == E.RightEdge | E.BottomEdge


def test_frame_is_never_fully_transparent(qtbot):
    o = Overlay()
    qtbot.addWidget(o)
    o.show()
    img = o.grab().toImage()
    from PySide6.QtGui import QColor
    for x, y in ((0, 0), (img.width() - 1, img.height() - 1), (img.width() - 1, 0)):
        assert QColor.fromRgba(img.pixel(x, y)).alpha() > 0


def test_overlay_blocks_are_2px_apart(qtbot):
    o = Overlay()
    qtbot.addWidget(o)
    o.view._error.show()  # status, error, hint and transcript all present
    o.show()
    qtbot.waitExposed(o)
    widgets = [o.view._error, o.view._current, o.view._transcript, o.view._status]
    def top(w):
        return w.mapTo(o.view, w.rect().topLeft()).y()

    def bottom(w):
        return w.mapTo(o.view, w.rect().bottomLeft()).y()

    for upper, lower in zip(widgets, widgets[1:]):
        gap = top(lower) - bottom(upper) - 1
        assert gap == 2, (upper, lower, gap)
