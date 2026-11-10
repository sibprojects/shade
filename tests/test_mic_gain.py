import numpy as np
import pytest

from shade.audio.capture import MicSource, level_percent
from shade.audio.resample import Resampler
from shade.config import Settings
from shade.ui.settings_dialog import SettingsDialog


def test_default_gain():
    assert Settings().mic_gain == 1.0


def _mic(gain):
    got = []
    src = MicSource(gain=gain, clock=lambda: 1.0)
    src._resampler = Resampler(16000, 1)
    src._on_audio = lambda a, t: got.append(a)
    return src, got


def test_gain_amplifies_mic_audio():
    src, got = _mic(4.0)
    src._deliver(np.full(1600, 0.1, dtype=np.float32), 16000)
    assert float(got[0].max()) == pytest.approx(0.4)


def test_gain_clips_instead_of_overflowing():
    src, got = _mic(20.0)
    src._deliver(np.full(1600, 0.5, dtype=np.float32), 16000)
    assert float(got[0].max()) == 1.0


def test_source_reports_last_level():
    src, _ = _mic(2.0)
    src._deliver(np.full(1600, 0.25, dtype=np.float32), 16000)
    assert src.last_peak == pytest.approx(0.5)


@pytest.mark.parametrize("peak,expected", [(0.0, 0), (0.001, 0), (0.0316, 50), (1.0, 100), (2.0, 100)])
def test_level_percent_maps_minus60_to_0_dbfs(peak, expected):
    assert level_percent(peak) == pytest.approx(expected, abs=1)


def test_dialog_has_gain_and_meter_on_audio_tab(qtbot):
    d = SettingsDialog(Settings(), {"mic": [], "loopback": []}, start_meter=False)
    qtbot.addWidget(d)
    tab = d.tabs.widget(2)
    assert tab.isAncestorOf(d.mic_gain) and tab.isAncestorOf(d.mic_level)
    d.mic_gain.setValue(60)  # slider in tenths: x6.0
    assert d.result_settings().mic_gain == 6.0
