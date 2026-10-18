"""On-screen feedback dot next to the cursor + the settings window (Tk, on its own thread).

Other threads never touch Tk directly: they call feed()/open_settings(), which only set fields or
queue requests that the Tk thread picks up on its next tick.
"""
import ctypes
import logging
import queue
import threading
import time
import tkinter as tk

from .actions import cursor_pos

log = logging.getLogger(__name__)
user32 = ctypes.windll.user32

KEY = "#010101"   # colour made fully transparent in the overlay window
MODE_COLORS = {
    "point": "#3fb950", "ok": "#3fb950", "lpinch": "#f85149", "drag": "#f85149", "rpinch": "#ff9f1c",
    "scroll": "#e3b341", "switcher": "#bc8cff", "palm": "#39c5cf", "victory": "#58a6ff",
    "volume": "#58a6ff", "call": "#ff7b72", "rest": "#8b949e", "paused": "#d29922",
}
LABELS = {
    "ctrl+tab": "Next tab", "ctrl+shift+tab": "Previous tab", "maximize": "Maximize",
    "minimize": "Minimize", "play_pause": "Play / pause", "volume_up": "Volume +",
    "volume_down": "Volume −", "win+h": "Voice typing", "media_next": "Next track",
    "media_prev": "Previous track", "right": "Next", "left": "Back", "tab": "Next window",
    "shift+tab": "Previous window",
}


def label_for(action):
    if action[0] == "pause":
        return "Paused" if action[1] else "Gestures on"
    if action[0] == "keydown" and action[1] == "alt":
        return "Switch window"
    if action[0] in ("keys", "window"):
        return LABELS.get(action[1], action[1])
    return None


