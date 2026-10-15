import copy
import math
import random

import pytest

from gesture_control.config import DEFAULTS, save_box, load
from gesture_control.filters import OneEuro
from gesture_control.gestures import GestureEngine
from gesture_control.mapping import BoxMapper, fit_box
from tests.synth import pose

SCREEN = (0, 0, 2256, 1504)
FPS = 30


def engine(**over):
    cfg = copy.deepcopy(DEFAULTS)
    for sec, vals in over.items():
        cfg[sec].update(vals)
    return GestureEngine(cfg, SCREEN)


class Run:
    """Feed frames at 30 fps and collect everything the engine does."""

    def __init__(self, eng):
        self.eng, self.t, self.actions, self.cursors, self.modes = eng, 0.0, [], [], []

    def feed(self, hand_fn, seconds=None, frames=None):
        n = frames if frames is not None else round(seconds * FPS)
        for i in range(n):
            out = self.eng.update(self.t, hand_fn(i, n) if callable(hand_fn) else hand_fn)
            self.actions += out.actions
            self.cursors.append(out.cursor)
            self.modes.append(out.mode)
            self.t += 1 / FPS
        return self

    def count(self, *prefix):
        return sum(1 for a in self.actions if a[:len(prefix)] == prefix)


# ---- filter / mapping ----------------------------------------------------------------------

def test_one_euro_removes_jitter_when_still():
    random.seed(1)
    f = OneEuro(min_cutoff=0.5, beta=0.01)
    outs = [f(i / FPS, 1000 + random.uniform(-8, 8)) for i in range(120)]
    spread = max(outs[60:]) - min(outs[60:])
    assert spread < 0.4 * 16, spread   # raw jitter is 16 px peak-to-peak


def test_one_euro_keeps_up_with_fast_motion():
    f = OneEuro(min_cutoff=0.5, beta=0.01)
    out = 0
    for i in range(30):
        out = f(i / FPS, i * 60.0)   # 1800 px/s
    assert 29 * 60 - out < 120       # lags by less than ~2 frames' worth


def test_mapping_corners_and_clamp():
    m = BoxMapper([0.25, 0.2, 0.75, 0.6], SCREEN)
    assert m.map(0.25, 0.2) == (0, 0)
    assert m.map(0.75, 0.6) == pytest.approx((2255, 1503))
    assert m.clamp(m.map(0.0, 1.0)) == (0, 1503)


def test_default_box_matches_screen_shape():
    x0, y0, x1, y1 = engine().mapper.box
    assert ((x1 - x0) * 4 / 3) / (y1 - y0) == pytest.approx(2256 / 1504, rel=0.01)
    assert (x0 + x1) / 2 == pytest.approx(0.5)


def test_fit_box_pads_to_screen_aspect():
    b = fit_box((0.4, 0.2), (0.6, 0.6), 1.5, 4 / 3)
    assert ((b[2] - b[0]) * 4 / 3) / (b[3] - b[1]) == pytest.approx(1.5)
    assert 0 <= b[0] < b[2] <= 1 and 0 <= b[1] < b[3] <= 1


