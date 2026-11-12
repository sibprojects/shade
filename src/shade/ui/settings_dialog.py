"""Settings dialog. API keys are never shown or stored — only whether they are set."""

from __future__ import annotations

import copy
import os
from dataclasses import replace

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from shade.config import Settings
from shade.llm.check import check_connection
from shade.ui.hotkeys import ACTIONS

DEFAULT_DEVICE = "(default)"
HOTKEY_LABELS = {
    "ask": "Answer last question",
    "screenshot": "Screenshot a region",
    "toggle_view": "Switch window / overlay",
    "toggle_overlay": "Show / hide overlay",
    "toggle_window": "Show / hide window",
    "click_through": "Overlay click-through",
    "dismiss": "Dismiss hint",
    "toggle_auto": "Toggle auto hints",
}


def _device_combo(names: list[str], current: str | None) -> QComboBox:
    c = QComboBox()
    c.addItem(DEFAULT_DEVICE, None)
    for n in names:
        c.addItem(n, n)
    if current and c.findData(current) < 0:
        c.addItem(current, current)  # saved device not present right now
    c.setCurrentIndex(max(0, c.findData(current)) if current else 0)
    return c


STT_MODELS = (
    ("large-v3-turbo", "large-v3-turbo — accurate and fast (recommended)"),
    ("large-v3", "large-v3 — most accurate, about 2x slower"),
    ("distil-large-v3", "distil-large-v3 — fast, ignores call context"),
)


