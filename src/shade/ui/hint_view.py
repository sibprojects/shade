"""Widget that shows the current hint, hint history and the live transcript."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
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
from shade.engine import QUICK_ACTIONS
from shade.transcript import format_lines
from shade.ui.syntax import SYNTAX, lexer_for, spans
from shade.ui.ui_state import ui_state

# Buttons in the window, between the answers and the transcript/history tabs.
ACTION_BUTTONS = [(name, label) for name, (label, _, _) in QUICK_ACTIONS.items()] + [("recap", "Recap")]

ERROR_MS = 8000
CODE_BG = QColor("#000000")
CODE_FG = QColor("#e8e8e8")
CODE_FONTS = ["Consolas", "Cascadia Mono", "Courier New"]
CODE_GAP = 8  # px above and below a code block
FEED_MAX = 20  # earlier answers kept on screen
HEADER_PREFIX = "Q:"  # starts each question line in the answer feed


def _is_code(block) -> bool:
    fmt = block.blockFormat()
    return fmt.hasProperty(QTextFormat.Property.BlockCodeFence) or fmt.nonBreakableLines()


def style_code_blocks(doc: QTextDocument, point_size: int) -> None:
    """Code blocks from Markdown: on black, own font size, wrapped to the width
    of the view instead of needing a horizontal scrollbar, and with syntax
    colors for the languages Shade knows (the language comes from the fence)."""
    runs: list[list] = []  # consecutive lines of one code block
    block = doc.begin()
    while block.isValid():
        if _is_code(block):
            language = block.blockFormat().stringProperty(QTextFormat.Property.BlockCodeLanguage)
            if runs and runs[-1][-1].next() == block and runs[-1][0].blockFormat().stringProperty(
                QTextFormat.Property.BlockCodeLanguage
            ) == language:
                runs[-1].append(block)
            else:
                runs.append([block])
        block = block.next()
    for run in runs:
        for b in run:
            fmt = b.blockFormat()
            fmt.setNonBreakableLines(False)
            fmt.setBackground(CODE_BG)
            # Space between code blocks that follow each other directly.
            fmt.setTopMargin(CODE_GAP if b == run[0] else 0)
            fmt.setBottomMargin(CODE_GAP if b == run[-1] else 0)
            cursor = QTextCursor(b)
            cursor.setBlockFormat(fmt)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            char = cursor.charFormat()
            char.setForeground(CODE_FG)
            char.setFontPointSize(point_size)
            char.setFontFixedPitch(True)
            char.setFontFamilies(CODE_FONTS)
            cursor.mergeCharFormat(char)
            cursor.setBlockCharFormat(char)
        _highlight(doc, run)


def _highlight(doc: QTextDocument, run: list) -> None:
    language = run[0].blockFormat().stringProperty(QTextFormat.Property.BlockCodeLanguage)
    lexer = lexer_for(language)
    if lexer is None:
        return
    # Offsets in the joined code -> document positions, line by line.
    starts, doc_starts, offset = [], [], 0
    for b in run:
        starts.append(offset)
        doc_starts.append(b.position())
        offset += len(b.text()) + 1
    code = "\n".join(b.text() for b in run)
    cursor = QTextCursor(doc)
    line = 0
    for start, end, role in spans(code, lexer):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(SYNTAX[role]))
        if role == "comment":
            fmt.setFontItalic(True)
        while line + 1 < len(starts) and starts[line + 1] <= start:
            line += 1
        # A token may span lines (multi-line strings): color it piece by piece.
        i, s = line, start
        while s < end and i < len(starts):
            line_end = starts[i] + len(run[i].text())
            e = min(end, line_end)
            if e > s:
                cursor.setPosition(doc_starts[i] + s - starts[i])
                cursor.setPosition(doc_starts[i] + e - starts[i], QTextCursor.MoveMode.KeepAnchor)
                cursor.mergeCharFormat(fmt)
            i += 1
            if i < len(starts):
                s = max(s, starts[i])


def _entry_markdown(question: str, answer: str) -> str:
    q = question.strip() or "(screenshot)"
    return f"**{HEADER_PREFIX}** {q}\n\n{answer}"


class HintView(QWidget):
    action_requested = Signal(str)  # quick action or "recap", from the buttons

    def __init__(
        self,
        transcript_lines: int | None = None,
        show_history: bool = True,
        font_size: int = 14,
        compact: bool = False,
        code_font_size: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._current_id: int | None = None
        self._current_parts: list[str] = []
        self._current_question = ""
        self._current_trigger = ""
        # Earlier answers of this topic stay on screen above the current one.
        self._feed: list[tuple[str, str]] = []
        # While an answer streams, the view follows its last line, unless the
        # user scrolls up to read; scrolling back to the bottom follows again.
        self._follow = True
        self._rendering = False
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
        self._current.verticalScrollBar().valueChanged.connect(self._on_user_scroll)

        self._history_view = QTextBrowser()

        self._transcript = QPlainTextEdit()
        self._transcript.setReadOnly(True)
        if transcript_lines:
            self._transcript.setMaximumBlockCount(transcript_lines)

        self._compact = compact
        self._code_pt = code_font_size or max(7, font_size - 2)
        self._current.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)
        self._transcript_lines = transcript_lines or 3
        self.set_font_size(font_size)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._error)  # alerts stay on top, next to the hint

        self.tabs: QTabWidget | None = None
        self.action_bar: QWidget | None = None
        self.action_buttons: list[QPushButton] = []
        if compact:
            layout.setSpacing(2)  # overlay: blocks close together
            # Overlay: the hint takes most of the space; a strip of the last
            # transcript lines below it (drag the border to resize); no history.
            self._transcript.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._transcript.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.split = QSplitter(Qt.Orientation.Vertical)
            self.split.setHandleWidth(2)
            self.split.setChildrenCollapsible(False)
            self.split.addWidget(self._current)
            self.split.addWidget(self._transcript)
            self.split.setStretchFactor(0, 1)
            self.split.setStretchFactor(1, 0)
            self._fit_transcript_strip()
            self.split.setSizes([1000, self._strip_height()])
            layout.addWidget(self.split, 1)
            layout.addWidget(self._status)  # trigger · model · cost, at the bottom
        else:
            # Window: current hint on top; transcript and history as tabs below.
            self.tabs = QTabWidget()
            self.tabs.addTab(self._transcript, "Transcript")
            if show_history:
                self.tabs.addTab(self._history_view, "History")
            # Quick action buttons, centered right above the tabs.
            self.action_bar = QWidget()
            row = QHBoxLayout(self.action_bar)
            row.setContentsMargins(0, 4, 0, 4)
            row.addStretch(1)
            for name, label in ACTION_BUTTONS:
                button = QPushButton(label)
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.clicked.connect(lambda checked=False, n=name: self.action_requested.emit(n))
                row.addWidget(button)
                self.action_buttons.append(button)
            row.addStretch(1)
            lower = QWidget()
            lower_layout = QVBoxLayout(lower)
            lower_layout.setContentsMargins(0, 0, 0, 0)
            lower_layout.setSpacing(0)
            lower_layout.addWidget(self.action_bar)
            lower_layout.addWidget(self.tabs, 1)
            self.split = QSplitter(Qt.Orientation.Vertical)
            self.split.addWidget(self._current)
            self.split.addWidget(lower)
            self.split.setStretchFactor(0, 3)
            self.split.setStretchFactor(1, 2)
            layout.addWidget(self.split, 1)
            layout.addWidget(self._status)  # trigger · model · cost, at the bottom

    # ---- fonts ---------------------------------------------------------

    def set_font_size(self, pt: int) -> None:
        """Hint text at `pt`; transcript and history 4 pt smaller."""
        f = QFont(self._current.font())
        f.setPointSize(pt)
        self._current.setFont(f)
        small = QFont(self._transcript.font())
        small.setPointSize(max(8, pt - 4))
        self._transcript.setFont(small)
        self._history_view.setFont(small)
        if getattr(self, "_compact", False):
            self._fit_transcript_strip()

    def set_code_font_size(self, pt: int) -> None:
        self._code_pt = pt
        self._render_current()
        self._render_history()

    def _strip_height(self, lines: int | None = None) -> int:
        return (lines or self._transcript_lines) * self._transcript.fontMetrics().lineSpacing() + 14

    def _fit_transcript_strip(self) -> None:
        # At least one transcript line stays visible; the border above it can be dragged.
        self._transcript.setMinimumHeight(self._strip_height(1))

    def remember_split(self, key: str) -> None:
        """Restore the hint/transcript border from `key` and save it whenever it moves."""
        saved = ui_state().value(key)
        if saved is not None:
            self.split.restoreState(saved)
        self.split.splitterMoved.connect(lambda *_: ui_state().setValue(key, self.split.saveState()))

    # ---- event handling ----------------------------------------------

    def handle(self, e: Event) -> None:
        if isinstance(e, UtteranceAdded):
            self._transcript.appendPlainText(format_lines([e.u]))
            bar = self._transcript.verticalScrollBar()
            bar.setValue(bar.maximum())
        elif isinstance(e, HintStarted):
            if self._current_id is not None and (self._current_question or self._current_parts):
                self._feed.append((self._current_question, self.current_text()))
                del self._feed[:-FEED_MAX]
            self._current_id = e.id
            self._current_parts = []
            self._current_question = e.question
            self._current_trigger = e.trigger
            self._follow = True
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
                self._render_history()
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
        """New topic: clear the answers on screen."""
        self._current_id = None
        self._current_parts = []
        self._current_question = ""
        self._feed = []
        self._render_current()

    # ---- rendering -----------------------------------------------------

    def _render_current(self) -> None:
        entries = list(self._feed)
        if self._current_id is not None:
            entries.append((self._current_question, self.current_text()))
        markdown = "\n\n---\n\n".join(_entry_markdown(q, a) for q, a in entries)
        bar = self._current.verticalScrollBar()
        kept = bar.value()
        self._rendering = True  # scroll changes from here on are ours, not the user's
        try:
            self._current.setMarkdown(markdown)
            style_code_blocks(self._current.document(), self._code_pt)
            # Follow the newest line; otherwise stay where the user scrolled
            # (re-rendering would reset the view to the top).
            bar.setValue(bar.maximum() if self._follow else kept)
        finally:
            self._rendering = False

    def _on_user_scroll(self, value: int) -> None:
        if not self._rendering:
            bar = self._current.verticalScrollBar()
            self._follow = value >= bar.maximum() - 2

    def _render_history(self) -> None:
        self._history_view.setMarkdown("\n\n---\n\n".join(self._history))
        # History text is 4 pt smaller than the hint; its code follows suit.
        style_code_blocks(self._history_view.document(), max(7, self._code_pt - 4))

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
