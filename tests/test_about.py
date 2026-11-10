from shade.ui.about import REPO_URL, about_html, app_version


def test_about_has_name_version_link_and_license():
    html = about_html("1.2.3")
    assert "<b>Shade</b>" in html
    assert "Version 1.2.3" in html
    assert f'<a href="{REPO_URL}">' in html
    assert "MIT License" in html


def test_app_version_from_package_metadata():
    assert app_version() == "0.1.0"