def test_save_box_keeps_comments(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("# hi\n[mapping]\nbox = [0, 0, 1, 1]  # old\ncursor_point = \"index_tip\"\n")
    save_box([0.1, 0.2, 0.3, 0.4], p)
    assert "# hi" in p.read_text()
    assert load(p)["mapping"]["box"] == pytest.approx([0.1, 0.2, 0.3, 0.4])


# ---- gestures ------------------------------------------------------------------------------

def moving_point(x0, x1):
    return lambda i, n: pose("point", center=(x0 + (x1 - x0) * i / max(n - 1, 1), 0.35))


def test_point_moves_cursor_without_actions():
    r = Run(engine()).feed(moving_point(0.4, 0.6), seconds=1)
    xs = [c[0] for c in r.cursors if c]
    assert r.actions == []
    assert xs[-1] - xs[5] > 500


def test_pinch_is_one_click_at_the_pre_pinch_spot():
    r = Run(engine()).feed(pose("point"), seconds=0.5)
    before = r.cursors[-1]
    r.feed(pose("lpinch"), seconds=0.15).feed(pose("point"), seconds=0.5)
    assert r.count("down", "left") == 1 and r.count("up", "left") == 1
    assert r.count("click", "right") == 0
    # The pinch moves the fingertip, but the click lands where the cursor was before.
    down_i = next(i for i, c in enumerate(r.cursors) if r.modes[i] == "lpinch")
    assert math.dist(r.cursors[down_i], before) < 3


def test_double_pinch_gives_two_clicks_in_same_place():
    r = Run(engine()).feed(pose("point"), seconds=0.5)
    for _ in range(2):
        r.feed(pose("lpinch"), seconds=0.12).feed(pose("point"), seconds=0.12)
    downs = [i for i, m in enumerate(r.modes) if m == "lpinch" and r.modes[i - 1] != "lpinch"]
    assert r.count("down", "left") == 2
    assert math.dist(r.cursors[downs[0]], r.cursors[downs[1]]) < 3


def test_pinch_hold_and_move_drags():
    r = Run(engine()).feed(pose("point"), seconds=0.5).feed(pose("lpinch"), seconds=0.2)
    start = r.cursors[-1]
    r.feed(lambda i, n: pose("lpinch", center=(0.5 + 0.15 * i / n, 0.35)), seconds=0.6)
    assert "drag" in r.modes
    assert r.cursors[-1][0] - start[0] > 300
    assert r.count("down", "left") == 1 and r.count("up", "left") == 0
    r.feed(pose("point"), seconds=0.3)
    assert r.count("up", "left") == 1


def test_ok_pose_points_and_tiny_close_clicks():
    r = Run(engine()).feed(lambda i, n: pose("ok", center=(0.4 + 0.2 * i / n, 0.4)), seconds=0.8)
    assert r.modes[-1] == "ok" and r.cursors[-1] is not None
    assert r.actions == []
    xs = [c[0] for c in r.cursors if c]
    assert xs[-1] - xs[0] > 300                      # the cursor follows the 👌 hand
    r.feed(pose("ok", center=(0.6, 0.4)), seconds=0.3)
    r.feed(pose("ok_closed", center=(0.6, 0.4)), seconds=0.15).feed(pose("ok", center=(0.6, 0.4)), seconds=0.4)
    assert r.count("down", "left") == 1 and r.count("up", "left") == 1


def test_right_pinch_right_clicks_once():
    r = Run(engine()).feed(pose("point"), seconds=0.5).feed(pose("rpinch"), seconds=0.2).feed(pose("point"), seconds=0.4)
    assert r.count("click", "right") == 1
    assert r.count("down", "left") == 0


def test_fist_does_not_click():
    r = Run(engine()).feed(pose("point"), seconds=0.3).feed(pose("fist"), seconds=1).feed(pose("point"), seconds=0.3)
    assert r.actions == []


def test_scroll_joystick():
    r = Run(engine()).feed(pose("two"), seconds=0.3)
    frozen = r.cursors[-1]
    r.feed(lambda i, n: pose("two", center=(0.5, 0.35 - 0.12 * min(i / 10, 1))), seconds=1.0)
    v = sum(a[2] for a in r.actions if a[0] == "scroll")
    assert v > 3                               # scrolled up a few notches
    assert all(c == frozen for c in r.cursors[10:] if c)  # cursor stayed put
    r2 = Run(engine()).feed(pose("two"), seconds=0.3).feed(
        lambda i, n: pose("two", center=(0.5, 0.35 + 0.12 * min(i / 10, 1))), seconds=1.0)
    assert sum(a[2] for a in r2.actions if a[0] == "scroll") < -3


def test_small_wobble_in_scroll_mode_does_not_scroll():
    r = Run(engine()).feed(pose("two"), seconds=0.3).feed(
        lambda i, n: pose("two", center=(0.5, 0.35 + 0.01 * math.sin(i))), seconds=1)
    assert r.count("scroll") == 0


def swipe(dx, dy, frames=6):
    return lambda i, n: pose("palm", center=(0.5 + dx * i / (n - 1), 0.35 + dy * i / (n - 1)))


@pytest.mark.parametrize("dx,dy,expected", [
    (0.4, 0, ("keys", "ctrl+tab")),
    (-0.4, 0, ("keys", "ctrl+shift+tab")),
    (0, 0.35, ("window", "minimize")),
    (0, -0.35, ("window", "maximize")),
])
def test_swipes(dx, dy, expected):
    r = Run(engine()).feed(pose("palm"), seconds=0.3).feed(swipe(dx, dy), frames=7).feed(pose("palm", center=(0.5 + dx, 0.35 + dy)), seconds=0.3)
    assert [a[:2] for a in r.actions] == [expected]
    assert r.actions[0][2].startswith("swipe_")  # carries its name for per-app overrides
    assert all(c is None for c in r.cursors)   # open palm never moves the cursor


def test_slow_palm_drift_is_not_a_swipe():
    r = Run(engine()).feed(swipe(0.3, 0), seconds=2)
    assert r.actions == []


def test_window_switcher():
    r = Run(engine()).feed(pose("three"), seconds=0.3)
    r.feed(lambda i, n: pose("three", center=(0.5 + 0.16 * i / (n - 1), 0.35)), seconds=0.6)
    r.feed(pose("fist"), seconds=0.4)
    assert r.actions[:2] == [("keydown", "alt"), ("keys", "tab")]
    assert r.count("keys", "tab") == 3        # initial + 2 steps
    assert r.actions[-1] == ("keyup", "alt")


def test_switcher_releases_alt_when_hand_disappears():
    r = Run(engine()).feed(pose("three"), seconds=0.6).feed(None, seconds=0.5)
    assert r.actions[-1] == ("keyup", "alt")


def test_thumbs_down_pauses_and_thumbs_up_resumes():
    r = Run(engine()).feed(pose("thumbs_down"), seconds=1.0)
    assert r.actions == [("pause", True)]
    r.feed(moving_point(0.4, 0.6), seconds=0.5).feed(pose("lpinch"), seconds=0.3)
    assert r.count("down") == 0 and all(c is None for c in r.cursors)
    r.feed(pose("thumbs_up"), seconds=1.0)
    assert r.actions[-1] == ("pause", False)
    r.feed(moving_point(0.4, 0.6), seconds=0.5)
    assert any(r.cursors[-5:])


def test_short_thumbs_up_does_nothing():
    r = Run(engine()).feed(pose("thumbs_down"), seconds=0.5).feed(pose("fist"), seconds=0.5)
    assert r.actions == []


def test_hand_lost_mid_drag_releases_button():
    r = Run(engine()).feed(pose("point"), seconds=0.3).feed(pose("lpinch"), seconds=0.3).feed(None, seconds=0.5)
    assert r.count("down", "left") == 1 and r.count("up", "left") == 1


def test_brief_dropout_does_not_break_drag():
    r = Run(engine()).feed(pose("point"), seconds=0.3).feed(pose("lpinch"), seconds=0.3)
    r.feed(None, frames=3).feed(pose("lpinch"), seconds=0.3)
    assert r.count("up", "left") == 0


def test_left_hand_and_tiny_hands_ignored():
    r = Run(engine()).feed(lambda i, n: pose("point", handedness="Left"), seconds=0.5)
    r.feed(lambda i, n: pose("point", scale=0.4), seconds=0.5)
    assert r.actions == [] and all(c is None for c in r.cursors)


def test_typing_guard_releases():
    eng = engine()
    r = Run(eng).feed(pose("point"), seconds=0.3).feed(pose("lpinch"), seconds=0.3)
    out = eng.update(r.t, pose("lpinch"), suppress=True)
    assert out.actions == [("up", "left")] and out.cursor is None


def test_cursor_does_not_jump_after_scroll():
    r = Run(engine()).feed(pose("point"), seconds=0.3)
    before = r.cursors[-1]
    r.feed(pose("two"), seconds=0.3).feed(lambda i, n: pose("two", center=(0.5, 0.25)), seconds=0.3)
    r.feed(pose("point", center=(0.5, 0.25)), seconds=0.3)
    first_after = next(c for c, m in zip(r.cursors[-9:], r.modes[-9:]) if m == "point")
    assert math.dist(first_after, before) < 40


# ---- V-sign, call-me, precision -------------------------------------------------------------

def test_victory_hold_plays_pauses_once():
    r = Run(engine()).feed(pose("victory"), seconds=1.5)
    assert [a[:2] for a in r.actions] == [("keys", "play_pause")]
    assert r.actions[0][2] == "victory_hold"


def test_brief_victory_does_nothing():
    r = Run(engine()).feed(pose("victory"), seconds=0.4).feed(pose("point"), seconds=0.3)
    assert r.actions == []


def test_victory_move_up_raises_volume_not_play_pause():
    r = Run(engine()).feed(pose("victory"), seconds=0.3)
    r.feed(lambda i, n: pose("victory", center=(0.5, 0.35 - 0.12 * min(i / 8, 1))), seconds=1.0)
    ups = r.count("keys", "volume_up")
    assert ups >= 3 and r.count("keys", "volume_down") == 0
    assert r.count("keys", "play_pause") == 0


def test_victory_move_down_lowers_volume():
    r = Run(engine()).feed(pose("victory"), seconds=0.3)
    r.feed(lambda i, n: pose("victory", center=(0.5, 0.35 + 0.12 * min(i / 8, 1))), seconds=1.0)
    assert r.count("keys", "volume_down") >= 3 and r.count("keys", "volume_up") == 0


def test_call_hold_starts_voice_typing_once():
    r = Run(engine()).feed(pose("call"), seconds=2.0)
    assert [a[:2] for a in r.actions] == [("keys", "win+h")]


def test_scroll_pose_is_not_victory():
    r = Run(engine()).feed(pose("two"), seconds=1.5)
    assert r.count("keys") == 0


def test_precision_slow_moves_less_fast_moves_full():
    slow = Run(engine()).feed(pose("point", center=(0.45, 0.4)), seconds=0.3)
    x0 = slow.cursors[-1][0]
    slow.feed(lambda i, n: pose("point", center=(0.45 + 0.02 * i / n, 0.4)), seconds=1.0)   # ~90 px/s
    slow_dx = slow.cursors[-1][0] - x0
    off = engine(smoothing={"precision": False})
    plain = Run(off).feed(pose("point", center=(0.45, 0.4)), seconds=0.3)
    p0 = plain.cursors[-1][0]
    plain.feed(lambda i, n: pose("point", center=(0.45 + 0.02 * i / n, 0.4)), seconds=1.0)
    plain_dx = plain.cursors[-1][0] - p0
    assert slow_dx < 0.6 * plain_dx            # careful movement is finer with precision on
    fast = Run(engine()).feed(pose("point", center=(0.3, 0.4)), seconds=0.3)
    fast.feed(lambda i, n: pose("point", center=(0.3 + 0.3 * i / n, 0.4)), seconds=0.3)  # ~4500 px/s
    fast.feed(pose("point", center=(0.6, 0.4)), seconds=0.3)
    assert fast.cursors[-1][0] - fast.cursors[8][0] > 1100


def test_precision_reaches_screen_edge():
    r = Run(engine()).feed(pose("point", center=(0.45, 0.4)), seconds=0.3)
    r.feed(lambda i, n: pose("point", center=(0.45 - 0.4 * i / n, 0.4)), seconds=2.0)   # slow drift far left
    assert r.cursors[-1][0] == 0


def test_set_values_keeps_comments_and_adds_missing(tmp_path):
    from gesture_control.config import set_values
    p = tmp_path / "c.toml"
    p.write_text("# top\n[smoothing]\nmin_cutoff = 0.5   # steadier\n\n[gestures]\npinch_dip = 0.05\n", encoding="utf-8")
    set_values({("smoothing", "min_cutoff"): 0.3, ("smoothing", "precision"): False,
                ("gestures", "pinch_dip"): 0.06, ("feedback", "overlay"): True}, p)
    text = p.read_text(encoding="utf-8")
    assert "min_cutoff = 0.3   # steadier" in text and "# top" in text
    cfg = load(p)
    assert cfg["smoothing"]["precision"] is False and cfg["gestures"]["pinch_dip"] == 0.06
    assert cfg["feedback"]["overlay"] is True
