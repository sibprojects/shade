"""Global hotkeys via pynput, delivered to the UI thread as a Qt signal.

pynput's GlobalHotKeys misses combos like Ctrl+Alt+A on Windows: with Ctrl+Alt
held, the letter arrives as a bare virtual-key code without a character, so it
never equals the parsed KeyCode('a'). We run our own Listener and normalize
keys with canonical_key() before feeding the HotKey matchers.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from pynput import keyboard
from pynput.keyboard import Key, KeyCode

ACTIONS = (
    "ask", "screenshot", "toggle_view", "toggle_overlay", "toggle_window", "click_through", "dismiss",
    "toggle_auto",
)

_MODIFIERS = {
    Key.ctrl_l: Key.ctrl, Key.ctrl_r: Key.ctrl,
    Key.alt_l: Key.alt, Key.alt_r: Key.alt, Key.alt_gr: Key.alt,
    Key.shift_l: Key.shift, Key.shift_r: Key.shift,
    Key.cmd_l: Key.cmd, Key.cmd_r: Key.cmd,
}


def canonical_key(key):
    if key in _MODIFIERS:
        return _MODIFIERS[key]
    if isinstance(key, KeyCode):
        vk = key.vk
        if vk is not None and (0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39):
            return KeyCode.from_char(chr(vk).lower())
        if key.char:
            return KeyCode.from_char(key.char.lower())
    return key


class HotkeyManager(QObject):
    triggered = Signal(str)  # action name
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._listener: keyboard.Listener | None = None
        self._hotkeys: list[keyboard.HotKey] = []

    @staticmethod
    def parse(bindings: dict[str, str]) -> tuple[dict[str, str], list[str]]:
        valid: dict[str, str] = {}
        errors: list[str] = []
        for name, combo in bindings.items():
            if name not in ACTIONS:
                errors.append(f"Unknown hotkey action: {name}")
                continue
            try:
                keyboard.HotKey.parse(combo)
            except (ValueError, KeyError):
                errors.append(f"Invalid hotkey for {name}: {combo}")
                continue
            valid[name] = combo
        return valid, errors

    def _set_bindings(self, bindings: dict[str, str]) -> list[str]:
        valid, errors = self.parse(bindings)
        self._hotkeys = [
            keyboard.HotKey(
                [canonical_key(k) for k in keyboard.HotKey.parse(combo)],
                # Runs on the pynput thread; the signal is queued to the UI thread.
                lambda n=name: self.triggered.emit(n),
            )
            for name, combo in valid.items()
        ]
        return errors

    def _on_press(self, key) -> None:
        k = canonical_key(key)
        for hk in self._hotkeys:
            hk.press(k)

    def _on_release(self, key) -> None:
        k = canonical_key(key)
        for hk in self._hotkeys:
            hk.release(k)

    def start(self, bindings: dict[str, str]) -> list[str]:
        """(Re)start listening; returns error messages for bindings that were skipped."""
        self.stop()
        errors = self._set_bindings(bindings)
        if self._hotkeys:
            self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
            self._listener.start()
        for e in errors:
            self.error.emit(e)
        return errors

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
