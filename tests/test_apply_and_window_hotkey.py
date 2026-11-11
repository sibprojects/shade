from PySide6.QtWidgets import QDialogButtonBox

from shade.config import Settings
from shade.ui.hotkeys import ACTIONS, HotkeyManager
from shade.ui.settings_dialog import HOTKEY_LABELS, SettingsDialog

DEVICES = {"mic": [], "loopback": []}


def test_apply_button_emits_settings_and_keeps_dialog_open(qtbot):
    d = SettingsDialog(Settings(), DEVICES, start_meter=False)
    qtbot.addWidget(d)
    d.show()
    d.window_font.setValue(19)
    with qtbot.waitSignal(d.applied, timeout=1000) as blocker:
        d.buttons.button(QDialogButtonBox.StandardButton.Apply).click()
    assert blocker.args[0].window_font_size == 19
    assert d.isVisible()


def test_speech_model_choice_on_audio_tab(qtbot):
    d = SettingsDialog(Settings(), DEVICES, start_meter=False)
    qtbot.addWidget(d)
    assert d.tabs.widget(2).isAncestorOf(d.stt_model)
    d.stt_model.setCurrentIndex(d.stt_model.findData("large-v3"))
    assert d.result_settings().stt_model == "large-v3"


def test_toggle_window_hotkey():
    assert "toggle_window" in ACTIONS
    assert Settings().hotkeys["toggle_window"] == "<ctrl>+<alt>+w"
    assert HOTKEY_LABELS["toggle_window"] == "Show / hide window"
    _, errors = HotkeyManager.parse(Settings().hotkeys)
    assert errors == []
