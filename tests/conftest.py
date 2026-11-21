import pytest

from shade.ui import ui_state


@pytest.fixture(autouse=True)
def _isolated_window_state(tmp_path):
    """Window positions/sizes go to a temp file, never to the user's registry."""
    ui_state.use_file(tmp_path / "ui-state.ini")
    yield
    ui_state.use_file(None)


@pytest.fixture(autouse=True)
def _no_real_microphone(monkeypatch):
    """The settings dialog's level meter must not open the real microphone in tests:
    a stream left open by a dialog that is never closed crashes the run on exit."""
    from shade.audio.capture import MicSource

    monkeypatch.setattr(MicSource, "start", lambda self, on_audio: setattr(self, "_on_audio", on_audio))
