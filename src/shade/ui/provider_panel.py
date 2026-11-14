"""A provider choice with that provider's own settings, used twice in Settings → Model:
for the main model and for the fallback model.

Both panels edit one shared ProviderStore. They never show the same provider at
the same time, so each provider's settings have exactly one editor on screen.
"""

from __future__ import annotations

import copy
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from shade.config import Settings
from shade.llm.check import check_connection
from shade.llm.claude_code import find_claude

CC_MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
STORE_FIELDS = (
    "claude_model", "claude_detector_model", "claude_effort",
    "cc_model", "cc_detector_model", "cc_effort", "cc_path", "cc_auto",
)


class ProviderStore:
    """Settings of every provider while the dialog is open."""

    def __init__(self, settings: Settings) -> None:
        self.values = {k: getattr(settings, k) for k in STORE_FIELDS}
        self.presets = copy.deepcopy(settings.presets)

    def choices(self) -> list[tuple[str, str]]:
        """(label, key) of every provider, in combo order."""
        return [("Claude", "claude"), ("Claude Code (subscription)", "claude_code")] + [
            (p.get("label", key), key) for key, p in self.presets.items()
        ]


class ProviderPanel(QWidget):
    changed = Signal(str)  # provider key now shown ("" = none)

    def __init__(self, store: ProviderStore, current: str, allow_none: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self._shown: str | None = None  # provider whose values the widgets hold

        self.provider = QComboBox()
        if allow_none:
            self.provider.addItem("(none)", "")
        for label, key in store.choices():
            self.provider.addItem(label, key)
        self.key_status = QLabel()

        # --- Claude API ---
        self.claude_model = QLineEdit()
        self.claude_detector = QLineEdit()
        self.claude_effort = QComboBox()
        self.claude_effort.addItems(["low", "medium", "high"])
        self.claude_box = QGroupBox("Claude")
        cf = QFormLayout(self.claude_box)
        cf.addRow("Answer model", self.claude_model)
        cf.addRow("Detector model", self.claude_detector)
        cf.addRow("Effort", self.claude_effort)

        # --- Claude Code ---
        self.cc_model = QComboBox()
        self.cc_model.setEditable(True)  # any other model id can be typed in
        self.cc_model.addItems(CC_MODELS)
        self.cc_detector = QLineEdit()
        self.cc_effort = QComboBox()
        self.cc_effort.addItems(["low", "medium", "high"])
        self.cc_path = QLineEdit()
        self.cc_path.setPlaceholderText("found automatically")
        self.cc_path.textChanged.connect(self._update_key_status)
        self.cc_auto = QCheckBox("Auto hints (questions found by rules, no AI)")
        self.cc_warning = QLabel(
            "Uses the installed Claude Code with your own Claude sign-in, for your personal use. "
            "Answers count toward your subscription's usage limits. Questions are found by rules "
            "on this PC, so only the answers use the plan. Anthropic's terms apply."
        )
        self.cc_warning.setWordWrap(True)
        self.cc_box = QGroupBox("Claude Code (subscription)")
        ccf = QFormLayout(self.cc_box)
        ccf.addRow("Answer model", self.cc_model)
        ccf.addRow("Detector model", self.cc_detector)
        ccf.addRow("Effort", self.cc_effort)
        ccf.addRow("Claude Code path", self.cc_path)
        ccf.addRow("", self.cc_auto)
        ccf.addRow(self.cc_warning)

        # --- OpenAI-compatible presets ---
        self.base_url = QLineEdit()
        self.preset_model = QLineEdit()
        self.preset_detector = QLineEdit()
        self.preset_images = QCheckBox("Model can read images (screenshots)")
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

        self.provider_row = QHBoxLayout()
        self.provider_row.addWidget(self.provider, 1)
        form = QFormLayout()
        self.provider_label = QLabel("Provider")
        form.addRow(self.provider_label, self.provider_row)
        form.addRow("", self.key_status)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(form)
        layout.addWidget(self.claude_box)
        layout.addWidget(self.cc_box)
        layout.addWidget(self.preset_box)

        self.provider.currentIndexChanged.connect(self._on_provider_changed)
        self.provider.setCurrentIndex(max(0, self.provider.findData(current)))
        self._on_provider_changed()

    # ---- state ------------------------------------------------------------

    def key(self) -> str:
        return self.provider.currentData() or ""

    def set_key(self, key: str) -> None:
        self.provider.setCurrentIndex(max(0, self.provider.findData(key)))

    def add_choice(self, label: str, key: str) -> None:
        self.provider.addItem(label, key)

    def store_shown(self) -> None:
        """Write what the widgets show back into the store."""
        key, v = self._shown, self.store.values
        if key == "claude":
            v["claude_model"] = self.claude_model.text().strip()
            v["claude_detector_model"] = self.claude_detector.text().strip()
            v["claude_effort"] = self.claude_effort.currentText()
        elif key == "claude_code":
            v["cc_model"] = self.cc_model.currentText().strip()
            v["cc_detector_model"] = self.cc_detector.text().strip()
            v["cc_effort"] = self.cc_effort.currentText()
            v["cc_path"] = self.cc_path.text().strip()
            v["cc_auto"] = self.cc_auto.isChecked()
        elif key in self.store.presets:
            p = self.store.presets[key]
            p["base_url"] = self.base_url.text().strip()
            p["model"] = self.preset_model.text().strip()
            p["detector_model"] = self.preset_detector.text().strip()
            p["supports_images"] = self.preset_images.isChecked()

    def _load(self, key: str) -> None:
        v = self.store.values
        if key == "claude":
            self.claude_model.setText(v["claude_model"])
            self.claude_detector.setText(v["claude_detector_model"])
            self.claude_effort.setCurrentText(v["claude_effort"])
        elif key == "claude_code":
            self.cc_model.setCurrentText(v["cc_model"])
            self.cc_detector.setText(v["cc_detector_model"])
            self.cc_effort.setCurrentText(v["cc_effort"])
            self.cc_path.setText(v["cc_path"])
            self.cc_auto.setChecked(v["cc_auto"])
        elif key in self.store.presets:
            p = self.store.presets[key]
            self.base_url.setText(p.get("base_url", ""))
            self.preset_model.setText(p.get("model", ""))
            self.preset_detector.setText(p.get("detector_model", ""))
            self.preset_images.setChecked(bool(p.get("supports_images", True)))

    def _on_provider_changed(self, *_) -> None:
        self.store_shown()
        key = self.key()
        self._load(key)
        self._shown = key or None
        self.claude_box.setVisible(key == "claude")
        self.cc_box.setVisible(key == "claude_code")
        self.preset_box.setVisible(key in self.store.presets)
        self.key_status.setVisible(bool(key))
        self.network_hint.setVisible(key == "network")
        self.test_result.clear()
        self._update_key_status()
        self.changed.emit(key)

    def _update_key_status(self, *_) -> None:
        key = self.key()
        if key == "claude_code":
            exe = find_claude(self.cc_path.text().strip())
            self.key_status.setText(
                f"Uses your Claude subscription · {exe}" if exe else "Claude Code not found: install it or set its path"
            )
            return
        env = "ANTHROPIC_API_KEY" if key == "claude" else (self.store.presets.get(key, {}).get("key_env") or "")
        if not env:
            self.key_status.setText("No API key needed")
        elif os.environ.get(env):
            self.key_status.setText(f"{env} is set")
        else:
            self.key_status.setText(f"{env} is not set")

    def _test_connection(self) -> None:
        env = self.store.presets.get(self.key(), {}).get("key_env") or ""
        api_key = os.environ.get(env, "") if env else "local"
        self.test_result.setText("Checking…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            _, message = check_connection(
                self.base_url.text().strip(), api_key, self.preset_model.text().strip(), timeout=5
            )
        finally:
            QApplication.restoreOverrideCursor()
        self.test_result.setText(message)
