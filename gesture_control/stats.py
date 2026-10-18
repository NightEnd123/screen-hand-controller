"""Session numbers for the dashboard: what you did, how you moved, and when gestures were on.

Pure logic: add() is called once per camera frame (engine thread) and snapshot() returns plain
data for the charts (UI thread). Python's GIL keeps the simple updates safe enough for display.
"""
import math
import threading
from collections import Counter, deque

# radar axes: dashboard name -> engine modes counted towards it
MODE_GROUPS = {
    "Point": ("point", "ok"),
    "Click": ("lpinch", "drag", "rpinch"),
    "Scroll": ("scroll",),
    "Swipe": ("palm",),
    "Switch": ("switcher",),
    "Media": ("victory", "volume", "call"),
}
_GROUP_OF = {m: g for g, modes in MODE_GROUPS.items() for m in modes}
STATES = ("active", "paused", "off")


class SessionStats:
    def __init__(self, speed_window=60, span_s=600):
        self.lock = threading.Lock()
        self.counts = Counter()            # clicks, scrolls, shortcuts, pauses
        self.mode_time = Counter()         # radar group -> seconds
        self.speed = deque(maxlen=speed_window)   # cursor px per second, one value per second
        self.span = span_s
        self.intervals = {k: [] for k in STATES + ("hand",)}   # [start, end] in seconds
        self.prev_t = None
        self.prev_mode = None
        self.sec = None
        self.dist = 0.0
        self.last_cursor = None

    def add(self, t, state, mode, actions=(), cursor=None):
        with self.lock:
            dt = 0.0 if self.prev_t is None else min(max(t - self.prev_t, 0.0), 0.5)
            self.prev_t = t
            group = _GROUP_OF.get(mode)
            if group and state == "active":
                self.mode_time[group] += dt
            for a in actions:
                if a[0] == "down" or a[0] == "click":
                    self.counts["clicks"] += 1
                elif a[0] in ("keys", "window") and len(a) == 3:
                    self.counts["shortcuts"] += 1
                elif a[0] == "keydown" and a[1] == "alt":
                    self.counts["shortcuts"] += 1           # window switcher opened
                elif a[0] == "pause" and a[1]:
                    self.counts["pauses"] += 1
            if mode == "scroll" and self.prev_mode != "scroll":
                self.counts["scrolls"] += 1
            self.prev_mode = mode
            # cursor speed, bucketed per whole second
            if cursor is not None and self.last_cursor is not None:
                self.dist += math.dist(cursor, self.last_cursor)
            self.last_cursor = cursor
            sec = int(t)
            if self.sec is None:
                self.sec = sec
            while sec > self.sec:
                self.speed.append(self.dist)
                self.dist = 0.0
                self.sec += 1
            # timeline
            self._extend(state, t)
            if state == "active" and mode not in ("idle", "typing", "calibrating", None):
                self._extend("hand", t)
            for rows in self.intervals.values():
                while rows and rows[0][1] < t - self.span:
                    rows.pop(0)

    def _extend(self, key, t):
        rows = self.intervals.get(key)
        if rows is None:
            return
        if rows and t - rows[-1][1] <= 1.5:
            rows[-1][1] = t
        else:
            rows.append([t, t])

    def snapshot(self):
        with self.lock:
            return {
                "counts": dict(self.counts),
                "mode_time": dict(self.mode_time),
                "speed": list(self.speed),
                "intervals": {k: [list(r) for r in v] for k, v in self.intervals.items()},
                "now": self.prev_t,
                "span": self.span,
            }
