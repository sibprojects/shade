"""Copy button, left of the note box in the window and the overlay: last answer to the clipboard."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from shade.models import HintDelta, HintDone, HintStarted, Usage
from shade.ui.hint_view import HintView


def answer(v, id_, text):
    v.handle(HintStarted(id_, "auto", "q?"))
    v.handle(HintDelta(id_, text))
    v.handle(HintDone(id_, "m", Usage(1, 1), 0.0, 0.0))


def views(qtbot):
    for compact in (False, True):
        v = HintView(compact=compact, transcript_lines=3 if compact else None)
        qtbot.addWidget(v)
        yield v


def test_copies_the_last_answer(qtbot):
    for v in views(qtbot):
        QApplication.clipboard().setText("old")
        answer(v, 1, "First **answer**")
        answer(v, 2, "Second answer\n\n```go\nfmt.Println(1)\n```")
        qtbot.mouseClick(v.copy_button, Qt.MouseButton.LeftButton)
        assert QApplication.clipboard().text() == "Second answer\n\n```go\nfmt.Println(1)\n```"


def test_copies_the_answer_while_it_streams(qtbot):
    for v in views(qtbot):
        v.handle(HintStarted(1, "auto", "q?"))
        v.handle(HintDelta(1, "So far"))
        qtbot.mouseClick(v.copy_button, Qt.MouseButton.LeftButton)
        assert QApplication.clipboard().text() == "So far"


def test_copies_the_last_answer_after_a_new_topic(qtbot):
    for v in views(qtbot):
        answer(v, 1, "Kept")
        v.dismiss()
        qtbot.mouseClick(v.copy_button, Qt.MouseButton.LeftButton)
        assert QApplication.clipboard().text() == "Kept"


def test_nothing_to_copy_keeps_the_clipboard(qtbot):
    for v in views(qtbot):
        QApplication.clipboard().setText("mine")
        qtbot.mouseClick(v.copy_button, Qt.MouseButton.LeftButton)
        assert QApplication.clipboard().text() == "mine"
        assert "No answer" in v.status_text()


def test_button_says_copied(qtbot):
    for v in views(qtbot):
        answer(v, 1, "x")
        qtbot.mouseClick(v.copy_button, Qt.MouseButton.LeftButton)
        assert v.copy_button.text() == "Copied"
        qtbot.waitUntil(lambda: v.copy_button.text() == "Copy", timeout=3000)


def test_button_sits_left_of_the_note(qtbot):
    for v in views(qtbot):
        v.resize(600, 700)
        v.show()
        qtbot.waitExposed(v)
        b = v.copy_button.mapTo(v, v.copy_button.rect().center())
        n = v.note.mapTo(v, v.note.rect().center())
        assert b.x() < n.x()
        assert abs(b.y() - n.y()) <= 4
        assert v.copy_button.focusPolicy() == Qt.FocusPolicy.NoFocus
