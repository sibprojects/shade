import pytest

from shade.ui import ui_state


@pytest.fixture(autouse=True)
def _isolated_window_state(tmp_path):
    """Window positions/sizes go to a temp file, never to the user's registry."""
    ui_state.use_file(tmp_path / "ui-state.ini")
    yield
    ui_state.use_file(None)
