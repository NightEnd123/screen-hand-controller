"""Dashboard charts drawn with Pillow: a smooth area chart, a segmented donut, a radar and a
timeline. Each function returns an RGBA image of the requested pixel size (drawn 3x larger and
scaled down so edges are smooth). `s` is the screen scale (1.0 at 96 dpi) for line widths and text.
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .glass import GREY, LAVENDER, MINT, MUTED, PINK, SOFT, TEXT, hex_rgb

SS = 3
_FONTS = {}
_WIN = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


def font(px, bold=False):
    key = (px, bold)
    if key not in _FONTS:
        for name in (("seguisb.ttf", "segoeuib.ttf") if bold else ("segoeui.ttf",)):
            try:
                _FONTS[key] = ImageFont.truetype(os.path.join(_WIN, name), px)
                break
            except OSError:
                continue
        else:
            _FONTS[key] = ImageFont.load_default()
    return _FONTS[key]


def _canvas(w, h):
    img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _done(img, w, h):
    return img.resize((w, h), Image.LANCZOS)


def _rgba(color, a=255):
    return hex_rgb(color) + (a,)


def _smooth(points, steps=12):
    """Catmull-Rom spline through the points (keeps the curve passing through every value)."""
    if len(points) < 3:
        return points
    out = []
    pts = [points[0]] + points + [points[-1]]
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for k in range(steps):
            t = k / steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    out.append(points[-1])
    return out


def nice_max(v):
    if v <= 0:
        return 100
    mag = 10 ** math.floor(math.log10(v))
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if v <= m * mag:
            return m * mag
    return 10 * mag


def area_chart(values, w, h, s, unit="", x_labels=()):
    """Smooth lavender area chart with a y grid and labels (values oldest -> newest)."""
    img, d = _canvas(w, h)
    S = SS * s
    f = font(int(9 * S))
    left, right, top, bottom = 52 * S, 8 * S, 10 * S, 22 * S
    W, H = w * SS, h * SS
    vmax = nice_max(max(values) if values else 0)
    for i in range(6):                                   # grid + y labels
        y = top + (H - top - bottom) * i / 5
        d.line((left, y, W - right, y), fill=_rgba(GREY, 110), width=max(int(1 * S), 1))
        lab = f"{int(vmax * (5 - i) / 5)}{unit}"
        d.text((left - 8 * S, y), lab, font=f, fill=_rgba(MUTED), anchor="rm")
    if x_labels:
        for i, lab in enumerate(x_labels):
            x = left + (W - left - right) * i / max(len(x_labels) - 1, 1)
            d.text((x, H - 6 * S), lab, font=f, fill=_rgba(MUTED), anchor="ms")
    vals = list(values) or [0]
    if len(vals) == 1:
        vals = vals * 2
    n = len(vals)
    pts = [(left + (W - left - right) * i / (n - 1), H - bottom - (H - top - bottom) * min(v / vmax, 1.0))
           for i, v in enumerate(vals)]
    curve = _smooth(pts)
    curve = [(x, min(max(y, top), H - bottom)) for x, y in curve]
    # gradient fill: lavender at the line fading to transparent at the bottom
    poly = curve + [(curve[-1][0], H - bottom), (curve[0][0], H - bottom)]
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    ys = np.linspace(0, 1, img.size[1], dtype=np.float32)[:, None]
    shade = np.clip(1.0 - (ys - top / H) / (1 - top / H) * 1.1, 0, 1) * 0.55
    alpha = (np.asarray(mask, np.float32) * np.repeat(shade, img.size[0], 1)).astype(np.uint8)
    fill = Image.new("RGBA", img.size, _rgba(LAVENDER, 0))
    fill.putalpha(Image.fromarray(alpha))
    img.alpha_composite(fill)
    d.line(curve, fill=_rgba("#e4e1ff"), width=max(int(2 * S), 2), joint="curve")
    return _done(img, w, h)


def donut(segments, d_px, s, thickness=12, gap_deg=9, total_label="", total_value=""):
    """Segmented ring: segments = [(value, color)], drawn clockwise from the top with gaps and
    round ends, plus a centred label."""
    img, dr = _canvas(d_px, d_px)
    S = SS * s
    D = d_px * SS
    t = thickness * S
    box = (0, 0, D - 1, D - 1)          # Pillow draws a thick arc inward from this box
    total = sum(v for v, _ in segments)
    r = (D - t) / 2                     # radius of the middle of the stroke
    cx = cy = D / 2
    cap_deg = math.degrees((t / 2) / r)
    if total <= 0:
        dr.ellipse(box, outline=_rgba(GREY, 160), width=int(t))
    else:
        start = -90.0
        for v, color in segments:
            if v <= 0:
                continue
            sweep = 360.0 * v / total
            g = gap_deg + 2 * cap_deg if len([1 for vv, _ in segments if vv > 0]) > 1 else 0
            a0, a1 = start + g / 2, start + sweep - g / 2
            if a1 <= a0:                         # tiny share: a dot in the middle of its slot
                a0 = a1 = start + sweep / 2
            if a1 > a0:
                dr.arc(box, a0, a1, fill=_rgba(color), width=int(t))
            for a in (a0, a1):                   # round caps
                x, y = cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))
                dr.ellipse((x - t / 2, y - t / 2, x + t / 2, y + t / 2), fill=_rgba(color))
            start += sweep
    if total_label:
        dr.text((cx, cy - 4 * S), total_label, font=font(int(9 * S)), fill=_rgba(SOFT), anchor="ms")
        dr.text((cx, cy + 4 * S), total_value, font=font(int(11 * S)), fill=_rgba(TEXT), anchor="mt")
    return _done(img, d_px, d_px)


def radar(values, w, h, s, color=PINK):
    """Hexagon radar: values = {label: share 0..1}; labels with percentages around it."""
    img, d = _canvas(w, h)
    S = SS * s
    W, H = w * SS, h * SS
    labels = list(values)
    n = len(labels)
    cx, cy = W / 2, H / 2 + 4 * S
    R = min(W * 0.30, H * 0.34)
    ang = [math.radians(-90 + 360 * i / n) for i in range(n)]
    ring = [(cx + R * math.cos(a), cy + R * math.sin(a)) for a in ang]
    d.polygon(ring, outline=_rgba(GREY, 200), width=max(int(1.4 * S), 1))
    for x, y in ring:
        d.line((cx, cy, x, y), fill=_rgba(GREY, 110), width=max(int(1 * S), 1))
    top = max(values.values()) if values and max(values.values()) > 0 else 1
    # square-root scale keeps the shape readable when one gesture dominates (labels stay exact)
    reach = {l: 0.12 + 0.88 * math.sqrt(values[l] / top) for l in labels}
    pts = [(cx + R * reach[l] * math.cos(a), cy + R * reach[l] * math.sin(a)) for l, a in zip(labels, ang)]
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon(pts, fill=_rgba(color, 70), outline=_rgba(color, 255), width=max(int(1.6 * S), 2))
    img.alpha_composite(layer)
    fl, fv = font(int(9 * S)), font(int(9 * S), bold=True)
    for (x, y), l, a in zip(ring, labels, ang):
        lx = cx + (R + 26 * S) * math.cos(a)
        ly = cy + (R + 18 * S) * math.sin(a)
        d.text((lx, ly - 7 * S), l, font=fl, fill=_rgba(SOFT), anchor="mm")
        d.text((lx, ly + 7 * S), f"{round(100 * values[l])}%", font=fv, fill=_rgba(TEXT), anchor="mm")
    return _done(img, w, h)


def timeline(rows, now, span, w, h, s, ticks=6):
    """Gantt-style rows: rows = [(label, color, [[t0, t1], ...], chip_text)] over the last `span`
    seconds; x axis in minutes ago."""
    img, d = _canvas(w, h)
    S = SS * s
    W, H = w * SS, h * SS
    left, right, top, bottom = 64 * S, 8 * S, 6 * S, 22 * S
    fl = font(int(9 * S))
    fc = font(int(8 * S), bold=True)
    row_h = (H - top - bottom) / max(len(rows), 1)
    x_of = lambda t: left + (W - left - right) * (1 - (now - t) / span)   # noqa: E731
    for i, (label, color, spans, chip) in enumerate(rows):
        cy = top + row_h * (i + 0.5)
        d.text((0, cy), label, font=fl, fill=_rgba(MUTED), anchor="lm")
        x = left
        while x < W - right:                              # dotted guide
            d.line((x, cy, min(x + 3 * S, W - right), cy), fill=_rgba(GREY, 120), width=max(int(1 * S), 1))
            x += 8 * S
        bh = 15 * S
        for t0, t1 in spans:
            x0, x1 = max(x_of(t0), left), x_of(max(t1, t0 + span / 300))
            if x1 <= left:
                continue
            x1 = max(x1, x0 + bh)
            d.rounded_rectangle((x0, cy - bh / 2, x1, cy + bh / 2), radius=4 * S, fill=_rgba(color))
            if chip and x1 - x0 > d.textlength(chip, font=fc) + 10 * S:
                d.text(((x0 + x1) / 2, cy), chip, font=fc, fill=(31, 36, 41, 255), anchor="mm")
    for i in range(ticks):
        frac = i / (ticks - 1)
        x = left + (W - left - right) * frac
        mins = round(span / 60 * (1 - frac))
        d.text((x, H - 4 * S), "now" if mins == 0 else f"-{mins}m", font=fl, fill=_rgba(MUTED), anchor="ms")
    return _done(img, w, h)


def arc_meter(d_px, s, frac, color=PINK, thickness=4):
    """A small ring that fills clockwise (like the weight dial in the white card)."""
    img, dr = _canvas(d_px, d_px)
    S = SS * s
    D = d_px * SS
    t = thickness * S
    box = (0, 0, D - 1, D - 1)
    dr.arc(box, 0, 360, fill=(230, 232, 236, 255), width=int(t))
    frac = min(max(frac, 0.0), 1.0)
    if frac > 0:
        dr.arc(box, -90, -90 + 360 * frac, fill=_rgba(color), width=int(t))
    return _done(img, d_px, d_px)


LEGEND = (("Clicks", "clicks", MINT), ("Scrolls", "scrolls", PINK), ("Shortcuts", "shortcuts", LAVENDER),
          ("Pauses", "pauses", GREY))
