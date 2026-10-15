"""Output thread: glides the cursor toward the latest target at ~120 Hz and runs actions in order."""
import logging
import math
import queue
import threading
import time

from .actions import cursor_pos

log = logging.getLogger(__name__)

BUTTON_ACTIONS = {"down", "up", "click"}


class OutputThread(threading.Thread):
    def __init__(self, act, glide_ms=15, hz=120, resolver=None):
        super().__init__(daemon=True, name="output")
        self.act = act
        self.tau = max(glide_ms, 1) / 1000
        self.period = 1 / hz
        self.target = None
        self.pos = None
        self.sent = None
        self.q = queue.Queue()
        self.wake = threading.Event()
        self.running = True
        self.resolver = resolver     # gesture name -> per-app replacement action, or None

    def submit(self, cursor, actions=()):
        self.target = cursor
        for a in actions:
            self.q.put(a)
        self.wake.set()

    def stop(self):
        self.running = False
        self.wake.set()

    def _flush(self):
        """Jump straight to the target so a click lands exactly where the engine meant."""
        if self.target is not None:
            self.pos = self.target
            self._send_move()

    def _send_move(self):
        p = (round(self.pos[0]), round(self.pos[1]))
        if p != self.sent:
            self.act.move(*p)
            self.sent = p

    def _do(self, a):
        if len(a) == 3 and a[0] in ("keys", "window") and self.resolver:
            a = self.resolver(a[2]) or a
        kind = a[0]
        if kind in BUTTON_ACTIONS:
            self._flush()
        if kind == "down":
            self.act.button(a[1], True)
        elif kind == "up":
            self.act.button(a[1], False)
        elif kind == "click":
            self.act.click(a[1])
        elif kind == "scroll":
            self.act.scroll(a[1], a[2])
        elif kind == "keys":
            self.act.keys(a[1])
        elif kind == "keydown":
            self.act.keydown(a[1])
        elif kind == "keyup":
            self.act.keyup(a[1])
        elif kind == "window":
            self.act.window(a[1])
        # "pause" is handled by the app, not here

    def run(self):
        last = time.perf_counter()
        try:
            while self.running:
                while True:
                    try:
                        a = self.q.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        self._do(a)
                    except Exception:
                        log.exception("action %r failed", a)
                now = time.perf_counter()
                dt, last = now - last, now
                target = self.target
                if target is None:
                    self.pos = None
                    self.sent = None
                    self.wake.wait(0.05)
                    self.wake.clear()
                    continue
                if self.pos is None:
                    self.pos = cursor_pos()
                k = 1 - math.exp(-dt / self.tau)
                self.pos = (self.pos[0] + (target[0] - self.pos[0]) * k,
                            self.pos[1] + (target[1] - self.pos[1]) * k)
                if math.dist(self.pos, target) < 0.5:
                    self.pos = target
                self._send_move()
                if self.pos == target:
                    self.wake.wait(0.05)    # settled: sleep until the next target arrives
                    self.wake.clear()
                else:
                    time.sleep(self.period)
        finally:
            self.act.release_all()
