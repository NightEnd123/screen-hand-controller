"""Make Microsoft Store screenshots (1920x1080 PNGs) of the real windows, filled with demo data:
a synthetic hand from the tests, never a real camera picture. Each window is captured on its
own (PrintWindow, so nothing else on screen can end up in the picture) and placed on the app's
gradient background.

Run:  .venv\\Scripts\\python.exe packaging\\msix\\make_screenshots.py
"""
import copy
import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent / "screenshots"
user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))


class _BIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def grab(win):
    """The window's own pixels (including the title bar), whatever is on top of it."""
    hwnd = user32.GetParent(win.winfo_id())
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    vis = wintypes.RECT()   # the visible frame, without the invisible resize borders
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(vis), ctypes.sizeof(vis))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, 2)
    bih = _BIH(ctypes.sizeof(_BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bih), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    return img.crop((vis.left - r.left, vis.top - r.top, vis.right - r.left, vis.bottom - r.top))


def compose(shot, name):
    from gesture_control.glass import background
    W, H = 1920, 1080
    bg = background(W, H)
    scale = min((W - 160) / shot.width, (H - 120) / shot.height, 1.0)
    shot = shot.resize((round(shot.width * scale), round(shot.height * scale)), Image.LANCZOS)
    x, y = (W - shot.width) // 2, (H - shot.height) // 2
    shadow = Image.new("RGBA", (W, H), (20, 16, 60, 0))
    a = Image.new("L", (W, H), 0)
    a.paste(110, (x + 6, y + 18, x + shot.width + 6, y + shot.height + 18))
    shadow.putalpha(a.filter(ImageFilter.GaussianBlur(28)))
    bg = Image.alpha_composite(bg, shadow)
    bg.paste(shot, (x, y))
    OUT.mkdir(exist_ok=True)
    bg.convert("RGB").save(OUT / f"{name}.png")
    print("saved", OUT / f"{name}.png")


def settle(root):
    root.update()
    root.after(300)
    root.update()


def main():
    import tkinter as tk
    from gesture_control.config import DEFAULTS
    from gesture_control.main_window import MainWindow
    from gesture_control.preview import annotate
    from gesture_control.settings_window import SettingsWindow
    from gesture_control.setup_wizard import SetupWizard
    from gesture_control.setup_window import SetupWindow
    from tests.synth import pose

    class DemoApp:
        camera_off = False
        cfg = copy.deepcopy(DEFAULTS)
        cfg["apps"] = {"POWERPNT.EXE": {}, "Spotify.exe": {}}

        def __getattr__(self, name):
            return lambda *a, **k: None

        def startup_enabled(self):
            return True

    root = tk.Tk()
    root.withdraw()
    root.tk.call("tk", "scaling", user32.GetDpiForSystem() / 72)
    # a soft dark-slate backdrop (BGR), clearly not a real camera picture
    ys = np.linspace(0, 1, 480, dtype=np.float32)[:, None, None]
    backdrop = (np.array([88, 72, 60], np.float32) * (1 - ys) + np.array([60, 50, 46], np.float32) * ys)
    backdrop = np.repeat(backdrop, 640, axis=1).astype(np.uint8)

    def picture(hand, box=None):
        return cv2.cvtColor(annotate(backdrop, hand, box, (80, 200, 80)), cv2.COLOR_BGR2RGB)

    from PIL import ImageTk
    from gesture_control.icon import tile
    icon = ImageTk.PhotoImage(tile(64), master=root)
    app = DemoApp()
    w = MainWindow(root, app, icon)
    w.toggle_camera_view(True)
    w.update({"state": "active", "mode": "point", "fps": 30, "cpu": 8, "last": "Next tab"},
             picture(pose("point", center=(0.47, 0.42)), w.g.canvas and [0.275, 0.22, 0.725, 0.62]))
    settle(root)
    compose(grab(w.win), "1-main-window")

    guide = w.show_guide() or w.guide
    settle(root)
    compose(grab(guide.win), "4-gesture-guide")
    guide.win.destroy()
    w.close()

    class SetupApp(DemoApp):
        def __init__(self):
            self.wz = SetupWizard(DEFAULTS, 16 / 9, 4 / 3, True)

        def wizard_cmd(self, name, arg=None):
            pass
    sa = SetupApp()
    sw = SetupWindow(root, sa, icon)
    sa.wz.choose_hand("right")
    t, v = 0.0, None
    for _ in range(20):
        t += 1 / 30
        v = sa.wz.update(t, pose("palm", center=(0.5, 0.45)))
    sw.show(v, picture(pose("palm", center=(0.5, 0.45))))
    settle(root)
    compose(grab(sw.win), "2-setup")
    sw.close()

    s = SettingsWindow(root, app, icon)
    settle(root)
    compose(grab(s.win), "3-settings")
    s.win.destroy()


if __name__ == "__main__":
    main()
