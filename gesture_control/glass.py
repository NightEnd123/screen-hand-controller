"""Dark neon look for the app's windows (one Tk Canvas per window + Pillow).

The background of a window (charcoal, soft dark spheres, glowing blue/violet lines and rings, and
every card and pill) is rendered once with Pillow into one image: each card blurs what is behind
it, darkens it, rounds the corners and gets a faint border and a soft shadow. Live things are canvas items on
top: text, icons, the camera picture, hover highlights, toggles, sliders and progress bars.

Coordinates given to Glass are logical (96-dpi) pixels; Glass scales them for the screen.
Only the Tk thread may use this module.
"""
import ctypes
import tkinter as tk
import tkinter.font as tkfont

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageTk

TEXT = "#ffffff"
SOFT = "#b9bdcc"
MUTED = "#7f8498"
ACCENT = "#7c5cff"         # violet: switches, progress, highlights
BLUE = (37, 99, 255)
VIOLET = (112, 80, 255)
BG_TOP, BG_BOTTOM = (24, 25, 29), (15, 16, 19)
TITLE_BAR = (21, 22, 26)   # Windows 11 title bar colour, matches the top of the background

ICONS = {   # Segoe Fluent Icons / Segoe MDL2 Assets code points
    "play": "", "pause": "", "camera": "", "settings": "",
    "guide": "", "setup": "", "calibrate": "", "power": "",
    "check": "", "warning": "", "windows": "", "next": "",
    "close": "", "save": "", "undo": "", "edit": "", "eye": "",
    "hand": "", "sync": "", "mouse": "", "left": "", "right": "",
}

_user32 = ctypes.windll.user32


def screen_scale():
    try:
        return _user32.GetDpiForSystem() / 96
    except Exception:
        return 1.0


_families = {}


def family(kind):
    """'display' / 'text' / 'icons' -> best installed font family."""
    if kind not in _families:
        have = set(tkfont.families())
        prefs = {"display": ("Segoe UI Variable Display", "Segoe UI"),
                 "text": ("Segoe UI Variable Text", "Segoe UI"),
                 "icons": ("Segoe Fluent Icons", "Segoe MDL2 Assets")}[kind]
        _families[kind] = next((f for f in prefs if f in have), prefs[-1])
    return _families[kind]


def style_title_bar(win):
    """Windows 11: colour the native title bar to match (ignored on older Windows)."""
    try:
        win.update_idletasks()
        hwnd = _user32.GetParent(win.winfo_id())
        dwm = ctypes.windll.dwmapi
        one = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(one), 4)              # dark mode
        r, g, b = TITLE_BAR
        cap = ctypes.c_int(r | g << 8 | b << 16)
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cap), 4)              # caption colour
        txt = ctypes.c_int(0xFFFFFF)
        dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(txt), 4)              # caption text
    except Exception:
        pass


# ---- Pillow rendering -------------------------------------------------------------------------

def background(w, h, dots=True):
    """Charcoal with soft dark spheres, glowing blue/violet lines and rings, a dotted blue row and a
    violet bar (laid out relative to the window size), as RGBA."""
    ys = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    grad = np.array(BG_TOP, np.float32) * (1 - ys) + np.array(BG_BOTTOM, np.float32) * ys
    img = Image.fromarray(np.repeat(grad, w, axis=1).astype(np.uint8)).convert("RGBA")
    big = max(w, h)
    s = big / 1000
    for cx, cy, r in ((0.20, -0.03, 0.13), (0.15, 0.46, 0.065), (0.79, 1.03, 0.21), (1.01, 0.68, 0.075)):
        img = _dark_sphere(img, cx * w, cy * h, r * big)
    P = lambda x, y: (x * w, y * h)   # noqa: E731
    shapes = [("line", (*P(0.33, 0.19), *P(0.47, -0.01)), BLUE),
              ("line", (*P(0.47, 0.09), *P(0.545, -0.01)), BLUE),
              ("line", (*P(0.05, 0.61), *P(0.26, 0.29)), VIOLET),
              ("line", (*P(-0.01, 0.81), *P(0.07, 0.70)), BLUE),
              ("line", (*P(0.83, 0.69), *P(1.01, 0.42)), BLUE),
              ("ring", (*P(0.06, 0.29), 0.028 * big), VIOLET),
              ("ring", (*P(0.935, 0.52), 0.115 * big), VIOLET),
              ("ring", (*P(0.935, 0.90), 0.03 * big), VIOLET)]
    img = neon_shapes(img, shapes, s, width=3.4)
    d = ImageDraw.Draw(img)
    q = 0.0115 * big                                                    # dotted blue row
    x = 0.66 * w if dots else w
    while x < 0.945 * w:
        d.rectangle((x, 0.065 * h, x + q, 0.065 * h + q), fill=(10, 82, 255, 255))
        x += 0.031 * w
    d.rectangle((0.955 * w, 0, w, 0.28 * h), fill=(68, 44, 200, 255))  # violet bar
    return img


