"""Settings → Model: the main model with its settings, then the fallback model with its own."""

from shade.config import Settings
from shade.ui.settings_dialog import SettingsDialog


def _dialog(qtbot, **kw):
    d = SettingsDialog(Settings(**kw), {}, start_meter=False)
    qtbot.addWidget(d)
    return d


def test_fallback_shows_its_own_settings(qtbot):
    d = _dialog(qtbot, provider="claude_code", fallback_provider="claude")
    d.show()
    fb = d.fallback_panel
    assert d.cc_box.isVisible()  # main: Claude Code settings
    assert fb.claude_box.isVisible()  # fallback: Claude API settings
    assert not fb.cc_box.isVisible()


def test_fallback_none_shows_no_settings(qtbot):
    d = _dialog(qtbot, provider="claude_code")
    d.show()
    fb = d.fallback_panel
    assert fb.key() == ""
    assert not (fb.claude_box.isVisible() or fb.cc_box.isVisible() or fb.preset_box.isVisible())
    assert not fb.key_status.isVisible()


def test_fallback_settings_are_saved(qtbot):
    d = _dialog(qtbot, provider="claude_code", fallback_provider="claude")
    d.fallback_panel.claude_model.setText("claude-sonnet-5-5")
    d.fallback_panel.claude_effort.setCurrentText("medium")
    d.cc_model.setCurrentText("claude-haiku-5-5")
    s = d.result_settings()
    assert s.provider == "claude_code" and s.fallback_provider == "claude"
    assert s.claude_model == "claude-sonnet-5-5"
    assert s.claude_effort == "medium"
    assert s.cc_model == "claude-haiku-5-5"


def test_two_presets_keep_their_own_values(qtbot):
    d = _dialog(qtbot, provider="local", fallback_provider="network")
    d.base_url.setText("http://localhost:1234/v1")
    d.fallback_panel.base_url.setText("http://192.168.1.77:11434/v1")
    d.fallback_panel.preset_model.setText("gemma3:12b")
    s = d.result_settings()
    assert s.presets["local"]["base_url"] == "http://localhost:1234/v1"
    assert s.presets["network"]["base_url"] == "http://192.168.1.77:11434/v1"
    assert s.presets["network"]["model"] == "gemma3:12b"


def test_main_and_fallback_cannot_be_the_same(qtbot):
    d = _dialog(qtbot, provider="claude_code", fallback_provider="claude")
    d.provider.setCurrentIndex(d.provider.findData("claude"))  # main takes the fallback's provider
    assert d.fallback_panel.key() == ""
    d.fallback.setCurrentIndex(d.fallback.findData("claude"))  # fallback picks the main one
    assert d.fallback_panel.key() == ""
    assert d.result_settings().fallback_provider == ""


def test_edits_survive_switching_providers(qtbot):
    d = _dialog(qtbot, provider="claude_code", fallback_provider="claude")
    d.fallback_panel.claude_model.setText("my-model")
    d.fallback.setCurrentIndex(d.fallback.findData("local"))
    d.fallback.setCurrentIndex(d.fallback.findData("claude"))
    assert d.fallback_panel.claude_model.text() == "my-model"


def test_custom_preset_is_offered_for_both(qtbot):
    d = _dialog(qtbot, provider="claude")
    d.add_custom_preset("My vLLM")
    assert d.provider.currentData() == "my-vllm"
    assert d.fallback.findData("my-vllm") >= 0
