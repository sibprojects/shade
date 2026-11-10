"""Where window positions and sizes are remembered (registry by default)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

_file: Path | None = None


def use_file(path: Path | None) -> None:
    """Store window state in an INI file instead of the registry (tests)."""
    global _file
    _file = Path(path) if path else None


def ui_state() -> QSettings:
    if _file is not None:
        return QSettings(str(_file), QSettings.Format.IniFormat)
    return QSettings("Shade", "Shade")
