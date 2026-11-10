from shade.ui import ui_state


def test_tests_never_write_window_state_to_the_registry(tmp_path):
    # conftest.py redirects window state to a temp file for every test.
    s = ui_state.ui_state()
    assert s.fileName().endswith(".ini")
    assert "HKEY" not in s.fileName()


def test_use_file_redirects(tmp_path):
    path = tmp_path / "state.ini"
    ui_state.use_file(path)
    s = ui_state.ui_state()
    s.setValue("k", 1)
    s.sync()
    assert path.exists()
