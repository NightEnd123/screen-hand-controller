"""The first-run setup window, in the frosted-glass style (glass.py). Lives on the UI thread; see
setup_wizard.py for the logic.

The engine thread hands over (View, RGB picture) through UI.setup_feed(); this window only reads the
latest pair on each Tk tick. Buttons call back into the app with App.wizard_cmd(). Each step has
its own buttons, so the canvas is rebuilt when the step changes.
"""
import tkinter as tk

from .glass import ACCENT, MUTED, SOFT, Glass, style_title_bar
from .guide_window import draw_sheet
from .setup_wizard import STEPS

W, H = 1000, 654
CAM = (40, 120, 568, 426)
WARN = "#ffe9a8"


class SetupWindow:
    def __init__(self, root, app, icon=None):
        self.app = app
        self.step = None
        win = self.win = tk.Toplevel(root)
        win.title("AirCursor setup")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        if icon is not None:
            win.iconphoto(False, icon)
        win.protocol("WM_DELETE_WINDOW", lambda: app.wizard_cmd("cancel"))
        style_title_bar(win)
        self.g = Glass(win, W, H, dots=False)
        self._build("welcome")
        win.update_idletasks()
        win.geometry(f"+{max((win.winfo_screenwidth() - win.winfo_width()) // 2, 0)}+"
                     f"{max((win.winfo_screenheight() - win.winfo_height()) // 3, 0)}")
        win.focus_force()

    def alive(self):
        return self.win.winfo_exists()

    def close(self):
        if self.alive():
            self.win.destroy()

    def _build(self, step):
        g, cmd = self.g, self.app.wizard_cmd
        g.reset()
        self.step = step
        n = STEPS.index(step)

        # header with step dots
        g.accent_line(30, 28, 80)
        g.text(46, 22, "Set up AirCursor", 22, "bold", kind="display")
        g.text(48, 60, "About two minutes. Nothing is saved until you click Finish.", 11, color=SOFT)
        for i in range(len(STEPS)):
            x, r = W - 84 - (len(STEPS) - 1 - i) * 22, 7 if i == n else 5
            fill, outline = (ACCENT, ACCENT) if i == n else ("#ffffff", "#ffffff") if i < n else ("", "#5c6172")
            g.canvas.create_oval(g.px(x - r), g.px(48 - r), g.px(x + r), g.px(48 + r), fill=fill,
                                 outline=outline, width=max(1, g.px(1.2)))

        # left: camera, or the gesture sheet on the last step
        self.slot = None
        if step == "done":
            draw_sheet(g, 24, 104, cols=3, tw=192, th=122, gap=13, size=10)
        else:
            g.card(24, 104, 600, 458)
            self.slot = g.photo_slot(*CAM, r=16)
            self.slot.message("Starting the camera…")

        # right: instructions
        g.card(640, 104, 336, 380)
        self.stepl = g.text(664, 124, "", 9, "bold", color=MUTED)
        self.title = g.text(664, 146, "", 21, "bold", width=290, kind="display")
        self.text = g.text(664, 196, "", 11, color=SOFT, width=290)
        self.warn = g.text(664, 404, "", 10, "bold", color=WARN, width=290, anchor="sw")
        self.bar = g.progress(664, 452, 288, 0) if step not in ("welcome", "done") else None

        # buttons
        if step == "welcome":
            g.button(640, 500, 164, 62, "Left hand", "left", lambda: cmd("hand", "left"), strong=True, size=12)
            g.button(812, 500, 164, 62, "Right hand", "right", lambda: cmd("hand", "right"), strong=True, size=12)
            g.button(24, 578, 230, 50, "Use another camera", "camera", lambda: cmd("camera_next"))
            g.button(266, 578, 160, 50, "Skip setup", "next", lambda: cmd("skip_all"))
            g.text(976, 600, "The camera picture stays on this computer and is never saved.", 9,
                   color=MUTED, anchor="e")
        elif step == "done":
            g.button(640, 500, 336, 62, "Finish", "check", lambda: cmd("finish"), strong=True, size=13)
            g.text(24, 600, "Change any of this later from the main window: Settings, Run setup, Calibrate area.",
                   9, color=MUTED, anchor="w")
        else:
            g.button(640, 500, 164, 62, "Skip this step", "next", lambda: cmd("skip"))
            g.button(812, 500, 164, 62, "Cancel", "close", lambda: cmd("cancel"))
            g.text(24, 600, "The camera picture stays on this computer and is never saved.", 9,
                   color=MUTED, anchor="w")
        g.finish()

    def show(self, view, rgb):
        if view is None:
            return
        if view.step != self.step:
            self._build(view.step)
        g = self.g
        g.set(self.stepl, text=f"STEP {view.number} OF {view.total}")
        if g.canvas.itemcget(self.title, "text") != view.title:
            g.set(self.title, text=view.title)
            # the instructions go right under the title, however many lines it wraps to
            g.canvas.coords(self.text, g.px(664), g.canvas.bbox(self.title)[3] + g.px(10))
        g.set(self.text, text=view.text)
        g.set(self.warn, text=view.warn)
        if self.bar is not None:
            self.bar.set(view.progress)
        if self.slot is not None:
            if rgb is not None:
                self.slot.set(rgb)
            elif view.title == "Camera":
                self.slot.message(view.text)
