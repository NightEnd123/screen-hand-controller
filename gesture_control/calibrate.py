"""Guided control-box calibration: hold your fingertip still at two corners."""
from collections import deque

from .mapping import fit_box

STEPS = ("TOP-LEFT", "BOTTOM-RIGHT")


class Calibrator:
    def __init__(self, screen_aspect, cam_aspect, hold_s=1.5, still=0.012, timeout_s=30):
        self.screen_aspect, self.cam_aspect = screen_aspect, cam_aspect
        self.hold_s, self.still, self.timeout_s = hold_s, still, timeout_s
        self.points = []
        self.window = deque()
        self.t0 = None
        self.gap_until = 0.0
        self.progress = 0.0

    def update(self, t, hand):
        """Returns (status text, result) where result is None (keep going), a box, or "timeout"."""
        if self.t0 is None:
            self.t0 = t
        if t - self.t0 > self.timeout_s:
            return "Calibration timed out", "timeout"
        step = STEPS[len(self.points)]
        text = f"Point at the {step} corner of a comfortable area and hold still"
        if t < self.gap_until or hand is None:
            self.window.clear()
            self.progress = 0.0
            return text, None
        tip = (float(hand.img[8, 0]), float(hand.img[8, 1]))
        self.window.append((t, tip))
        while self.window and t - self.window[0][0] > self.hold_s:
            self.window.popleft()
        xs = [p[0] for _, p in self.window]
        ys = [p[1] for _, p in self.window]
        if max(xs) - min(xs) > self.still or max(ys) - min(ys) > self.still:
            # moved: restart the hold from this frame
            self.window.clear()
            self.window.append((t, tip))
        span = t - self.window[0][0]
        self.progress = min(span / self.hold_s, 1.0)
        if span >= self.hold_s * 0.95:
            self.points.append((sum(xs) / len(xs), sum(ys) / len(ys)))
            self.window.clear()
            self.gap_until = t + 0.8
            self.t0 = t
            if len(self.points) == len(STEPS):
                return "Saved", fit_box(*self.points, self.screen_aspect, self.cam_aspect)
        return text, None
