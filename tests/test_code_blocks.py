from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from shade.config import Settings, load_settings
from shade.ui.hint_view import HintView
from shade.models import HintDelta, HintStarted

ANSWER = (
    "I'd use a set.\n\n"
    "```python\n"
    "def has_duplicates(items: list[int]) -> bool:  # a deliberately long line that would need a scrollbar\n"
    "    return len(set(items)) != len(items)\n"
    "```\n"
)


def _blocks(view):
    doc = view._current.document()
    b = doc.begin()
    while b.isValid():
        yield b
        b = b.next()


def _show(qtbot, view, width=360):
    qtbot.addWidget(view)
    view.resize(width, 500)
    view.show()
    qtbot.waitExposed(view)
    view.handle(HintStarted(1, "hotkey", "q"))
    view.handle(HintDelta(1, ANSWER))


def _code_blocks(view):
    return [b for b in _blocks(view) if "has_duplicates" in b.text() or "return len" in b.text()]


def test_code_is_on_a_black_background(qtbot):
    view = HintView(font_size=14)
    _show(qtbot, view)
    code = _code_blocks(view)
    assert code
    for b in code:
        assert b.blockFormat().background().color() == QColor("#000000")
        assert b.charFormat().foreground().color().lightness() > 200 or all(
            f.charFormat().foreground().color().lightness() > 200 for f in _fragments(b)
        )


def _fragments(block):
    it = block.begin()
    while not it.atEnd():
        yield it.fragment()
        it += 1


def test_long_code_lines_wrap_instead_of_scrolling(qtbot):
    view = HintView(font_size=14)
    _show(qtbot, view)
    for b in _code_blocks(view):
        assert not b.blockFormat().nonBreakableLines()
    qtbot.wait(50)
    assert view._current.horizontalScrollBar().maximum() == 0


def test_code_font_is_its_own_size(qtbot):
    view = HintView(font_size=14, code_font_size=11)
    _show(qtbot, view)
    for b in _code_blocks(view):
        for f in _fragments(b):
            assert round(f.charFormat().fontPointSize()) == 11
    view.set_code_font_size(9)
    for b in _code_blocks(view):
        for f in _fragments(b):
            assert round(f.charFormat().fontPointSize()) == 9


def test_plain_text_keeps_the_hint_font(qtbot):
    view = HintView(font_size=14, code_font_size=11)
    _show(qtbot, view)
    first = next(b for b in _blocks(view) if b.text().startswith("I'd use a set"))
    assert first.text().startswith("I'd use a set")
    assert first.blockFormat().background().style() == Qt.BrushStyle.NoBrush


def test_code_font_defaults_to_two_points_smaller():
    s = Settings()
    assert (s.window_code_font_size, s.overlay_code_font_size) == (s.window_font_size - 2, s.overlay_font_size - 2)


def test_old_settings_get_code_font_two_points_smaller(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text("window_font_size = 16\noverlay_font_size = 13\n", encoding="utf-8")
    s = load_settings(p)
    assert (s.window_code_font_size, s.overlay_code_font_size) == (14, 11)


def test_subscription_defaults_to_opus():
    assert Settings().cc_model == "claude-opus-5-5"
