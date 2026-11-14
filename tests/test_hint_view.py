from shade.models import HintDelta, HintDone, HintError, HintStarted, Usage, Utterance, UtteranceAdded
from shade.ui.hint_view import HintView


def test_deltas_accumulate_into_current_hint(qtbot):
    v = HintView()
    qtbot.addWidget(v)
    v.handle(HintStarted(1, "auto", "Why?"))
    v.handle(HintDelta(1, "Because "))
    v.handle(HintDelta(1, "it is fast."))
    assert v.current_text() == "Because it is fast."


def test_delta_of_old_hint_ignored(qtbot):
    v = HintView()
    qtbot.addWidget(v)
    v.handle(HintStarted(1, "auto", "Q1"))
    v.handle(HintStarted(2, "hotkey", "Q2"))
    v.handle(HintDelta(1, "stale"))
    v.handle(HintDelta(2, "fresh"))
    assert v.current_text() == "fresh"


def test_done_moves_hint_to_history_and_shows_cost(qtbot):
    v = HintView()
    qtbot.addWidget(v)
    v.handle(HintStarted(1, "auto", "Q1"))
    v.handle(HintDelta(1, "A1"))
    v.handle(HintDone(1, "m", Usage(1, 1), 0.001, 0.0123))
    assert v.history_count() == 1
    assert "$0.0123" in v.status_text()


def test_error_shown(qtbot):
    v = HintView()
    qtbot.addWidget(v)
    v.handle(HintError(1, "Claude: cannot connect."))
    assert "Claude: cannot connect." in v.error_text()


def test_dismiss_clears_current(qtbot):
    v = HintView()
    qtbot.addWidget(v)
    v.handle(HintStarted(1, "auto", "Q"))
    v.handle(HintDelta(1, "text"))
    v.dismiss()
    assert v.current_text() == ""


def test_overlay_transcript_keeps_the_last_lines(qtbot):
    from shade.ui.hint_view import OVERLAY_TRANSCRIPT_LINES

    v = HintView(transcript_lines=2, compact=True)
    qtbot.addWidget(v)
    n = OVERLAY_TRANSCRIPT_LINES + 5
    for i in range(n):  # speakers alternate, so each phrase is its own line
        v.handle(UtteranceAdded(Utterance("them" if i % 2 else "me", f"line {i}", i, i + 1)))
    lines = v.transcript_text().splitlines()
    assert len(lines) == OVERLAY_TRANSCRIPT_LINES
    assert lines[-1].endswith(f"line {n - 1}")


def test_window_mode_has_transcript_and_history_tabs(qtbot):
    v = HintView()
    qtbot.addWidget(v)
    assert [v.tabs.tabText(i) for i in range(v.tabs.count())] == ["Transcript", "History"]


def test_compact_mode_has_no_history_and_a_resizable_transcript_strip(qtbot):
    v = HintView(transcript_lines=3, compact=True)
    qtbot.addWidget(v)
    v.resize(400, 500)
    v.show()
    qtbot.waitExposed(v)
    assert v.tabs is None
    line = v._transcript.fontMetrics().lineSpacing()
    assert abs(v._transcript.height() - (3 * line + 14)) <= 4  # starts at about three lines
    assert v._transcript.minimumHeight() <= line + 20  # can shrink to one line
    assert v._transcript.maximumHeight() > 3 * line + 20  # and grow


def test_status_line_is_at_the_bottom_in_window_mode(qtbot):
    v = HintView()
    qtbot.addWidget(v)
    v.resize(500, 600)
    v.show()
    qtbot.waitExposed(v)
    assert v._status.geometry().top() > v.tabs.geometry().bottom()


def test_status_line_is_at_the_bottom_in_overlay_mode(qtbot):
    v = HintView(transcript_lines=3, compact=True)
    qtbot.addWidget(v)
    v.resize(500, 400)
    v.show()
    qtbot.waitExposed(v)
    assert v._status.geometry().top() > v._transcript.geometry().bottom()