class UI(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True, name="ui")
        self.app = app
        self.requests = queue.Queue()
        self.mode, self.hold, self.fed_at = "idle", None, 0.0
        self.flash_until, self.flash_color = 0.0, "#ffffff"
        self.label, self.label_until = "", 0.0
        self.settings_win = None
        self.setup_win = None
        self.setup_view = self.setup_rgb = None
        self.setup_new = False
        self.main_win = None
        self.main_status, self.main_rgb, self.main_new = {}, None, False
        self.main_wants_camera = False   # read by the engine thread; set on the Tk thread
        self.last_action = ""
        from .stats import SessionStats
        self.stats = SessionStats()       # numbers for the dashboard charts
        self.shown = None
        self.drawn_key = None    # what's currently on the canvas, to skip identical redraws
        self.pos = None

    # ---- called from other threads ---------------------------------------------------------
    def feed(self, mode, hold, actions, resolve=None):
        self.mode, self.hold, self.fed_at = mode, hold, time.perf_counter()
        now = self.fed_at
        for a in actions:
            if a[0] in ("down", "click"):
                self.flash_until = now + 0.25
                self.flash_color = "#f85149" if a[1] == "left" else "#ff9f1c"
            if len(a) == 3 and resolve:
                a = resolve(a[2]) or a
            text = label_for(a)
            if text and not (a[0] == "keys" and a[1] in ("volume_up", "volume_down", "tab", "shift+tab")
                             and self.label_until > now and self.label == text):
                self.label, self.label_until = text, now + 1.2
            if text:
                self.last_action = text
            elif a[0] in ("down", "click"):
                self.last_action = "Left click" if a[1] == "left" else "Right click"

    def open_settings(self):
        self.requests.put("settings")

    def open_setup(self):
        self.setup_view = self.setup_rgb = None
        self.requests.put("setup_open")

    def close_setup(self):
        self.requests.put("setup_close")

    def setup_feed(self, view, rgb):
        self.setup_view, self.setup_rgb, self.setup_new = view, rgb, True

    def show_main(self, camera=False):
        self.requests.put("main_camera" if camera else "main_show")

    def main_feed(self, status, rgb):
        status["last"] = self.last_action
        self.stats.add(time.perf_counter(), status.get("state"), status.get("mode"),
                       status.pop("actions", ()) or (), status.pop("cursor", None))
        status["stats"] = self.stats
        self.main_status, self.main_rgb, self.main_new = status, rgb, True

    def stop(self):
        self.requests.put("quit")

    # ---- Tk thread ---------------------------------------------------------------------------
    def run(self):
        try:
            self.root = tk.Tk()
            self.root.withdraw()
            try:
                self.root.tk.call("tk", "scaling", user32.GetDpiForSystem() / 72)
            except Exception:
                pass
            self._make_overlay()
            self._make_main()
            self.root.after(16, self._tick)
            self.root.mainloop()
        except Exception:
            log.exception("UI thread failed; continuing without overlay/settings")

    def _make_overlay(self):
        self.size = (260, 70)
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.attributes("-topmost", True, "-transparentcolor", KEY, "-alpha", 0.0)
        top.geometry(f"{self.size[0]}x{self.size[1]}+0+0")
        self.canvas = tk.Canvas(top, width=self.size[0], height=self.size[1], bg=KEY, highlightthickness=0)
        self.canvas.pack()
        top.update_idletasks()
        # Click-through, never takes focus, no taskbar button.
        hwnd = user32.GetParent(top.winfo_id())
        GWL_EXSTYLE = -20
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | 0x80000 | 0x20 | 0x80 | 0x08000000)
        self.overlay = top

    def _tick(self):
        try:
            while not self.requests.empty():
                req = self.requests.get_nowait()
                if req == "quit":
                    self.root.quit()
                    return
                if req == "settings":
                    self._show_settings()
                elif req == "setup_open":
                    self._open_setup()
                elif req == "setup_close" and self.setup_win is not None:
                    self.setup_win.close()
                    self.setup_win = None
                elif req in ("main_show", "main_camera") and self.main_win is not None:
                    self.main_win.show()
                    if req == "main_camera":
                        self.main_win.toggle_camera_view(True)
            if self.setup_win is not None and self.setup_new:
                self.setup_new = False
                if self.setup_win.alive():
                    self.setup_win.show(self.setup_view, self.setup_rgb)
            if self.main_win is not None and self.main_win.alive():
                if self.main_new:
                    self.main_new = False
                    self.main_win.update(self.main_status, self.main_rgb)
                self.main_wants_camera = self.main_win.wants_camera()
            self._draw()
        except Exception:
            log.exception("overlay tick failed")
        self.root.after(16, self._tick)

    def _draw(self):
        now = time.perf_counter()
        enabled = self.app.cfg["feedback"].get("overlay", True)
        stale = now - self.fed_at > 0.5
        active = self.mode not in ("idle", "typing", "paused", "calibrating")
        want = enabled and not stale and (active or self.hold is not None or self.label_until > now)
        if not want:
            if self.shown is not False:
                self.overlay.attributes("-alpha", 0.0)
                self.shown = False
            return
        x, y = cursor_pos()
        if (x, y) != self.pos:
            self.overlay.geometry(f"+{x + 14}+{y + 14}")
            self.pos = (x, y)
        flashing, labelled = self.flash_until > now, self.label_until > now
        key = (self.mode, None if self.hold is None else round(self.hold, 2),
               flashing and self.flash_color, labelled and self.label, active)
        if key == self.drawn_key and self.shown:
            return
        self.drawn_key = key
        c = self.canvas
        c.delete("all")
        cx, cy, s = 24, 24, self.size[1] / 70
        color = MODE_COLORS.get(self.mode, "#8b949e")
        if active:
            r = 6 * s
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline="#ffffff", width=1)
        if self.hold is not None:
            r = 15 * s
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#30363d", width=3)
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=-359.9 * self.hold,
                         style="arc", outline="#ffffff", width=3)
        if flashing:
            r = 12 * s
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=self.flash_color, width=3)
        if labelled:
            c.create_text(cx + 22 * s, cy, text=self.label, anchor="w", fill="#000000",
                          font=("Segoe UI", 10, "bold"))
            c.create_text(cx + 22 * s - 1, cy - 1, text=self.label, anchor="w", fill="#ffffff",
                          font=("Segoe UI", 10, "bold"))
        if self.shown is not True:
            self.overlay.attributes("-alpha", 1.0)
            self.shown = True

    def _icon_for(self, win):
        try:
            from PIL import ImageTk
            from .icon import tile
            return ImageTk.PhotoImage(tile(64), master=win)
        except Exception:
            return None

    def _make_main(self):
        from .main_window import MainWindow
        self._main_icon = self._icon_for(self.root)
        self.main_win = MainWindow(self.root, self.app, self._main_icon)
        if self.app.args.background:
            self.main_win.win.withdraw()

    def _open_setup(self):
        from .setup_window import SetupWindow
        if self.setup_win is not None and self.setup_win.alive():
            self.setup_win.win.lift()
            return
        self._setup_icon = self._icon_for(self.root)
        self.setup_win = SetupWindow(self.root, self.app, self._setup_icon)

    def _show_settings(self):
        from .settings_window import SettingsWindow
        if self.settings_win is not None and self.settings_win.alive():
            self.settings_win.show()
            return
        self._settings_icon = self._icon_for(self.root)
        self.settings_win = SettingsWindow(self.root, self.app, self._settings_icon)
