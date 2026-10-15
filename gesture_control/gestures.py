"""Gesture state machine. Pure logic: no camera, no OS calls, so it is unit-testable.

Each frame: update(t, hand) -> Output(cursor, actions, mode, info)
  cursor  : (x, y) screen pixels to glide to, or None = leave the mouse alone
  actions : list of tuples, executed in order by actions.py:
            ("down"|"up"|"click", "left"|"right"), ("scroll", h, v) in wheel notches,
            ("keys", "ctrl+tab"), ("keydown", "alt"), ("keyup", "alt"),
            ("window", "minimize"|"maximize"), ("pause", True|False)
            Shortcut actions carry the gesture's name as a 3rd item, e.g. ("keys", "ctrl+tab",
            "swipe_right"), so per-app settings can swap in a different action at run time.
"""
import math
from collections import deque
from dataclasses import dataclass, field

from .features import compute
from .filters import OneEuro2D
from .mapping import BoxMapper


@dataclass
class Output:
    cursor: tuple | None
    actions: list
    mode: str
    info: dict = field(default_factory=dict)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


POINTING = ("point", "ok")     # poses that move the cursor (and can pinch-click)


class GestureEngine:
    def __init__(self, cfg, screen):
        self.cfg = cfg
        self.g = cfg["gestures"]
        self.mapper = BoxMapper(cfg["mapping"]["box"], screen)
        s = cfg["smoothing"]
        self.filter = OneEuro2D(min_cutoff=s["min_cutoff"], beta=s["beta"], d_cutoff=s["d_cutoff"])
        self.paused = False
        self.last_seen = None
        self.prev_t = None
        self._reset()

    # ---- state -------------------------------------------------------------------------
    def _reset(self):
        self.filter.reset()
        self.mode = "idle"
        self.pose, self.pose_cand, self.pose_count = "none", None, 0
        self.lpinch = self.rpinch = False
        self.lcount = self.rcount = 0
        self.armed = False            # a pinch may only start after the hand was open with fingers out
        self.lockout_until = 0.0      # no swipes / switcher / scroll right after a click
        self.three_since = None
        self.two_since = None
        self.open_count = 0           # consecutive frames with the pinch gap open (release / re-arm)
        self.gaps = deque()           # (t, ratio_l, ratio_r) recent pinch gaps, for dip detection
        self.pinch_base = self.pinch_min = 0.0
        self.button_down = False
        self.raw = None
        self.offset = (0.0, 0.0)
        self.cursor = None            # last cursor position we drove
        self.freeze = None            # frozen cursor position
        self.freeze_until = None      # time a post-click freeze ends
        self.pinch_raw0 = None
        self.history = deque()        # (t, cursor, ratio_l, ratio_r)
        self.scroll_anchor = None
        self.swipe_hist = deque()
        self.swipe_cool_until = 0.0
        self.switcher = None
        self.thumb_pose, self.thumb_since, self.thumb_fired = None, 0.0, False
        self.vee = None               # V-sign state: hold for play/pause, or move for volume
        self.call_since, self.call_fired = None, False
        self.hold_progress = None     # 0..1 for the on-screen ring while a hold gesture charges

    def _end_all(self):
        """Release anything held and drop back to idle (filter/offset kept)."""
        acts = []
        if self.button_down:
            acts.append(("up", "left"))
        if self.switcher is not None:
            acts.append(("keyup", "alt"))
        self.button_down = self.lpinch = self.rpinch = False
        self.lcount = self.rcount = 0
        self.armed = False
        self.open_count = 0
        self.gaps.clear()
        self.switcher = self.scroll_anchor = None
        self.freeze = self.freeze_until = None
        self.swipe_hist.clear()
        self.vee = self.call_since = None
        return acts

    def set_paused(self, paused):
        acts = self._end_all() if paused else []
        self.paused = paused
        self.thumb_pose = None
        return acts

    def set_box(self, box):
        self.mapper.box = list(box)

    # ---- helpers -----------------------------------------------------------------------
    def _stable_pose(self, pose):
        if pose == self.pose_cand:
            self.pose_count += 1
        else:
            self.pose_cand, self.pose_count = pose, 1
        if self.pose_count >= self.g["pose_frames"]:
            self.pose = pose
        return self.pose

    def _snap(self, t, which, off):
        """Cursor position from just before the fingers started closing (gap still >= off)."""
        lookback = self.g["snap_lookback_ms"] / 1000
        oldest = None
        for ht, cur, rl, rr in reversed(self.history):
            if t - ht > lookback:
                break
            oldest = cur
            if (rl if which == "l" else rr) >= off:
                return cur
        return oldest

    def _unfreeze(self, raw_ref):
        if self.freeze is not None and raw_ref is not None:
            self.offset = _sub(self.freeze, raw_ref)
        self.freeze = self.freeze_until = None

    # ---- main --------------------------------------------------------------------------
    def update(self, t, hand, suppress=False):
        dt = min(t - self.prev_t, 0.1) if self.prev_t is not None else 0.0
        self.prev_t = t
        g = self.g
        info = {}

        f = None
        if hand is not None:
            f = compute(hand, g)
            want = self.cfg["tracking"]["hand"].lower()
            if (want != "any" and hand.handedness.lower() != want) or f.size < self.cfg["tracking"]["min_hand_size"]:
                f = None

        if suppress:
            acts = self._end_all()
            self.mode = "typing"
            return Output(None, acts, self.mode, info)

        if f is None:
            if self.last_seen is not None and t - self.last_seen <= g["hand_lost_grace_ms"] / 1000:
                return Output(None, [], self.mode, info)   # brief dropout: hold state
            acts = self._end_all()
            if self.last_seen is not None:
                self.filter.reset()
                self.offset = (0.0, 0.0)
                self.raw = None
                self.history.clear()
            self.last_seen = None
            self.pose, self.pose_cand, self.pose_count = "none", None, 0
            self.thumb_pose = None
            self.mode = "paused" if self.paused else "idle"
            return Output(None, acts, self.mode, info)

        self.last_seen = t
        acts = []
        pose = self._stable_pose(f.pose)
        info.update(pose=pose, raw_pose=f.pose, ratio_l=f.ratio_l, ratio_r=f.ratio_r, ext=f.ext)

        # Thumbs up / down held -> resume / pause. Checked even while paused.
        if pose in ("thumbs_up", "thumbs_down"):
            if self.thumb_pose != pose:
                self.thumb_pose, self.thumb_since, self.thumb_fired = pose, t, False
            info["hold"] = min((t - self.thumb_since) / g["thumb_hold_s"], 1.0)
            if not self.thumb_fired and t - self.thumb_since >= g["thumb_hold_s"]:
                self.thumb_fired = True
                if pose == "thumbs_down" and not self.paused:
                    acts += self.set_paused(True)
                    acts.append(("pause", True))
                elif pose == "thumbs_up" and self.paused:
                    self.set_paused(False)
                    acts.append(("pause", False))
        else:
            self.thumb_pose = None

        if self.paused:
            self.mode = "paused"
            return Output(None, acts, self.mode, info)

        # Raw cursor: mapped + One Euro filtered (unclamped), plus a decaying offset after freezes.
        pt = f.index_knuckle if self.cfg["mapping"]["cursor_point"] == "index_knuckle" else f.index_tip
        raw = self.filter(t, self.mapper.map(*pt))
        sm = self.cfg["smoothing"]
        if self.raw is not None and dt > 0:
            d = _sub(raw, self.raw)
            moved = math.hypot(*d)
            speed = moved / dt
            fast = True
            if sm["precision"]:
                # Precision mode: slow, careful movement moves the cursor less than the hand
                # (finer control, less jitter); fast movement moves it 1:1.
                k = min(max((speed - sm["precision_slow"]) / (sm["precision_fast"] - sm["precision_slow"]), 0.0), 1.0)
                gain = sm["precision_gain"] + (1 - sm["precision_gain"]) * k
                self.offset = (self.offset[0] + d[0] * (gain - 1), self.offset[1] + d[1] * (gain - 1))
                fast = speed >= sm["precision_fast"]
            if fast and self.offset != (0.0, 0.0):
                # Re-sync the cursor with the finger during fast moves (unnoticeable then).
                k = max(0.0, 1.0 - moved / sm["offset_decay_px"])
                self.offset = (self.offset[0] * k, self.offset[1] * k)
        self.raw = raw
        in_zone = self.mapper.in_zone(*f.index_tip, self.cfg["tracking"]["zone_margin"])
        here = self.cursor if self.cursor is not None else self.mapper.clamp(_add(raw, self.offset))

        # Pinches are detected as a quick dip in the thumb-fingertip gap relative to where it was a
        # moment ago (tiny pinches only close ~0.06-0.14), and must end below a cap. Release = the
        # gap recovers part of the way back toward where it started.
        self.gaps.append((t, f.ratio_l, f.ratio_r))
        while self.gaps and t - self.gaps[0][0] > g["pinch_window_ms"] / 1000:
            self.gaps.popleft()
        base_l = max(x[1] for x in self.gaps)
        base_r = max(x[2] for x in self.gaps)
        if self.lpinch or self.rpinch:
            gap = f.ratio_l if self.lpinch else f.ratio_r
            self.pinch_min = min(self.pinch_min, gap)
            thr = min(g["pinch_off"], self.pinch_min + g["release_frac"] * (self.pinch_base - self.pinch_min))
            is_open = gap > thr
        else:
            is_open = f.ratio_l > g["pinch_max_left"] and f.ratio_r > g["pinch_max_right"]
        self.open_count = self.open_count + 1 if is_open else 0
        released = self.open_count >= g["release_frames"]

        if self.switcher is not None:
            acts += self._switcher_step(t, f)
        elif self.lpinch:
            if released or f.index_folded:
                acts.append(("up", "left"))
                self.button_down = self.lpinch = False
                self.armed = (bool(f.ext[1]) or pose in POINTING) and pose not in ("fist", "thumbs_up", "thumbs_down")
                self.gaps.clear()
                self.lockout_until = t + g["after_click_lockout_ms"] / 1000
                self.freeze = here
                self.freeze_until = t + g["release_freeze_ms"] / 1000
                self.mode = "rest"
            elif self.freeze is not None and math.dist(raw, self.pinch_raw0) > g["drag_threshold_px"]:
                self._unfreeze(self.pinch_raw0)      # becomes a drag; cursor follows relative to the snap point
                self.mode = "drag"
        elif self.rpinch:
            if released or f.middle_folded:
                acts.append(("click", "right"))
                self.rpinch = False
                self.armed = (bool(f.ext[1]) or pose in POINTING) and pose not in ("fist", "thumbs_up", "thumbs_down")
                self.gaps.clear()
                self.lockout_until = t + g["after_click_lockout_ms"] / 1000
                self.freeze_until = t + g["release_freeze_ms"] / 1000
                self.mode = "rest"
        elif self.scroll_anchor is None:
            # Arm only from a hand with the index pointing out and the gap clearly open. A relaxed
            # curled hand (steady "fist" pose) or an index curled deep into the palm disarms, so a
            # resting hand can't fake a pinch. A single mid-pinch frame with no extended fingers is
            # normal (the index bends to meet the thumb), hence the steady pose, not the raw one.
            if f.index_folded or pose in ("fist", "thumbs_up", "thumbs_down"):
                self.armed = False
            elif released and (f.ext[1] or pose in POINTING):
                self.armed = True
            # Whichever fingertip is closer to the thumb decides left vs right (the index and
            # middle tips often sit close together, so the thumb can be near both).
            l_cand = (self.armed and f.ratio_l < g["pinch_max_left"] and f.ratio_l <= base_l - g["pinch_dip"]
                      and not f.index_folded and f.ratio_l <= f.ratio_r)
            r_cand = (self.armed and f.ratio_r < g["pinch_max_right"] and f.ratio_r <= base_r - g["pinch_dip"]
                      and not f.middle_folded and f.ratio_r < f.ratio_l)
            self.lcount = self.lcount + 1 if (l_cand and in_zone) else 0
            self.rcount = self.rcount + 1 if (r_cand and in_zone) else 0
            if self.lcount >= g["pinch_frames"]:
                self.pinch_base, self.pinch_min = base_l, f.ratio_l
                self.open_count = 0
                self.freeze = self._snap(t, "l", base_l - g["pinch_dip"] / 2) or here
                self.freeze_until = None
                self.pinch_raw0 = raw
                self.lpinch = self.button_down = True
                self.lcount = 0
                self.swipe_hist.clear()
                self.mode = "lpinch"
                acts.append(("down", "left"))
            elif self.rcount >= g["pinch_frames"]:
                self.pinch_base, self.pinch_min = base_r, f.ratio_r
                self.open_count = 0
                self.freeze = self._snap(t, "r", base_r - g["pinch_dip"] / 2) or here
                self.freeze_until = None
                self.rpinch = True
                self.rcount = 0
                self.mode = "rpinch"

        pinching = self.lpinch or self.rpinch
        if self.switcher is None and not pinching:
            acts += self._pose_modes(t, dt, f, pose, in_zone, raw, here)

        # Post-click freeze runs out -> cursor follows the finger again (no jump, via offset).
        if (self.freeze_until is not None and t >= self.freeze_until
                and not pinching and self.scroll_anchor is None and self.switcher is None):
            self._unfreeze(raw)

        unclamped = _add(raw, self.offset)
        free = self.mapper.clamp(unclamped)
        if sm["precision"] and free != unclamped and self.freeze is None:
            # Pushing past a screen edge: keep the cursor on the edge, and respond immediately
            # when the hand comes back (like a mouse against the edge of the screen).
            self.offset = _sub(free, raw)
        if self.freeze is not None:
            cursor = self.freeze
        elif self.lpinch:                                        # dragging
            cursor = free
        elif pose in POINTING and self.switcher is None and self.scroll_anchor is None:
            cursor = free
            self.mode = pose
        else:
            cursor = None
        if cursor is not None:
            self.cursor = cursor

        self.history.append((t, self.cursor, f.ratio_l, f.ratio_r))
        while self.history and t - self.history[0][0] > 1.0:
            self.history.popleft()

        info["offset"] = self.offset
        info["in_zone"] = in_zone
        if self.hold_progress is not None and "hold" not in info:
            info["hold"] = self.hold_progress
        return Output(cursor, acts, self.mode, info)

    # ---- pose-driven modes ---------------------------------------------------------------
    def _pose_modes(self, t, dt, f, pose, in_zone, raw, here):
        g = self.g
        acts = []

        # Scroll: two fingers together, hand works like a joystick around where it started.
        if self.scroll_anchor is not None:
            if pose != "two":
                self.scroll_anchor = None
                self._unfreeze(raw)
                self.mode = "rest"
            else:
                dz = g["scroll_deadzone"]
                dy = (self.scroll_anchor[1] - f.palm[1]) / f.size
                dx = (f.palm[0] - self.scroll_anchor[0]) / f.size

                def rate(d, dead):
                    m = max(0.0, abs(d) - dead)
                    return math.copysign(min(g["scroll_gain"] * m, g["scroll_max"]), d) if m else 0.0

                v, h = rate(dy, dz) * dt, rate(dx, dz * 1.5) * dt
                if v or h:
                    acts.append(("scroll", h, v))
                return acts
        elif pose == "two" and in_zone and t >= self.lockout_until:
            if self.two_since is None:
                self.two_since = t
            if t - self.two_since < g["scroll_hold_ms"] / 1000:
                return acts
            self.two_since = None
            self.scroll_anchor = f.palm
            self.freeze, self.freeze_until = here, None
            self.mode = "scroll"
            return acts

        self.two_since = None
        self.hold_progress = None

        # V-sign: hold still = play/pause; move up/down = volume (joystick, like scroll).
        if pose == "victory" and in_zone and t >= self.lockout_until:
            if self.vee is None:
                self.vee = {"anchor": f.palm[1], "since": t, "moving": False, "acc": 0.0, "fired": False}
            v = self.vee
            dy = (v["anchor"] - f.palm[1]) / f.size        # hand up = positive
            if (not v["moving"] and not v["fired"] and t - v["since"] >= g["volume_arm_s"]
                    and abs(dy) > g["volume_deadzone"]):
                v["moving"] = True
            if v["moving"]:
                self.mode = "volume"
                m = max(0.0, abs(dy) - g["volume_deadzone"])
                v["acc"] += min(g["volume_gain"] * m, g["volume_max"]) * dt
                while v["acc"] >= 1:
                    v["acc"] -= 1
                    acts.append(("keys", "volume_up" if dy > 0 else "volume_down"))
            elif not v["fired"]:
                self.mode = "victory"
                self.hold_progress = min((t - v["since"]) / g["gesture_hold_s"], 1.0)
                if t - v["since"] >= g["gesture_hold_s"]:
                    v["fired"] = True
                    acts.append(shortcut_action(self.cfg["shortcuts"]["victory_hold"], "victory_hold"))
            return acts
        self.vee = None

        # Call-me sign held = voice typing (or whatever call_hold is set to).
        if pose == "call" and in_zone and t >= self.lockout_until:
            if self.call_since is None:
                self.call_since, self.call_fired = t, False
            self.mode = "call"
            if not self.call_fired:
                self.hold_progress = min((t - self.call_since) / g["gesture_hold_s"], 1.0)
                if t - self.call_since >= g["gesture_hold_s"]:
                    self.call_fired = True
                    acts.append(shortcut_action(self.cfg["shortcuts"]["call_hold"], "call_hold"))
            return acts
        self.call_since = None

        # Window switcher: three fingers held still-ish for a moment.
        if pose == "three" and in_zone and t >= self.lockout_until:
            if self.three_since is None:
                self.three_since = t
        else:
            self.three_since = None
        if self.three_since is not None and t - self.three_since >= g["switcher_hold_ms"] / 1000:
            self.three_since = None
            self.switcher = {"anchor": f.palm[0], "steps": 0, "t0": t, "miss": 0}
            self.freeze, self.freeze_until = here, None
            self.mode = "switcher"
            return [("keydown", "alt"), ("keys", "tab")]

        # Open-palm swipes.
        if f.pose == "palm":
            self.mode = "palm"
            self.swipe_hist.append((t, f.palm, in_zone))
            win = g["swipe_window_ms"] / 1000
            while self.swipe_hist and t - self.swipe_hist[0][0] > win:
                self.swipe_hist.popleft()
            if (t >= max(self.swipe_cool_until, self.lockout_until) and len(self.swipe_hist) >= 3
                    and any(z for _, _, z in self.swipe_hist)):   # must pass through the control box
                dx, dy = _sub(f.palm, self.swipe_hist[0][1])
                r, md = g["swipe_axis_ratio"], g["swipe_min_dist"]
                name = None
                if abs(dx) >= md and abs(dx) >= r * abs(dy):
                    name = "swipe_right" if dx > 0 else "swipe_left"
                elif abs(dy) >= md and abs(dy) >= r * abs(dx):
                    name = "swipe_down" if dy > 0 else "swipe_up"
                if name:
                    acts.append(shortcut_action(self.cfg["shortcuts"][name], name))
                    self.swipe_cool_until = t + g["swipe_cooldown_ms"] / 1000
                    self.swipe_hist.clear()
        else:
            self.swipe_hist.clear()
            if pose not in POINTING and self.freeze is None:
                self.mode = "rest"
        return acts

    def _switcher_step(self, t, f):
        g = self.g
        sw = self.switcher
        acts = []
        if f.pose == "three":
            sw["miss"] = 0
            k = int((f.palm[0] - sw["anchor"]) / (g["switcher_step"] * f.size))
            while k > sw["steps"]:
                acts.append(("keys", "tab"))
                sw["steps"] += 1
            while k < sw["steps"]:
                acts.append(("keys", "shift+tab"))
                sw["steps"] -= 1
        else:
            sw["miss"] += 1
        if sw["miss"] >= g["switcher_exit_frames"] or t - sw["t0"] > g["switcher_timeout_s"]:
            acts.append(("keyup", "alt"))
            self.switcher = None
            self._unfreeze(self.raw)
            self.mode = "rest"
        return acts


def shortcut_action(spec, name=None):
    """'window:minimize' -> ("window", "minimize", name); anything else is a key combo."""
    if spec.startswith("window:"):
        a = ("window", spec.split(":", 1)[1])
    else:
        a = ("keys", spec)
    return a + (name,) if name else a
