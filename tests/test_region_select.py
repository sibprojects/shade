from PySide6.QtCore import QPoint, QRect

from shade.ui.region_select import physical_rect, selection_rect


def test_selection_rect_normalizes_reverse_drag():
    assert selection_rect(QPoint(110, 70), QPoint(10, 20)) == QRect(10, 20, 100, 50)


def test_physical_rect_scales_by_device_pixel_ratio():
    assert physical_rect(QRect(10, 20, 100, 50), 1.5) == QRect(15, 30, 150, 75)


def test_physical_rect_identity_at_100_percent():
    assert physical_rect(QRect(1, 2, 3, 4), 1.0) == QRect(1, 2, 3, 4)
