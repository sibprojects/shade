from shade.config import Settings, load_settings, save_settings, stt_config


def test_stt_config_light_for_local():
    assert stt_config(Settings(provider="local")) == ("small.en", "int8_float16")


def test_stt_config_default_for_cloud():
    assert stt_config(Settings()) == ("large-v3-turbo", "float16")


def test_missing_file_creates_defaults(tmp_path):
    path = tmp_path / "s.toml"
    assert load_settings(path) == Settings()
    assert path.exists()


def test_roundtrip(tmp_path):
    path = tmp_path / "s.toml"
    s = Settings(provider="local")
    s.hotkeys["ask"] = "<f8>"
    save_settings(s, path)
    assert load_settings(path) == s


def test_unknown_keys_ignored(tmp_path):
    path = tmp_path / "s.toml"
    path.write_text('foo = 1\nprovider = "openai"\n', encoding="utf-8")
    assert load_settings(path).provider == "openai"


def test_no_api_keys_in_file(tmp_path):
    path = tmp_path / "s.toml"
    save_settings(Settings(), path)
    text = path.read_text(encoding="utf-8")
    assert "api_key" not in text
    assert "sk-" not in text


def test_presets_merge(tmp_path):
    path = tmp_path / "s.toml"
    path.write_text(
        '[presets.grok]\nmodel = "x"\n\n'
        '[presets.custom]\nlabel = "Custom"\nbase_url = "http://h/v1"\nmodel = "m"\n'
        'detector_model = "m"\nkey_env = "CUSTOM_KEY"\nsupports_images = false\n',
        encoding="utf-8",
    )
    s = load_settings(path)
    assert s.presets["grok"]["model"] == "x"
    assert s.presets["grok"]["base_url"] == "https://api.x.ai/v1"
    assert set(s.presets) == {"openai", "grok", "groq", "deepseek", "gemini", "local", "network", "custom"}


def test_default_end_of_phrase_pause_is_600_ms():
    assert Settings().vad_silence_ms == 600


def test_two_local_presets_this_pc_and_network_pc():
    s = Settings()
    assert s.presets["local"]["label"] == "Local model (this PC)"
    assert s.presets["local"]["base_url"] == "http://localhost:11434/v1"
    assert s.presets["network"]["label"] == "Local model (network PC)"
    assert s.presets["network"]["key_env"] == ""
    assert s.presets["network"]["base_url"].startswith("http://192.168.")


def test_stt_config_full_for_network_pc_model():
    assert stt_config(Settings(provider="network")) == ("large-v3-turbo", "float16")


def test_stt_config_full_when_local_preset_points_to_another_pc():
    s = Settings(provider="local")
    s.presets["local"]["base_url"] = "http://192.168.1.50:11434/v1"
    assert stt_config(s) == ("large-v3-turbo", "float16")


def test_stt_config_light_for_any_preset_on_loopback():
    for provider, url in (
        ("local", "http://127.0.0.1:11434/v1"),
        ("network", "http://LOCALHOST:1234/v1"),
        ("custom", "http://[::1]:8000/v1"),
    ):
        s = Settings(provider=provider)
        s.presets.setdefault("custom", dict(s.presets["local"]))
        s.presets[provider]["base_url"] = url
        assert stt_config(s) == ("small.en", "int8_float16"), url


def test_builtin_preset_labels_are_not_taken_from_old_settings(tmp_path):
    path = tmp_path / "s.toml"
    path.write_text('[presets.local]\nlabel = "Local model"\nmodel = "m"\n', encoding="utf-8")
    s = load_settings(path)
    assert s.presets["local"]["label"] == "Local model (this PC)"
    assert s.presets["local"]["model"] == "m"
