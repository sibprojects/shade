"""Tray application: owns the windows and runs sessions."""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QSystemTrayIcon

from shade import gpu
from shade.audio.capture import LoopbackSource, MicSource, list_devices
from shade.audio.segmenter import Segmenter
from shade.audio.vad import SileroVad
from shade.config import (
    DEFAULT_SETTINGS_PATH,
    Settings,
    auto_allowed,
    billable_prices,
    detection_by_rules,
    load_settings,
    save_settings,
    stt_config,
)
from shade.cost import CostMeter
from shade.detect import Detector, RuleDetector
from shade.engine import Engine
from shade.llm.factory import make_provider_or_unavailable
from shade.models import HintError, Status
from shade.session import SessionWriter
from shade.stt import SttWorker, Transcriber, build_stt_prompt
from shade.transcript import Transcript
from shade.ui.about import show_about
from shade.ui.bridge import QtBridge
from shade.ui.hotkeys import HotkeyManager
from shade.ui.icon import make_icon
from shade.ui.main_window import MainWindow
from shade.ui.overlay import Overlay
from shade.ui.region_select import RegionSelector
from shade.ui.settings_dialog import SettingsDialog

CAPTURE_WARNING = "Warning: window may be visible in screen sharing."
VRAM_WARNING = "GPU memory almost full — hints may lag."
NEXT_SESSION = "Applies to the next session."
AUTO_BLOCKED = (
    "Auto hints are off for Claude Code (subscription): ask with the hotkey, "
    "or turn them on in Settings → Model."
)


class Session:
    """Everything that lives for the duration of one call."""

    def __init__(self, settings: Settings, transcriber, profile: Path, bridge: QtBridge) -> None:
        # A provider that can't be built (e.g. missing key) still lets the session
        # transcribe; every hint then shows the reason in the hint area.
        provider, self.provider_problem = make_provider_or_unavailable(settings)
        self.provider = provider
        status = lambda msg: bridge.emit_event(Status(msg))  # noqa: E731
        start = time.monotonic()
        clock = lambda: time.monotonic() - start  # noqa: E731
        self.writer = SessionWriter(Path(settings.sessions_dir), profile.stem, datetime.now())
        self.engine = Engine(
            provider=provider,
            detector=RuleDetector() if detection_by_rules(settings) else Detector(provider, on_error=status),
            transcript=Transcript(),
            writer=self.writer,
            cost=CostMeter(billable_prices(settings)),
            profile_text=profile.read_text(encoding="utf-8", errors="replace"),
            context_seconds=settings.context_seconds,
            on_event=bridge.emit_event,
            clock=clock,
        )
        self.engine.set_auto(settings.auto_enabled and auto_allowed(settings))
        profile_text = profile.read_text(encoding="utf-8", errors="replace")
        transcript = self.engine.transcript
        self.stt = SttWorker(
            transcriber,
            self.engine.on_utterance,
            on_error=status,
            # The call topic and the last lines help the speech model with terms.
            prompt_fn=lambda: build_stt_prompt(profile_text, transcript.all()[-2:]),
        )
        self.sources = []
        for name, cls, device in (
            ("me", MicSource, settings.mic_device),
            ("them", LoopbackSource, settings.loopback_device),
        ):
            seg = Segmenter(name, SileroVad(), self.stt.submit, silence_ms=settings.vad_silence_ms)
            gain = settings.mic_gain if name == "me" else 1.0
            src = cls(device, on_error=status, clock=clock, gain=gain)
            src.start(seg.feed)
            self.sources.append(src)

    def stop(self) -> None:
        for s in self.sources:
            s.stop()
        self.stt.stop()
        self.engine.stop()
        close = getattr(self.provider, "close", None)
        if close is not None:
            close()  # e.g. Claude Code processes started in advance
        self.writer.close()


