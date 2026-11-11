"""User settings stored as TOML. API keys are never stored here."""

from __future__ import annotations

import copy
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

DEFAULT_SETTINGS_PATH = Path("settings.toml")


def _preset(label, base_url, model, key_env, supports_images):
    return {
        "label": label,
        "base_url": base_url,
        "model": model,
        "detector_model": model,
        "key_env": key_env,
        "supports_images": supports_images,
    }


DEFAULT_PRESETS: dict[str, dict] = {
    "openai": _preset("OpenAI", "https://api.openai.com/v1", "gpt-5-mini", "OPENAI_API_KEY", True),
    "grok": _preset("Grok (xAI)", "https://api.x.ai/v1", "grok-4-fast", "XAI_API_KEY", True),
    "groq": _preset(
        "Groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_API_KEY", False
    ),
    "deepseek": _preset(
        "DeepSeek", "https://api.deepseek.com", "deepseek-chat", "DEEPSEEK_API_KEY", False
    ),
    "gemini": _preset(
        "Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-2.5-flash",
        "GEMINI_API_KEY",
        True,
    ),
    "local": _preset("Local model", "http://localhost:11434/v1", "qwen2.5vl:7b", "", True),
}

DEFAULT_HOTKEYS = {
    "ask": "<ctrl>+<alt>+a",
    "screenshot": "<ctrl>+<alt>+s",
    "toggle_view": "<ctrl>+<alt>+v",
    "toggle_overlay": "<ctrl>+<alt>+o",
    "toggle_window": "<ctrl>+<alt>+w",
    "click_through": "<ctrl>+<alt>+c",
    "dismiss": "<ctrl>+<alt>+d",
    "toggle_auto": "<ctrl>+<alt>+q",
}

DEFAULT_PRICES = {
    "claude-opus-5-5": [4.0, 20.0],
    "claude-sonnet-5-5": [2.0, 10.0],
    "claude-haiku-5-5": [0.10, 0.50],
}


@dataclass
class Settings:
    provider: str = "claude"
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "low"
    claude_detector_model: str = "claude-haiku-5-5"
    presets: dict[str, dict] = field(default_factory=lambda: copy.deepcopy(DEFAULT_PRESETS))
    display_mode: str = "window"
    window_theme: str = "day"  # "day" | "night"
    window_font_size: int = 14
    overlay_font_size: int = 12
    overlay_opacity: float = 0.85  # background alpha; text stays opaque
    overlay_bg_color: str = "#101218"
    overlay_text_color: str = "#f2f2f2"
    click_through: bool = False
    auto_enabled: bool = True
    mic_device: str | None = None
    loopback_device: str | None = None
    mic_gain: float = 1.0  # x1..x20, applied before speech detection
    stt_model: str = "large-v3-turbo"  # or "large-v3" (most accurate) / "distil-large-v3"
    stt_compute: str = "float16"
    stt_model_light: str = "small.en"
    stt_compute_light: str = "int8_float16"
    vad_silence_ms: int = 600
    context_seconds: int = 180
    profiles_dir: str = "profiles"
    sessions_dir: str = "sessions"
    hotkeys: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_HOTKEYS))
    prices: dict[str, list[float]] = field(default_factory=lambda: copy.deepcopy(DEFAULT_PRICES))


def stt_config(s: Settings) -> tuple[str, str]:
    """Speech model and compute type; lighter when a local LLM shares the GPU."""
    if s.provider == "local":
        return s.stt_model_light, s.stt_compute_light
    return s.stt_model, s.stt_compute


def _merge_presets(saved: dict) -> dict[str, dict]:
    merged = copy.deepcopy(DEFAULT_PRESETS)
    for key, values in saved.items():
        merged[key] = {**merged.get(key, {}), **values}
    return merged


def load_settings(path: Path) -> Settings:
    """Load settings; a missing file is created with defaults."""
    if not path.exists():
        settings = Settings()
        save_settings(settings, path)
        return settings
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(Settings)}
    kwargs = {k: v for k, v in data.items() if k in known}
    if "presets" in kwargs:
        kwargs["presets"] = _merge_presets(kwargs["presets"])
    if "hotkeys" in kwargs:
        kwargs["hotkeys"] = {**DEFAULT_HOTKEYS, **kwargs["hotkeys"]}
    return Settings(**kwargs)


def save_settings(s: Settings, path: Path) -> None:
    # TOML has no null: unset optional values are simply omitted.
    data = {k: v for k, v in asdict(s).items() if v is not None}
    path.write_text(tomli_w.dumps(data), encoding="utf-8")
