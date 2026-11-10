import ctypes
import ctypes.wintypes

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


def test_restore_after_minimize_brings_window_to_front(qtbot):
    user32 = ctypes.windll.user32
    w = MainWindow()
    qtbot.addWidget(w)
    w.bring_to_front()
    qtbot.waitUntil(lambda: w.isVisible(), timeout=2000)
    hwnd = int(w.winId())
    user32.PostMessageW(hwnd, 0x0112, 0xF020, 0)  # WM_SYSCOMMAND / SC_MINIMIZE, like the title-bar button
    qtbot.waitUntil(lambda: not w.isVisible(), timeout=2000)
    w.bring_to_front()
    qtbot.waitUntil(lambda: w.isVisible(), timeout=2000)
    assert not user32.IsIconic(hwnd)
    # Visible on top: the window under its own centre is this window.
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    center = ctypes.wintypes.POINT((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
    user32.WindowFromPoint.argtypes = [ctypes.wintypes.POINT]
    top = user32.GetAncestor(user32.WindowFromPoint(center), 2)  # GA_ROOT
    assert top == hwnd
