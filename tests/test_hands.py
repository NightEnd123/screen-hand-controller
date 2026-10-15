"""The same gestures across many different hands: big/small, near/far, long/short fingers, wide
palms, short thumbs, tilted, off-centre, and left hands. Movements are given in hand sizes, as a
person would make the same physical gesture whatever their distance from the camera."""
import copy

import pytest

from gesture_control.config import DEFAULTS
from gesture_control.gestures import GestureEngine
from gesture_control.setup_wizard import SetupWizard
from tests.synth import pose

SCREEN = (0, 0, 1920, 1080)
FPS = 30
ASPECT = 4 / 3

HANDS = {
    "default": {},
    "far_small": dict(scale=1.0),
    "near_big": dict(scale=3.0),
    "long_fingers": dict(finger_len=1.2),
    "short_fingers": dict(finger_len=0.85),
    "wide_palm": dict(palm_width=1.3),
    "short_thumb": dict(thumb_len=0.8),
    "tilt_left": dict(tilt=-15),
    "tilt_right": dict(tilt=15),
    "low_right": dict(center=(0.62, 0.45)),
    "left_hand": dict(mirror=True),
    "left_far_tilted": dict(mirror=True, scale=1.3, tilt=12, center=(0.42, 0.4)),
    "left_big_long": dict(mirror=True, scale=2.6, finger_len=1.15, palm_width=1.2),
}


class Hand:
    def __init__(self, variant):
        self.v = dict(variant)
        self.center = self.v.pop("center", (0.5, 0.35))
        self.size = 0.09 * self.v.get("scale", 2.0)   # wrist -> middle knuckle, frame heights
        self.cfg = copy.deepcopy(DEFAULTS)
        self.cfg["tracking"]["hand"] = "left" if self.v.get("mirror") else "right"

    def at(self, name, dx=0.0, dy=0.0):
        """Pose `name` moved by (dx, dy) hand sizes from the start position."""
        cx, cy = self.center
        return pose(name, center=(cx + dx * self.size / ASPECT, cy + dy * self.size), **self.v)


class Run:
    def __init__(self, hand):
        self.eng = GestureEngine(hand.cfg, SCREEN)
        self.t, self.actions, self.cursors, self.modes = 0.0, [], [], []

    def feed(self, fn, seconds=None, frames=None):
        n = frames if frames is not None else round(seconds * FPS)
        for i in range(n):
            out = self.eng.update(self.t, fn(i, n) if callable(fn) else fn)
            self.actions += out.actions
            self.cursors.append(out.cursor)
            self.modes.append(out.mode)
            self.t += 1 / FPS
        return self

    def count(self, *prefix):
        return sum(1 for a in self.actions if a[:len(prefix)] == prefix)


@pytest.fixture(params=list(HANDS), ids=list(HANDS))
def hand(request):
    return Hand(HANDS[request.param])


def test_poses_are_recognised(hand):
    from gesture_control.features import compute
    for name in ("point", "two", "victory", "three", "palm", "fist", "thumbs_up", "thumbs_down", "call", "ok"):
        assert compute(hand.at(name), DEFAULTS["gestures"]).pose == name, name


def test_point_moves_cursor(hand):
    r = Run(hand).feed(lambda i, n: hand.at("point", dx=-1 + 2 * i / n), seconds=1)
    xs = [c[0] for c in r.cursors if c]
    assert r.actions == [] and xs[-1] - xs[5] > 200


def test_click_and_double_click(hand):
    r = Run(hand).feed(hand.at("point"), seconds=0.5).feed(hand.at("lpinch"), seconds=0.15)
    r.feed(hand.at("point"), seconds=0.5)
    assert r.count("down", "left") == 1 and r.count("up", "left") == 1
    for _ in range(2):
        r.feed(hand.at("lpinch"), seconds=0.12).feed(hand.at("point"), seconds=0.12)
    assert r.count("down", "left") == 3 and r.count("click", "right") == 0


