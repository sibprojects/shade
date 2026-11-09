"""Shade: real-time call assistant for Windows."""


def main() -> int:
    from shade.ui.app import ShadeApp

    return ShadeApp().run()
