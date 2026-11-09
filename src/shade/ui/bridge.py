"""Thread-safe hand-off of engine events to the Qt UI thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from shade.models import Event


class QtBridge(QObject):
    # Emitting a signal from a worker thread queues delivery to receivers
    # living in the UI thread.
    event = Signal(object)

    def emit_event(self, e: Event) -> None:
        self.event.emit(e)
