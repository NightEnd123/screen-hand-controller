"""Dashboard look for the app's windows (one Tk Canvas per window + Pillow).

Flat dark slate with a blue-grey sidebar, rounded cards, one white "highlight" card, and mint /
pink / lavender accents. The static parts of a window (background, sidebar, cards, pills) are
rendered once with Pillow into one image; live things are canvas items on top: text, icons, the
camera picture, charts, hover highlights, toggles, sliders and progress bars.

Coordinates given to Glass are logical (96-dpi) pixels; Glass scales them for the screen.
Only the Tk thread may use this module.
"""
import ctypes
import tkinter as tk
import tkinter.font as tkfont

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageTk

BG = (43, 48, 54)            # window
SIDEBAR = (36, 50, 63)       # left navigation strip
CARD = (36, 40, 46)          # cards (a touch darker than the window)
CARD_HI = (52, 57, 64)       # buttons and raised bits
WHITE_CARD = (248, 249, 251)
TEXT = "#eef1f5"
SOFT = "#b3b9c3"
MUTED = "#7f868f"
DARK = "#1f2429"             # text on white
MINT = "#7cf0c9"
PINK = "#e8336d"
LAVENDER = "#c7c3f6"
GREY = "#5e646c"
ACCENT = MINT
TITLE_BAR = BG               # Windows 11 title bar colour

ICONS = {   # Segoe Fluent Icons / Segoe MDL2 Assets code points
    "play": "", "pause": "", "camera": "", "settings": "",
    "guide": "", "setup": "", "calibrate": "", "power": "",
    "check": "", "warning": "", "windows": "", "next": "",
    "close": "", "save": "", "undo": "", "edit": "", "eye": "",
    "hand": "", "sync": "", "mouse": "", "left": "", "right": "",
    "home": "", "dashboard": "", "search": "", "down": "", "tray": "",
    "chart": "", "globe": "",
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

def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def background(w, h, dots=True, sidebar=0):
    """Flat slate, with a blue-grey sidebar strip `sidebar` px wide on the left. (dots is unused,
    kept so older callers still work.)"""
    img = Image.new("RGBA", (w, h), BG + (255,))
    if sidebar:
        ImageDraw.Draw(img).rectangle((0, 0, sidebar - 1, h), fill=SIDEBAR + (255,))
    return img


def rounded_mask(w, h, r, ss=4):
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), r * ss, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def flat_card(base, box, r, s, fill=CARD, shadow=0.0):
    """Composite one flat rounded rectangle onto `base` (RGBA), with an optional soft shadow."""
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    w, h = x1 - x0, y1 - y0
    if w <= 2 or h <= 2:
        return base
    base = base.copy()
    if shadow:
        m = int(24 * s)
        sh = Image.new("L", (w + 2 * m, h + 2 * m), 0)
        ImageDraw.Draw(sh).rounded_rectangle((m, m + int(6 * s), m + w, m + h + int(6 * s)), r, fill=int(255 * shadow))
        layer = Image.new("RGBA", sh.size, (0, 0, 0, 0))
        layer.putalpha(sh.filter(ImageFilter.GaussianBlur(12 * s)))
        base.alpha_composite(layer, (x0 - m, y0 - m))
    body = Image.new("RGBA", (w, h), tuple(fill) + (255,))
    base.paste(body, (x0, y0), rounded_mask(w, h, r))
    return base