class SettingsDialog(QDialog):
    applied = Signal(object)  # Settings, emitted by the Apply button
    def __init__(
        self,
        settings: Settings,
        devices: dict[str, list[str]],
        parent: QWidget | None = None,
        start_meter: bool = True,
    ):
        super().__init__(parent)
        self.setWindowTitle("Shade settings")
        self._original = settings
        self._presets = copy.deepcopy(settings.presets)
        self._shown_preset: str | None = None

        # --- provider ---
        self.provider = QComboBox()
        self.provider.addItem("Claude", "claude")
        for key, p in self._presets.items():
            self.provider.addItem(p.get("label", key), key)
        self.claude_model = QLineEdit(settings.claude_model)
        self.claude_detector = QLineEdit(settings.claude_detector_model)
        self.claude_effort = QComboBox()
        self.claude_effort.addItems(["low", "medium", "high"])
        self.claude_effort.setCurrentText(settings.claude_effort)
        self.base_url = QLineEdit()
        self.preset_model = QLineEdit()
        self.preset_detector = QLineEdit()
        self.preset_images = QCheckBox("Model can read images (screenshots)")
        self.key_status = QLabel()
        add_btn = QPushButton("Add custom preset…")
        add_btn.clicked.connect(self._ask_custom_preset)

        self.claude_box = QGroupBox("Claude")
        cf = QFormLayout(self.claude_box)
        cf.addRow("Answer model", self.claude_model)
        cf.addRow("Detector model", self.claude_detector)
        cf.addRow("Effort", self.claude_effort)
        self.preset_box = QGroupBox("OpenAI-compatible service")
        pf = QFormLayout(self.preset_box)
        pf.addRow("Base URL", self.base_url)
        pf.addRow("Answer model", self.preset_model)
        pf.addRow("Detector model", self.preset_detector)
        pf.addRow("", self.preset_images)
        self.test_button = QPushButton("Test connection")
        self.test_button.clicked.connect(self._test_connection)
        self.test_result = QLabel()
        self.test_result.setWordWrap(True)
        self.test_result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        pf.addRow(self.test_button, self.test_result)
        self.network_hint = QLabel(
            "On the other PC: install Ollama, run  setx OLLAMA_HOST 0.0.0.0  and restart Ollama, "
            "allow TCP port 11434 in its firewall, then put that PC's IP address into Base URL."
        )
        self.network_hint.setWordWrap(True)
        pf.addRow(self.network_hint)

        prov_row = QHBoxLayout()
        prov_row.addWidget(self.provider, 1)
        prov_row.addWidget(add_btn)

        # --- display / behavior ---
        self.display_mode = QComboBox()
        self.display_mode.addItem("Window", "window")
        self.display_mode.addItem("Overlay", "overlay")
        self.display_mode.setCurrentIndex(self.display_mode.findData(settings.display_mode))
        self.window_theme = QComboBox()
        self.window_theme.addItem("Day", "day")
        self.window_theme.addItem("Night", "night")
        self.window_theme.setCurrentIndex(max(0, self.window_theme.findData(settings.window_theme)))
        self.window_font = QSpinBox()
        self.window_font.setRange(8, 40)
        self.window_font.setSuffix(" pt")
        self.window_font.setValue(settings.window_font_size)
        self.overlay_font = QSpinBox()
        self.overlay_font.setRange(8, 40)
        self.overlay_font.setSuffix(" pt")
        self.overlay_font.setValue(settings.overlay_font_size)
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(round(settings.overlay_opacity * 100))
        self.overlay_bg_button = QPushButton()
        self.overlay_text_button = QPushButton()
        self.overlay_bg_button.clicked.connect(
            lambda: self._pick_color(self._overlay_bg, self.set_overlay_bg, "Overlay background")
        )
        self.overlay_text_button.clicked.connect(
            lambda: self._pick_color(self._overlay_text, self.set_overlay_text, "Overlay text")
        )
        self.set_overlay_bg(settings.overlay_bg_color)
        self.set_overlay_text(settings.overlay_text_color)
        self.click_through = QCheckBox("Overlay ignores mouse clicks")
        self.click_through.setChecked(settings.click_through)
        self.auto = QCheckBox("Answer detected questions automatically")
        self.auto.setChecked(settings.auto_enabled)

        # --- audio ---
        self.mic = _device_combo(devices.get("mic", []), settings.mic_device)
        self.loopback = _device_combo(devices.get("loopback", []), settings.loopback_device)
        self.mic_gain = QSlider(Qt.Orientation.Horizontal)
        self.mic_gain.setRange(10, 200)  # tenths: x1.0 .. x20.0
        self.mic_gain.setValue(round(settings.mic_gain * 10))
        self.mic_gain_label = QLabel()
        self.mic_level = QProgressBar()
        self.mic_level.setRange(0, 100)
        self.mic_level.setTextVisible(False)
        self.mic_level.setFixedHeight(10)
        self.mic_gain.valueChanged.connect(self._on_gain_changed)
        self._on_gain_changed()
        self.stt_model = QComboBox()
        for key, label in STT_MODELS:
            self.stt_model.addItem(label, key)
        if self.stt_model.findData(settings.stt_model) < 0:
            self.stt_model.addItem(settings.stt_model, settings.stt_model)
        self.stt_model.setCurrentIndex(self.stt_model.findData(settings.stt_model))
        self.vad_silence = QSpinBox()
        self.vad_silence.setRange(200, 3000)
        self.vad_silence.setSingleStep(50)
        self.vad_silence.setSuffix(" ms")
        self.vad_silence.setValue(settings.vad_silence_ms)
        self.context = QSpinBox()
        self.context.setRange(30, 1800)
        self.context.setSuffix(" s")
        self.context.setValue(settings.context_seconds)

        # --- hotkeys ---
        self.hotkey_edits = {a: QLineEdit(settings.hotkeys.get(a, "")) for a in ACTIONS}

        # --- tabs ---
        model_tab = QWidget()
        mt = QVBoxLayout(model_tab)
        form = QFormLayout()
        form.addRow("Provider", prov_row)
        form.addRow("", self.key_status)
        mt.addLayout(form)
        mt.addWidget(self.claude_box)
        mt.addWidget(self.preset_box)
        mt.addStretch(1)

        display_tab = QWidget()
        dt = QFormLayout(display_tab)
        dt.addRow("Display", self.display_mode)
        dt.addRow("Window theme", self.window_theme)
        dt.addRow("Window font size", self.window_font)
        dt.addRow("Overlay font size", self.overlay_font)
        dt.addRow("Overlay background", self.overlay_bg_button)
        dt.addRow("Overlay text", self.overlay_text_button)
        dt.addRow("Overlay background opacity", self.opacity)
        dt.addRow("", self.click_through)
        dt.addRow("", self.auto)

        audio_tab = QWidget()
        at = QFormLayout(audio_tab)
        at.addRow("Microphone", self.mic)
        gain_row = QHBoxLayout()
        gain_row.addWidget(self.mic_gain, 1)
        gain_row.addWidget(self.mic_gain_label)
        at.addRow("Microphone gain", gain_row)
        at.addRow("Microphone level", self.mic_level)
        at.addRow("System audio", self.loopback)
        at.addRow("Speech model", self.stt_model)
        at.addRow("End of phrase pause", self.vad_silence)
        at.addRow("Context sent to model", self.context)

        hotkeys_tab = QWidget()
        ht = QFormLayout(hotkeys_tab)
        for a in ACTIONS:
            ht.addRow(HOTKEY_LABELS[a], self.hotkey_edits[a])
        ht.addRow("", QLabel("Format: <ctrl>+<alt>+a, <f8>, <shift>+<f2>"))

        self.tabs = QTabWidget()
        self.tabs.addTab(model_tab, "Model")
        self.tabs.addTab(display_tab, "Display")
        self.tabs.addTab(audio_tab, "Audio")
        self.tabs.addTab(hotkeys_tab, "Hotkeys")
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        self.setMinimumWidth(480)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        layout.addWidget(self.buttons)

        self._meter_source = None
        self._meter_timer = QTimer(self)
        self._meter_timer.setInterval(60)
        self._meter_timer.timeout.connect(self._update_meter)
        if start_meter:
            self.mic.currentIndexChanged.connect(self._restart_meter)
            self._restart_meter()

        self.provider.currentIndexChanged.connect(self._on_provider_changed)
        self.provider.setCurrentIndex(max(0, self.provider.findData(settings.provider)))
        self._on_provider_changed()

    def _apply(self) -> None:
        """Apply without closing: later Apply/OK compare against these values."""
        new = self.result_settings()
        self._original = new
        self.applied.emit(new)

    # ---- microphone gain and level meter ----------------------------------

    def _gain(self) -> float:
        return self.mic_gain.value() / 10

    def _on_gain_changed(self, *_):
        self.mic_gain_label.setText(f"x{self._gain():.1f}")
        if getattr(self, "_meter_source", None):
            self._meter_source.gain = self._gain()

    def _restart_meter(self, *_):
        self._stop_meter()
        from shade.audio.capture import MicSource

        src = MicSource(self.mic.currentData(), gain=self._gain())
        src.start(lambda audio, t: None)
        self._meter_source = src
        self._meter_timer.start()

    def _update_meter(self) -> None:
        from shade.audio.capture import level_percent

        src = self._meter_source
        if src is not None:
            self.mic_level.setValue(level_percent(src.last_peak))

    def _stop_meter(self) -> None:
        self._meter_timer.stop()
        if self._meter_source is not None:
            self._meter_source.stop()
            self._meter_source = None

    def done(self, result: int) -> None:  # OK, Cancel or closing the dialog
        self._stop_meter()
        super().done(result)

    # ---- colors -----------------------------------------------------------

    @staticmethod
    def _paint_swatch(button: QPushButton, color: str) -> None:
        text = "#000000" if QColor(color).lightness() > 140 else "#ffffff"
        button.setText(color)
        button.setStyleSheet(f"background: {color}; color: {text}; padding: 4px 10px;")

    def set_overlay_bg(self, color: str) -> None:
        self._overlay_bg = color
        self._paint_swatch(self.overlay_bg_button, color)

    def set_overlay_text(self, color: str) -> None:
        self._overlay_text = color
        self._paint_swatch(self.overlay_text_button, color)

    def _pick_color(self, current: str, setter, title: str) -> None:
        chosen = QColorDialog.getColor(QColor(current), self, title)
        if chosen.isValid():
            setter(chosen.name())

    # ---- presets ----------------------------------------------------------

    def _store_shown_preset(self) -> None:
        key = self._shown_preset
        if key is None:
            return
        p = self._presets[key]
        p["base_url"] = self.base_url.text().strip()
        p["model"] = self.preset_model.text().strip()
        p["detector_model"] = self.preset_detector.text().strip()
        p["supports_images"] = self.preset_images.isChecked()

    def _on_provider_changed(self, *_):
        self._store_shown_preset()
        key = self.provider.currentData()
        is_claude = key == "claude"
        self.claude_box.setVisible(is_claude)
        self.preset_box.setVisible(not is_claude)
        if is_claude:
            self._shown_preset = None
            env = "ANTHROPIC_API_KEY"
        else:
            p = self._presets[key]
            self._shown_preset = key
            self.base_url.setText(p.get("base_url", ""))
            self.preset_model.setText(p.get("model", ""))
            self.preset_detector.setText(p.get("detector_model", ""))
            self.preset_images.setChecked(bool(p.get("supports_images", True)))
            env = p.get("key_env") or ""
        self.network_hint.setVisible(key == "network")
        self.test_result.clear()
        if not env:
            self.key_status.setText("No API key needed")
        elif os.environ.get(env):
            self.key_status.setText(f"{env} is set")
        else:
            self.key_status.setText(f"{env} is not set")

    def _test_connection(self) -> None:
        env = (self._presets.get(self._shown_preset or "", {}).get("key_env") or "")
        key = os.environ.get(env, "") if env else "local"
        self.test_result.setText("Checking…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            _, message = check_connection(
                self.base_url.text().strip(), key, self.preset_model.text().strip(), timeout=5
            )
        finally:
            QApplication.restoreOverrideCursor()
        self.test_result.setText(message)

    def _ask_custom_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Custom preset", "Preset name (letters, digits, dashes):")
        if ok and name.strip():
            self.add_custom_preset(name.strip())

    def add_custom_preset(self, name: str) -> None:
        key = name.lower().replace(" ", "-")
        if key not in self._presets:
            self._presets[key] = {
                "label": name,
                "base_url": "http://localhost:8000/v1",
                "model": "",
                "detector_model": "",
                "key_env": "",
                "supports_images": False,
            }
            self.provider.addItem(name, key)
        self.provider.setCurrentIndex(self.provider.findData(key))

    # ---- result -------------------------------------------------------------

    def result_settings(self) -> Settings:
        self._store_shown_preset()
        hotkeys = dict(self._original.hotkeys)
        hotkeys.update({a: e.text().strip() for a, e in self.hotkey_edits.items()})
        return replace(
            self._original,
            provider=self.provider.currentData(),
            claude_model=self.claude_model.text().strip(),
            claude_detector_model=self.claude_detector.text().strip(),
            claude_effort=self.claude_effort.currentText(),
            presets=copy.deepcopy(self._presets),
            display_mode=self.display_mode.currentData(),
            window_theme=self.window_theme.currentData(),
            window_font_size=self.window_font.value(),
            overlay_font_size=self.overlay_font.value(),
            overlay_opacity=self.opacity.value() / 100,
            overlay_bg_color=self._overlay_bg,
            overlay_text_color=self._overlay_text,
            click_through=self.click_through.isChecked(),
            auto_enabled=self.auto.isChecked(),
            mic_device=self.mic.currentData(),
            mic_gain=self._gain(),
            loopback_device=self.loopback.currentData(),
            vad_silence_ms=self.vad_silence.value(),
            stt_model=self.stt_model.currentData(),
            context_seconds=self.context.value(),
            hotkeys=hotkeys,
        )
