"""The main window (Tk): shows in the taskbar, with status, an optional live camera view and the
main controls. Lives on the UI thread; the engine thread only hands over the latest status and
picture through UI.main_feed(). Buttons call App methods, which queue work for the engine thread.

Closing the window hides it; the app keeps running in the tray (tray icon -> Open brings it back).
"""
import tkinter as tk
from tkinter import ttk

from . import __version__
from .setup_wizard import GESTURE_SHEET

BG = "#ffffff"
PANEL = "#f6f8fa"
MUTED = "#57606a"
STATES = {   # tray state -> (dot colour, title, explanation)
    "active": ("#2da44e", "Active", "Gestures control your mouse."),
    "paused": ("#d4a72c", "Paused", "Gestures do nothing. Hold a thumbs-up, press Ctrl+Alt+G or click Resume."),
    "off": ("#8c959f", "Camera off", "The camera is switched off. Click Turn camera on, or press Ctrl+Alt+G."),
    "error": ("#cf222e", "Camera problem", "No picture from the camera. What to try is shown on the left."),
    "calibrating": ("#0969da", "Setting up", "Follow the instructions in the camera view."),
}
MODES = {
    "idle": "No hand in view", "point": "Pointing", "ok": "Pointing (👌)", "lpinch": "Clicking",
    "drag": "Dragging", "rpinch": "Right click", "scroll": "Scrolling", "switcher": "Switching windows",
    "palm": "Open palm", "victory": "V-sign", "volume": "Changing volume", "call": "Call-me sign",
    "rest": "Hand resting", "paused": "Paused", "typing": "Typing (gestures off for a moment)",
    "calibrating": "Setting up",
}
VIEW = (512, 384)
CAMERA_HELP = ("No picture from the camera.\n\n"
               "\u2022 Close other apps that use it (Teams, Zoom, the Camera app).\n"
               "\u2022 Windows Settings > Privacy & security > Camera:\n"
               "   turn on Camera access and \"Let desktop apps access your camera\".\n"
               "\u2022 Wrong camera? Run setup again and pick another.\n\n"
               "The app keeps trying in the background.")


