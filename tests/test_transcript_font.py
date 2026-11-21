"""Own font size for the transcript/history block: window and overlay set separately."""

from shade.config import Settings, load_settings
from shade.models import HintDelta, HintDone, HintStarted, Usage
from shade.ui.hint_view import HintView
from shade.ui.main_window import MainWindow
from shade.ui.overlay import Overlay
from shade.ui.settings_dialog import SettingsDialog


def test_defaults_keep_the_old_look():
    s = Settings()
    assert s.window_transcript_font_size == s.window_font_size - 4
    assert s.overlay_transcript_font_size == s.overlay_font_size - 4


def test_old_settings_get_transcript_four_points_smaller(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text("window_font_size = 18\noverlay_font_size = 15\n", encoding="utf-8")
    s = load_settings(p)
    assert (s.window_transcript_font_size, s.overlay_transcript_font_size) == (14, 11)


def test_saved_transcript_size_is_kept(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text("window_font_size = 18\nwindow_transcript_font_size = 17\n", encoding="utf-8")
    assert load_settings(p).window_transcript_font_size == 17


def test_view_sets_transcript_and_history_size_on_its_own(qtbot):
    v = HintView(font_size=14, transcript_font_size=13)
    qtbot.addWidget(v)
    assert v._transcript.font().pointSize() == 13
    assert v._history_view.font().pointSize() == 13
    v.set_font_size(20)  # the hint text does not move the transcript
    assert v._current.font().pointSize() == 20
    assert v._transcript.font().pointSize() == 13
    v.set_transcript_font_size(9)
    assert v._transcript.font().pointSize() == 9
    assert v._history_view.font().pointSize() == 9
    assert v._current.font().pointSize() == 20


def test_history_code_follows_the_history_size(qtbot):
    v = HintView(font_size=14, code_font_size=12, transcript_font_size=10)
    qtbot.addWidget(v)
    v.handle(HintStarted(1, "auto", "q?"))
    v.handle(HintDelta(1, "x\n\n```python\nprint(1)\n```"))
    v.handle(HintDone(1, "m", Usage(1, 1), 0.0, 0.0))

    def history_code_pt():
        doc = v._history_view.document()
        sizes = set()
        b = doc.begin()
        while b.isValid():
            if "print(1)" in b.text():
                it = b.begin()
                while not it.atEnd():
                    sizes.add(round(it.fragment().charFormat().fontPointSize()))
                    it += 1
            b = b.next()
        return sizes

    assert history_code_pt() == {8}  # code 2 pt smaller than its text, as before
    v.set_transcript_font_size(16)
    assert history_code_pt() == {14}


def test_overlay_strip_fits_the_new_size(qtbot):
    v = HintView(compact=True, transcript_lines=3, font_size=12, transcript_font_size=8)
    qtbot.addWidget(v)
    small = v._strip_height()
    v.set_transcript_font_size(16)
    assert v._strip_height() > small


def test_window_and_overlay_take_their_sizes(qtbot):
    w = MainWindow(font_size=14, transcript_font_size=12)
    o = Overlay(font_size=12, transcript_font_size=9)
    qtbot.addWidget(w)
    qtbot.addWidget(o)
    assert w.view._transcript.font().pointSize() == 12
    assert o.view._transcript.font().pointSize() == 9


def test_display_tab_edits_both_sizes(qtbot):
    d = SettingsDialog(Settings(), {"mic": [], "loopback": []}, start_meter=False)
    qtbot.addWidget(d)
    for box in (d.window_transcript_font, d.overlay_transcript_font):
        assert d.tabs.widget(1).isAncestorOf(box)
    assert (d.window_transcript_font.value(), d.overlay_transcript_font.value()) == (10, 8)
    d.window_transcript_font.setValue(13)
    d.overlay_transcript_font.setValue(11)
    s = d.result_settings()
    assert (s.window_transcript_font_size, s.overlay_transcript_font_size) == (13, 11)