def _dark_sphere(img, cx, cy, r):
    """A soft charcoal ball: a little lighter than the background, with a shadow below-right."""
    sh = Image.new("L", img.size, 0)
    ImageDraw.Draw(sh).ellipse((cx - r + 0.05 * r, cy - r + 0.09 * r, cx + r + 0.05 * r, cy + r + 0.09 * r), fill=150)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    layer.putalpha(sh.filter(ImageFilter.GaussianBlur(max(r * 0.12, 2))))
    img = Image.alpha_composite(img, layer)
    x0, y0 = int(cx - r - 3), int(cy - r - 3)
    size = int(2 * r + 6)
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    d = np.hypot(xs + x0 - cx, ys + y0 - cy) / r
    hl = np.hypot(xs + x0 - (cx - 0.4 * r), ys + y0 - (cy - 0.4 * r)) / r
    a = np.clip((1 - d) * r / 1.2, 0, 1)
    shade = np.clip(1.25 - hl, 0, 1)[..., None]
    rgb = np.array((27, 28, 32), np.float32) + shade * 7
    patch = np.dstack([rgb.repeat(1, 2) if False else np.broadcast_to(rgb, (size, size, 3)), a * 255]).astype(np.uint8)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    layer.paste(Image.fromarray(patch, "RGBA"), (x0, y0))
    return Image.alpha_composite(img, layer)


def neon_shapes(img, shapes, s, width=2.2):
    """Draw glowing lines ("line", (x0, y0, x1, y1), rgb) and rings ("ring", (cx, cy, r), rgb)."""
    ss = 2
    core = Image.new("RGBA", (img.width * ss, img.height * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(core)
    lw = max(int(width * s * ss), 2)
    for kind, g, rgb in shapes:
        if kind == "line":
            d.line([v * ss for v in g], fill=rgb + (255,), width=lw)
        else:
            cx, cy, r = (v * ss for v in g)
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=rgb + (255,), width=lw)
    core = core.resize(img.size, Image.LANCZOS)
    glow = core.filter(ImageFilter.GaussianBlur(max(7 * s, 2)))
    a = np.asarray(glow.getchannel("A"), np.float32)
    glow.putalpha(Image.fromarray(np.clip(a * 3.4, 0, 255).astype(np.uint8)))
    return Image.alpha_composite(Image.alpha_composite(img, glow), core)


def neon_pill(w, h, r, m):
    """Violet-to-blue rounded pill with a soft glow; returned with margin m on every side."""
    xs = np.linspace(0, 1, w, dtype=np.float32)[None, :, None]
    col = np.array(VIOLET, np.float32) * (1 - xs) + np.array(BLUE, np.float32) * xs
    body = Image.fromarray(np.repeat(col, h, axis=0).astype(np.uint8)).convert("RGBA")
    mask = rounded_mask(w, h, r)
    body.putalpha(mask)
    out = Image.new("RGBA", (w + 2 * m, h + 2 * m), VIOLET + (0,))
    halo = Image.new("L", out.size, 0)
    halo.paste(mask, (m, m))
    out.putalpha(Image.fromarray((np.asarray(halo.filter(ImageFilter.GaussianBlur(m * 0.45)), np.float32) * 0.55).astype(np.uint8)))
    out.alpha_composite(body, (m, m))
    hi = Image.new("RGBA", (w, h), (255, 255, 255, 0))       # soft top sheen
    hi.putalpha(Image.fromarray((np.asarray(_vgrad(w, h, 0.18, 0.0), np.float32) * np.asarray(mask, np.float32) / 255).astype(np.uint8)))
    out.alpha_composite(hi, (m, m))
    return out


def rounded_mask(w, h, r, ss=4):
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), r * ss, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def _vgrad(w, h, top, bottom):
    col = np.linspace(top, bottom, h, dtype=np.float32)[:, None]
    return Image.fromarray((np.repeat(col, w, 1) * 255).astype(np.uint8), "L")


