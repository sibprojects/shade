"""Overlay: Ctrl + drag anywhere moves it; the border between hint and transcript moves too."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QSplitter

from shade.ui.main_window import MainWindow
from shade.ui.overlay import Overlay


def _overlay(qtbot):
    o = Overlay()
    qtbot.addWidget(o)
    o.resize(500, 400)
    o.show()
    qtbot.waitExposed(o)
    moves = []
    o._start_move = lambda: moves.append(True)
    return o, moves


def test_ctrl_drag_on_the_hint_moves_the_overlay(qtbot):
    o, moves = _overlay(qtbot)
    viewport = o.view._current.viewport()
    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, QPoint(50, 50))
    assert moves == [True]


def test_ctrl_drag_on_the_transcript_moves_the_overlay(qtbot):
    o, moves = _overlay(qtbot)
    viewport = o.view._transcript.viewport()
    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, QPoint(10, 10))
    assert moves == [True]


def test_plain_click_does_not_move(qtbot):
    o, moves = _overlay(qtbot)
    qtbot.mousePress(o.view._current.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(50, 50))
    assert moves == []


def test_overlay_hint_and_transcript_are_split(qtbot):
    o, _ = _overlay(qtbot)
    split = o.view.split
    assert isinstance(split, QSplitter)
    assert split.widget(0) is o.view._current
    assert split.widget(1) is o.view._transcript
    assert split.handleWidth() == 1


def test_overlay_split_is_remembered(qtbot):
    o, _ = _overlay(qtbot)
    o.view.split.setSizes([150, 200])
    o.view.split.splitterMoved.emit(150, 1)
    o2 = Overlay()
    qtbot.addWidget(o2)
    o2.resize(500, 400)
    o2.show()
    qtbot.waitExposed(o2)
    assert abs(o2.view.split.sizes()[1] - o.view.split.sizes()[1]) <= 2


def test_window_split_is_remembered(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(500, 700)
    w.show()
    qtbot.waitExposed(w)
    w.view.split.setSizes([200, 400])
    w.view.split.splitterMoved.emit(200, 1)
    sizes = w.view.split.sizes()
    w2 = MainWindow()
    qtbot.addWidget(w2)
    w2.resize(500, 700)
    w2.show()
    qtbot.waitExposed(w2)
    assert abs(w2.view.split.sizes()[0] - sizes[0]) <= 2


def test_border_has_no_color_of_its_own(qtbot):
    o, _ = _overlay(qtbot)
    assert "QSplitter::handle { background: transparent; }" in o.styleSheet()


def _press_move_release(qtbot, widget, start, end):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    def send(kind, pos, buttons):
        ev = QMouseEvent(kind, QPointF(pos), QPointF(widget.mapToGlobal(pos)), Qt.MouseButton.LeftButton,
                         buttons, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(widget, ev)

    send(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
    send(QEvent.Type.MouseMove, end, Qt.MouseButton.LeftButton)
    send(QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.NoButton)


def test_border_can_be_dragged_from_a_few_pixels_away(qtbot):
    o, moves = _overlay(qtbot)
    tr = o.view._transcript
    before = tr.height()
    # Just inside the transcript, 2 px below the border: drag up by 60 px.
    _press_move_release(qtbot, tr.viewport(), QPoint(100, 1), QPoint(100, -59))
    assert abs(tr.height() - (before + 60)) <= 3
    assert moves == []  # a border drag doesn't move the overlay


def test_border_drag_from_the_hint_side(qtbot):
    o, _ = _overlay(qtbot)
    cur = o.view._current.viewport()
    tr = o.view._transcript
    before = tr.height()
    y = cur.height() - 2
    _press_move_release(qtbot, cur, QPoint(100, y), QPoint(100, y + 30))
    assert abs(tr.height() - (before - 30)) <= 3


def test_border_drag_is_remembered(qtbot):
    o, _ = _overlay(qtbot)
    _press_move_release(qtbot, o.view._transcript.viewport(), QPoint(100, 1), QPoint(100, -59))
    height = o.view._transcript.height()
    o2 = Overlay()
    qtbot.addWidget(o2)
    o2.resize(500, 400)
    o2.show()
    qtbot.waitExposed(o2)
    assert abs(o2.view._transcript.height() - height) <= 2


def test_click_away_from_the_border_is_left_alone(qtbot):
    o, _ = _overlay(qtbot)
    tr = o.view._transcript
    before = tr.height()
    _press_move_release(qtbot, tr.viewport(), QPoint(100, 30), QPoint(100, -30))
    assert tr.height() == before
