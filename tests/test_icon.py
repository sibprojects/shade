from PySide6.QtGui import QColor

from shade.ui.icon import make_icon


def _img(size=64):
    return make_icon().pixmap(size, size).toImage()  # may be larger on high-DPI screens


def _opaque(img, fx, fy):
    """Is the pixel at fractional position (fx, fy) of the image opaque?"""
    x = min(img.width() - 1, int(fx * img.width()))
    y = min(img.height() - 1, int(fy * img.height()))
    return QColor.fromRgba(img.pixel(x, y)).alpha() > 200


def test_diamond_fills_the_icon_width(qtbot):
    img = _img()
    # The girdle (widest row) spans almost edge to edge — bigger than the old circle.
    assert _opaque(img, 0.04, 0.35) and _opaque(img, 0.95, 0.35)


def test_diamond_pavilion_ends_in_a_point(qtbot):
    img = _img()
    assert _opaque(img, 0.5, 0.93)       # tip at the bottom centre
    assert not _opaque(img, 0.1, 0.9)    # bottom-left is empty
    assert not _opaque(img, 0.9, 0.9)    # bottom-right is empty


def test_diamond_is_blue(qtbot):
    img = _img()
    c = QColor.fromRgba(img.pixel(img.width() // 2, int(img.height() * 0.62)))
    assert c.blue() > c.red() and c.blue() > c.green()
