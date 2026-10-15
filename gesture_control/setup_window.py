"""The first-run setup window (Tk). Lives on the UI thread; see setup_wizard.py for the logic.

The engine thread hands over (View, RGB picture) through UI.setup_feed(); this window only reads the
latest pair on each Tk tick. Buttons call back into the app with App.wizard_cmd().
"""
import tkinter as tk
from tkinter import ttk

from .setup_wizard import GESTURE_SHEET

BG = "#ffffff"
MUTED = "#57606a"
WARN = "#9a6700"


class SetupWindow:
    def __init__(self, root, app, icon=None):
        self.app = app
        self.step = None
        self.photo = None
        win = self.win = tk.Toplevel(root)
        win.title("Gesture Control setup")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        if icon is not None:
            win.iconphoto(False, icon)
        win.protocol("WM_DELETE_WINDOW", lambda: app.wizard_cmd("cancel"))

        style = ttk.Style(win)
        style.configure("Setup.TFrame", background=BG)
        style.configure("Setup.TLabel", background=BG)
        style.configure("Big.TButton", font=("Segoe UI", 12), padding=(18, 8))

        outer = ttk.Frame(win, padding=18, style="Setup.TFrame")
        outer.pack(fill="both", expand=True)
        self.stepl = ttk.Label(outer, style="Setup.TLabel", foreground=MUTED, font=("Segoe UI", 9))
        self.stepl.pack(anchor="w")
        self.title = ttk.Label(outer, style="Setup.TLabel", font=("Segoe UI", 18, "bold"))
        self.title.pack(anchor="w", pady=(0, 10))

        row = ttk.Frame(outer, style="Setup.TFrame")
        row.pack(fill="both", expand=True)
        box = self.picture_box = tk.Frame(row, width=512, height=384, bg="#1f2328")
        box.pack_propagate(False)
        box.pack(side="left", anchor="n")
        self.picture = tk.Label(box, bg="#1f2328", fg="#d0d7de", text="Starting the camera…",
                                font=("Segoe UI", 11))
        self.picture.pack(fill="both", expand=True)
        side = ttk.Frame(row, padding=(18, 0, 0, 0), style="Setup.TFrame")
        side.pack(side="left", fill="both", expand=True)
        self.text = ttk.Label(side, style="Setup.TLabel", wraplength=360, justify="left", font=("Segoe UI", 11))
        self.text.pack(anchor="w")
        self.sheet = ttk.Frame(side, style="Setup.TFrame")
        self.sheet.pack(anchor="w", pady=(10, 0))
        self.warn = ttk.Label(side, style="Setup.TLabel", wraplength=360, justify="left",
                              foreground=WARN, font=("Segoe UI", 10, "bold"))
        self.warn.pack(anchor="w", pady=(14, 0))
        self.bar = ttk.Progressbar(side, length=360, maximum=1.0)
        self.bar.pack(anchor="w", pady=(14, 0))

        self.buttons = ttk.Frame(outer, style="Setup.TFrame")
        self.buttons.pack(fill="x", pady=(16, 0))
        self.privacy = ttk.Label(outer, style="Setup.TLabel", foreground=MUTED, font=("Segoe UI", 8),
                                 text="The camera picture stays on this computer and is never saved.")
        self.privacy.pack(anchor="w", pady=(10, 0))
        win.update_idletasks()
        win.geometry(f"+{max((win.winfo_screenwidth() - win.winfo_width()) // 2, 0)}+"
                     f"{max((win.winfo_screenheight() - win.winfo_height()) // 3, 0)}")
        win.focus_force()

    def alive(self):
        return self.win.winfo_exists()

    def close(self):
        if self.alive():
            self.win.destroy()

    def show(self, view, rgb):
        if view is None:
            return
        if view.step != self.step:
            self.step = view.step
            self._build_buttons(view.step)
            self._build_sheet(view.step == "done")
            if view.step == "done":   # the cheat sheet gets the whole window
                self.picture_box.pack_forget()
                self.text.config(wraplength=600)
        self.stepl.config(text=f"Step {view.number} of {view.total}")
        self.title.config(text=view.title)
        self.text.config(text=view.text)
        self.warn.config(text=view.warn)
        self.bar["value"] = view.progress
        if view.step in ("welcome", "done"):
            self.bar.pack_forget()
        elif not self.bar.winfo_ismapped():
            self.bar.pack(anchor="w", pady=(14, 0))
        if rgb is not None and view.step != "done":
            from PIL import Image, ImageTk
            self.photo = ImageTk.PhotoImage(Image.fromarray(rgb), master=self.win)
            self.picture.config(image=self.photo, text="")
        elif view.title == "Camera":
            self.picture.config(image="", text="No camera picture")
            self.photo = None

    def _build_buttons(self, step):
        for w in self.buttons.winfo_children():
            w.destroy()
        cmd = self.app.wizard_cmd
        if step == "welcome":
            ttk.Button(self.buttons, text="✋  Left hand", style="Big.TButton",
                       command=lambda: cmd("hand", "left")).pack(side="left", padx=(0, 8))
            ttk.Button(self.buttons, text="Right hand  ✋", style="Big.TButton",
                       command=lambda: cmd("hand", "right")).pack(side="left")
            ttk.Button(self.buttons, text="Skip setup", command=lambda: cmd("skip_all")).pack(side="right")
            ttk.Button(self.buttons, text="Use another camera",
                       command=lambda: cmd("camera_next")).pack(side="right", padx=8)
        elif step == "done":
            ttk.Button(self.buttons, text="Finish", style="Big.TButton",
                       command=lambda: cmd("finish")).pack(side="right")
        else:
            ttk.Button(self.buttons, text="Cancel", command=lambda: cmd("cancel")).pack(side="right")
            ttk.Button(self.buttons, text="Skip this step",
                       command=lambda: cmd("skip")).pack(side="right", padx=8)

    def _build_sheet(self, show):
        for w in self.sheet.winfo_children():
            w.destroy()
        if not show:
            return
        for r, (gesture, action) in enumerate(GESTURE_SHEET):
            ttk.Label(self.sheet, text=gesture, style="Setup.TLabel", font=("Segoe UI", 9, "bold")).grid(
                row=r, column=0, sticky="nw", padx=(0, 12), pady=1)
            ttk.Label(self.sheet, text=action, style="Setup.TLabel", font=("Segoe UI", 9),
                      wraplength=330, justify="left").grid(row=r, column=1, sticky="nw", pady=1)
