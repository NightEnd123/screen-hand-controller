"""On-screen feedback dot next to the cursor + the settings window (Tk, on its own thread).

Other threads never touch Tk directly: they call feed()/open_settings(), which only set fields or
queue requests that the Tk thread picks up on its next tick.
"""
import ctypes
import logging
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk

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

    def open_settings(self):
        self.requests.put("settings")

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

    # ---- settings window -----------------------------------------------------------------------
    # (section, key, label, low, high, step, hint)
    SLIDERS = [
        ("Cursor", None),
        ("smoothing", "min_cutoff", "Steadiness when still", 0.1, 2.0, 0.05, "steadier ←  → more responsive"),
        ("smoothing", "beta", "Keep-up on fast moves", 0.0, 0.05, 0.001, "smoother ←  → less lag"),
        ("smoothing", "precision", "Precision mode (slow movement = finer control)", None, None, None, None),
        ("smoothing", "precision_gain", "Precision strength", 0.2, 1.0, 0.05, "finer ←  → off"),
        ("Clicks", None),
        ("gestures", "pinch_dip", "Pinch sensitivity", 0.03, 0.10, 0.005, "tinier pinches count ←  → fewer accidental clicks"),
        ("gestures", "release_freeze_ms", "Cursor hold after a click (ms)", 0, 400, 10, "helps double-clicks line up"),
        ("Scrolling, volume, swipes", None),
        ("gestures", "scroll_gain", "Scroll speed", 5, 60, 1, None),
        ("gestures", "volume_gain", "Volume change speed", 4, 30, 1, None),
        ("gestures", "swipe_min_dist", "Swipe size needed", 0.15, 0.5, 0.01, "shorter swipes ←  → bigger swipes"),
        ("Feedback", None),
        ("feedback", "overlay", "Show the dot next to the cursor", None, None, None, None),
        ("feedback", "sounds", "Sounds on pause / resume", None, None, None, None),
        ("feedback", "notifications", "Pop-up notifications", None, None, None, None),
    ]

    def _show_settings(self):
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.deiconify()
            self.settings_win.lift()
            self.settings_win.focus_force()
            return
        from . import config
        cfg = self.app.cfg
        win = tk.Toplevel(self.root)
        win.title("Gesture Control settings")
        try:
            from PIL import ImageTk
            from .tray import COLORS, make_icon
            self._icon = ImageTk.PhotoImage(make_icon(COLORS["active"], 32), master=win)
            win.iconphoto(False, self._icon)
        except Exception:
            pass
        win.attributes("-topmost", True)
        win.resizable(False, False)
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        self.vars = {}
        row = 0
        for item in self.SLIDERS:
            if item[1] is None:
                ttk.Label(body, text=item[0], font=("Segoe UI", 11, "bold")).grid(
                    row=row, column=0, columnspan=3, sticky="w", pady=(10 if row else 0, 2))
                row += 1
                continue
            sec, key, text, lo, hi, step, hint = item
            value = cfg[sec][key]
            if lo is None:
                var = tk.BooleanVar(value=bool(value))
                ttk.Checkbutton(body, text=text, variable=var).grid(row=row, column=0, columnspan=3, sticky="w")
            else:
                var = tk.DoubleVar(value=float(value))
                ttk.Label(body, text=text).grid(row=row, column=0, sticky="w", padx=(0, 10))
                shown = ttk.Label(body, width=6)
                shown.grid(row=row, column=2, sticky="e")

                def show(_=None, v=var, lbl=shown, st=step):
                    q = round(round(v.get() / st) * st, 4)
                    v.set(q)
                    lbl.config(text=f"{q:g}")
                tk.Scale(body, from_=lo, to=hi, resolution=step, orient="horizontal", length=260,
                         variable=var, showvalue=False, command=show).grid(row=row, column=1, sticky="we")
                show()
                var.trace_add("write", lambda *_, f=show, v=var, lbl=shown: lbl.config(text=f"{v.get():g}"))
                if hint:
                    row += 1
                    ttk.Label(body, text=hint, foreground="#6e7781", font=("Segoe UI", 8)).grid(
                        row=row, column=1, sticky="w")
            self.vars[(sec, key)] = (var, lo is None, step)
            row += 1

        apps = cfg.get("apps") or {}
        app_text = ", ".join(apps) if apps else "none set up"
        ttk.Label(body, text=f"Per-app gestures: {app_text}", foreground="#6e7781").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(12, 0))
        row += 1
        buttons = ttk.Frame(body)
        buttons.grid(row=row, column=0, columnspan=3, sticky="e", pady=(14, 0))

        def save():
            updates = {}
            for (sec, key), (var, is_bool, step) in self.vars.items():
                v = var.get()
                if is_bool:
                    updates[(sec, key)] = bool(v)
                elif float(step).is_integer() and float(config.DEFAULTS[sec][key]).is_integer():
                    updates[(sec, key)] = int(round(v))
                else:
                    updates[(sec, key)] = round(float(v), 4)
            try:
                config.set_values(updates)
            except Exception as e:
                log.exception("saving settings failed")
                ttk.Label(body, text=f"Could not save: {e}", foreground="red").grid(row=row + 1, column=0, columnspan=3)
                return
            self.app.reload_settings()
            win.destroy()

        def defaults():
            for (sec, key), (var, is_bool, step) in self.vars.items():
                var.set(config.DEFAULTS[sec][key])

        def edit_file():
            subprocess.Popen(["notepad.exe", str(config.CONFIG_PATH)])

        ttk.Button(buttons, text="Edit per-app gestures…", command=edit_file).pack(side="left", padx=(0, 24))
        ttk.Button(buttons, text="Defaults", command=defaults).pack(side="left", padx=4)
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="left", padx=4)
        ttk.Button(buttons, text="Save", command=save).pack(side="left", padx=4)
        self.settings_win = win
        win.focus_force()
