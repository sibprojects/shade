from shade.config import Settings
from shade.ui.settings_dialog import SettingsDialog

DEVICES = {"mic": ["Mic A", "Mic B"], "loopback": ["Speakers [Loopback]"]}


def test_unchanged_dialog_returns_equal_settings(qtbot):
    s = Settings()
    d = SettingsDialog(s, DEVICES)
    qtbot.addWidget(d)
    assert d.result_settings() == s


def test_edits_are_applied(qtbot):
    d = SettingsDialog(Settings(), DEVICES)
    qtbot.addWidget(d)
    d.provider.setCurrentIndex(d.provider.findData("grok"))
    d.preset_model.setText("grok-x")
    d.opacity.setValue(60)
    d.mic.setCurrentText("Mic B")
    d.hotkey_edits["ask"].setText("<f8>")
    s = d.result_settings()
    assert s.provider == "grok"
    assert s.presets["grok"]["model"] == "grok-x"
    assert s.overlay_opacity == 0.6
    assert s.mic_device == "Mic B"
    assert s.hotkeys["ask"] == "<f8>"


def test_switching_preset_keeps_edits_of_previous(qtbot):
    d = SettingsDialog(Settings(), DEVICES)
    qtbot.addWidget(d)
    d.provider.setCurrentIndex(d.provider.findData("groq"))
    d.preset_model.setText("edited-groq")
    d.provider.setCurrentIndex(d.provider.findData("gemini"))
    assert d.result_settings().presets["groq"]["model"] == "edited-groq"


def test_key_status_never_shows_value(qtbot, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "secret-value")
    d = SettingsDialog(Settings(provider="grok"), DEVICES)
    qtbot.addWidget(d)
    assert d.key_status.text() == "XAI_API_KEY is set"
    assert "secret-value" not in d.key_status.text()


def test_add_custom_preset(qtbot):
    d = SettingsDialog(Settings(), DEVICES)
    qtbot.addWidget(d)
    d.add_custom_preset("custom1")
    s = d.result_settings()
    assert s.provider == "custom1"
    assert s.presets["custom1"]["label"] == "custom1"
