from shade.models import HintDelta, HintDone, HintStarted, Usage
from shade.ui.hint_view import HintView


def _answer(v, hid, q, a, done=True):
    v.handle(HintStarted(hid, "auto", q))
    v.handle(HintDelta(hid, a))
    if done:
        v.handle(HintDone(hid, "m", Usage(1, 1), 0.0, 0.0))


def _shown(v):
    return v._current.toPlainText()


def test_new_question_keeps_earlier_answers_on_screen(qtbot):
    v = HintView()
    qtbot.addWidget(v)
    _answer(v, 1, "How would you cache it?", "Use Redis with a TTL.")
    _answer(v, 2, "And what about writes?", "Write-through for hot keys.")
    text = _shown(v)
    assert "How would you cache it?" in text and "Use Redis with a TTL." in text
    assert "And what about writes?" in text and "Write-through for hot keys." in text
    assert text.index("Use Redis") < text.index("Write-through")  # oldest first
    assert v.current_text() == "Write-through for hot keys."


def test_replaced_answer_stays_too(qtbot):
    v = HintView()
    qtbot.addWidget(v)
    _answer(v, 1, "Q1", "Partial first", done=False)
    _answer(v, 2, "Q2", "Second")
    assert "Partial first" in _shown(v) and "Second" in _shown(v)


def test_dismiss_starts_a_new_topic(qtbot):
    v = HintView()
    qtbot.addWidget(v)
    _answer(v, 1, "Q1", "A1")
    _answer(v, 2, "Q2", "A2")
    v.dismiss()
    assert _shown(v).strip() == ""
    _answer(v, 3, "Q3", "A3")
    assert "A1" not in _shown(v) and "A3" in _shown(v)


LONG = "\n\n".join(f"Line {i} of a long answer." for i in range(80))


def test_scrolling_is_not_taken_over_while_the_answer_streams(qtbot):
    v = HintView()
    qtbot.addWidget(v)
    v.resize(400, 300)
    v.show()
    qtbot.waitExposed(v)
    v.handle(HintStarted(1, "hotkey", "Q"))
    v.handle(HintDelta(1, LONG))
    bar = v._current.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum() // 2)
    kept = bar.value()
    for i in range(5):
        v.handle(HintDelta(1, f"\n\nMore text {i}."))
    assert bar.value() == kept


def test_new_question_scrolls_to_its_start_once(qtbot):
    v = HintView()
    qtbot.addWidget(v)
    v.resize(400, 300)
    v.show()
    qtbot.waitExposed(v)
    _answer(v, 1, "First question", LONG)
    bar = v._current.verticalScrollBar()
    bar.setValue(0)
    v.handle(HintStarted(2, "hotkey", "Second question"))
    assert bar.value() > 0
    # The new question's header is at the top of the visible area.
    doc = v._current.document()
    block = doc.begin()
    header = None
    while block.isValid():
        if "Second question" in block.text():
            header = block
        block = block.next()
    top = doc.documentLayout().blockBoundingRect(header).top()
    assert abs(bar.value() - top) <= 2 or bar.value() == bar.maximum()
    # Then the user is free to scroll while it streams.
    bar.setValue(0)
    v.handle(HintDelta(2, "Streaming answer."))
    assert bar.value() == 0
