"""The main window: shows in the taskbar, with status, an optional live camera view and the main
controls, in the frosted-glass style (glass.py). Lives on the UI thread; the engine thread only
hands over the latest status and picture through UI.main_feed(). Buttons call App methods, which
queue work for the engine thread.

Closing the window hides it; the app keeps running in the tray (tray icon -> Open brings it back).
"""
import tkinter as tk

from . import __version__
from .glass import MUTED, SOFT, Glass, style_title_bar

STATES = {   # tray state -> (dot colour, title, explanation)
    "active": ("#4ade80", "Active", "Gestures are controlling your mouse."),
    "paused": ("#facc15", "Paused", "Gestures do nothing right now. Hold a thumbs-up, press Ctrl+Alt+G or click Resume."),
    "off": ("#cbd5e1", "Camera off", "The camera is switched off. Turn it back on below, or press Ctrl+Alt+G."),
    "error": ("#f87171", "Camera problem", "No picture from the camera. What to try is shown on the left."),
    "calibrating": ("#60a5fa", "Setting up", "Follow the instructions next to the camera view."),
}
MODES = {
    "idle": "No hand in view", "point": "Pointing", "ok": "Pointing (👌)", "lpinch": "Clicking",
    "drag": "Dragging", "rpinch": "Right click", "scroll": "Scrolling", "switcher": "Switching windows",
    "palm": "Open palm", "victory": "V-sign", "volume": "Changing volume", "call": "Call-me sign",
    "rest": "Hand resting", "paused": "Paused", "typing": "Typing, gestures off for a moment",
    "calibrating": "Setting up",
}
CAMERA_HELP = ("No picture from the camera.\n\n"
               "•  Close other apps that use it (Teams, Zoom, the Camera app).\n"
               "•  Windows Settings › Privacy & security › Camera: turn on Camera access and "
               "\"Let desktop apps access your camera\".\n"
               "•  Wrong camera? Run setup again and pick another.\n\n"
               "The app keeps trying in the background.")
HIDDEN_TEXT = ("Camera view is hidden\n\nSwitch on \"Show\" to see your hand's tracking points and the "
               "control area. The picture is never saved.")
W, H = 1000, 720
CAM = (40, 168, 568, 426)     # camera picture: x, y, w, h


