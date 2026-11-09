from pynput.keyboard import Key, KeyCode

from shade.ui.hotkeys import HotkeyManager, canonical_key


def test_canonical_key_maps_vk_letter_without_char():
    # With Ctrl+Alt held, Windows reports letters as a bare virtual-key code.
    assert canonical_key(KeyCode.from_vk(0x41)) == KeyCode.from_char("a")


def test_canonical_key_maps_left_modifiers():
    assert canonical_key(Key.ctrl_l) == Key.ctrl
    assert canonical_key(Key.alt_l) == Key.alt


def test_ctrl_alt_letter_fires_from_vk_events(qtbot):
    m = HotkeyManager()
    m._set_bindings({"ask": "<ctrl>+<alt>+a"})
    with qtbot.waitSignal(m.triggered, timeout=1000) as blocker:
        for k in (Key.ctrl_l, Key.alt_l, KeyCode.from_vk(0x41)):
            m._on_press(k)
    assert blocker.args == ["ask"]


def test_parse_valid_and_invalid():
    valid, errors = HotkeyManager.parse({"ask": "<ctrl>+<alt>+a", "dismiss": "<ctrl>+<nope>"})
    assert valid == {"ask": "<ctrl>+<alt>+a"}
    assert errors == ["Invalid hotkey for dismiss: <ctrl>+<nope>"]


def test_parse_ignores_unknown_actions():
    valid, errors = HotkeyManager.parse({"fly": "<ctrl>+f"})
    assert valid == {}
    assert errors == ["Unknown hotkey action: fly"]