class ShadeApp(QObject):
    transcriber_ready = Signal(object)
    transcriber_failed = Signal(str)

    def __init__(self, settings_path: Path = DEFAULT_SETTINGS_PATH) -> None:
        self.qapp = QApplication.instance() or QApplication(sys.argv)
        super().__init__()
        self.qapp.setQuitOnLastWindowClosed(False)
        self.qapp.setWindowIcon(make_icon())
        self.settings_path = settings_path
        self.settings = load_settings(settings_path)
        self.bridge = QtBridge()
        self.session: Session | None = None
        self.transcriber = None
        self.transcriber_config: tuple[str, str] | None = None
        self._loading = False
        self._vram_warned = False
        self.vram_timer = QTimer()
        self.vram_timer.setInterval(10_000)
        self.vram_timer.timeout.connect(self._check_vram)

        self.window = MainWindow(
            self.settings.window_theme, self.settings.window_font_size, self.settings.window_code_font_size
        )
        self.overlay = Overlay(
            self.settings.overlay_opacity,
            self.settings.click_through,
            self.settings.overlay_bg_color,
            self.settings.overlay_text_color,
            self.settings.overlay_font_size,
            self.settings.overlay_code_font_size,
        )
        for view in (self.window.view, self.overlay.view):
            self.bridge.event.connect(view.handle)

        self.tray = QSystemTrayIcon(make_icon())
        self.tray.setToolTip("Shade — loading speech model…")
        self._build_menu()
        self.tray.show()

        self.region = RegionSelector()
        self.region.selected.connect(self._on_screenshot)
        self.hotkeys = HotkeyManager()
        self.hotkeys.triggered.connect(self.on_hotkey)
        self.hotkeys.error.connect(lambda msg: self.bridge.emit_event(Status(msg)))
        self.hotkeys.start(self.settings.hotkeys)

        self.transcriber_ready.connect(self._on_transcriber_ready)
        self.transcriber_failed.connect(self._on_transcriber_failed)
        self.load_transcriber()

    # ---- hotkeys --------------------------------------------------------

    def on_hotkey(self, action: str) -> None:
        if action == "toggle_view":
            self.toggle_view()
        elif action == "toggle_overlay":
            self.toggle_overlay()
        elif action == "toggle_window":
            self.toggle_window()
        elif action == "click_through":
            self.overlay.set_click_through(not self.overlay.click_through)
            self.settings.click_through = self.overlay.click_through
            save_settings(self.settings, self.settings_path)
            state = "on" if self.overlay.click_through else "off"
            self.bridge.emit_event(Status(f"Click-through {state}"))
        elif action == "dismiss":
            self.window.view.dismiss()
            self.overlay.view.dismiss()
        elif action == "toggle_auto":
            self.set_auto(not self.settings.auto_enabled)
            self.bridge.emit_event(Status(f"Auto hints {'on' if self.settings.auto_enabled else 'off'}"))
        elif not self.session:
            self.bridge.emit_event(Status("Start a session first."))
        elif action == "ask":
            self.session.engine.ask_now()
        elif action == "screenshot":
            self.region.start()

    def _on_screenshot(self, png: bytes) -> None:
        if self.session:
            self.session.engine.ask_with_image(png)

    # ---- speech model ---------------------------------------------------

    def load_transcriber(self) -> None:
        """(Re)load the speech model for the current provider in the background."""
        config = stt_config(self.settings)
        if self._loading or config == self.transcriber_config:
            return
        self._loading = True
        self.transcriber = None
        self.tray.setToolTip(f"Shade — loading speech model ({config[0]})…")

        def work():
            try:
                self.transcriber_ready.emit((config, Transcriber(*config)))
            except Exception as e:
                self.transcriber_failed.emit(str(e))

        threading.Thread(target=work, daemon=True).start()

    def _on_transcriber_ready(self, result) -> None:
        self._loading = False
        self.transcriber_config, self.transcriber = result
        self.tray.setToolTip("Shade — ready")
        self.load_transcriber()  # settings may have changed while loading

    def _on_transcriber_failed(self, message: str) -> None:
        self._loading = False
        self.tray.setToolTip("Shade — speech model failed")
        self.notify(f"Speech model failed to load: {message}")

    # ---- menu -------------------------------------------------------------

    def _build_menu(self) -> None:
        menu = QMenu()
        self.start_menu = menu.addMenu("Start session")
        self.start_menu.aboutToShow.connect(self._fill_profiles)
        self.stop_action = menu.addAction("Stop session", self.stop_session)
        self.stop_action.setEnabled(False)
        menu.addSeparator()
        self.auto_action = menu.addAction("Auto hints")
        self.auto_action.setCheckable(True)
        self.auto_action.setChecked(self.settings.auto_enabled)
        self.auto_action.toggled.connect(self.set_auto)
        view_menu = menu.addMenu("View")
        group = QActionGroup(view_menu)
        self.view_actions = {}
        for mode, label in (("window", "Window"), ("overlay", "Overlay")):
            a = QAction(label, view_menu, checkable=True)
            a.setChecked(self.settings.display_mode == mode)
            a.triggered.connect(lambda checked, m=mode: self.set_display_mode(m))
            group.addAction(a)
            view_menu.addAction(a)
            self.view_actions[mode] = a
        menu.addAction("Show", self.show_current_view)
        menu.addAction("Settings…", self.open_settings)
        menu.addAction("Open sessions folder", self.open_sessions_folder)
        menu.addAction("About…", lambda: show_about(make_icon().pixmap(64, 64)))
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self.menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_current_view()

    def _fill_profiles(self) -> None:
        self.start_menu.clear()
        profiles = sorted(Path(self.settings.profiles_dir).glob("*.md"))
        for p in profiles:
            self.start_menu.addAction(p.stem, lambda p=p: self.start_session(p))
        if profiles:
            self.start_menu.addSeparator()
        self.start_menu.addAction("Browse…", self._browse_profile)

    def _browse_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            None, "Choose a call profile", self.settings.profiles_dir, "Markdown (*.md)"
        )
        if path:
            self.start_session(Path(path))

    # ---- actions ----------------------------------------------------------

    def notify(self, message: str) -> None:
        self.tray.showMessage("Shade", message, QSystemTrayIcon.MessageIcon.Information, 4000)

    def start_session(self, profile: Path) -> None:
        if self.session:
            self.stop_session()
        if self.transcriber is None or self.transcriber_config != stt_config(self.settings):
            self.load_transcriber()
            self.notify("Speech model is still loading — try again in a moment.")
            return
        self.session = Session(self.settings, self.transcriber, profile, self.bridge)
        self.stop_action.setEnabled(True)
        self._vram_warned = False
        self.vram_timer.start()
        self.tray.setToolTip(f"Shade — session: {profile.stem}")
        self.show_current_view()
        self.bridge.emit_event(Status(f"Session started: {profile.stem}"))
        if self.settings.auto_enabled and not auto_allowed(self.settings):
            self.bridge.emit_event(Status(AUTO_BLOCKED))
        if self.session.provider_problem:
            self.bridge.emit_event(HintError(0, self.session.provider_problem))
            self.notify(self.session.provider_problem)

    def stop_session(self) -> None:
        if not self.session:
            return
        self.vram_timer.stop()
        self.session.stop()
        self.session = None
        self.stop_action.setEnabled(False)
        self.tray.setToolTip("Shade — ready")
        self.bridge.emit_event(Status("Session stopped."))

    def set_auto(self, on: bool) -> None:
        self.settings.auto_enabled = on
        save_settings(self.settings, self.settings_path)
        if self.session:
            self.session.engine.set_auto(on and auto_allowed(self.settings))
        if on and not auto_allowed(self.settings):
            self.bridge.emit_event(Status(AUTO_BLOCKED))
        if self.auto_action.isChecked() != on:
            self.auto_action.setChecked(on)

    def current_view_widget(self):
        return self.overlay if self.settings.display_mode == "overlay" else self.window

    def show_current_view(self) -> None:
        other = self.window if self.settings.display_mode == "overlay" else self.overlay
        other.hide()
        w = self.current_view_widget()
        if w is self.window:
            self.window.bring_to_front()
        else:
            w.show()
            w.raise_()
        if not w.capture_ok:
            self.bridge.emit_event(Status(CAPTURE_WARNING))

    def set_display_mode(self, mode: str) -> None:
        self.settings.display_mode = mode
        save_settings(self.settings, self.settings_path)
        self.view_actions[mode].setChecked(True)
        self.show_current_view()

    def toggle_window(self) -> None:
        """Show or hide the hint window without touching the display mode setting."""
        if self.window.isVisible():
            self.window.hide()
        else:
            self.window.bring_to_front()

    def toggle_overlay(self) -> None:
        """Show or hide the overlay without touching the window mode setting."""
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.overlay.show()
            self.overlay.raise_()
            if not self.overlay.capture_ok:
                self.bridge.emit_event(Status(CAPTURE_WARNING))

    def toggle_view(self) -> None:
        self.set_display_mode("window" if self.settings.display_mode == "overlay" else "overlay")

    def _check_vram(self) -> None:
        if not self._vram_warned and gpu.vram_nearly_full(gpu.vram()):
            self._vram_warned = True
            self.bridge.emit_event(Status(VRAM_WARNING))

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, list_devices())
        dialog.applied.connect(self.apply_settings)
        if dialog.exec():
            self.apply_settings(dialog.result_settings())

    def apply_settings(self, new: Settings) -> None:
        old = self.settings
        if new == old:
            return
        self.settings = new
        save_settings(new, self.settings_path)
        # Display and behavior apply now.
        self.window.apply_theme(new.window_theme)
        self.window.view.set_font_size(new.window_font_size)
        self.overlay.view.set_font_size(new.overlay_font_size)
        self.window.view.set_code_font_size(new.window_code_font_size)
        self.overlay.view.set_code_font_size(new.overlay_code_font_size)
        self.overlay.apply_style(new.overlay_bg_color, new.overlay_text_color, new.overlay_opacity)
        if new.click_through != self.overlay.click_through:
            self.overlay.set_click_through(new.click_through)
        self.set_auto(new.auto_enabled)
        if new.hotkeys != old.hotkeys:
            self.hotkeys.start(new.hotkeys)
        if new.display_mode != old.display_mode:
            self.set_display_mode(new.display_mode)
        # Provider, models and audio apply to the next session.
        session_keys = (
            "provider", "claude_model", "claude_effort", "claude_detector_model", "presets",
            "mic_device", "mic_gain", "loopback_device", "vad_silence_ms", "context_seconds", "prices",
            "stt_model",
        )
        if self.session and any(getattr(old, k) != getattr(new, k) for k in session_keys):
            self.bridge.emit_event(Status(NEXT_SESSION))
        if not self.session:
            self.load_transcriber()

    def open_sessions_folder(self) -> None:
        folder = Path(self.settings.sessions_dir)
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder.resolve())  # noqa: S606 (Windows only)

    def quit(self) -> None:
        self.hotkeys.stop()
        self.stop_session()
        self.tray.hide()
        self.qapp.quit()

    def run(self) -> int:
        return self.qapp.exec()
