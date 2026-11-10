from PySide6.QtGui import QColor

from shade.ui.icon import make_icon


def _img(size=64):
    return make_icon().pixmap(size, size).toImage()  # may be larger on high-DPI screens


def _px(img, fx, fy):
    x = min(img.width() - 1, int(fx * img.width()))
    y = min(img.height() - 1, int(fy * img.height()))
    return QColor.fromRgba(img.pixel(x, y))


def test_gem_seen_from_above_fills_the_square(qtbot):
    img = _img()
    for fx, fy in ((0.5, 0.04), (0.5, 0.96), (0.04, 0.5), (0.96, 0.5)):
        assert _px(img, fx, fy).alpha() > 200


def test_gem_is_a_polygon_not_a_square(qtbot):
    img = _img()
    for fx, fy in ((0.03, 0.03), (0.97, 0.03), (0.03, 0.97), (0.97, 0.97)):
        assert _px(img, fx, fy).alpha() < 50


def test_gem_is_black_and_gray(qtbot):
    img = _img()
    for fx in (0.15, 0.3, 0.7, 0.85):
        for fy in (0.15, 0.5, 0.85):
            c = _px(img, fx, fy)
            if c.alpha() > 200:
                assert max(c.red(), c.green(), c.blue()) - min(c.red(), c.green(), c.blue()) < 12


def test_gem_has_the_s_letter(qtbot):
    img = _img(128)
    w, h = img.width(), img.height()
    bright = sum(
        1
        for x in range(int(w * 0.35), int(w * 0.65))
        for y in range(int(h * 0.3), int(h * 0.7))
        if QColor.fromRgba(img.pixel(x, y)).lightness() > 200
    )
    assert bright > 50


def test_s_letter_is_large(qtbot):
    img = _img(256)
    w, h = img.width(), img.height()
    rows = [
        y for y in range(h)
        if any(QColor.fromRgba(img.pixel(x, y)).lightness() > 225 for x in range(int(w * 0.3), int(w * 0.7)))
    ]
    assert (max(rows) - min(rows)) / h >= 0.6  # letter height: twice the old ~0.33
