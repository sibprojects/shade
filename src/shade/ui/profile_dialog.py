"""Dialog: create a call profile from a CV and a job description."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from shade.llm.base import Provider, ProviderError
from shade.profile_builder import generate_profile, profile_path, read_document

DOC_FILTER = "Documents (*.txt *.md *.docx);;All files (*)"


class ProfileDialog(QDialog):
    delta = Signal(str)
    finished = Signal(str)
    failed = Signal(str)
    saved = Signal(object)  # Path of the new profile

    def __init__(
        self,
        provider_factory: Callable[[], Provider],
        folder: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create profile")
        self.provider_factory = provider_factory
        self.folder = Path(folder)
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. PHP backend - Acme")
        self.cv = QPlainTextEdit()
        self.cv.setPlaceholderText("Paste your CV here, or load a file")
        self.job = QPlainTextEdit()
        self.job.setPlaceholderText("Paste the job description (optional)")
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Optional: who is on the call, its format, what to focus on")
        self.result = QPlainTextEdit()
        self.result.setPlaceholderText("The profile appears here; you can edit it before saving.")
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.generate_button = QPushButton("Generate")
        self.generate_button.clicked.connect(self.generate)
        self.save_button = QPushButton("Save")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save_and_close)

        form = QFormLayout()
        form.addRow("Profile name", self.name)
        form.addRow(self._with_load("CV", self.cv), self.cv)
        form.addRow(self._with_load("Job", self.job), self.job)
        form.addRow("Call notes", self.notes)
        buttons = QHBoxLayout()
        buttons.addWidget(self.generate_button)
        buttons.addWidget(self.status, 1)
        buttons.addWidget(self.save_button)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.result, 1)
        layout.addLayout(buttons)
        self.resize(720, 820)

        self.delta.connect(self._on_delta)
        self.finished.connect(self._on_finished)
        self.failed.connect(self._on_failed)

    def _with_load(self, label: str, target: QPlainTextEdit) -> QWidget:
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.addWidget(QLabel(label))
        button = QPushButton("Load file…")
        button.clicked.connect(lambda: self._load_into(target))
        col.addWidget(button)
        col.addStretch(1)
        return box

    def _load_into(self, target: QPlainTextEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a file", "", DOC_FILTER)
        if path:
            try:
                target.setPlainText(read_document(Path(path)))
            except Exception as e:  # a broken or unsupported file
                self.status.setText(f"Cannot read the file: {e}")

    # ---- generation -----------------------------------------------------

    def generate(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        cv, job, notes = self.cv.toPlainText(), self.job.toPlainText(), self.notes.text()
        if not cv.strip():
            self.status.setText("Add your CV first.")
            return
        self._cancel = threading.Event()
        self.result.clear()
        self.save_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self.status.setText("Writing the profile…")
        cancel = self._cancel

        def work():
            provider = None
            try:
                provider = self.provider_factory()
                text = generate_profile(provider, cv, job, notes, cancel, on_delta=self.delta.emit)
                if not cancel.is_set():
                    self.finished.emit(text)
            except (ProviderError, ValueError) as e:
                self.failed.emit(str(e))
            except Exception as e:  # never die silently
                self.failed.emit(f"Profile generation failed: {e}")
            finally:
                close = getattr(provider, "close", None)
                if close is not None:
                    close()

        self._thread = threading.Thread(target=work, daemon=True, name="profile")
        self._thread.start()

    def _on_delta(self, text: str) -> None:
        self.result.insertPlainText(text)

    def _on_finished(self, text: str) -> None:
        self.result.setPlainText(text)
        self.generate_button.setEnabled(True)
        self.save_button.setEnabled(bool(text.strip()))
        self.status.setText("Done. Check it, edit if needed, then Save.")
        if not self.name.text().strip():
            first = text.splitlines()[0] if text else ""
            self.name.setText(first.lstrip("# ").strip())

    def _on_failed(self, message: str) -> None:
        self.generate_button.setEnabled(True)
        self.status.setText(message)

    # ---- saving ----------------------------------------------------------

    def save(self) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        path = profile_path(self.folder, self.name.text().strip() or "profile")
        text = self.result.toPlainText().strip() + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
        self.saved.emit(path)
        return path

    def _save_and_close(self) -> None:
        path = self.save()
        self.status.setText(f"Saved: {path}")
        self.accept()

    def done(self, result: int) -> None:
        self._cancel.set()  # closing stops a generation still running
        super().done(result)
