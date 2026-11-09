from shade.gpu import vram_nearly_full


def test_vram_nearly_full_above_90_percent():
    assert vram_nearly_full((7_400, 8_000))
    assert not vram_nearly_full((7_000, 8_000))


def test_vram_unknown_is_not_full():
    assert not vram_nearly_full(None)
