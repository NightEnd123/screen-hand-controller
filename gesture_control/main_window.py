"""The main window: a dashboard with a sidebar, a status card, live charts of what you're doing,
and the camera view. Lives on the UI thread; the engine thread only hands over the latest status
and picture through UI.main_feed(). Buttons call App methods, which queue work for the engine
thread.

Closing the window (X) quits the app. The tray button in the top bar hides it to the tray instead
(tray icon -> Open brings it back).
"""
import time
import tkinter as tk

from . import __version__, charts
from .glass import (DARK, GREY, LAVENDER, MINT, MUTED, PINK, SOFT, TEXT, Glass, hex_rgb, round_rect_image,
                    style_title_bar)
from .icon import tile

STATES = {   # tray state -> (dot colour, title, short explanation)
    "active": ("#4ade80", "Active", "Gestures are controlling your mouse"),
    "paused": ("#facc15", "Paused", "Thumbs-up or Ctrl+Alt+G to resume"),
    "off": ("#9aa0a8", "Camera off", "The camera is switched off"),
    "error": ("#f87171", "Camera problem", "No picture from the camera"),
    "calibrating": ("#60a5fa", "Setting up", "Follow the instructions in the camera view"),
}
MODES = {
    "idle": "No hand", "point": "Pointing", "ok": "Pointing", "lpinch": "Clicking",
    "drag": "Dragging", "rpinch": "Right click", "scroll": "Scrolling", "switcher": "Switching",
    "palm": "Open palm", "victory": "V-sign", "volume": "Volume", "call": "Call-me",
    "rest": "Resting", "paused": "Paused", "typing": "Typing", "calibrating": "Setting up",
}
CAMERA_HELP = ("No picture from the camera.\n\n"
               "•  Close other apps that use it (Teams, Zoom, the Camera app).\n"
               "•  Windows Settings › Privacy & security › Camera: turn on Camera access and "
               "\"Let desktop apps access your camera\".\n"
               "•  Wrong camera? Run setup again and pick another.")
W, H, SIDE = 1120, 680, 200
ROW1, ROW1_H, ROW2, ROW2_H = 92, 272, 380, 272
WHITE = (232, 92, 220)              # status card x, y-offset unused, width
BIG = (468, 620)                    # chart card x, width
CHART = (480, ROW1 + 44, 596, 216)  # chart / camera area
CAM_W = round(CHART[3] * 4 / 3)
INK_MUTED = "#8a9099"               # labels on the white card


