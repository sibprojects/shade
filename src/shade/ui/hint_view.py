"""Widget that shows the current hint, hint history and the live transcript."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QFont, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
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
from shade.transcript import joins, line_start
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
OVERLAY_TRANSCRIPT_LINES = 200
SPLIT_GRAB = 5  # px around the overlay's 1 px hint/transcript border that grab it
NOTE_MAX_LINES = 5  # the note box grows up to this many lines, then scrolls
COPIED_MS = 1500  # how long the Copy button says "Copied"
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


class NoteEdit(QPlainTextEdit):
    """Box to type a note to the AI: Enter asks now, Ctrl+Enter only adds it,
    Shift+Enter starts a new line. One line high; grows with the text up to
    NOTE_MAX_LINES, then scrolls."""

    submitted = Signal(str, bool)  # text, ask now

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("note")
        self.setPlaceholderText(
            "Note to AI — Enter: ask now · Ctrl+Enter: just add to the context · Shift+Enter: new line"
        )
        self.setTabChangesFocus(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.document().setDocumentMargin(2)
        self.textChanged.connect(self._fit_height)
        self._fit_height()

    def text(self) -> str:
        return self.toPlainText()

    def _fit_height(self, *_) -> None:
        # A plain-text document's height is its number of laid-out lines
        # (wrapped lines included); blocks not laid out yet count as one.
        doc = self.document()
        lines = max(1, round(doc.size().height()), doc.blockCount())
        shown = min(lines, NOTE_MAX_LINES)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if lines > NOTE_MAX_LINES else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        # Border and padding from the stylesheet: what the frame adds around the text area.
        m = self.contentsMargins()
        height = shown * self.fontMetrics().lineSpacing() + 2 * doc.documentMargin() + m.top() + m.bottom()
        self.setFixedHeight(round(height))

    def changeEvent(self, e):  # noqa: N802
        super().changeEvent(e)
        if e.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._fit_height()

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self._fit_height()

    def keyPressEvent(self, e):  # noqa: N802
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.insertPlainText("\n")  # soft Enter: a new line in the note
                return
            text = self.text().strip()
            if text:
                ask = not (e.modifiers() & Qt.KeyboardModifier.ControlModifier)
                self.clear()
                self.submitted.emit(text, ask)
            return
        super().keyPressEvent(e)


class HintView(QWidget):
    action_requested = Signal(str)  # quick action or "recap", from the buttons
    note_submitted = Signal(str, bool)  # typed note, ask now

    def __init__(
        self,
        transcript_lines: int | None = None,
        show_history: bool = True,
        font_size: int = 14,
        compact: bool = False,
        code_font_size: int | None = None,
        transcript_font_size: int | None = None,
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
        self._last_answer = ""  # last finished answer, kept after a new topic
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
        self.note = NoteEdit()
        self.note.submitted.connect(self.note_submitted)
        # Copy: the last answer to the clipboard. Window: first in the button
        # row; overlay (no button row): left of the note box.
        self.copy_button = QPushButton("Copy")
        self.copy_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.copy_button.setToolTip("Copy the last answer")
        self.copy_button.clicked.connect(self.copy_answer)
        self._copied_timer = QTimer(self)
        self._copied_timer.setSingleShot(True)
        self._copied_timer.timeout.connect(lambda: self.copy_button.setText("Copy"))

        self._transcript = QPlainTextEdit()
        self._transcript.setReadOnly(True)
        self._last_source: str | None = None  # speaker of the last transcript line
        if transcript_lines:
            # The overlay strip can be dragged taller, so it keeps a good amount of history.
            self._transcript.setMaximumBlockCount(OVERLAY_TRANSCRIPT_LINES)

        self._compact = compact
        self._code_pt = code_font_size or max(7, font_size - 2)
        self._current.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)
        self._transcript_lines = transcript_lines or 3
        self._font_pt = font_size
        self._small_pt = transcript_font_size or max(7, font_size - 4)
        self.set_font_size(font_size)
        self.set_transcript_font_size(self._small_pt)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._error)  # alerts stay on top, next to the hint

        self.tabs: QTabWidget | None = None
        self._split_key: str | None = None
        self._split_dragging = False
        self._vp_cursors: dict = {}
        self.action_bar: QWidget | None = None
        self.action_buttons: list[QPushButton] = []
        if compact:
            layout.setSpacing(2)  # overlay: blocks close together
            # Overlay: the hint takes most of the space; a strip of the last
            # transcript lines below it (drag the border to resize); no history.
            self._transcript.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._transcript.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.split = QSplitter(Qt.Orientation.Vertical)
            self.split.setHandleWidth(1)  # thin; it can be grabbed SPLIT_GRAB px around it
            self.split.setChildrenCollapsible(False)
            for vp in (self._current.viewport(), self._transcript.viewport()):
                vp.setMouseTracking(True)
                vp.installEventFilter(self)
                self._vp_cursors[vp] = vp.cursor()
            self.split.addWidget(self._current)
            self.split.addWidget(self._transcript)
            self.split.setStretchFactor(0, 1)
            self.split.setStretchFactor(1, 0)
            self._fit_transcript_strip()
            self.split.setSizes([1000, self._strip_height()])
            layout.addWidget(self.split, 1)
            note_row = QHBoxLayout()
            note_row.setSpacing(4)
            note_row.addWidget(self.copy_button)
            note_row.addWidget(self.note, 1)
            layout.addLayout(note_row)
            layout.addWidget(self._status)  # trigger · model · cost, at the bottom
        else:
            # Window: current hint on top; transcript and history as tabs below.
            self.tabs = QTabWidget()
            self.tabs.addTab(self._transcript, "Transcript")
            if show_history:
                self.tabs.addTab(self._history_view, "History")
            # Copy and the quick action buttons, centered right above the tabs.
            self.action_bar = QWidget()
            row = QHBoxLayout(self.action_bar)
            row.setContentsMargins(0, 4, 0, 4)
            row.addStretch(1)
            row.addWidget(self.copy_button)
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
            lower_layout.addSpacing(4)
            lower_layout.addWidget(self.note)
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
        """Hint text at `pt` (the transcript and history have their own size)."""
        self._font_pt = pt
        f = QFont(self._current.font())
        f.setPointSize(pt)
        self._current.setFont(f)
        self._render_history()  # history code keeps its distance from the text

    def set_transcript_font_size(self, pt: int) -> None:
        """Transcript and history text at `pt`."""
        self._small_pt = pt
        small = QFont(self._transcript.font())
        small.setPointSize(pt)
        self._transcript.setFont(small)
        self._history_view.setFont(small)
        self._render_history()
        if self._compact:
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
        self._split_key = key
        saved = ui_state().value(key)
        if saved is not None:
            self.split.restoreState(saved)
        self.split.splitterMoved.connect(self._save_split)

    def _save_split(self, *_) -> None:
        if self._split_key:
            ui_state().setValue(self._split_key, self.split.saveState())

    # ---- overlay border: grabbed a few pixels around it ---------------------

    def _near_border(self, y_in_split: int) -> bool:
        return abs(y_in_split - self._transcript.geometry().top()) <= SPLIT_GRAB

    def eventFilter(self, obj, e):  # noqa: N802
        if obj not in self._vp_cursors:
            return super().eventFilter(obj, e)
        kind = e.type()
        if kind not in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            return super().eventFilter(obj, e)
        y = obj.mapTo(self.split, e.position().toPoint()).y()
        if self._split_dragging:
            if kind == QEvent.Type.MouseMove:
                sizes = self.split.sizes()
                total = sum(sizes)
                low = self._strip_height(1)
                top = max(low, min(y, total - low))
                self.split.setSizes([top, total - top])
            elif kind == QEvent.Type.MouseButtonRelease:
                self._split_dragging = False
                self._save_split()
            return True
        near = self._near_border(y)
        if kind == QEvent.Type.MouseMove:
            obj.setCursor(Qt.CursorShape.SplitVCursor if near else self._vp_cursors[obj])
        elif (
            kind == QEvent.Type.MouseButtonPress
            and near
            and e.button() == Qt.MouseButton.LeftButton
            and not e.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self._split_dragging = True
            return True
        return super().eventFilter(obj, e)

    # ---- event handling ----------------------------------------------

    def handle(self, e: Event) -> None:
        if isinstance(e, UtteranceAdded):
            if joins(self._last_source, e.u):
                # Same speaker: the phrase continues their line, like live captions.
                cursor = self._transcript.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertText(" " + e.u.text)
            else:
                self._transcript.appendPlainText(line_start(e.u))
            self._last_source = e.u.source
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
                if self.current_text():
                    self._last_answer = self.current_text()
                self._render_history()
            self._update_status()
        elif isinstance(e, HintError):
            self.show_error(e.message)
        elif isinstance(e, Status):
            self._status.setText(e.message)

    def copy_answer(self) -> None:
        """The answer on screen (even while it streams), else the last finished one."""
        text = self.current_text() or self._last_answer
        if not text:
            self._status.setText("No answer yet.")
            return
        QGuiApplication.clipboard().setText(text)
        self.copy_button.setText("Copied")
        self._copied_timer.start(COPIED_MS)

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
        # History code is as much smaller than the history text as the hint's
        # code is than the hint text.
        style_code_blocks(self._history_view.document(), max(7, self._code_pt + self._small_pt - self._font_pt))

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
