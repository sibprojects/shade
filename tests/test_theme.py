from shade.config import Settings
from shade.ui.settings_dialog import SettingsDialog
from shade.ui.theme import overlay_stylesheet, window_stylesheet

DEVICES = {"mic": [], "loopback": []}


def test_defaults():
    s = Settings()
    assert s.window_theme == "day"
    assert s.overlay_bg_color == "#101218"
    assert s.overlay_text_color == "#f2f2f2"


def test_window_themes_differ_and_set_colors():
    day, night = window_stylesheet("day"), window_stylesheet("night")
    assert day != night
    assert "#1e1f24" in night  # night background
    assert "#ffffff" in day


def test_overlay_stylesheet_uses_colors_and_alpha():
    css = overlay_stylesheet("#ff0000", "#00ff00", 0.5)
    assert "rgba(255, 0, 0, 128)" in css
    assert "color: #00ff00" in css


def test_overlay_opacity_bounds():
    assert "rgba(0, 0, 0, 255)" in overlay_stylesheet("#000000", "#ffffff", 1.0)
    assert "rgba(0, 0, 0, 0)" in overlay_stylesheet("#000000", "#ffffff", 0.0)


def test_dialog_edits_theme_and_colors(qtbot):
    d = SettingsDialog(Settings(), DEVICES)
    qtbot.addWidget(d)
    d.window_theme.setCurrentIndex(d.window_theme.findData("night"))
    d.set_overlay_bg("#202040")
    d.set_overlay_text("#ffee88")
    s = d.result_settings()
    assert s.window_theme == "night"
    assert s.overlay_bg_color == "#202040"
    assert s.overlay_text_color == "#ffee88"


def test_dialog_theme_controls_on_display_tab(qtbot):
    d = SettingsDialog(Settings(), DEVICES)
    qtbot.addWidget(d)
    tab = d.tabs.widget(1)
    for w in (d.window_theme, d.overlay_bg_button, d.overlay_text_button, d.opacity):
        assert tab.isAncestorOf(w)


def test_main_window_has_min_max_close_buttons(qtbot):
    from PySide6.QtCore import Qt

    from shade.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    flags = w.windowFlags()
    for hint in (
        Qt.WindowType.WindowMinimizeButtonHint,
        Qt.WindowType.WindowMaximizeButtonHint,
        Qt.WindowType.WindowCloseButtonHint,
    ):
        assert flags & hint


def test_main_window_theme_switch(qtbot):
    from shade.ui.main_window import MainWindow

    w = MainWindow("night")
    qtbot.addWidget(w)
    assert "#1e1f24" in w.styleSheet()
    w.apply_theme("day")
    assert "#1e1f24" not in w.styleSheet()


def test_font_size_defaults():
    s = Settings()
    assert s.window_font_size == 14
    assert s.overlay_font_size == 12


def test_hint_view_font_size_applies_to_hint_and_transcript(qtbot):
    from shade.ui.hint_view import HintView

    v = HintView()
    qtbot.addWidget(v)
    v.set_font_size(20)
    assert v._current.font().pointSize() == 20
    assert v._transcript.font().pointSize() == 16


def test_dialog_edits_font_sizes(qtbot):
    d = SettingsDialog(Settings(), DEVICES)
    qtbot.addWidget(d)
    assert d.tabs.widget(1).isAncestorOf(d.window_font)
    assert d.tabs.widget(1).isAncestorOf(d.overlay_font)
    d.window_font.setValue(18)
    d.overlay_font.setValue(10)
    s = d.result_settings()
    assert (s.window_font_size, s.overlay_font_size) == (18, 10)