def glass_card(base, box, r, s, lift=0.04, shadow=0.45, border=0.11, blur=18):
    """Composite one dark glass rounded rectangle onto `base` (RGBA) and return the result."""
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    w, h = x1 - x0, y1 - y0
    if w <= 2 or h <= 2:
        return base
    # soft shadow underneath
    m = int(30 * s)
    sh = Image.new("L", (w + 2 * m, h + 2 * m), 0)
    ImageDraw.Draw(sh).rounded_rectangle((m, m + int(10 * s), m + w, m + h + int(10 * s)), r, fill=int(255 * shadow))
    sh = sh.filter(ImageFilter.GaussianBlur(14 * s))
    layer = Image.new("RGBA", sh.size, (0, 0, 0, 0))
    layer.putalpha(sh)
    base = base.copy()
    base.alpha_composite(layer, (x0 - m, y0 - m))
    # frosted: blur what's behind, darken it, and light it a touch from the top
    pad = int(blur * 2 * s)
    region = base.crop((x0 - pad, y0 - pad, x1 + pad, y1 + pad)).filter(ImageFilter.GaussianBlur(blur * s))
    region = region.crop((pad, pad, pad + w, pad + h))
    dark = Image.new("RGBA", (w, h), (28, 29, 35, 180))
    region = Image.alpha_composite(region, dark)
    white = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    white.putalpha(_vgrad(w, h, lift + 0.03, max(lift - 0.03, 0.0)))
    region = Image.alpha_composite(region, white)
    mask = rounded_mask(w, h, r)
    base.paste(region, (x0, y0), mask)
    # faint border, brighter at the top
    bw = max(1, round(1.0 * s))
    inner = Image.new("L", (w, h), 0)
    inner.paste(rounded_mask(w - 2 * bw, h - 2 * bw, max(r - bw, 1)), (bw, bw))
    ring = np.clip(np.asarray(mask, np.int16) - np.asarray(inner, np.int16), 0, 255).astype(np.float32)
    ring = Image.fromarray((ring * np.asarray(_vgrad(w, h, border, border * 0.35), np.float32) / 255).astype(np.uint8))
    edge = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    edge.putalpha(ring)
    base.alpha_composite(edge, (x0, y0))
    return base


