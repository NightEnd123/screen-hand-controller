"""System tray icon and menu."""
import pystray

from .icon import disc_icon

COLORS = {
    "active": (46, 160, 67),
    "paused": (219, 171, 9),
    "off": (128, 128, 128),
    "error": (207, 34, 46),
    "calibrating": (31, 111, 235),
}
TITLES = {
    "active": "Gesture Control: active",
    "paused": "Gesture Control: paused (thumbs-up to resume)",
    "off": "Gesture Control: camera off",
    "error": "Gesture Control: camera problem",
    "calibrating": "Gesture Control: setting up",
}


def make_icon(color, size=64):
    return disc_icon(color, size)


class Tray:
    def __init__(self, app):
        self.app = app
        self.images = {k: make_icon(c) for k, c in COLORS.items()}
        self.state = "paused"
        I = pystray.MenuItem
        menu = pystray.Menu(
            I("Open Gesture Control", lambda: app.open_window(), default=True),
            I(lambda _: "Resume" if app.is_paused() else "Pause", lambda: app.toggle_pause("tray")),
            I("Camera off", lambda: app.set_camera_off(not app.camera_off), checked=lambda _: app.camera_off),
            I("Show debug view", lambda: app.toggle_preview(), checked=lambda _: app.preview),
            I("Calibrate control box", lambda: app.start_calibration()),
            I("Run setup again", lambda: app.start_wizard()),
            pystray.Menu.SEPARATOR,
            I("Settings…", lambda: app.open_settings()),
            I("Edit settings file", lambda: app.edit_settings()),
            I("Reload settings", lambda: app.reload_settings()),
            I("Start with Windows", lambda: app.toggle_startup(), checked=lambda _: app.startup_enabled()),
            pystray.Menu.SEPARATOR,
            I("Quit", lambda: app.quit()),
        )
        self.icon = pystray.Icon("gesture-control", self.images["paused"], TITLES["paused"], menu)

    def set_state(self, state):
        if state != self.state:
            self.state = state
            self.icon.icon = self.images[state]
            self.icon.title = TITLES[state]
            self.icon.update_menu()

    def notify(self, msg):
        try:
            self.icon.notify(msg, "Gesture Control")
        except Exception:
            pass

    def run(self, setup):
        self.icon.run(setup=setup)

    def stop(self):
        self.icon.stop()
