"""First-run setup: fits the app to the person's hand, camera and pinch style.

Pure logic like calibrate.py: the engine thread calls update(t, hand) every frame and shows the
returned View in the setup window (ui.py). Nothing is written until finish() hands back the
settings to save.

Steps:
  welcome      pick the hand you'll use (and the camera)
  hand_check   hold that hand up open: checks it's the right hand and learns whether this camera
               needs the tracker's left/right label swapped
  box          the control box: point at two corners (calibrate.Calibrator)
  pinch_left   tap thumb + index 3 times: measures how far *your* pinches open and close
  pinch_right  the same with thumb + middle finger
  done         cheat sheet
"""
from collections import deque
from dataclasses import dataclass, field

from .calibrate import Calibrator
from .features import INDEX, PINKY, compute

STEPS = ("welcome", "hand_check", "box", "pinch_left", "pinch_right", "done")
TITLES = {
    "welcome": "Welcome",
    "hand_check": "Show your hand",
    "box": "Choose your control area",
    "pinch_left": "Left click",
    "pinch_right": "Right click",
    "done": "All set",
}
# Shown at the end of setup (same as the README table).
GESTURE_SHEET = [
    ("Point (index finger up)", "move the cursor"),
    ("Thumb + index pinch", "left click (twice = double-click; hold and move = drag)"),
    ("Thumb + middle pinch", "right click"),
    ("Index + middle together, move up/down", "scroll"),
    ("Open palm, quick swipe", "left/right = previous/next tab; down/up = minimize/maximize"),
    ("Three fingers up, slide sideways", "switch windows (Alt+Tab)"),
    ("V-sign: hold still / move up-down", "play-pause / volume"),
    ("Call-me sign (thumb + pinky), hold", "voice typing"),
    ("Thumbs-down / thumbs-up, hold", "pause / resume gestures (or Ctrl+Alt+G)"),
]
CYCLES = 3                # pinches to measure per finger
# Poses with other fingers up: the hand isn't in the pointing pose pinches start from (and the
# change into pointing would look like a pinch), so measuring restarts.
NOT_POINTING = ("palm", "three", "two", "victory", "call", "thumbs_up", "thumbs_down")


@dataclass
class View:
    step: str
    number: int           # 1-based step number, for "Step 2 of 6"
    total: int
    title: str
    text: str
    progress: float = 0.0
    warn: str = ""
    points: list = field(default_factory=list)   # calibration corners so far (normalized), to draw


def geometric_hand(hand):
    """'Right' or 'Left' from the shape alone, for a hand held up with the palm toward the screen.

    In the mirrored image a right palm has the index knuckle left of the pinky knuckle."""
    return "Right" if hand.img[PINKY[0], 0] > hand.img[INDEX[0], 0] else "Left"


class PinchMeter:
    """Counts pinch-and-release cycles of one thumb-fingertip gap and measures their open and
    closed levels, adapting to however big or tiny the person's pinches are."""

    def __init__(self, min_range=0.04, window_s=1.0, frac=0.6, agree=0.1):
        self.min_range, self.window_s, self.frac, self.agree = min_range, window_s, frac, agree
        self.hist = deque()
        self.closed = False
        self.cycle_open = self.cycle_min = 0.0
        self.opens, self.closes = [], []

    def reset(self):
        """Forget the recent gaps (not the finished cycles)."""
        self.hist.clear()
        self.closed = False

    def _tail(self):
        """The latest run of up to CYCLES pinches that closed to a similar level. Shifting from
        one hand pose to another can look like a pinch; requiring agreement filters those out."""
        n = 0
        for k in range(1, min(CYCLES, len(self.closes)) + 1):
            tail = self.closes[-k:]
            if max(tail) - min(tail) > self.agree:
                break
            n = k
        return n

    @property
    def count(self):
        return self._tail()

    def update(self, t, gap):
        self.hist.append((t, gap))
        while self.hist and t - self.hist[0][0] > self.window_s:
            self.hist.popleft()
        gaps = [g for _, g in self.hist]
        hi, lo = max(gaps), min(gaps)
        rng = hi - lo
        if not self.closed:
            if rng >= self.min_range and gap <= hi - self.frac * rng:
                self.closed, self.cycle_open, self.cycle_min = True, hi, gap
        else:
            self.cycle_min = min(self.cycle_min, gap)
            if gap >= self.cycle_min + self.frac * (self.cycle_open - self.cycle_min):
                self.closed = False
                self.opens.append(self.cycle_open)
                self.closes.append(self.cycle_min)

    def levels(self):
        """(depths, closes) of the agreeing pinches, or None if there aren't CYCLES of them yet."""
        n = self._tail()
        if n < CYCLES:
            return None
        return ([o - c for o, c in zip(self.opens[-n:], self.closes[-n:])], self.closes[-n:])


