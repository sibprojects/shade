"""Shade: real-time call assistant for Windows."""


def main() -> int:
    from shade.env import load_env

    load_env()  # before any provider is created

    from shade.ui.app import ShadeApp

    return ShadeApp().run()
