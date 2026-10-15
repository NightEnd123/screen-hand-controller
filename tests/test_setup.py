"""First-run setup wizard: pinch measurement, threshold maths, fallbacks, saved settings."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

from gesture_control.config import DEFAULTS
from gesture_control.features import Hand, compute
from gesture_control.setup_wizard import NOT_POINTING, PinchMeter, SetupWizard, pinch_settings
from tests.synth import pose
from tests.test_replay import FILES, check, mirror_cfg, mirrored, recorded_cfg, replay, tally

REC = Path(__file__).resolve().parent.parent / "recordings"
FPS = 30


def measure(frames, which="l"):
    """Feed recorded frames through a PinchMeter the way the wizard does."""
    m = PinchMeter()
    for fr in frames:
        h = fr["hand"]
        if h is None:
            continue
        f = compute(Hand(np.array(h["img"]), np.array(h["world"]), h["handedness"], h["score"]), DEFAULTS["gestures"])
        if f.pose in NOT_POINTING:
            m.reset()
            continue
        m.update(fr["t"], f.ratio_l if which == "l" else f.ratio_r)
        if m.levels():
            break
    return m.levels()


@pytest.mark.skipif(not (REC / "tiny_click.json").exists(), reason="no recordings")
def test_tiny_pinches_loosen_thresholds_to_about_the_hand_tuned_values():
    lv = measure(json.loads((REC / "tiny_click.json").read_text())["frames"])
    s = pinch_settings(lv, None, DEFAULTS["gestures"])
    # The recordings' owner pinches tiny; their hand-tuned values were dip 0.05, max_left 0.22.
    assert s["pinch_max_left"] == pytest.approx(0.23, abs=0.02)
    assert s.get("pinch_dip", DEFAULTS["gestures"]["pinch_dip"]) <= 0.05


@pytest.mark.skipif(not FILES, reason="no recordings")
def test_recordings_still_pass_with_wizard_settings():
    lv = measure(json.loads((REC / "tiny_click.json").read_text())["frames"])
    s = pinch_settings(lv, None, DEFAULTS["gestures"])
    for path in FILES:
        data = json.loads(path.read_text())
        for d, cfg in ((data, recorded_cfg()), (mirrored(data), mirror_cfg())):
            cfg["gestures"].update(s)
            assert not check(d, tally(replay(d, cfg))), path.stem


def test_big_pinches_keep_defaults():
    """Normal full pinches are already handled; setup never tightens thresholds."""
    m, t = PinchMeter(), 0.0
    for _ in range(3):
        for name, secs in (("point", 0.6), ("lpinch", 0.2)):
            for _ in range(int(secs * FPS)):
                m.update(t, compute(pose(name), DEFAULTS["gestures"]).ratio_l)
                t += 1 / FPS
    m.update(t, compute(pose("point"), DEFAULTS["gestures"]).ratio_l)
    assert m.levels() is not None
    assert pinch_settings(m.levels(), m.levels(), DEFAULTS["gestures"]) == {}


def test_inconsistent_pinches_dont_count():
    m, t = PinchMeter(), 0.0
    for close in (0.5, 0.1, 0.45, 0.1):        # alternate deep and shallow "pinches"
        for g in [0.8] * 15 + [close] * 6:
            m.update(t, g)
            t += 1 / FPS
    m.update(t, 0.8)
    assert m.levels() is None and m.count < 3


def test_pinch_settings_maths():
    d = DEFAULTS["gestures"]
    # weak closes (never below 0.3) -> max raised to fit; tiny depth -> smaller dip
    s = pinch_settings(([0.08, 0.09, 0.1], [0.3, 0.31, 0.32]), None, d)
    assert s["pinch_max_left"] == pytest.approx(0.37) and s["pinch_dip"] == pytest.approx(0.035)
    assert "pinch_max_right" not in s
    assert pinch_settings(None, None, d) == {}
    assert pinch_settings(([0.5] * 3, [0.6] * 3), None, d)["pinch_max_left"] == 0.38   # capped


def run_wizard(steps):
    wz = SetupWizard(copy.deepcopy(DEFAULTS), 16 / 9, 4 / 3, swap_now=True)
    t = 0.0
    for action, arg, hand, secs in steps:
        if action:
            getattr(wz, action)(*([arg] if arg else []))
        for _ in range(int(secs * FPS)):
            wz.update(t, hand)
            t += 1 / FPS
    return wz


def test_full_wizard_with_synthetic_hand():
    wz = run_wizard([
        ("choose_hand", "right", pose("palm", center=(0.5, 0.4)), 2.0),
        (None, None, pose("point", center=(0.35, 0.3)), 2.5),      # top-left corner
        (None, None, None, 1.0),
        (None, None, pose("point", center=(0.62, 0.55)), 2.5),     # bottom-right corner
    ])
    assert wz.step == "pinch_left"
    assert wz.box is not None and wz.box[0] < wz.box[2] and wz.box[1] < wz.box[3]
    wz.skip_step()
    wz.skip_step()
    assert wz.step == "done"
    up = wz.finish(camera_index=1)
    assert up[("profile", "setup_done")] is True
    assert up[("tracking", "hand")] == "right"
    assert up[("mapping", "box")] == wz.box
    assert up[("camera", "index")] == 1
    assert ("tracking", "swap_handedness") not in up      # labels agreed with the current setting
    assert not any(k[0] == "gestures" for k in up)        # pinches skipped -> defaults kept


def test_wrong_hand_is_not_accepted():
    wz = run_wizard([("choose_hand", "left", pose("palm"), 3.0)])   # a right hand shown
    assert wz.step == "hand_check"
    assert "RIGHT" in wz.update(10.0, pose("palm")).warn


def test_skip_everything_saves_only_setup_done_and_hand():
    wz = SetupWizard(copy.deepcopy(DEFAULTS), 16 / 9, 4 / 3, swap_now=True)
    for _ in range(5):
        wz.skip_step()
    assert wz.step == "done"
    assert wz.finish() == {("profile", "setup_done"): True, ("tracking", "hand"): "right"}
