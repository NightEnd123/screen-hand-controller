"""Gesture guide: one glass tile per gesture."""
import tkinter as tk

from .glass import SOFT, Glass, style_title_bar
from .setup_wizard import GESTURE_SHEET

COLS, TW, TH, GAP = 3, 250, 112, 14


def draw_sheet(g, x, y, cols=COLS, tw=TW, th=TH, gap=GAP, size=11):
    """Bake the gesture tiles into Glass `g` starting at (x, y). Returns the bottom edge.
    Each action sits just under its gesture name, however many lines that name wraps to."""
    pad = 16 if size >= 11 else 13
    for i, (gesture, action) in enumerate(GESTURE_SHEET):
        cx, cy = x + (i % cols) * (tw + gap), y + (i // cols) * (th + gap)
        g.card(cx, cy, tw, th, r=18)
        name = g.text(cx + pad, cy + pad - 2, gesture, size, "bold", width=tw - 2 * pad)
        below = g.canvas.bbox(name)[3] / g.s + 6
        g.text(cx + pad, below, action, size - 1, color=SOFT, width=tw - 2 * pad)
    rows = (len(GESTURE_SHEET) + cols - 1) // cols
    return y + rows * (th + gap) - gap


class GuideWindow:
    def __init__(self, parent):
        win = self.win = tk.Toplevel(parent)
        win.title("Gestures")
        win.resizable(False, False)
        style_title_bar(win)
        w = 28 * 2 + COLS * TW + (COLS - 1) * GAP
        rows = (len(GESTURE_SHEET) + COLS - 1) // COLS
        h = 112 + rows * (TH + GAP) - GAP + 96
        g = self.g = Glass(win, w, h)
        g.text(28, 24, "Gestures", 24, "bold", kind="display")
        g.text(30, 66, "Hold your hand up with the palm toward the screen. Both hands work the same way.",
               11, color=SOFT)
        draw_sheet(g, 28, 112)
        g.button(w - 28 - 140, h - 28 - 46, 140, 46, "Close", "close", win.destroy)
        g.finish()

    def alive(self):
        return self.win.winfo_exists()

    def show(self):
        self.win.deiconify()
        self.win.lift()
