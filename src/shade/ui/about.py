"""About box shown from the tray menu."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QMessageBox, QWidget

REPO_URL = "https://github.com/sibprojects/shade"


def app_version() -> str:
    try:
        return version("shade")
    except PackageNotFoundError:
        return "dev"


def about_html(ver: str) -> str:
    return (
        "<p><b>Shade</b><br>Version " + ver + "</p>"
        "<p>Real-time call assistant for Windows: live transcription of your "
        "microphone and system audio, and instant AI hints for questions and "
        "on-screen tasks.</p>"
        f'<p><a href="{REPO_URL}">{REPO_URL}</a></p>'
        "<p>MIT License</p>"
    )


def show_about(icon: QPixmap | None = None, parent: QWidget | None = None) -> None:
    box = QMessageBox(QMessageBox.Icon.NoIcon, "About Shade", about_html(app_version()), parent=parent)
    if icon is not None:
        box.setIconPixmap(icon)
    box.exec()
