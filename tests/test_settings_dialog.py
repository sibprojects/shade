from shade.config import Settings
from shade.ui.settings_dialog import SettingsDialog

DEVICES = {"mic": ["Mic A", "Mic B"], "loopback": ["Speakers [Loopback]"]}


def test_settings_split_into_tabs(qtbot):
    d = SettingsDialog(Settings(), DEVICES)
    qtbot.addWidget(d)
    names = [d.tabs.tabText(i) for i in range(d.tabs.count())]
    assert names == ["Model", "Display", "Audio", "Hotkeys"]
    assert d.tabs.widget(0).isAncestorOf(d.provider)
    assert d.tabs.widget(1).isAncestorOf(d.opacity)
    assert d.tabs.widget(2).isAncestorOf(d.mic)
    assert d.tabs.widget(3).isAncestorOf(d.hotkey_edits["ask"])


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


def test_both_local_variants_are_in_the_provider_list(qtbot):
    d = SettingsDialog(Settings(), DEVICES)
    qtbot.addWidget(d)
    labels = [d.provider.itemText(i) for i in range(d.provider.count())]
    assert "Local model (this PC)" in labels and "Local model (network PC)" in labels


def test_network_variant_shows_setup_hint(qtbot):
    d = SettingsDialog(Settings(provider="network"), DEVICES)
    qtbot.addWidget(d)
    assert not d.network_hint.isHidden()
    assert "OLLAMA_HOST" in d.network_hint.text()
    d.provider.setCurrentIndex(d.provider.findData("local"))
    assert d.network_hint.isHidden()


def test_test_connection_uses_the_fields_as_typed(qtbot, monkeypatch):
    import shade.ui.settings_dialog as sd
    calls = []
    monkeypatch.setattr(sd, "check_connection", lambda url, key, model, **kw: (calls.append((url, key, model)) or (True, "Connected. Available models: m1")))
    d = SettingsDialog(Settings(provider="network"), DEVICES)
    qtbot.addWidget(d)
    d.base_url.setText("http://10.0.0.7:11434/v1")
    d.preset_model.setText("m1")
    d.test_button.click()
    assert calls == [("http://10.0.0.7:11434/v1", "local", "m1")]
    assert d.test_result.text() == "Connected. Available models: m1"


def test_claude_code_provider_settings(qtbot, monkeypatch):
    import shade.ui.settings_dialog as sd
    monkeypatch.setattr(sd, "find_claude", lambda path="": r"C:\x\claude.exe")
    d = SettingsDialog(Settings(provider="claude_code"), DEVICES)
    qtbot.addWidget(d)
    assert d.provider.currentText() == "Claude Code (subscription)"
    assert not d.cc_box.isHidden() and d.claude_box.isHidden() and d.preset_box.isHidden()
    assert "claude.exe" in d.key_status.text() and "subscription" in d.key_status.text()
    assert "limits" in d.cc_warning.text()
    assert not d.cc_auto.isChecked()
    d.cc_model.setText("claude-opus-5-5")
    d.cc_effort.setCurrentText("medium")
    d.cc_path.setText(r"D:\tools\claude.exe")
    d.cc_auto.setChecked(True)
    s = d.result_settings()
    assert (s.provider, s.cc_model, s.cc_effort, s.cc_path, s.cc_auto) == (
        "claude_code", "claude-opus-5-5", "medium", r"D:\tools\claude.exe", True)


def test_claude_code_not_found_is_shown(qtbot, monkeypatch):
    import shade.ui.settings_dialog as sd
    monkeypatch.setattr(sd, "find_claude", lambda path="": None)
    d = SettingsDialog(Settings(provider="claude_code"), DEVICES)
    qtbot.addWidget(d)
    assert "not found" in d.key_status.text()
