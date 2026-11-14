"""Settings dialog. API keys are never shown or stored — only whether they are set."""

from __future__ import annotations

import copy
from dataclasses import replace

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from shade.config import Settings
from shade.ui.hotkeys import ACTIONS
from shade.ui.provider_panel import ProviderPanel, ProviderStore

DEFAULT_DEVICE = "(default)"
HOTKEY_LABELS = {
    "ask": "Answer last question",
    "screenshot": "Screenshot a region",
    "toggle_view": "Switch window / overlay",
    "toggle_overlay": "Show / hide overlay",
    "toggle_window": "Show / hide window",
    "click_through": "Overlay click-through",
    "dismiss": "Clear answers (new topic)",
    "toggle_auto": "Toggle auto hints",
    "shorter": "Last answer: shorter",
    "more": "Last answer: more detail",
    "code": "Last answer: code example",
    "followups": "Questions to ask them",
    "recap": "What did I miss (recap)",
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

        # --- models: the main one, then the fallback, each with its own settings ---
        self.store = ProviderStore(settings)
        self.main_panel = ProviderPanel(self.store, settings.provider)
        add_btn = QPushButton("Add custom preset…")
        add_btn.clicked.connect(self._ask_custom_preset)
        self.main_panel.provider_row.addWidget(add_btn)
        self.fallback_panel = ProviderPanel(self.store, settings.fallback_provider, allow_none=True)
        self.fallback_panel.provider_label.setText("If it fails, use")
        self.main_panel.changed.connect(self._on_main_changed)
        self.fallback_panel.changed.connect(self._on_fallback_changed)
        self._on_fallback_changed(self.fallback_panel.key())
        # The main panel's widgets, under the names the rest of Shade and the tests use.
        m = self.main_panel
        self.provider, self.key_status = m.provider, m.key_status
        self.claude_box, self.cc_box, self.preset_box = m.claude_box, m.cc_box, m.preset_box
        self.claude_model, self.claude_detector, self.claude_effort = m.claude_model, m.claude_detector, m.claude_effort
        self.cc_model, self.cc_detector, self.cc_effort = m.cc_model, m.cc_detector, m.cc_effort
        self.cc_path, self.cc_auto, self.cc_warning = m.cc_path, m.cc_auto, m.cc_warning
        self.base_url, self.preset_model, self.preset_detector = m.base_url, m.preset_model, m.preset_detector
        self.preset_images, self.network_hint = m.preset_images, m.network_hint
        self.test_button, self.test_result = m.test_button, m.test_result
        self.fallback = self.fallback_panel.provider

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
        self.window_code_font = QSpinBox()
        self.window_code_font.setRange(7, 40)
        self.window_code_font.setSuffix(" pt")
        self.window_code_font.setValue(settings.window_code_font_size)
        self.overlay_code_font = QSpinBox()
        self.overlay_code_font.setRange(7, 40)
        self.overlay_code_font.setSuffix(" pt")
        self.overlay_code_font.setValue(settings.overlay_code_font_size)
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
        self.auto_notes = QCheckBox("Write call notes when a session stops")
        self.auto_notes.setChecked(settings.auto_notes)

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
        main_group = QGroupBox("Main model")
        QVBoxLayout(main_group).addWidget(self.main_panel)
        fallback_group = QGroupBox("Fallback model")
        fb = QVBoxLayout(fallback_group)
        fb.addWidget(QLabel("Answers when the main model fails (usage limit, outage, missing key)."))
        fb.addWidget(self.fallback_panel)
        model_inner = QWidget()
        mt = QVBoxLayout(model_inner)
        mt.addWidget(main_group)
        mt.addWidget(fallback_group)
        mt.addStretch(1)
        model_tab = QScrollArea()  # two providers' settings can be taller than the dialog
        model_tab.setWidgetResizable(True)
        model_tab.setFrameShape(QFrame.Shape.NoFrame)
        model_tab.setWidget(model_inner)

        display_tab = QWidget()
        dt = QFormLayout(display_tab)
        dt.addRow("Display", self.display_mode)
        dt.addRow("Window theme", self.window_theme)
        dt.addRow("Window font size", self.window_font)
        dt.addRow("Window code font size", self.window_code_font)
        dt.addRow("Overlay font size", self.overlay_font)
        dt.addRow("Overlay code font size", self.overlay_code_font)
        dt.addRow("Overlay background", self.overlay_bg_button)
        dt.addRow("Overlay text", self.overlay_text_button)
        dt.addRow("Overlay background opacity", self.opacity)
        dt.addRow("", self.click_through)
        dt.addRow("", self.auto)
        dt.addRow("", self.auto_notes)

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

    # ---- models -----------------------------------------------------------

    def _on_main_changed(self, key: str) -> None:
        # The same provider can't be its own fallback.
        if key and key == self.fallback_panel.key():
            self.fallback_panel.set_key("")

    def _on_fallback_changed(self, key: str) -> None:
        if key and key == self.main_panel.key():
            self.fallback_panel.set_key("")

    def _ask_custom_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Custom preset", "Preset name (letters, digits, dashes):")
        if ok and name.strip():
            self.add_custom_preset(name.strip())

    def add_custom_preset(self, name: str) -> None:
        key = name.lower().replace(" ", "-")
        if key not in self.store.presets:
            self.store.presets[key] = {
                "label": name,
                "base_url": "http://localhost:8000/v1",
                "model": "",
                "detector_model": "",
                "key_env": "",
                "supports_images": False,
            }
            self.main_panel.add_choice(name, key)
            self.fallback_panel.add_choice(name, key)
        self.main_panel.set_key(key)

    # ---- result -------------------------------------------------------------

    def result_settings(self) -> Settings:
        self.main_panel.store_shown()
        self.fallback_panel.store_shown()
        hotkeys = dict(self._original.hotkeys)
        hotkeys.update({a: e.text().strip() for a, e in self.hotkey_edits.items()})
        return replace(
            self._original,
            **self.store.values,
            provider=self.main_panel.key(),
            presets=copy.deepcopy(self.store.presets),
            fallback_provider=self.fallback_panel.key(),
            display_mode=self.display_mode.currentData(),
            window_theme=self.window_theme.currentData(),
            window_font_size=self.window_font.value(),
            overlay_font_size=self.overlay_font.value(),
            window_code_font_size=self.window_code_font.value(),
            overlay_code_font_size=self.overlay_code_font.value(),
            overlay_opacity=self.opacity.value() / 100,
            overlay_bg_color=self._overlay_bg,
            overlay_text_color=self._overlay_text,
            click_through=self.click_through.isChecked(),
            auto_enabled=self.auto.isChecked(),
            auto_notes=self.auto_notes.isChecked(),
            mic_device=self.mic.currentData(),
            mic_gain=self._gain(),
            loopback_device=self.loopback.currentData(),
            vad_silence_ms=self.vad_silence.value(),
            stt_model=self.stt_model.currentData(),
            context_seconds=self.context.value(),
            hotkeys=hotkeys,
        )
