"""Tray application: owns the windows and runs sessions."""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QSystemTrayIcon

from shade.audio.capture import LoopbackSource, MicSource
from shade.audio.segmenter import Segmenter
from shade.audio.vad import SileroVad
from shade.config import DEFAULT_SETTINGS_PATH, Settings, load_settings, save_settings
from shade.cost import CostMeter
from shade.detect import Detector
from shade.engine import Engine
from shade.llm.base import ProviderError
from shade.llm.factory import make_provider
from shade.models import Status
from shade.session import SessionWriter
from shade.stt import SttWorker, Transcriber
from shade.transcript import Transcript
from shade.ui.bridge import QtBridge
from shade.ui.main_window import MainWindow
from shade.ui.overlay import Overlay

CAPTURE_WARNING = "Warning: window may be visible in screen sharing."


def make_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#3b3f8f"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, 60, 60)
    p.setPen(QColor("white"))
    f = QFont()
    f.setPixelSize(38)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "S")
    p.end()
    return QIcon(pix)


class Session:
    """Everything that lives for the duration of one call."""

    def __init__(self, settings: Settings, transcriber, profile: Path, bridge: QtBridge) -> None:
        provider = make_provider(settings)  # may raise ProviderError
        start = time.monotonic()
        clock = lambda: time.monotonic() - start  # noqa: E731
        self.writer = SessionWriter(Path(settings.sessions_dir), profile.stem, datetime.now())
        self.engine = Engine(
            provider=provider,
            detector=Detector(provider),
            transcript=Transcript(),
            writer=self.writer,
            cost=CostMeter(settings.prices),
            profile_text=profile.read_text(encoding="utf-8", errors="replace"),
            context_seconds=settings.context_seconds,
            on_event=bridge.emit_event,
            clock=clock,
        )
        self.engine.set_auto(settings.auto_enabled)
        status = lambda msg: bridge.emit_event(Status(msg))  # noqa: E731
        self.stt = SttWorker(transcriber, self.engine.on_utterance, on_error=status)
        self.sources = []
        for name, cls, device in (
            ("me", MicSource, settings.mic_device),
            ("them", LoopbackSource, settings.loopback_device),
        ):
            seg = Segmenter(name, SileroVad(), self.stt.submit, silence_ms=settings.vad_silence_ms)
            src = cls(device, on_error=status, clock=clock)
            src.start(seg.feed)
            self.sources.append(src)

    def stop(self) -> None:
        for s in self.sources:
            s.stop()
        self.stt.stop()
        self.engine.stop()
        self.writer.close()


class ShadeApp(QObject):
    transcriber_ready = Signal(object)
    transcriber_failed = Signal(str)

    def __init__(self, settings_path: Path = DEFAULT_SETTINGS_PATH) -> None:
        self.qapp = QApplication.instance() or QApplication(sys.argv)
        super().__init__()
        self.qapp.setQuitOnLastWindowClosed(False)
        self.settings_path = settings_path
        self.settings = load_settings(settings_path)
        self.bridge = QtBridge()
        self.session: Session | None = None
        self.transcriber = None

        self.window = MainWindow()
        self.overlay = Overlay(self.settings.overlay_opacity, self.settings.click_through)
        for view in (self.window.view, self.overlay.view):
            self.bridge.event.connect(view.handle)

        self.tray = QSystemTrayIcon(make_icon())
        self.tray.setToolTip("Shade — loading speech model…")
        self._build_menu()
        self.tray.show()

        self.transcriber_ready.connect(self._on_transcriber_ready)
        self.transcriber_failed.connect(self._on_transcriber_failed)
        threading.Thread(target=self._load_transcriber, daemon=True).start()

    # ---- speech model ---------------------------------------------------

    def stt_config(self) -> tuple[str, str]:
        return self.settings.stt_model, self.settings.stt_compute

    def _load_transcriber(self) -> None:
        try:
            model, compute = self.stt_config()
            self.transcriber_ready.emit(Transcriber(model, compute))
        except Exception as e:
            self.transcriber_failed.emit(str(e))

    def _on_transcriber_ready(self, transcriber) -> None:
        self.transcriber = transcriber
        self.tray.setToolTip("Shade — ready")

    def _on_transcriber_failed(self, message: str) -> None:
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
        menu.addAction("Open sessions folder", self.open_sessions_folder)
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self.menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.show_current_view()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )

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
        if self.transcriber is None:
            self.notify("Speech model is still loading — try again in a moment.")
            return
        try:
            self.session = Session(self.settings, self.transcriber, profile, self.bridge)
        except ProviderError as e:
            self.notify(str(e))
            return
        self.stop_action.setEnabled(True)
        self.tray.setToolTip(f"Shade — session: {profile.stem}")
        self.show_current_view()
        self.bridge.emit_event(Status(f"Session started: {profile.stem}"))

    def stop_session(self) -> None:
        if not self.session:
            return
        self.session.stop()
        self.session = None
        self.stop_action.setEnabled(False)
        self.tray.setToolTip("Shade — ready")
        self.bridge.emit_event(Status("Session stopped."))

    def set_auto(self, on: bool) -> None:
        self.settings.auto_enabled = on
        save_settings(self.settings, self.settings_path)
        if self.session:
            self.session.engine.set_auto(on)
        if self.auto_action.isChecked() != on:
            self.auto_action.setChecked(on)

    def current_view_widget(self):
        return self.overlay if self.settings.display_mode == "overlay" else self.window

    def show_current_view(self) -> None:
        other = self.window if self.settings.display_mode == "overlay" else self.overlay
        other.hide()
        w = self.current_view_widget()
        w.show()
        w.raise_()
        if not w.capture_ok:
            self.bridge.emit_event(Status(CAPTURE_WARNING))

    def set_display_mode(self, mode: str) -> None:
        self.settings.display_mode = mode
        save_settings(self.settings, self.settings_path)
        self.view_actions[mode].setChecked(True)
        self.show_current_view()

    def toggle_view(self) -> None:
        self.set_display_mode("window" if self.settings.display_mode == "overlay" else "overlay")

    def open_sessions_folder(self) -> None:
        folder = Path(self.settings.sessions_dir)
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder.resolve())  # noqa: S606 (Windows only)

    def quit(self) -> None:
        self.stop_session()
        self.tray.hide()
        self.qapp.quit()

    def run(self) -> int:
        return self.qapp.exec()