def pill_image(w, h, rgba):
    """A rounded (pill) RGBA image of one colour, for hover highlights and toggle tracks."""
    img = Image.new("RGBA", (w, h), rgba[:3] + (0,))
    img.putalpha(Image.fromarray((np.asarray(rounded_mask(w, h, h // 2), np.float32) * rgba[3] / 255).astype(np.uint8)))
    return img


def glow_dot(d, color):
    """A coloured disc with a soft halo, d = disc diameter in px."""
    size = d * 3
    img = Image.new("RGBA", (size, size), color + (0,))
    halo = Image.new("L", (size, size), 0)
    ImageDraw.Draw(halo).ellipse((d * 0.7, d * 0.7, size - d * 0.7, size - d * 0.7), fill=150)
    img.putalpha(halo.filter(ImageFilter.GaussianBlur(d * 0.35)))
    disc = Image.new("RGBA", (size, size), color + (0,))
    a = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(a).ellipse((d * 4, d * 4, size * 4 - d * 4, size * 4 - d * 4), fill=255)
    disc.putalpha(a.resize((size, size), Image.LANCZOS))
    return Image.alpha_composite(img, disc)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---- the canvas ---------------------------------------------------------------------------------

class Glass:
    """One window's canvas. Build: add cards/widgets, then finish(). Widgets stay live after."""

    def __init__(self, parent, w, h, dots=True):
        """dots=False leaves out the dotted row at the top right (where a window has its own)."""
        self.s = screen_scale()
        self.w, self.h = w, h
        self.canvas = tk.Canvas(parent, width=self.px(w), height=self.px(h), highlightthickness=0, bd=0,
                                bg="#16171a")
        self.canvas.pack()
        self.bg0 = background(self.px(w), self.px(h), dots)
        self.base = self.bg0.copy()
        self.widgets = []
        self.images = []          # keep PhotoImage references alive
        self.fonts = {}
        self.bg_item = None
        self.hover = self.pressed = None
        c = self.canvas
        c.bind("<Motion>", self._move)
        c.bind("<Leave>", lambda e: self._set_hover(None))
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<ButtonRelease-1>", self._release)

    # sizes / fonts
    def px(self, v):
        return int(round(v * self.s))

    def font(self, size, weight="normal", kind="text"):
        key = (size, weight, kind)
        if key not in self.fonts:
            self.fonts[key] = tkfont.Font(family=family(kind), size=size, weight=weight)
        return self.fonts[key]

    def photo(self, img):
        p = ImageTk.PhotoImage(img, master=self.canvas)
        self.images.append(p)
        return p

    # baked layers
    def card(self, x, y, w, h, r=22, tint=0.16, shadow=0.20):
        """A dark glass card. tint = how much lighter than the background (0.16 normal)."""
        self.base = glass_card(self.base, (self.px(x), self.px(y), self.px(x + w), self.px(y + h)),
                               self.px(r), self.s, lift=tint * 0.25, shadow=min(0.25 + shadow * 1.5, 0.6))
        return (x, y, w, h)

    def neon_card(self, x, y, w, h, r):
        """The bright violet-to-blue pill used for the main action."""
        m = self.px(18)
        self.base.alpha_composite(neon_pill(self.px(w), self.px(h), self.px(r), m), (self.px(x) - m, self.px(y) - m))

    def accent_line(self, x, y0, y1):
        """A glowing violet vertical line (beside headings)."""
        self.base = neon_shapes(self.base, [("line", (self.px(x), self.px(y0), self.px(x), self.px(y1)), VIOLET)], self.s)

    def ring(self, cx, cy, r, color=VIOLET, width=1.6):
        self.base = neon_shapes(self.base, [("ring", (self.px(cx), self.px(cy), self.px(r)), color)], self.s,
                                width=width)

    def finish(self):
        p = self.photo(self.base)
        if self.bg_item is None:
            self.bg_item = self.canvas.create_image(0, 0, image=p, anchor="nw")
        else:
            self.canvas.itemconfig(self.bg_item, image=p)
        self.canvas.tag_lower(self.bg_item)

    # live items
    def text(self, x, y, text="", size=11, weight="normal", color=TEXT, anchor="nw", width=None, kind="text",
             justify="left"):
        kw = {"width": self.px(width)} if width else {}
        return self.canvas.create_text(self.px(x), self.px(y), text=text, fill=color, anchor=anchor,
                                       font=self.font(size, weight, kind), justify=justify, **kw)

    def icon(self, x, y, name, size=14, color=TEXT, anchor="center"):
        return self.canvas.create_text(self.px(x), self.px(y), text=ICONS.get(name, name), fill=color,
                                       anchor=anchor, font=self.font(size, "normal", "icons"))

    def set(self, item, **kw):
        self.canvas.itemconfig(item, **kw)

    def image(self, x, y, img, anchor="nw"):
        return self.canvas.create_image(self.px(x), self.px(y), image=self.photo(img), anchor=anchor)

    # widgets
    def add(self, widget):
        self.widgets.append(widget)
        return widget

    def button(self, x, y, w, h, text="", icon=None, command=None, strong=False, size=11, r=None):
        return self.add(Button(self, x, y, w, h, text, icon, command, strong, size, r))

    def tile(self, x, y, w, h, text, icon, command):
        return self.add(Tile(self, x, y, w, h, text, icon, command))

    def toggle(self, x, y, value, command):
        return self.add(Toggle(self, x, y, value, command))

    def progress(self, x, y, w, value=0.0, thick=8, baked=True):
        """baked=False: the track is hidden too while the value is 0 (for hold meters)."""
        return Progress(self, x, y, w, value, thick, baked)

    def slider(self, x, y, w, lo, hi, step, value, on_change=None):
        return self.add(Slider(self, x, y, w, lo, hi, step, value, on_change))

    def photo_slot(self, x, y, w, h, r=16):
        return PhotoSlot(self, x, y, w, h, r)

    def glow(self, x, y, d, color):
        return Glow(self, x, y, d, color)

    def reset(self):
        """Remove everything and start again from the plain background (e.g. a new setup step)."""
        self.canvas.delete("all")
        self.widgets, self.images = [], []
        self.base = self.bg0.copy()
        self.bg_item = self.hover = self.pressed = None
        self.canvas.config(cursor="")

    def clear_widgets(self, keep=()):
        for wd in list(self.widgets):
            if wd not in keep:
                wd.destroy()
                self.widgets.remove(wd)

    # mouse
    def _hit(self, e):
        for wd in reversed(self.widgets):
            if wd.enabled and wd.contains(e.x, e.y):
                return wd
        return None

    def _set_hover(self, wd):
        if wd is not self.hover:
            if self.hover is not None:
                self.hover.on_hover(False)
            self.hover = wd
            if wd is not None:
                wd.on_hover(True)
            self.canvas.config(cursor="hand2" if wd is not None else "")

    def _move(self, e):
        if self.pressed is None:
            self._set_hover(self._hit(e))

    def _press(self, e):
        self.pressed = self._hit(e)
        if self.pressed is not None:
            self.pressed.on_press(e.x, e.y)

    def _drag(self, e):
        if self.pressed is not None:
            self.pressed.on_drag(e.x, e.y)

    def _release(self, e):
        wd, self.pressed = self.pressed, None
        if wd is not None:
            wd.on_release(e.x, e.y, wd.contains(e.x, e.y))
        self._set_hover(self._hit(e))


class Widget:
    enabled = True

    def __init__(self, g, x, y, w, h):
        self.g, self.box = g, (g.px(x), g.px(y), g.px(x + w), g.px(y + h))
        self.items = []

    def contains(self, x, y):
        x0, y0, x1, y1 = self.box
        return x0 <= x <= x1 and y0 <= y <= y1

    def on_hover(self, on):
        pass

    def on_press(self, x, y):
        pass

    def on_drag(self, x, y):
        pass

    def on_release(self, x, y, inside):
        pass

    def destroy(self):
        for it in self.items:
            self.g.canvas.delete(it)


class Button(Widget):
    """A glass pill with an optional icon and label. strong = brighter (the main action)."""

    def __init__(self, g, x, y, w, h, text, icon, command, strong, size, r):
        super().__init__(g, x, y, w, h)
        self.command = command
        r = h / 2 if r is None else r
        if strong:
            g.neon_card(x, y, w, h, r)
        else:
            g.card(x, y, w, h, r=r, tint=0.22, shadow=0.14)
        pw, ph = g.px(w), g.px(h)
        hover = Image.new("RGBA", (pw, ph), (255, 255, 255, 0))
        hover.putalpha(Image.fromarray((np.asarray(rounded_mask(pw, ph, g.px(r)), np.float32) * 0.08).astype(np.uint8)))
        press = hover.copy()
        press.putalpha(Image.fromarray((np.asarray(rounded_mask(pw, ph, g.px(r)), np.float32) * 0.16).astype(np.uint8)))
        self.hover_img, self.press_img = g.photo(hover), g.photo(press)
        self.hl = g.canvas.create_image(self.box[0], self.box[1], image=self.hover_img, anchor="nw", state="hidden")
        self.items.append(self.hl)
        cx, cy = x + w / 2, y + h / 2
        self.icon_item = self.label = None
        if icon and text:
            f = g.font(size, "bold" if strong else "normal")
            tw = f.measure(text) / g.s
            start = cx - (tw + size * 2.2) / 2
            self.icon_item = g.icon(start + size * 0.7, cy, icon, size + 1)
            self.label = g.text(start + size * 2.2, cy, text, size, "bold" if strong else "normal", anchor="w")
        elif icon:
            self.icon_item = g.icon(cx, cy, icon, size + 3)
        else:
            self.label = g.text(cx, cy, text, size, "bold" if strong else "normal", anchor="center")
        self.items += [i for i in (self.icon_item, self.label) if i]

    def set(self, text=None, icon=None):
        if text is not None and self.label:
            self.g.set(self.label, text=text)
        if icon is not None and self.icon_item:
            self.g.set(self.icon_item, text=ICONS.get(icon, icon))

    def on_hover(self, on):
        self.g.set(self.hl, state="normal" if on else "hidden", image=self.hover_img)

    def on_press(self, x, y):
        self.g.set(self.hl, state="normal", image=self.press_img)

    def on_release(self, x, y, inside):
        self.g.set(self.hl, image=self.hover_img)
        if inside and self.command:
            self.command()


class Tile(Button):
    """Icon in a glass circle with a label underneath (like a home-screen shortcut)."""

    def __init__(self, g, x, y, w, h, text, icon, command):
        Widget.__init__(self, g, x, y, w, h)
        self.command = command
        d = 46
        cx = x + w / 2
        g.card(cx - d / 2, y + 6, d, d, r=d / 2, tint=0.3, shadow=0.10)
        g.ring(cx, y + 6 + d / 2, d / 2 - 1, width=1.4)
        pw, ph = g.px(w), g.px(h)
        mk = rounded_mask(pw, ph, g.px(18))
        hover = Image.new("RGBA", (pw, ph), (255, 255, 255, 0))
        hover.putalpha(Image.fromarray((np.asarray(mk, np.float32) * 0.06).astype(np.uint8)))
        press = hover.copy()
        press.putalpha(Image.fromarray((np.asarray(mk, np.float32) * 0.12).astype(np.uint8)))
        self.hover_img, self.press_img = g.photo(hover), g.photo(press)
        self.hl = g.canvas.create_image(self.box[0], self.box[1], image=self.hover_img, anchor="nw", state="hidden")
        self.icon_item = g.icon(cx, y + 6 + d / 2, icon, 16)
        self.label = g.text(cx, y + d + 16, text, 9, anchor="n", justify="center", width=w - 4)
        self.items += [self.hl, self.icon_item, self.label]


class Toggle(Widget):
    W, H = 46, 26

    def __init__(self, g, x, y, value, command):
        super().__init__(g, x, y, self.W, self.H)
        self.command, self.value = command, bool(value)
        pw, ph = g.px(self.W), g.px(self.H)
        self.on_img = g.photo(pill_image(pw, ph, hex_rgb(ACCENT) + (255,)))
        self.off_img = g.photo(pill_image(pw, ph, (50, 52, 61, 255)))
        k = ph - g.px(6)
        knob_on = glow_dot(k, (255, 255, 255))
        knob_off = glow_dot(k, (150, 154, 170))
        self.kon, self.koff = g.photo(knob_on), g.photo(knob_off)
        self.track = g.canvas.create_image(self.box[0], self.box[1], anchor="nw")
        self.knob = g.canvas.create_image(0, 0, anchor="center")
        self.items += [self.track, self.knob]
        self._draw()

    def _draw(self):
        x0, y0, x1, y1 = self.box
        r = (y1 - y0) / 2
        self.g.set(self.track, image=self.on_img if self.value else self.off_img)
        cx = x1 - r if self.value else x0 + r
        self.g.set(self.knob, image=self.kon if self.value else self.koff)
        self.g.canvas.coords(self.knob, cx, y0 + r)

    def set(self, value):
        if bool(value) != self.value:
            self.value = bool(value)
            self._draw()

    def on_release(self, x, y, inside):
        if inside:
            self.value = not self.value
            self._draw()
            if self.command:
                self.command(self.value)


class Progress:
    """A rounded bar: track baked into the background, white fill as a round-capped line."""

    def __init__(self, g, x, y, w, value, thick, baked=True):
        self.g, self.x, self.y, self.w, self.t = g, x, y, w, thick
        track = pill_image(g.px(w), g.px(thick), (255, 255, 255, 26))
        self.track = None
        if baked:
            g.base.alpha_composite(track, (g.px(x), g.px(y)))
        else:
            self.track = g.canvas.create_image(g.px(x), g.px(y), image=g.photo(track), anchor="nw", state="hidden")
        self.line = g.canvas.create_line(0, 0, 0, 0, fill=ACCENT, width=g.px(thick), capstyle="round")
        self.set(value)

    def set(self, value):
        g, r = self.g, self.t / 2
        v = min(max(value or 0.0, 0.0), 1.0)
        x0, x1 = self.x + r, self.x + r + (self.w - 2 * r) * v
        cy = self.y + r
        g.canvas.coords(self.line, g.px(x0), g.px(cy), g.px(max(x1, x0 + 0.01)), g.px(cy))
        g.set(self.line, state="normal" if v > 0 else "hidden")
        if self.track is not None:
            g.set(self.track, state="normal" if v > 0 else "hidden")

    def show(self, on):
        self.g.set(self.line, state="normal" if on else "hidden")


class Slider(Widget):
    def __init__(self, g, x, y, w, lo, hi, step, value, on_change):
        super().__init__(g, x, y - 10, w, 28)
        self.lo, self.hi, self.step, self.on_change = lo, hi, step, on_change
        self.x, self.y, self.w = x, y, w
        self.bar = Progress(g, x, y, w, 0, 6)
        k = g.px(14)
        self.kimg = g.photo(glow_dot(k, (255, 255, 255)))
        self.knob = g.canvas.create_image(0, 0, anchor="center")
        self.items += [self.bar.line, self.knob]
        self.value = None
        self.set(value)

    def set(self, value):
        v = min(max(float(value), self.lo), self.hi)
        v = round(round((v - self.lo) / self.step) * self.step + self.lo, 6)
        self.value = v
        f = (v - self.lo) / (self.hi - self.lo)
        self.bar.set(max(f, 0.001))
        g = self.g
        g.set(self.knob, image=self.kimg)
        g.canvas.coords(self.knob, g.px(self.x + 3 + (self.w - 6) * f), g.px(self.y + 3))

    def _from_x(self, x):
        f = (x / self.g.s - self.x) / self.w
        self.set(self.lo + f * (self.hi - self.lo))
        if self.on_change:
            self.on_change(self.value)

    def on_press(self, x, y):
        self._from_x(x)

    def on_drag(self, x, y):
        self._from_x(x)


class PhotoSlot:
    """A rounded-corner area for the live camera picture (or a message when there is none)."""

    def __init__(self, g, x, y, w, h, r):
        self.g, self.size = g, (g.px(w), g.px(h))
        self.mask = rounded_mask(*self.size, g.px(r))
        dark = Image.new("RGBA", self.size, (9, 10, 13, 0))
        dark.putalpha(Image.fromarray((np.asarray(self.mask, np.float32) * 215 / 255).astype(np.uint8)))
        g.base.alpha_composite(dark, (g.px(x), g.px(y)))
        self.item = g.canvas.create_image(g.px(x), g.px(y), anchor="nw", state="hidden")
        self.msg = g.text(x + w / 2, y + h / 2, "", 11, color=SOFT, anchor="center", width=w - 60, justify="center")
        self.photo = None

    def set(self, rgb):
        img = Image.fromarray(rgb)
        if img.size != self.size:
            img = img.resize(self.size, Image.BILINEAR)
        img = img.convert("RGBA")
        img.putalpha(self.mask)
        self.photo = ImageTk.PhotoImage(img, master=self.g.canvas)
        self.g.set(self.item, image=self.photo, state="normal")
        self.g.set(self.msg, state="hidden")

    def message(self, text, justify="center"):
        self.g.set(self.item, state="hidden")
        self.photo = None
        self.g.set(self.msg, text=text, state="normal", justify=justify)


class Glow:
    def __init__(self, g, x, y, d, color):
        self.g, self.d, self.cache = g, g.px(d), {}
        self.item = g.canvas.create_image(g.px(x), g.px(y), anchor="center")
        self.set(color)

    def set(self, color):
        if color not in self.cache:
            self.cache[color] = self.g.photo(glow_dot(self.d, hex_rgb(color)))
        self.g.set(self.item, image=self.cache[color])
