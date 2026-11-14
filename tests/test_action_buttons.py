"""Quick action and recap buttons in the window, above the transcript/history tabs."""

from PySide6.QtCore import Qt

from shade.engine import QUICK_ACTIONS
from shade.ui.hint_view import ACTION_BUTTONS, HintView


def test_window_has_a_button_per_action(qtbot):
    v = HintView()
    qtbot.addWidget(v)
    names = [name for name, _ in ACTION_BUTTONS]
    assert names == [*QUICK_ACTIONS, "recap"]
    assert [b.text() for b in v.action_buttons] == [label for _, label in ACTION_BUTTONS]


def test_click_asks_for_the_action(qtbot):
    v = HintView()
    qtbot.addWidget(v)
    asked = []
    v.action_requested.connect(asked.append)
    for button in v.action_buttons:
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert asked == [name for name, _ in ACTION_BUTTONS]


def test_buttons_sit_centered_above_the_tabs(qtbot):
    v = HintView()
    qtbot.addWidget(v)
    v.resize(600, 700)
    v.show()
    qtbot.waitExposed(v)
    bar = v.action_bar
    tabs_top = v.tabs.mapTo(v, v.tabs.rect().topLeft()).y()
    bar_rect = bar.geometry()
    first = v.action_buttons[0].mapTo(v, v.action_buttons[0].rect().topLeft()).x()
    last_btn = v.action_buttons[-1]
    last = last_btn.mapTo(v, last_btn.rect().topRight()).x()
    assert v.action_buttons[0].mapTo(v, v.action_buttons[0].rect().bottomLeft()).y() < tabs_top
    assert abs(first - (v.width() - last)) <= 12  # centered
    assert bar_rect.height() > 0


def test_overlay_has_no_buttons(qtbot):
    v = HintView(compact=True, transcript_lines=3)
    qtbot.addWidget(v)
    assert v.action_buttons == []