def pill_image(w, h, rgba):
    """A rounded (pill) RGBA image of one colour, for hover highlights and toggle tracks."""
    img = Image.new("RGBA", (w, h), rgba[:3] + (0,))
    img.putalpha(Image.fromarray((np.asarray(rounded_mask(w, h, h // 2), np.float32) * rgba[3] / 255).astype(np.uint8)))
    return img


def round_rect_image(w, h, r, rgba):
    img = Image.new("RGBA", (w, h), rgba[:3] + (0,))
    img.putalpha(Image.fromarray((np.asarray(rounded_mask(w, h, r), np.float32) * rgba[3] / 255).astype(np.uint8)))
    return img


def disc(d, color, ring=None, ring_w=0):
    """An anti-aliased filled circle of diameter d (optionally with a ring outline)."""
    ss = 4
    img = Image.new("RGBA", (d * ss, d * ss), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.ellipse((0, 0, d * ss - 1, d * ss - 1), fill=tuple(color) + (255,))
    if ring:
        dr.ellipse((0, 0, d * ss - 1, d * ss - 1), outline=tuple(ring) + (255,), width=max(int(ring_w * ss), 1))
    return img.resize((d, d), Image.LANCZOS)


def glow_dot(d, color):
    """A coloured disc with a soft halo (status lights), d = disc diameter in px."""
    size = d * 3
    img = Image.new("RGBA", (size, size), tuple(color) + (0,))
    halo = Image.new("L", (size, size), 0)
    ImageDraw.Draw(halo).ellipse((d * 0.8, d * 0.8, size - d * 0.8, size - d * 0.8), fill=110)
    img.putalpha(halo.filter(ImageFilter.GaussianBlur(d * 0.3)))
    img.alpha_composite(disc(d, color), (d, d))
    return img


# ---- the canvas ---------------------------------------------------------------------------------

class Glass:
    """One window's canvas. Build: add cards/widgets, then finish(). Widgets stay live after."""

    def __init__(self, parent, w, h, dots=True, sidebar=0):
        """sidebar = width of the blue-grey navigation strip on the left (0 = none)."""
        self.s = screen_scale()
        self.w, self.h = w, h
        self.canvas = tk.Canvas(parent, width=self.px(w), height=self.px(h), highlightthickness=0, bd=0,
                                bg="#2b3036")
        self.canvas.pack()
        self.bg0 = background(self.px(w), self.px(h), dots, self.px(sidebar))
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
    def card(self, x, y, w, h, r=16, tint=0.16, shadow=0.20, fill=None):
        """A flat card. tint >= 0.2 gives the raised (lighter) shade used for buttons."""
        fill = fill or (CARD_HI if tint >= 0.2 else CARD)
        self.base = flat_card(self.base, (self.px(x), self.px(y), self.px(x + w), self.px(y + h)),
                              self.px(r), self.s, fill=fill, shadow=0.0)
        return (x, y, w, h)

    def white_card(self, x, y, w, h, r=16):
        """The bright highlight card (dark text goes on it)."""
        self.base = flat_card(self.base, (self.px(x), self.px(y), self.px(x + w), self.px(y + h)),
                              self.px(r), self.s, fill=WHITE_CARD, shadow=0.35)
        return (x, y, w, h)

    def neon_card(self, x, y, w, h, r):
        """The white pill used for the main action."""
        self.base = flat_card(self.base, (self.px(x), self.px(y), self.px(x + w), self.px(y + h)),
                              self.px(r), self.s, fill=WHITE_CARD)

    def accent_line(self, x, y0, y1, color=MINT):
        """A short rounded accent bar (beside headings)."""
        w = max(self.px(3), 2)
        bar = round_rect_image(w, self.px(y1 - y0), w // 2, hex_rgb(color) + (255,))
        self.base.alpha_composite(bar, (self.px(x) - w // 2, self.px(y0)))

    def ring(self, cx, cy, r, color=LAVENDER, width=1.4):
        ss = 4
        d = self.px(2 * r)
        img = Image.new("RGBA", (d * ss, d * ss), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((0, 0, d * ss - 1, d * ss - 1), outline=hex_rgb(color) + (255,),
                                    width=max(int(width * self.s * ss), 1))
        self.base.alpha_composite(img.resize((d, d), Image.LANCZOS), (self.px(cx) - d // 2, self.px(cy) - d // 2))

    def bake(self, x, y, img):
        """Paste a Pillow image into the background at logical (x, y)."""
        self.base.alpha_composite(img, (self.px(x), self.px(y)))

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

    def nav(self, x, y, w, text, icon, command, selected=False, badge=None):
        return self.add(NavItem(self, x, y, w, text, icon, command, selected, badge))

    def icon_button(self, x, y, icon, command, size=14):
        return self.add(IconButton(self, x, y, icon, command, size))

    def tile(self, x, y, w, h, text, icon, command):
        return self.add(Tile(self, x, y, w, h, text, icon, command))

    def toggle(self, x, y, value, command):
        return self.add(Toggle(self, x, y, value, command))

    def progress(self, x, y, w, value=0.0, thick=8, baked=True):
        """baked=False: the track is hidden too while the value is 0 (for hold meters)."""
        return Progress(self, x, y, w, value, thick, baked)

    def slider(self, x, y, w, lo, hi, step, value, on_change=None):
        return self.add(Slider(self, x, y, w, lo, hi, step, value, on_change))

    def photo_slot(self, x, y, w, h, r=12, backing=True):
        """backing=False: no dark panel behind it (the area is shared with something else)."""
        return PhotoSlot(self, x, y, w, h, r, backing)

    def live_image(self, x, y):
        """A spot for a picture that changes (charts); set it with .set(pil_image)."""
        return LiveImage(self, x, y)

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


def _overlays(g, w, h, r, light=True):
    """Hover and pressed highlight images for a rounded area."""
    pw, ph = g.px(w), g.px(h)
    base = (255, 255, 255) if light else (0, 0, 0)
    return (g.photo(round_rect_image(pw, ph, g.px(r), base + (20,))),
            g.photo(round_rect_image(pw, ph, g.px(r), base + (40,))))


class Button(Widget):
    """A pill with an optional icon and label. strong = the white main-action pill."""

    def __init__(self, g, x, y, w, h, text, icon, command, strong, size, r):
        super().__init__(g, x, y, w, h)
        self.command = command
        r = h / 2 if r is None else r
        if strong:
            g.neon_card(x, y, w, h, r)
        else:
            g.card(x, y, w, h, r=r, tint=0.22)
        self.hover_img, self.press_img = _overlays(g, w, h, r, light=not strong)
        self.hl = g.canvas.create_image(self.box[0], self.box[1], image=self.hover_img, anchor="nw", state="hidden")
        self.items.append(self.hl)
        color = DARK if strong else TEXT
        weight = "bold" if strong else "normal"
        cx, cy = x + w / 2, y + h / 2
        self.icon_item = self.label = None
        if icon and text:
            f = g.font(size, weight)
            tw = f.measure(text) / g.s
            start = cx - (tw + size * 2.2) / 2
            self.icon_item = g.icon(start + size * 0.7, cy, icon, size + 1, color=color)
            self.label = g.text(start + size * 2.2, cy, text, size, weight, color=color, anchor="w")
        elif icon:
            self.icon_item = g.icon(cx, cy, icon, size + 3, color=color)
        else:
            self.label = g.text(cx, cy, text, size, weight, color=color, anchor="center")
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


class NavItem(Button):
    """A sidebar entry: icon + label; the selected one sits on a white pill."""

    H = 34

    def __init__(self, g, x, y, w, text, icon, command, selected, badge):
        Widget.__init__(self, g, x, y, w, self.H)
        self.command = command
        self.pill = g.canvas.create_image(self.box[0], self.box[1], anchor="nw", state="hidden",
                                          image=g.photo(round_rect_image(g.px(w), g.px(self.H), g.px(9),
                                                                         WHITE_CARD + (255,))))
        self.hover_img, self.press_img = _overlays(g, w, self.H, 9)
        self.hl = g.canvas.create_image(self.box[0], self.box[1], image=self.hover_img, anchor="nw", state="hidden")
        self.icon_item = g.icon(x + 22, y + self.H / 2, icon, 13)
        self.label = g.text(x + 44, y + self.H / 2, text, 10, anchor="w")
        self.badge = None
        self.items += [self.pill, self.hl, self.icon_item, self.label]
        if badge is not None:
            self.badge_dot = g.canvas.create_image(g.px(x + w - 22), g.px(y + self.H / 2), anchor="center",
                                                   image=g.photo(disc(g.px(18), hex_rgb(PINK))), state="hidden")
            self.badge = g.text(x + w - 22, y + self.H / 2, "", 8, "bold", anchor="center", color="#ffffff")
            self.items += [self.badge_dot, self.badge]
        self.select(selected)

    def select(self, on):
        self.selected = on
        self.g.set(self.pill, state="normal" if on else "hidden")
        self.g.set(self.icon_item, fill=DARK if on else TEXT)
        self.g.set(self.label, fill=DARK if on else TEXT)

    def set_badge(self, text):
        if self.badge is not None:
            self.g.set(self.badge, text=text or "")
            self.g.set(self.badge_dot, state="normal" if text else "hidden")

    def on_hover(self, on):
        if not self.selected:
            super().on_hover(on)

    def on_press(self, x, y):
        if not self.selected:
            super().on_press(x, y)


class IconButton(Button):
    """Just an icon, with a round hover highlight."""

    def __init__(self, g, x, y, icon, command, size):
        d = size + 18
        Widget.__init__(self, g, x - d / 2, y - d / 2, d, d)
        self.command = command
        self.hover_img, self.press_img = _overlays(g, d, d, d / 2)
        self.hl = g.canvas.create_image(self.box[0], self.box[1], image=self.hover_img, anchor="nw", state="hidden")
        self.icon_item = g.icon(x, y, icon, size)
        self.label = None
        self.items += [self.hl, self.icon_item]


class Tile(Button):
    """Icon in a circle with a label underneath (like a home-screen shortcut)."""

    def __init__(self, g, x, y, w, h, text, icon, command):
        Widget.__init__(self, g, x, y, w, h)
        self.command = command
        d = 46
        cx = x + w / 2
        g.card(cx - d / 2, y + 6, d, d, r=d / 2, tint=0.3)
        self.hover_img, self.press_img = _overlays(g, w, h, 14)
        self.hl = g.canvas.create_image(self.box[0], self.box[1], image=self.hover_img, anchor="nw", state="hidden")
        self.icon_item = g.icon(cx, y + 6 + d / 2, icon, 16, color=MINT)
        self.label = g.text(cx, y + d + 16, text, 9, anchor="n", justify="center", width=w - 4)
        self.items += [self.hl, self.icon_item, self.label]


class Toggle(Widget):
    """On = white track with a dark knob on the right (like the reference); off = grey, knob left."""

    W, H = 44, 24

    def __init__(self, g, x, y, value, command):
        super().__init__(g, x, y, self.W, self.H)
        self.command, self.value = command, bool(value)
        pw, ph = g.px(self.W), g.px(self.H)
        self.on_img = g.photo(pill_image(pw, ph, WHITE_CARD + (255,)))
        self.off_img = g.photo(pill_image(pw, ph, (70, 76, 84, 255)))
        k = ph - g.px(8)
        self.kon, self.koff = g.photo(disc(k, BG)), g.photo(disc(k, (170, 176, 186)))
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
    """A rounded bar: track baked into the background, mint fill as a round-capped line."""

    def __init__(self, g, x, y, w, value, thick, baked=True, color=MINT):
        self.g, self.x, self.y, self.w, self.t = g, x, y, w, thick
        track = pill_image(g.px(w), g.px(thick), (255, 255, 255, 28))
        self.track = None
        if baked:
            g.base.alpha_composite(track, (g.px(x), g.px(y)))
        else:
            self.track = g.canvas.create_image(g.px(x), g.px(y), image=g.photo(track), anchor="nw", state="hidden")
        self.line = g.canvas.create_line(0, 0, 0, 0, fill=color, width=g.px(thick), capstyle="round")
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
        self.kimg = g.photo(disc(k, WHITE_CARD, ring=hex_rgb(MINT), ring_w=g.px(2)))
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

    def __init__(self, g, x, y, w, h, r, backing=True):
        self.g, self.size = g, (g.px(w), g.px(h))
        self.mask = rounded_mask(*self.size, g.px(r))
        if backing:
            dark = Image.new("RGBA", self.size, (26, 30, 34, 0))
            dark.putalpha(self.mask)
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

    def hide(self):
        self.g.set(self.item, state="hidden")
        self.g.set(self.msg, state="hidden")


class LiveImage:
    """A canvas image that is replaced as a whole (charts redrawn once a second)."""

    def __init__(self, g, x, y):
        self.g = g
        self.item = g.canvas.create_image(g.px(x), g.px(y), anchor="nw")
        self.photo = None

    def set(self, img):
        self.photo = ImageTk.PhotoImage(img, master=self.g.canvas)
        self.g.set(self.item, image=self.photo, state="normal")

    def show(self, on):
        self.g.set(self.item, state="normal" if on else "hidden")


class Glow:
    def __init__(self, g, x, y, d, color):
        self.g, self.d, self.cache = g, g.px(d), {}
        self.item = g.canvas.create_image(g.px(x), g.px(y), anchor="center")
        self.set(color)

    def set(self, color):
        if color not in self.cache:
            self.cache[color] = self.g.photo(glow_dot(self.d, hex_rgb(color)))
        self.g.set(self.item, image=self.cache[color])