class MainWindow:
    def __init__(self, root, app, icon=None):
        self.app = app
        self.camera_on = False
        self.state = None
        self.told_hidden = False
        self.guide = None
        win = self.win = tk.Toplevel(root)
        win.title("Gesture Control")
        win.resizable(False, False)
        if icon is not None:
            win.iconphoto(False, icon)
        win.protocol("WM_DELETE_WINDOW", self.hide)
        style_title_bar(win)
        g = self.g = Glass(win, W, H)

        # header
        g.canvas.create_line(g.px(30), g.px(30), g.px(30), g.px(92), fill="#c7d4ff", width=max(1, g.px(2)))
        g.text(46, 22, "Gesture Control", 26, "bold", kind="display")
        g.text(48, 68, "Your hand is the mouse.", 12, color=SOFT)
        self.stats = g.text(W - 28, 34, "", 9, color=MUTED, anchor="ne")

        # camera card
        g.card(24, 112, 600, 498)
        g.icon(52, 140, "camera", 14)
        g.text(72, 140, "Camera view", 12, "bold", anchor="w")
        g.text(520, 140, "Show", 10, color=SOFT, anchor="e")
        self.view_toggle = g.toggle(530, 127, False, lambda v: self.toggle_camera_view(v))
        self.slot = g.photo_slot(*CAM, r=16)

        # now card
        g.card(24, 626, 600, 70)
        self.now = g.text(48, 646, "", 13, "bold", width=330)
        self.last = g.text(48, 672, "", 10, color=SOFT)
        self.hold = g.progress(400, 657, 200, 0, thick=8, baked=False)

        # status card
        g.card(640, 112, 336, 196)
        g.text(664, 132, "STATUS", 9, "bold", color=MUTED)
        self.dot = g.glow(676, 180, 16, "#4ade80")
        self.title = g.text(696, 180, "", 24, "bold", anchor="w", kind="display")
        self.explain = g.text(664, 214, "", 11, color=SOFT, width=290)
        self.info = g.text(664, 284, "", 9, color=MUTED)

        self.pause_btn = g.button(640, 324, 336, 56, "Pause", "pause", lambda: app.toggle_pause("window"),
                                  strong=True, size=13)

        # shortcuts
        g.card(640, 396, 336, 118)
        for i, (text, icon, cmd) in enumerate((("Gesture guide", "guide", self.show_guide),
                                               ("Settings", "settings", app.open_settings),
                                               ("Run setup", "setup", app.start_wizard),
                                               ("Calibrate area", "calibrate", app.start_calibration))):
            g.tile(650 + i * 79, 404, 79, 102, text, icon, cmd)

        # switches
        g.card(640, 530, 336, 96)
        g.icon(666, 556, "camera", 13)
        g.text(686, 556, "Camera on", 11, anchor="w")
        self.cam_toggle = g.toggle(906, 543, True, lambda v: app.set_camera_off(not v))
        g.icon(666, 600, "windows", 13)
        g.text(686, 600, "Start with Windows", 11, anchor="w")
        self.startup = g.toggle(906, 587, app.startup_enabled(), self._toggle_startup)

        g.button(640, 642, 336, 54, "Quit Gesture Control", "power", app.quit)
        g.finish()
        self._placeholder()

        win.update_idletasks()
        win.geometry(f"+{max((win.winfo_screenwidth() - win.winfo_width()) // 2, 0)}+"
                     f"{max((win.winfo_screenheight() - win.winfo_height()) // 3, 0)}")

    # ---- visibility --------------------------------------------------------------------------
    def alive(self):
        return self.win.winfo_exists()

    def visible(self):
        return self.win.state() not in ("withdrawn", "iconic")

    def show(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def hide(self):
        self.win.withdraw()
        if not self.told_hidden:
            self.told_hidden = True
            self.app.notify("Gesture Control is still running. Click the tray icon to open it, or Quit from there.")

    def close(self):
        if self.alive():
            self.win.destroy()

    # ---- camera view -------------------------------------------------------------------------
    def wants_camera(self):
        return self.camera_on and self.visible()

    def toggle_camera_view(self, on=None):
        self.camera_on = (not self.camera_on) if on is None else on
        self.view_toggle.set(self.camera_on)
        if not self.camera_on and self.state != "error":
            self._placeholder()

    def _placeholder(self, text=None):
        self.slot.message(text or HIDDEN_TEXT)

    # ---- updates from the engine thread (via UI) ---------------------------------------------
    def update(self, status, rgb):
        g = self.g
        state = status.get("state", "active")
        if state != self.state:
            was_error = self.state == "error"
            self.state = state
            color, title, text = STATES.get(state, STATES["active"])
            self.dot.set(color)
            g.set(self.title, text=title)
            g.set(self.explain, text=text)
            paused = state in ("paused", "off")
            self.pause_btn.set("Resume" if paused else "Pause", "play" if paused else "pause")
            self.cam_toggle.set(state != "off")
            if state == "error":
                self.slot.message(CAMERA_HELP, justify="left")
            elif was_error or state == "off":
                self._placeholder("The camera is off." if state == "off" and self.camera_on else None)

        hand = str(self.app.cfg["tracking"]["hand"]).lower()
        g.set(self.info, text="Watching either hand" if hand == "any" else f"Watching your {hand} hand")

        banner = status.get("banner")
        mode = MODES.get(status.get("mode"), status.get("mode") or "")
        g.set(self.now, text=banner or f"Now: {mode}", font=g.font(11 if banner else 13, "bold"))
        g.set(self.last, text=f"Last action: {status['last']}" if status.get("last") else "")
        progress = status.get("progress")
        self.hold.set(progress if progress is not None else 0)
        g.set(self.stats, text=f"{status.get('fps', 0):.0f} fps  ·  {status.get('cpu', 0):.0f}% CPU  ·  v{__version__}")
        if self.camera_on and state not in ("error", "off") and rgb is not None:
            self.slot.set(rgb)

    def _toggle_startup(self, _value):
        self.app.toggle_startup()
        self.startup.set(self.app.startup_enabled())

    # ---- gesture guide -----------------------------------------------------------------------
    def show_guide(self):
        from .guide_window import GuideWindow
        if self.guide is not None and self.guide.alive():
            self.guide.show()
            return
        self.guide = GuideWindow(self.win)