class MainWindow:
    def __init__(self, root, app, icon=None):
        self.app = app
        self.camera_on = False          # big card shows the camera instead of the chart
        self.state = None
        self.told_hidden = False
        self.guide = None
        self.last_chart = 0.0
        win = self.win = tk.Toplevel(root)
        win.title("AirCursor")
        win.resizable(False, False)
        if icon is not None:
            win.iconphoto(False, icon)
        win.protocol("WM_DELETE_WINDOW", app.quit)
        style_title_bar(win)
        g = self.g = Glass(win, W, H, sidebar=SIDE)

        self._sidebar(g, app)
        self._top_bar(g, app)
        self._status_card(g)
        self._big_card(g)
        self._session_card(g)
        self._mix_card(g)
        self._timeline_card(g)
        g.finish()
        self._show_chart()

        win.update_idletasks()
        win.geometry(f"+{max((win.winfo_screenwidth() - win.winfo_width()) // 2, 0)}+"
                     f"{max((win.winfo_screenheight() - win.winfo_height()) // 3, 0)}")

    # ---- layout ------------------------------------------------------------------------------
    def _sidebar(self, g, app):
        g.bake(SIDE / 2 - 22, 26, tile(g.px(44)))
        g.text(SIDE / 2, 84, "AirCursor", 12, "bold", anchor="n", kind="display")
        items = (("Dashboard", "dashboard", self._show_chart),
                 ("Camera view", "camera", lambda: self.toggle_camera_view(True)),
                 ("Gestures", "guide", self.show_guide),
                 ("Settings", "settings", app.open_settings),
                 ("Run setup", "setup", app.start_wizard),
                 ("Calibrate", "calibrate", app.start_calibration))
        self.nav = {}
        for i, (text, icon, cmd) in enumerate(items):
            self.nav[text] = g.nav(20, 124 + i * 42, SIDE - 40, text, icon, cmd, selected=(i == 0),
                                   badge=0 if text == "Camera view" else None)
        g.text(28, 410, "Start with Windows", 9, color=SOFT, anchor="w")
        self.startup = g.toggle(SIDE - 64, 398, app.startup_enabled(), self._toggle_startup)
        g.nav(20, 440, SIDE - 40, "Quit AirCursor", "power", app.quit)
        # "profile" at the bottom: the hand being watched
        g.bake(SIDE / 2 - 28, H - 120, _avatar(g.px(56)))
        self.hand_label = g.text(SIDE / 2, H - 54, "", 10, anchor="n")
        self.hand_sub = g.text(SIDE / 2, H - 34, "", 8, color=MUTED, anchor="n")

    def _top_bar(self, g, app):
        self.page = g.text(SIDE + 32, 46, "Dashboard", 15, "bold", anchor="w", kind="display")
        g.card(470, 28, 410, 36, r=10)                  # the "search" pill holds the status
        self.dot = g.glow(492, 46, 9, "#4ade80")
        self.pill = g.text(506, 46, "", 9, color=SOFT, anchor="w", width=366)
        self.cam_btn = g.icon_button(978, 46, "camera", lambda: app.set_camera_off(not app.camera_off), 14)
        g.icon_button(1016, 46, "tray", self.hide, 13)
        self.power = g.toggle(1046, 34, True, self._toggle_gestures)

    def _status_card(self, g):
        x, y, w = WHITE[0], ROW1, WHITE[2]
        g.white_card(x, y, w, ROW1_H)
        g.text(x + w / 2, y + 24, "Status", 12, "bold", color=DARK, anchor="n", kind="display")
        self.rows = {}
        for i, label in enumerate(("State", "Hand", "Now", "Last")):
            yy = y + 66 + i * 30
            g.text(x + 18, yy, label, 9, color=INK_MUTED, anchor="w")
            self.rows[label] = g.text(x + 82, yy, "", 10, color=DARK, anchor="w", width=w - 92)
        self.hold = g.progress(x + 18, y + 190, w - 36, 0, thick=6, baked=False)
        # bottom row: fps bar on the left, CPU dial on the right (like height / weight)
        by = y + ROW1_H - 40
        g.icon(x + 22, by, "camera", 11, color=DARK)
        g.bake(x + 36, by - 15, round_rect_image(g.px(4), g.px(30), g.px(2), hex_rgb(MINT) + (255,)))
        self.fps = g.text(x + 48, by, "", 10, color=DARK, anchor="w")
        self.cpu = g.text(x + w - 54, by, "", 10, color=DARK, anchor="e")
        self.cpu_dial = g.live_image(x + w - 48, by - 15)

    def _big_card(self, g):
        x, w = BIG
        g.card(x, ROW1, w, ROW1_H)
        self.big_title = g.text(x + 20, ROW1 + 24, "Cursor movement", 11, "bold", anchor="w", width=430)
        self.view_btn = g.button(x + w - 20 - 132, ROW1 + 11, 132, 28, "Camera view", "camera",
                                 lambda: self.toggle_camera_view(), size=9)
        cx, cy, cw, ch = CHART
        self.chart = g.live_image(cx, cy)
        self.slot = g.photo_slot(cx + (cw - CAM_W) / 2, cy, CAM_W, ch, r=12, backing=False)
        self.slot.hide()

    def _session_card(self, g):
        x, y, w = 232, ROW2, 220
        g.card(x, y, w, ROW2_H)
        g.text(x + 18, y + 24, "This session", 11, "bold", anchor="w")
        self.donut = g.live_image(x + 12, y + 82)
        self.legend = []
        for i, (label, key, color) in enumerate(charts.LEGEND):
            yy = y + 78 + i * 44
            g.bake(x + 146, yy, _dot(g.px(9), color))
            g.text(x + 161, yy + 4, label, 9, anchor="w")
            self.legend.append((key, g.text(x + 161, yy + 22, "0", 9, color=MUTED, anchor="w")))

    def _mix_card(self, g):
        x, y, w = 468, ROW2, 300
        g.card(x, y, w, ROW2_H)
        g.icon(x + 26, y + 24, "globe", 13)
        g.text(x + 44, y + 24, "Gesture mix", 11, "bold", anchor="w")
        self.radar = g.live_image(x + 12, y + 46)

    def _timeline_card(self, g):
        x, y, w = 784, ROW2, 304
        g.card(x, y, w, ROW2_H)
        g.text(x + 20, y + 24, "Timeline", 11, "bold", anchor="w")
        g.text(x + w - 20, y + 24, "last 10 min", 9, color=MUTED, anchor="e")
        self.timeline = g.live_image(x + 14, y + 52)

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
            self.app.notify("AirCursor is still running. Click the tray icon to open it, or Quit from there.")

    def close(self):
        if self.alive():
            self.win.destroy()

    # ---- camera view / chart -----------------------------------------------------------------
    def wants_camera(self):
        return self.camera_on and self.visible()

    def toggle_camera_view(self, on=None):
        self.camera_on = (not self.camera_on) if on is None else on
        if self.camera_on:
            self._show_camera()
        else:
            self._show_chart()

    def _select(self, name):
        for key, item in self.nav.items():
            item.select(key == name)

    def _show_chart(self):
        self.camera_on = False
        self._select("Dashboard")
        self.g.set(self.page, text="Dashboard")
        self.g.set(self.big_title, text="Cursor movement")
        self.view_btn.set("Camera view", "camera")
        self.slot.hide()
        self.chart.show(True)
        self.last_chart = 0.0

    def _show_camera(self):
        self.camera_on = True
        self._select("Camera view")
        self.g.set(self.page, text="Camera view")
        self.g.set(self.big_title, text="Camera view")
        self.view_btn.set("Show chart", "chart")
        self.chart.show(False)
        if self.state == "error":
            self.slot.message(CAMERA_HELP, justify="left")
        elif self.state == "off":
            self.slot.message("The camera is off. Click the camera icon at the top to turn it on.")
        else:
            self.slot.message("Starting the camera view…")

    # ---- updates from the engine thread (via UI) ---------------------------------------------
    def update(self, status, rgb):
        g = self.g
        state = status.get("state", "active")
        if state != self.state:
            self.state = state
            color, title, text = STATES.get(state, STATES["active"])
            self.dot.set(color)
            g.set(self.pill, text=f"{title}  ·  {text}")
            g.set(self.rows["State"], text=title)
            self.power.set(state not in ("paused", "off"))
            g.set(self.cam_btn.icon_item, fill=MUTED if state == "off" else TEXT)
            self.nav["Camera view"].set_badge("!" if state == "error" else "")
            if self.camera_on:
                self._show_camera()
        hand = str(self.app.cfg["tracking"]["hand"]).lower()
        hand_text = "Either hand" if hand == "any" else f"{hand.capitalize()} hand"
        g.set(self.rows["Hand"], text=hand_text)
        g.set(self.hand_label, text=hand_text)
        g.set(self.hand_sub, text=f"v{__version__}")
        banner = status.get("banner")
        g.set(self.rows["Now"], text=MODES.get(status.get("mode"), status.get("mode") or ""))
        g.set(self.rows["Last"], text=status.get("last") or "–")
        if banner:
            g.set(self.big_title, text=banner)
        progress = status.get("progress")
        self.hold.set(progress if progress is not None else 0)
        g.set(self.fps, text=f"{status.get('fps', 0):.0f} fps")
        cpu = status.get("cpu", 0) or 0
        g.set(self.cpu, text=f"CPU {cpu:.0f}%")
        if self.camera_on and rgb is not None and state not in ("error", "off"):
            self.slot.set(rgb)

        now = time.perf_counter()
        if now - self.last_chart >= 1.0:
            self.last_chart = now
            self.cpu_dial.set(charts.arc_meter(g.px(30), g.s, cpu / 100))
            stats = status.get("stats")
            if stats is not None:
                self._draw_charts(stats.snapshot())

    def _draw_charts(self, snap):
        g = self.g
        if not self.camera_on:
            cx, cy, cw, ch = CHART
            speed = snap["speed"][-60:]
            self.chart.set(charts.area_chart([0] * (60 - len(speed)) + speed, g.px(cw), g.px(ch), g.s,
                                             x_labels=("-60s", "-45s", "-30s", "-15s", "now")))
        counts = snap["counts"]
        total = sum(counts.get(k, 0) for _, k, _ in charts.LEGEND)
        self.donut.set(charts.donut([(counts.get(k, 0), c) for _, k, c in charts.LEGEND], g.px(122), g.s,
                                    total_label="Total", total_value=str(total)))
        for key, item in self.legend:
            g.set(item, text=str(counts.get(key, 0)))
        times = snap["mode_time"]
        spent = sum(times.values())
        self.radar.set(charts.radar({k: (times.get(k, 0) / spent if spent else 0) for k in
                                     ("Point", "Click", "Scroll", "Swipe", "Switch", "Media")},
                                    g.px(276), g.px(216), g.s))
        iv = snap["intervals"]
        now = snap["now"] or time.perf_counter()
        self.timeline.set(charts.timeline(
            [("Active", MINT, iv.get("active", []), "On"), ("Paused", LAVENDER, iv.get("paused", []), ""),
             ("Camera off", GREY, iv.get("off", []), ""), ("Hand seen", PINK, iv.get("hand", []), "")],
            now, snap["span"], g.px(276), g.px(204), g.s))

    # ---- buttons -------------------------------------------------------------------------------
    def _toggle_gestures(self, on):
        paused = self.state in ("paused", "off")
        if on == paused:
            self.app.toggle_pause("window")

    def _toggle_startup(self, _value):
        self.app.toggle_startup()
        self.startup.set(self.app.startup_enabled())

    def show_guide(self):
        from .guide_window import GuideWindow
        if self.guide is not None and self.guide.alive():
            self.guide.show()
            return
        self.guide = GuideWindow(self.win)


def _dot(d, color):
    from .glass import disc
    return disc(d, hex_rgb(color))


def _avatar(d):
    """The round "profile picture": the app's hand on a dark disc with a mint ring."""
    from .glass import disc
    from .icon import glyph
    img = disc(d, (30, 42, 54), ring=hex_rgb(MINT), ring_w=max(d // 26, 2))
    hand = glyph(int(d * 0.62))
    img.alpha_composite(hand, ((d - hand.width) // 2, (d - hand.height) // 2))
    return img
