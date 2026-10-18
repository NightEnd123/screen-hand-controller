"""The settings window: sliders and switches for the common settings, in the glass style.
Saving writes config.toml (keeping its comments) and reloads the settings."""
import logging
import subprocess
import tkinter as tk

from . import config
from .glass import MUTED, SOFT, Glass, style_title_bar

log = logging.getLogger(__name__)

# (section, key, label, low, high, step, hint); low None = on/off switch
COLUMNS = [
    [("Cursor", [
        ("smoothing", "min_cutoff", "Steadiness when still", 0.1, 2.0, 0.05, "steadier  ←  →  more responsive"),
        ("smoothing", "beta", "Keep-up on fast moves", 0.0, 0.05, 0.001, "smoother  ←  →  less lag"),
        ("smoothing", "precision", "Precision mode (slow = finer)", None, None, None, None),
        ("smoothing", "precision_gain", "Precision strength", 0.2, 1.0, 0.05, "finer  ←  →  off"),
    ]),
     ("Clicks", [
         ("gestures", "pinch_dip", "Pinch sensitivity", 0.03, 0.10, 0.005,
          "tinier pinches count  ←  →  fewer accidental clicks"),
         ("gestures", "release_freeze_ms", "Cursor hold after a click (ms)", 0, 400, 10, "helps double-clicks line up"),
     ])],
    [("Scrolling, volume, swipes", [
        ("gestures", "scroll_gain", "Scroll speed", 5, 60, 1, None),
        ("gestures", "volume_gain", "Volume change speed", 4, 30, 1, None),
        ("gestures", "swipe_min_hands", "Swipe size needed", 0.4, 1.5, 0.05, "shorter swipes  ←  →  bigger swipes"),
    ]),
     ("Feedback", [
         ("feedback", "overlay", "Dot next to the cursor", None, None, None, None),
         ("feedback", "sounds", "Sounds on pause / resume", None, None, None, None),
         ("feedback", "notifications", "Pop-up notifications", None, None, None, None),
     ])],
]
CW, X0, Y0, GAP = 410, 24, 104, 16


def _row_height(item):
    return 40 if item[3] is None else (66 if item[6] else 54)


def _fmt(v, step):
    return f"{int(round(v))}" if float(step).is_integer() else f"{v:g}"


class SettingsWindow:
    def __init__(self, root, app, icon=None):
        self.app = app
        cfg = app.cfg
        win = self.win = tk.Toplevel(root)
        win.title("AirCursor settings")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        if icon is not None:
            win.iconphoto(False, icon)
        style_title_bar(win)
        heights = [sum(44 + sum(_row_height(i) for i in items) + 12 for _, items in col) + GAP * (len(col) - 1)
                   for col in COLUMNS]
        w = X0 * 2 + CW * 2 + GAP
        h = Y0 + max(heights) + 24 + 52 + 24
        g = self.g = Glass(win, w, h)
        g.accent_line(30, 28, 80)
        g.text(46, 22, "Settings", 22, "bold", kind="display")
        g.text(48, 60, "Changes apply when you click Save.", 11, color=SOFT)

        self.controls = {}
        for ci, col in enumerate(COLUMNS):
            x, y = X0 + ci * (CW + GAP), Y0
            for title, items in col:
                ch = 44 + sum(_row_height(i) for i in items) + 12
                g.card(x, y, CW, ch)
                g.text(x + 22, y + 18, title.upper(), 9, "bold", color=MUTED)
                ry = y + 44
                for item in items:
                    self._row(g, x, ry, item, cfg)
                    ry += _row_height(item)
                y += ch + GAP
            if ci == 1:   # per-app gestures under the right column
                apps = ", ".join(cfg.get("apps") or {}) or "none set up"
                g.text(x + 4, y + 4, f"Per-app gestures: {apps}. Change them in the settings file "
                       "(button below).", 9, color=SOFT, width=CW - 8)

        by = h - 24 - 52
        g.button(X0, by, 220, 52, "Open settings file", "edit", self._edit_file)
        g.button(w - X0 - 3 * 150 - 2 * 12, by, 150, 52, "Defaults", "undo", self._defaults)
        g.button(w - X0 - 2 * 150 - 12, by, 150, 52, "Cancel", "close", win.destroy)
        g.button(w - X0 - 150, by, 150, 52, "Save", "save", self._save, strong=True)
        self.error = g.text(X0 + 236, by + 26, "", 10, "bold", color="#ffd1d1", anchor="w")
        g.finish()
        win.update_idletasks()
        win.geometry(f"+{max((win.winfo_screenwidth() - win.winfo_width()) // 2, 0)}+"
                     f"{max((win.winfo_screenheight() - win.winfo_height()) // 4, 0)}")
        win.focus_force()

    def _row(self, g, x, y, item, cfg):
        sec, key, label, lo, hi, step, hint = item
        value = cfg[sec][key]
        if lo is None:
            g.text(x + 22, y + 13, label, 11, anchor="w")
            t = g.toggle(x + CW - 22 - 46, y, bool(value), None)
            self.controls[(sec, key)] = ("bool", t, None)
            return
        g.text(x + 22, y + 2, label, 11)
        shown = g.text(x + CW - 22, y + 2, _fmt(value, step), 11, "bold", anchor="ne")
        s = g.slider(x + 22, y + 32, CW - 44, lo, hi, step, value,
                     lambda v, it=shown, st=step: g.set(it, text=_fmt(v, st)))
        if hint:
            g.text(x + 22, y + 44, hint, 9, color=MUTED)
        self.controls[(sec, key)] = ("num", s, shown)

    # ---- buttons -------------------------------------------------------------------------------
    def _edit_file(self):
        subprocess.Popen(["notepad.exe", str(config.CONFIG_PATH)])

    def _defaults(self):
        for (sec, key), (kind, ctl, shown) in self.controls.items():
            v = config.DEFAULTS[sec][key]
            ctl.set(v)
            if shown is not None:
                self.g.set(shown, text=_fmt(ctl.value, ctl.step))

    def _save(self):
        updates = {}
        for (sec, key), (kind, ctl, _) in self.controls.items():
            if kind == "bool":
                updates[(sec, key)] = bool(ctl.value)
            elif float(ctl.step).is_integer() and float(config.DEFAULTS[sec][key]).is_integer():
                updates[(sec, key)] = int(round(ctl.value))
            else:
                updates[(sec, key)] = round(float(ctl.value), 4)
        try:
            config.set_values(updates)
        except Exception as e:
            log.exception("saving settings failed")
            self.g.set(self.error, text=f"Could not save: {e}")
            return
        self.app.reload_settings()
        self.win.destroy()

    def alive(self):
        return self.win.winfo_exists()

    def show(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
