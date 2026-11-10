"""Widget that shows the current hint, hint history and the live transcript."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from shade.models import (
    Event,
    HintDelta,
    HintDone,
    HintError,
    HintStarted,
    Status,
    UtteranceAdded,
)
from shade.transcript import format_lines

ERROR_MS = 8000


class HintView(QWidget):
    def __init__(
        self,
        transcript_lines: int | None = None,
        show_history: bool = True,
        font_size: int = 14,
        compact: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._current_id: int | None = None
        self._current_parts: list[str] = []
        self._current_question = ""
        self._current_trigger = ""
        self._history: list[str] = []
        self._model = ""
        self._total_cost = 0.0

        self._status = QLabel("Ready")
        self._status.setObjectName("status")
        self._error = QLabel()
        self._error.setObjectName("error")
        self._error.setStyleSheet("color: #e5484d; font-weight: 600;")
        self._error.setWordWrap(True)
        self._error.hide()
        self._error_timer = QTimer(self)
        self._error_timer.setSingleShot(True)
        self._error_timer.timeout.connect(self._error.hide)

        self._current = QTextBrowser()
        self._current.setOpenExternalLinks(False)
        f = QFont()
        f.setPointSize(font_size)
        self._current.setFont(f)

        self._history_view = QTextBrowser()

        self._transcript = QPlainTextEdit()
        self._transcript.setReadOnly(True)
        if transcript_lines:
            self._transcript.setMaximumBlockCount(transcript_lines)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._status)
        layout.addWidget(self._error)

        self.tabs: QTabWidget | None = None
        if compact:
            # Overlay: the hint takes all the space; a fixed strip of the last
            # few transcript lines below it; no history.
            self._transcript.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._transcript.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            lines = transcript_lines or 3
            height = lines * self._transcript.fontMetrics().lineSpacing() + 14
            self._transcript.setFixedHeight(height)
            layout.addWidget(self._current, 1)
            layout.addWidget(self._transcript)
        else:
            # Window: current hint on top; transcript and history as tabs below.
            self.tabs = QTabWidget()
            self.tabs.addTab(self._transcript, "Transcript")
            if show_history:
                self.tabs.addTab(self._history_view, "History")
            split = QSplitter(Qt.Orientation.Vertical)
            split.addWidget(self._current)
            split.addWidget(self.tabs)
            split.setStretchFactor(0, 3)
            split.setStretchFactor(1, 2)
            layout.addWidget(split, 1)

    # ---- event handling ----------------------------------------------

    def handle(self, e: Event) -> None:
        if isinstance(e, UtteranceAdded):
            self._transcript.appendPlainText(format_lines([e.u]))
            bar = self._transcript.verticalScrollBar()
            bar.setValue(bar.maximum())
        elif isinstance(e, HintStarted):
            self._current_id = e.id
            self._current_parts = []
            self._current_question = e.question
            self._current_trigger = e.trigger
            self._render_current()
            self._update_status()
        elif isinstance(e, HintDelta):
            if e.id == self._current_id:
                self._current_parts.append(e.text)
                self._render_current()
        elif isinstance(e, HintDone):
            self._model = e.model
            self._total_cost = e.total_cost
            if e.id == self._current_id:
                q = self._current_question or "(screenshot)"
                self._history.insert(0, f"**Q:** {q}\n\n{self.current_text()}")
                self._history_view.setMarkdown("\n\n---\n\n".join(self._history))
            self._update_status()
        elif isinstance(e, HintError):
            self.show_error(e.message)
        elif isinstance(e, Status):
            self._status.setText(e.message)

    def show_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.show()
        self._error_timer.start(ERROR_MS)

    def dismiss(self) -> None:
        self._current_id = None
        self._current_parts = []
        self._current_question = ""
        self._render_current()

    # ---- rendering -----------------------------------------------------

    def _render_current(self) -> None:
        self._current.setMarkdown(self.current_text())

    def _update_status(self) -> None:
        bits = []
        if self._current_trigger:
            bits.append(self._current_trigger)
        if self._model:
            bits.append(self._model)
        bits.append(f"session ${self._total_cost:.4f}")
        self._status.setText(" · ".join(bits))

    # ---- accessors (also used by tests) --------------------------------

    def current_text(self) -> str:
        return "".join(self._current_parts)

    def history_count(self) -> int:
        return len(self._history)

    def status_text(self) -> str:
        return self._status.text()

    def error_text(self) -> str:
        return self._error.text()

    def transcript_text(self) -> str:
        return self._transcript.toPlainText()