DIP_FRAC = 0.35       # a pinch counts after dipping this fraction of your shallowest measured pinch
MAX_MARGIN = 0.05     # ... and ending at most this far above your weakest measured close


def pinch_settings(left, right, defaults):
    """Turn measured pinches into thresholds; a side that wasn't measured keeps its default.

    Thresholds are only ever loosened, for people whose pinches are smaller than the defaults
    allow (tiny pinches, or fingers that don't close far), never tightened: the defaults already
    suit normal pinches, and tightening them makes the occasional small pinch miss."""
    out, depths = {}, []
    for key, lv in (("pinch_max_left", left), ("pinch_max_right", right)):
        if lv is None:
            continue
        d, closes = lv
        depths += d
        need = round(max(closes) + MAX_MARGIN, 3)
        if need > defaults.get(key, 0):
            out[key] = min(need, 0.38)
    if depths:
        dip = round(max(DIP_FRAC * min(depths), 0.035), 3)
        if dip < defaults.get("pinch_dip", 1):
            out["pinch_dip"] = dip
    return {k: v for k, v in out.items() if v != defaults.get(k)}


class SetupWizard:
    def __init__(self, cfg, screen_aspect, cam_aspect, swap_now):
        self.cfg = cfg
        self.screen_aspect, self.cam_aspect = screen_aspect, cam_aspect
        self.swap_now = swap_now
        self.step = "welcome"
        self.hand = None                # "Left" / "Right"
        self.labels = []                # tracker labels seen during hand_check
        self.check_t = 0.0              # seconds of good open-hand frames
        self.prev_t = None
        self.calibrator = None
        self.box = None
        self.meters = {"pinch_left": PinchMeter(), "pinch_right": PinchMeter()}
        self.levels = {"pinch_left": None, "pinch_right": None}
        self.step_t0 = None
        self.swap = swap_now

    # ---- user choices (from the setup window) ----------------------------------------------
    def choose_hand(self, hand):
        self.hand = "Left" if hand.lower().startswith("l") else "Right"
        self._go("hand_check")

    def skip_step(self):
        """Keep the current setting for this step and move on."""
        nxt = STEPS[min(STEPS.index(self.step) + 1, len(STEPS) - 1)]
        if self.step == "welcome":
            self.hand = self.hand or "Right"
        self._go(nxt)

    def _go(self, step):
        self.step = step
        self.step_t0 = None
        if step == "box":
            self.calibrator = Calibrator(self.screen_aspect, self.cam_aspect, timeout_s=1e9)

    # ---- per frame ----------------------------------------------------------------------------
    def update(self, t, hand):
        dt = 0.0 if self.prev_t is None else min(t - self.prev_t, 0.1)
        self.prev_t = t
        if self.step_t0 is None:
            self.step_t0 = t
        step = self.step
        view = View(step, STEPS.index(step) + 1, len(STEPS), TITLES[step], "")
        side = (self.hand or "right").upper()

        if step == "welcome":
            view.text = ("Gesture Control lets you use your mouse with one hand in front of the webcam.\n\n"
                         "You should see yourself on the left. Which hand do you want to use?")
            if hand is None:
                view.warn = "No hand in view yet. That's fine, you'll show it in the next step."

        elif step == "hand_check":
            view.text = (f"Hold your {side} hand up, open, fingers apart, with your palm toward the "
                         "screen, about where it would be when using the mouse. Keep it there for a moment.")
            if hand is None:
                view.warn = "Can't see a hand yet. Make sure there's light on it and it's not too far away."
            else:
                f = compute(hand, self.cfg["gestures"])
                if f.pose != "palm":
                    view.warn = "Open your hand fully: all five fingers out."
                elif geometric_hand(hand) != self.hand:
                    other = "LEFT" if self.hand == "Right" else "RIGHT"
                    view.warn = f"That looks like your {other} hand (or the back of your hand). Use your {side} hand, palm toward the screen."
                else:
                    self.labels.append(hand.handedness)
                    self.check_t += dt
            view.progress = min(self.check_t / 1.2, 1.0)
            if view.progress >= 1.0:
                # The tracker should call this hand self.hand. If it mostly says the opposite,
                # this camera needs the label swapped (flip whatever is set now).
                agree = sum(1 for lab in self.labels if lab == self.hand)
                self.swap = self.swap_now if agree * 2 >= len(self.labels) else not self.swap_now
                self._go("box")

        elif step == "box":
            view.text = ("Pick the area your hand will move in. Small is fine: it's stretched to fill your screen.\n\n"
                         "Point your index finger where the screen's TOP-LEFT corner should be and hold still, "
                         "then the BOTTOM-RIGHT corner.")
            _, result = self.calibrator.update(t, hand)
            done = len(self.calibrator.points)
            view.points = list(self.calibrator.points)
            view.progress = min((done + self.calibrator.progress) / 2, 1.0)
            corner = "TOP-LEFT" if done == 0 else "BOTTOM-RIGHT"
            view.warn = "Can't see your hand." if hand is None else f"Now: hold still at the {corner} corner."
            if isinstance(result, list):
                self.box = result
                self._go("pinch_left")

        elif step in ("pinch_left", "pinch_right"):
            finger = "index" if step == "pinch_left" else "MIDDLE"
            view.text = (f"Point with your index finger, then tap your thumb and {finger} fingertip together "
                         f"{CYCLES} times. Use the size of pinch that feels natural: small is fine.")
            m = self.meters[step]
            if hand is None:
                view.warn = "Can't see your hand."
            else:
                f = compute(hand, self.cfg["gestures"])
                if f.pose in NOT_POINTING:
                    m.reset()
                    view.warn = "Point with your index finger (other fingers down), then pinch."
                else:
                    m.update(t, f.ratio_l if step == "pinch_left" else f.ratio_r)
                    view.warn = f"Pinches counted: {m.count} of {CYCLES}"
            view.progress = min(m.count / CYCLES, 1.0)
            if m.count >= CYCLES:
                self.levels[step] = m.levels()
                self._go("pinch_right" if step == "pinch_left" else "done")

        else:  # done
            view.text = "That's it. The app is ready to use. Here's what each gesture does (also in the README):"
            view.progress = 1.0
        return view

    def camera_problem(self, index):
        """View to show while the camera delivers no pictures."""
        return View(self.step, STEPS.index(self.step) + 1, len(STEPS), "Camera", (
            f"No picture from camera {index} yet. It can take a few seconds to start.\n\n"
            "If it stays blank: close other apps using the camera (Teams, Zoom, the Camera app), check "
            "Windows Settings > Privacy & security > Camera (turn on camera access and \"Let desktop "
            "apps access your camera\"), or try another camera."), warn="Waiting for the camera...")

    # ---- result ---------------------------------------------------------------------------------
    def finish(self, camera_index=None):
        """{(section, key): value} to write to config.toml."""
        up = {("profile", "setup_done"): True}
        if self.hand:
            up[("tracking", "hand")] = self.hand.lower()
        if self.swap != self.swap_now:
            up[("tracking", "swap_handedness")] = self.swap
        if self.box:
            up[("mapping", "box")] = list(self.box)
        for key, value in pinch_settings(self.levels["pinch_left"], self.levels["pinch_right"],
                                         self.cfg["gestures"]).items():
            up[("gestures", key)] = value
        if camera_index is not None:
            up[("camera", "index")] = camera_index
        return up
