import threading

from shade.models import Status
from shade.ui.bridge import QtBridge


def test_bridge_delivers_event_from_thread(qtbot):
    bridge = QtBridge()
    event = Status("hello")
    with qtbot.waitSignal(bridge.event, timeout=2000) as blocker:
        threading.Thread(target=bridge.emit_event, args=(event,)).start()
    assert blocker.args == [event]