def test_drag(hand):
    r = Run(hand).feed(hand.at("point"), seconds=0.5).feed(hand.at("lpinch"), seconds=0.2)
    r.feed(lambda i, n: hand.at("lpinch", dx=1.2 * i / n), seconds=0.6).feed(hand.at("point"), seconds=0.3)
    assert "drag" in r.modes and r.count("down", "left") == 1 and r.count("up", "left") == 1


def test_right_click(hand):
    r = Run(hand).feed(hand.at("point"), seconds=0.5).feed(hand.at("rpinch"), seconds=0.2)
    r.feed(hand.at("point"), seconds=0.4)
    assert r.count("click", "right") == 1 and r.count("down", "left") == 0


def test_resting_hand_does_nothing(hand):
    r = Run(hand).feed(hand.at("point"), seconds=0.3).feed(hand.at("fist"), seconds=1)
    r.feed(lambda i, n: hand.at("palm", dx=0.6 * i / n), seconds=2)        # slow drift
    assert r.actions == []


@pytest.mark.parametrize("d,expected", [((2.2, 0), "swipe_right"), ((-2.2, 0), "swipe_left"),
                                        ((0, 2.0), "swipe_down"), ((0, -2.0), "swipe_up")])
def test_swipes(hand, d, expected):
    dx, dy = d
    r = Run(hand).feed(hand.at("palm"), seconds=0.4)
    r.feed(lambda i, n: hand.at("palm", dx=dx * i / (n - 1), dy=dy * i / (n - 1)), frames=7)
    r.feed(hand.at("palm", dx=dx, dy=dy), seconds=0.3)
    assert [a[2] for a in r.actions] == [expected]


def test_scroll(hand):
    r = Run(hand).feed(hand.at("two"), seconds=0.3)
    r.feed(lambda i, n: hand.at("two", dy=-0.7 * min(i / 10, 1)), seconds=1.0)
    assert sum(a[2] for a in r.actions if a[0] == "scroll") > 3


def test_window_switcher(hand):
    r = Run(hand).feed(hand.at("three"), seconds=0.4)
    r.feed(lambda i, n: hand.at("three", dx=1.2 * i / (n - 1)), seconds=0.6).feed(hand.at("fist"), seconds=0.4)
    assert r.actions[0] == ("keydown", "alt") and r.actions[-1] == ("keyup", "alt")
    assert r.count("keys", "tab") >= 2


def test_holds(hand):
    r = Run(hand).feed(hand.at("victory"), seconds=1.5)
    assert [a[2] for a in r.actions] == ["victory_hold"]
    r = Run(hand).feed(hand.at("call"), seconds=2.0)
    assert [a[2] for a in r.actions] == ["call_hold"]
    r = Run(hand).feed(hand.at("thumbs_down"), seconds=1.0).feed(hand.at("thumbs_up"), seconds=1.0)
    assert r.actions == [("pause", True), ("pause", False)]


def test_other_hand_is_ignored(hand):
    other = dict(hand.v, mirror=not hand.v.get("mirror", False))
    r = Run(hand).feed(lambda i, n: pose("point", center=hand.center, **other), seconds=0.5)
    assert r.actions == [] and all(c is None for c in r.cursors)


def test_setup_hand_check_accepts_the_chosen_hand(hand):
    """The wizard's 'show your hand' step finishes for the hand chosen, and learns the label swap."""
    side = "left" if hand.v.get("mirror") else "right"
    for label_flipped in (False, True):
        wz = SetupWizard(DEFAULTS, 16 / 9, ASPECT, swap_now=True)
        wz.choose_hand(side)
        t = 0.0
        while wz.step == "hand_check" and t < 3:
            h = hand.at("palm")
            if label_flipped:
                h.handedness = "Right" if h.handedness == "Left" else "Left"
            wz.update(t, h)
            t += 1 / FPS
        assert wz.step == "box", "hand check never finished"
        assert wz.swap is (not label_flipped)   # flipped labels -> flip the swap setting
