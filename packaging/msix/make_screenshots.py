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
from PIL import Image, ImageDraw, ImageFilter

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


def neon_wall(W, H, left_x, right_x, top, bottom):
    """A dark textured wall lit by a cyan neon tube on the left and a pink one on the right."""
    rng = np.random.default_rng(4)
    noise = rng.normal(0, 1, (H // 2, W // 2)).astype(np.float32)
    noise = cv2.GaussianBlur(noise, (0, 0), 1.2)
    noise = cv2.resize(noise, (W, H))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    vign = 1 - 0.45 * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 1.6)) ** 2)
    base = np.array((34, 48, 56), np.float32)[None, None, :] * vign[..., None]
    base = base + noise[..., None] * 6
    img = np.clip(base, 0, 255)
    for x, color in ((left_x, (40, 225, 255)), (right_x, (255, 80, 205))):
        d = np.abs(xx - x)
        inside = (yy > top) & (yy < bottom)
        ydist = np.where(inside, 0, np.minimum(np.abs(yy - top), np.abs(yy - bottom)))
        r = np.hypot(d, ydist)
        glow = np.exp(-(r / 170) ** 2) * 0.85 + np.exp(-(r / 45) ** 2) * 0.6
        img = img + glow[..., None] * np.array(color, np.float32)[None, None, :] * 0.75
    img = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(img)
    for x, color in ((left_x, (120, 240, 255)), (right_x, (255, 150, 230))):
        d.rounded_rectangle((x - 7, top, x + 7, bottom), radius=7, fill=color + (255,))
        d.rounded_rectangle((x - 3, top + 4, x + 3, bottom - 4), radius=3, fill=(245, 252, 255, 255))
    return img


def compose(shot, name):
    W, H = 1920, 1080
    scale = min((W - 380) / shot.width, (H - 150) / shot.height, 1.0)
    shot = shot.resize((round(shot.width * scale), round(shot.height * scale)), Image.LANCZOS)
    x, y = (W - shot.width) // 2, (H - shot.height) // 2
    bg = neon_wall(W, H, x - 46, x + shot.width + 46, y + 40, y + shot.height - 40)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    a = Image.new("L", (W, H), 0)
    a.paste(150, (x + 4, y + 22, x + shot.width + 4, y + shot.height + 22))
    shadow.putalpha(a.filter(ImageFilter.GaussianBlur(26)))
    bg = Image.alpha_composite(bg, shadow)
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, shot.width - 1, shot.height - 1), radius=14, fill=255)
    bg.paste(shot, (x, y), mask)
    OUT.mkdir(exist_ok=True)
    bg.convert("RGB").save(OUT / f"{name}.png")
    print("saved", OUT / f"{name}.png")


def demo_stats():
    """A believable 10-minute session for the dashboard charts (made up, no camera)."""
    import math
    import random
    import time
    from gesture_control.stats import SessionStats
    st = SessionStats()
    random.seed(11)
    t0 = time.perf_counter() - 600
    x = y = 600.0
    modes = ["point"] * 60 + ["lpinch"] * 10 + ["scroll"] * 9 + ["palm"] * 7 + ["switcher"] * 4 + ["victory"] * 5
    mode = "point"
    for i in range(6000):
        sec = i / 10
        state = "paused" if 190 < sec < 240 else "off" if 515 < sec < 530 else "active"
        if i % 15 == 0:
            mode = random.choice(modes) if (sec % 80) < 66 else "idle"
        acts = []
        if state == "active" and mode != "idle":
            r = random.random()
            if mode == "lpinch" and r < 0.05:
                acts = [("down", "left")]
            elif mode == "palm" and r < 0.03:
                acts = [("keys", "ctrl+tab", "swipe_right")]
        if 240 <= sec < 240.1:
            acts = [("pause", True)]
        sp = 260 + 220 * math.sin(sec / 6.5) + 160 * math.sin(sec / 2.3) + (sec > 565) * 380
        x += random.uniform(-1, 1) * max(sp, 30) / 10
        y += random.uniform(-1, 1) * max(sp, 30) / 10
        st.add(t0 + sec, state, mode, acts, (x, y) if mode != "idle" else None)
    return st


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
    status = {"state": "active", "mode": "point", "fps": 30, "cpu": 7, "last": "Next tab", "stats": demo_stats()}
    w.update(status, None)
    settle(root)
    compose(grab(w.win), "1-dashboard")
    w.toggle_camera_view(True)
    w.update(status, picture(pose("point", center=(0.47, 0.42)), [0.275, 0.22, 0.725, 0.62]))
    settle(root)
    compose(grab(w.win), "2-camera-view")

    guide = w.show_guide() or w.guide
    settle(root)
    compose(grab(guide.win), "5-gesture-guide")
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
    compose(grab(sw.win), "3-setup")
    sw.close()

    s = SettingsWindow(root, app, icon)
    settle(root)
    compose(grab(s.win), "4-settings")
    s.win.destroy()


if __name__ == "__main__":
    main()
