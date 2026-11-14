"""Stylesheets for the hint window (day/night) and the overlay (custom colors)."""

from __future__ import annotations

from PySide6.QtGui import QColor

WINDOW_THEMES = {
    "day": {"bg": "#f3f3f3", "panel": "#ffffff", "text": "#1b1b1f", "muted": "#5b5f6b",
            "border": "#d0d3da", "accent": "#3b3f8f"},
    "night": {"bg": "#1e1f24", "panel": "#26282f", "text": "#e8e8ec", "muted": "#a0a4b0",
              "border": "#3a3d47", "accent": "#8b90ff"},
}


def window_stylesheet(theme: str) -> str:
    c = WINDOW_THEMES.get(theme, WINDOW_THEMES["day"])
    return f"""
QMainWindow, QWidget {{ background: {c['bg']}; color: {c['text']}; }}
QTextBrowser, QPlainTextEdit {{ background: {c['panel']}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 6px; }}
QLabel#status {{ color: {c['muted']}; }}
QTabWidget::pane {{ border: 1px solid {c['border']}; }}
QTabBar::tab {{ background: {c['bg']}; color: {c['muted']}; padding: 4px 12px;
    border: 1px solid {c['border']}; border-bottom: none; }}
QTabBar::tab:selected {{ background: {c['panel']}; color: {c['text']}; }}
QSplitter::handle {{ background: {c['border']}; }}
QPushButton {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']};
    border-radius: 6px; padding: 4px 12px; }}
QPushButton:hover {{ border-color: {c['accent']}; }}
QPushButton:pressed {{ background: {c['border']}; }}
QLineEdit {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']};
    border-radius: 6px; padding: 4px 8px; }}
QLineEdit:focus {{ border-color: {c['accent']}; }}
a {{ color: {c['accent']}; }}
"""


def overlay_stylesheet(bg: str, text: str, opacity: float) -> str:
    """Panels get the background color with `opacity` as alpha; text stays opaque."""
    col = QColor(bg)
    alpha = round(max(0.0, min(1.0, opacity)) * 255)
    rgba = f"rgba({col.red()}, {col.green()}, {col.blue()}, {alpha})"
    return (
        "#overlay { background: transparent; }"
        f"QTextBrowser, QPlainTextEdit {{ background: {rgba}; color: {text};"
        " border: 1px solid rgba(255,255,255,40); border-radius: 8px; }"
        f"QLabel {{ color: {text}; background: {rgba}; border-radius: 4px; padding: 2px 6px; }}"
        f"QLineEdit {{ color: {text}; background: {rgba}; border: 1px solid rgba(255,255,255,40);"
        " border-radius: 4px; padding: 2px 6px; }"
    )
