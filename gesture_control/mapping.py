"""Control box (normalized camera coords) -> screen pixels."""


class BoxMapper:
    def __init__(self, box, screen):
        """box = [x0, y0, x1, y1] in 0..1; screen = (left, top, width, height) in physical pixels."""
        self.box = list(box)
        self.screen = screen

    def map(self, x, y):
        """Unclamped mapping; points outside the box land off-screen (see clamp)."""
        x0, y0, x1, y1 = self.box
        left, top, w, h = self.screen
        u = (x - x0) / (x1 - x0)
        v = (y - y0) / (y1 - y0)
        return (left + u * (w - 1), top + v * (h - 1))

    def clamp(self, p):
        left, top, w, h = self.screen
        return (min(max(p[0], left), left + w - 1), min(max(p[1], top), top + h - 1))

    def in_zone(self, x, y, margin):
        x0, y0, x1, y1 = self.box
        return x0 - margin <= x <= x1 + margin and y0 - margin <= y <= y1 + margin


def default_box(screen_aspect, cam_aspect):
    """Starting control box before calibration: the middle of the camera view, screen-shaped."""
    return fit_box((0.30, 0.22), (0.70, 0.62), screen_aspect, cam_aspect)


def fit_box(p1, p2, screen_aspect, cam_aspect, min_size=0.15):
    """Build a control box from two calibration corners, padded to the screen's shape.

    screen_aspect = width/height of the screen; cam_aspect = width/height of the camera image.
    """
    x0, x1 = sorted((p1[0], p2[0]))
    y0, y1 = sorted((p1[1], p2[1]))
    w, h = max(x1 - x0, min_size), max(y1 - y0, min_size)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    # Box shape in real proportions is (w * cam_aspect) / h; grow the short side to match the screen.
    if (w * cam_aspect) / h < screen_aspect:
        w = h * screen_aspect / cam_aspect
    else:
        h = w * cam_aspect / screen_aspect
    w, h = min(w, 1.0), min(h, 1.0)
    cx = min(max(cx, w / 2), 1 - w / 2)
    cy = min(max(cy, h / 2), 1 - h / 2)
    return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
