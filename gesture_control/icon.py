"""The app's hand symbol: an open palm with five fingers (a single raised finger reads as rude).
Used for the tray icon, window icons, the exe icon and the Store tiles."""
import numpy as np
from PIL import Image, ImageDraw

# (x0, top, x1) of each finger on a 64-unit grid, index -> pinky; all end inside the palm
FINGERS = ((17.6, 17.0, 24.4), (25.4, 11.5, 32.2), (33.2, 13.5, 40.0), (41.0, 20.0, 47.0))


def open_hand(size, color=(255, 255, 255, 255), scale=1.0):
    """Open palm on a transparent square. scale < 1 shrinks it towards the middle."""
    ss = 4
    s = size * ss
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = s / 64 * scale
    off = s * (1 - scale) / 2 + 1.5 * u          # centre it (the drawing leans slightly left)

    def P(x, y):
        return off + x * u, off + y * u
    for x0, top, x1 in FINGERS:
        d.rounded_rectangle((*P(x0, top), *P(x1, 40)), radius=(x1 - x0) / 2 * u, fill=color)
    d.rounded_rectangle((*P(17.6, 30), *P(47, 55)), radius=9 * u, fill=color)          # palm
    w = 7.4 * u                                                                        # thumb
    a, b = P(21, 46), P(10.5, 33.5)
    d.line((a, b), fill=color, width=round(w))
    for cx, cy in (a, b):
        d.ellipse((cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2), fill=color)
    return img.resize((size, size), Image.LANCZOS)


def disc_icon(color, size=64):
    """Tray icon: a coloured disc (state colour) with the white open hand."""
    ss = 4
    img = Image.new("RGBA", (size * ss, size * ss), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((2 * ss, 2 * ss, (size - 2) * ss, (size - 2) * ss), fill=tuple(color) + (255,))
    img = img.resize((size, size), Image.LANCZOS)
    return Image.alpha_composite(img, open_hand(size, scale=0.78))


# ---- the app icon: charcoal rounded square with a glowing violet-to-blue open hand ----

STOPS = [(0.0, (150, 124, 255)), (1.0, (64, 128, 255))]


def gradient(size):
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    t = np.clip((xs + ys) / (2 * size - 2), 0, 1)
    out = np.zeros((size, size, 3), np.float32)
    for (t0, c0), (t1, c1) in zip(STOPS, STOPS[1:]):
        m = (t >= t0) & (t <= t1)
        k = ((t - t0) / (t1 - t0))[m][:, None]
        out[m] = np.array(c0) * (1 - k) + np.array(c1) * k
    return Image.fromarray(out.astype(np.uint8)).convert("RGBA")


def tile(size, rounded=True, pad=0.0):
    """The app icon. pad = transparent margin around it (0..0.5)."""
    from PIL import ImageFilter
    inner = max(int(size * (1 - 2 * pad)), 1)
    bg = Image.new("RGBA", (inner, inner), (26, 27, 32, 255))
    if rounded:
        m = Image.new("L", (inner * 4, inner * 4), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, inner * 4 - 1, inner * 4 - 1), radius=inner * 4 * 0.24, fill=255)
        bg.putalpha(m.resize((inner, inner), Image.LANCZOS))
    shape = open_hand(inner, scale=0.84).getchannel("A")
    hand = gradient(inner)
    hand.putalpha(shape)
    glow = Image.new("RGBA", (inner, inner), (124, 92, 255, 0))
    glow.putalpha(shape.filter(ImageFilter.GaussianBlur(max(inner * 0.05, 1))).point(lambda v: min(255, int(v * 0.9))))
    g = Image.alpha_composite(Image.alpha_composite(bg, glow), hand)
    if rounded:
        g.putalpha(Image.fromarray(np.minimum(np.asarray(g.getchannel("A")), np.asarray(bg.getchannel("A")))))
        # thin violet edge so the tile still reads on a dark taskbar
        ss = 4
        e = Image.new("RGBA", (inner * ss, inner * ss), (0, 0, 0, 0))
        bw = max(inner * ss * 0.03, ss)
        ImageDraw.Draw(e).rounded_rectangle((bw / 2, bw / 2, inner * ss - bw / 2 - 1, inner * ss - bw / 2 - 1),
                                            radius=inner * ss * 0.24, outline=(124, 92, 255, 210), width=round(bw))
        g = Image.alpha_composite(g, e.resize((inner, inner), Image.LANCZOS))
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(g, ((size - inner) // 2, (size - inner) // 2), g)
    return out


def glyph(size):
    """Just the glowing gradient hand on transparent (taskbar / title bar sizes)."""
    shape = open_hand(size, scale=1.0).getchannel("A")
    hand = gradient(size)
    hand.putalpha(shape)
    return hand
