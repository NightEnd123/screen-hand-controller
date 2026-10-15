"""System tray icon and menu."""
import pystray
from PIL import Image, ImageDraw

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
    "calibrating": "Gesture Control: calibrating",
}


def make_icon(color, size=64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, size - 2, size - 2), fill=color + (255,))
    s = size / 64
    white = (255, 255, 255, 255)
    d.rounded_rectangle((27 * s, 12 * s, 36 * s, 40 * s), radius=4 * s, fill=white)   # index finger
    d.rounded_rectangle((20 * s, 30 * s, 45 * s, 52 * s), radius=7 * s, fill=white)   # palm
    return img


class Tray:
    def __init__(self, app):
        self.app = app
        self.images = {k: make_icon(c) for k, c in COLORS.items()}
        self.state = "paused"
        I = pystray.MenuItem
        menu = pystray.Menu(
            I(lambda _: "Resume" if app.is_paused() else "Pause", lambda: app.toggle_pause("tray"), default=True),
            I("Camera off", lambda: app.set_camera_off(not app.camera_off), checked=lambda _: app.camera_off),
            I("Show debug view", lambda: app.toggle_preview(), checked=lambda _: app.preview),
            I("Calibrate control box", lambda: app.start_calibration()),
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