class MainWindow:
    def __init__(self, root, app, icon=None):
        self.app = app
        self.photo = None
        self.camera_on = False
        self.state = None
        self.told_hidden = False
        self.showing_help = False
        win = self.win = tk.Toplevel(root)
        win.title("Gesture Control")
        win.configure(bg=BG)
        win.resizable(False, False)
        if icon is not None:
            win.iconphoto(False, icon)
        win.protocol("WM_DELETE_WINDOW", self.hide)

        style = ttk.Style(win)
        style.configure("Main.TFrame", background=BG)
        style.configure("Main.TLabel", background=BG)
        style.configure("Main.TCheckbutton", background=BG)
        style.configure("Big.TButton", font=("Segoe UI", 12), padding=(14, 8))

        outer = ttk.Frame(win, padding=16, style="Main.TFrame")
        outer.pack(fill="both", expand=True)

        # ---- left: camera view ----
        left = ttk.Frame(outer, style="Main.TFrame")
        left.pack(side="left", anchor="n")
        box = tk.Frame(left, width=VIEW[0], height=VIEW[1], bg="#1f2328")
        box.pack_propagate(False)
        box.pack()
        self.picture = tk.Label(box, bg="#1f2328", fg="#d0d7de", font=("Segoe UI", 11), justify="center",
                                wraplength=VIEW[0] - 40)
        self.picture.pack(fill="both", expand=True)
        row = ttk.Frame(left, style="Main.TFrame")
        row.pack(fill="x", pady=(10, 0))
        self.cam_btn = ttk.Button(row, command=self.toggle_camera_view)
        self.cam_btn.pack(side="left")
        self.now = ttk.Label(row, style="Main.TLabel", font=("Segoe UI", 10))
        self.now.pack(side="left", padx=(12, 0))
        self.last = ttk.Label(left, style="Main.TLabel", foreground=MUTED, font=("Segoe UI", 9))
        self.last.pack(anchor="w", pady=(6, 0))
        bar_row = tk.Frame(left, height=22, bg=BG)   # fixed room so the window never changes size
        bar_row.pack_propagate(False)
        bar_row.pack(fill="x", pady=(6, 0))
        self.bar = ttk.Progressbar(bar_row, length=VIEW[0], maximum=1.0)

        # ---- right: status and controls ----
        right = ttk.Frame(outer, padding=(18, 0, 0, 0), style="Main.TFrame")
        right.pack(side="left", fill="y")
        head = ttk.Frame(right, style="Main.TFrame")
        head.pack(anchor="w")
        self.dot = tk.Canvas(head, width=18, height=18, bg=BG, highlightthickness=0)
        self.dot.pack(side="left")
        self.title = ttk.Label(head, style="Main.TLabel", font=("Segoe UI", 16, "bold"))
        self.title.pack(side="left", padx=(8, 0))
        self.explain = tk.Label(right, bg=BG, fg=MUTED, font=("Segoe UI", 10), wraplength=270,
                                justify="left", anchor="nw", height=3)
        self.explain.pack(anchor="w", fill="x", pady=(4, 10))

        self.pause_btn = ttk.Button(right, style="Big.TButton", width=20,
                                    command=lambda: app.toggle_pause("window"))
        self.pause_btn.pack(anchor="w", fill="x")
        self.camoff_btn = ttk.Button(right, width=20, command=lambda: app.set_camera_off(not app.camera_off))
        self.camoff_btn.pack(anchor="w", fill="x", pady=(6, 0))

        ttk.Separator(right).pack(fill="x", pady=14)
        for text, cmd in (("Gesture guide", self.show_guide),
                          ("Settings…", app.open_settings),
                          ("Run setup again", app.start_wizard),
                          ("Calibrate control area", app.start_calibration)):
            ttk.Button(right, text=text, command=cmd).pack(anchor="w", fill="x", pady=2)
        self.startup = tk.BooleanVar(value=app.startup_enabled())
        ttk.Checkbutton(right, text="Start with Windows", variable=self.startup, style="Main.TCheckbutton",
                        command=self._toggle_startup).pack(anchor="w", pady=(10, 0))

        spacer = ttk.Frame(right, style="Main.TFrame")
        spacer.pack(fill="both", expand=True)
        ttk.Button(right, text="Quit Gesture Control", command=app.quit).pack(anchor="w", fill="x", pady=(14, 0))
        self.stats = ttk.Label(right, style="Main.TLabel", foreground=MUTED, font=("Segoe UI", 8))
        self.stats.pack(anchor="w", pady=(8, 0))

        self.guide = None
        self._update_camera_button()
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
        self._update_camera_button()
        if not self.camera_on:
            self._placeholder()

    def _update_camera_button(self):
        self.cam_btn.config(text="Hide camera view" if self.camera_on else "Show camera view")

    def _placeholder(self, text=None):
        self.photo = None
        self.picture.config(image="", text=text or (
            "Camera view is hidden.\n\nClick \"Show camera view\" to see your hand's\n"
            "tracking points and the control area.\n\nThe picture is never saved."))

    # ---- updates from the engine thread (via UI) ---------------------------------------------
    def update(self, status, rgb):
        state = status.get("state", "active")
        if state != self.state:
            self.state = state
            color, title, text = STATES.get(state, STATES["active"])
            self.dot.delete("all")
            self.dot.create_oval(2, 2, 16, 16, fill=color, outline="")
            self.title.config(text=title)
            self.explain.config(text=text)
        paused = state in ("paused", "off")
        self.pause_btn.config(text="▶  Resume" if paused else "⏸  Pause")
        self.camoff_btn.config(text="Turn camera on" if state == "off" else "Turn camera off")

        banner = status.get("banner")
        mode = MODES.get(status.get("mode"), status.get("mode") or "")
        self.now.config(text=banner or f"Now: {mode}")
        self.last.config(text=f"Last action: {status['last']}" if status.get("last") else "")
        progress = status.get("progress")
        if progress is not None:
            if not self.bar.winfo_ismapped():
                self.bar.pack(anchor="w")
            self.bar["value"] = progress
        elif self.bar.winfo_ismapped():
            self.bar.pack_forget()
        self.stats.config(text=f"{status.get('fps', 0):.0f} fps · {status.get('cpu', 0):.0f}% CPU · v{__version__}")

        if state == "error":
            self.photo = None
            self.picture.config(image="", text=CAMERA_HELP, justify="left", font=("Segoe UI", 10))
            self.showing_help = True
        elif self.showing_help:
            self.showing_help = False
            self.picture.config(justify="center", font=("Segoe UI", 11))
            if not self.camera_on:
                self._placeholder()
        if self.camera_on and state != "error":
            if rgb is not None:
                from PIL import Image, ImageTk
                self.photo = ImageTk.PhotoImage(Image.fromarray(rgb), master=self.win)
                self.picture.config(image=self.photo, text="")
            elif state == "off":
                self._placeholder("The camera is off.")

    def _toggle_startup(self):
        self.app.toggle_startup()
        self.startup.set(self.app.startup_enabled())

    # ---- gesture guide -----------------------------------------------------------------------
    def show_guide(self):
        if self.guide is not None and self.guide.winfo_exists():
            self.guide.deiconify()
            self.guide.lift()
            return
        g = self.guide = tk.Toplevel(self.win)
        g.title("Gestures")
        g.configure(bg=BG)
        g.resizable(False, False)
        body = ttk.Frame(g, padding=16, style="Main.TFrame")
        body.pack()
        ttk.Label(body, text="Hold your hand up with the palm toward the screen.", style="Main.TLabel",
                  font=("Segoe UI", 10)).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        for r, (gesture, action) in enumerate(GESTURE_SHEET, 1):
            ttk.Label(body, text=gesture, style="Main.TLabel", font=("Segoe UI", 10, "bold")).grid(
                row=r, column=0, sticky="nw", padx=(0, 14), pady=2)
            ttk.Label(body, text=action, style="Main.TLabel", font=("Segoe UI", 10), wraplength=320,
                      justify="left").grid(row=r, column=1, sticky="nw", pady=2)
        ttk.Button(body, text="Close", command=g.destroy).grid(row=len(GESTURE_SHEET) + 1, column=1,
                                                               sticky="e", pady=(12, 0))
