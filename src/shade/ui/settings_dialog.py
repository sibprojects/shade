"""Settings dialog. API keys are never shown or stored — only whether they are set."""

from __future__ import annotations

import copy
import os
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from shade.config import Settings
from shade.ui.hotkeys import ACTIONS

DEFAULT_DEVICE = "(default)"
HOTKEY_LABELS = {
    "ask": "Answer last question",
    "screenshot": "Screenshot a region",
    "toggle_view": "Switch window / overlay",
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


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, devices: dict[str, list[str]], parent: QWidget | None = None):
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

        prov_row = QHBoxLayout()
        prov_row.addWidget(self.provider, 1)
        prov_row.addWidget(add_btn)

        # --- display / behavior ---
        self.display_mode = QComboBox()
        self.display_mode.addItem("Window", "window")
        self.display_mode.addItem("Overlay", "overlay")
        self.display_mode.setCurrentIndex(self.display_mode.findData(settings.display_mode))
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(20, 100)
        self.opacity.setValue(round(settings.overlay_opacity * 100))
        self.click_through = QCheckBox("Overlay ignores mouse clicks")
        self.click_through.setChecked(settings.click_through)
        self.auto = QCheckBox("Answer detected questions automatically")
        self.auto.setChecked(settings.auto_enabled)

        # --- audio ---
        self.mic = _device_combo(devices.get("mic", []), settings.mic_device)
        self.loopback = _device_combo(devices.get("loopback", []), settings.loopback_device)
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
        dt.addRow("Overlay opacity", self.opacity)
        dt.addRow("", self.click_through)
        dt.addRow("", self.auto)

        audio_tab = QWidget()
        at = QFormLayout(audio_tab)
        at.addRow("Microphone", self.mic)
        at.addRow("System audio", self.loopback)
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
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.provider.currentIndexChanged.connect(self._on_provider_changed)
        self.provider.setCurrentIndex(max(0, self.provider.findData(settings.provider)))
        self._on_provider_changed()

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
        if not env:
            self.key_status.setText("No API key needed")
        elif os.environ.get(env):
            self.key_status.setText(f"{env} is set")
        else:
            self.key_status.setText(f"{env} is not set")

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
            overlay_opacity=self.opacity.value() / 100,
            click_through=self.click_through.isChecked(),
            auto_enabled=self.auto.isChecked(),
            mic_device=self.mic.currentData(),
            loopback_device=self.loopback.currentData(),
            vad_silence_ms=self.vad_silence.value(),
            context_seconds=self.context.value(),
            hotkeys=hotkeys,
        )
