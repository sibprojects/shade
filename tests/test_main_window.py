import ctypes

from PySide6.QtCore import Qt

from shade.ui.main_window import MainWindow

GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000


def test_window_has_program_icon(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert not w.windowIcon().isNull()


def test_window_is_owned_so_it_stays_off_the_taskbar(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    hwnd = int(w.winId())
    user32 = ctypes.windll.user32
    assert user32.GetWindow(hwnd, GW_OWNER) != 0
    assert not user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_APPWINDOW


def test_window_keeps_min_max_close_buttons(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    for hint in (
        Qt.WindowType.WindowMinimizeButtonHint,
        Qt.WindowType.WindowMaximizeButtonHint,
        Qt.WindowType.WindowCloseButtonHint,
    ):
        assert w.windowFlags() & hint


def test_minimize_hides_to_tray(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    w.showMinimized()
    qtbot.waitUntil(lambda: not w.isVisible(), timeout=2000)
    w.show()
    assert not w.isMinimized()
