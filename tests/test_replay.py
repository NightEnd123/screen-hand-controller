"""Replay real landmark recordings (tools/record_landmarks.py) through the gesture engine."""
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

import copy

from gesture_control.config import DEFAULTS
from gesture_control.features import Hand
from gesture_control.gestures import GestureEngine

REC = Path(__file__).resolve().parent.parent / "recordings"
FILES = sorted(REC.glob("*.json")) if REC.exists() else []


def recorded_cfg():
    """Defaults plus the setup the recordings were made with (a right hand, calibrated box)."""
    cfg = copy.deepcopy(DEFAULTS)
    cfg["mapping"]["box"] = [0.200, 0.220, 0.700, 0.664]
    cfg["tracking"]["hand"] = "right"
    return cfg


def replay(data, cfg=None):
    eng = GestureEngine(cfg or recorded_cfg(), (0, 0, 2256, 1504))
    actions = []
    for fr in data["frames"]:
        h = fr["hand"]
        hand = None if h is None else Hand(np.array(h["img"]), np.array(h["world"]), h["handedness"],
                                           h["score"], data.get("aspect", 4 / 3))
        actions += eng.update(fr["t"], hand).actions
    return actions


def tally(actions):
    c = Counter()
    for a in actions:
        if a[0] == "scroll":
            c["scroll_up" if a[2] > 0 else "scroll_down" if a[2] < 0 else "scroll_side"] += 1
        else:
            c[f"{a[0]}:{a[1]}"] += 1
    return c


MIRROR_SWAP = {"keys:ctrl+tab": "keys:ctrl+shift+tab", "keys:ctrl+shift+tab": "keys:ctrl+tab"}


def mirrored(data):
    """The same recording as if done with the LEFT hand: flip x, swap the label, and expect
    left/right swipes to swap (the hand now moves the other way)."""
    out = {**data, "expect": {MIRROR_SWAP.get(k, k): v for k, v in data["expect"].items()}, "frames": []}
    for fr in data["frames"]:
        h = fr["hand"]
        if h is not None:
            img, world = np.array(h["img"]), np.array(h["world"])
            img[:, 0] = 1 - img[:, 0]
            world[:, 0] = -world[:, 0]
            h = {**h, "img": img.tolist(), "world": world.tolist(),
                 "handedness": {"Left": "Right", "Right": "Left"}[h["handedness"]]}
        out["frames"].append({**fr, "hand": h})
    return out


def mirror_cfg():
    cfg = recorded_cfg()
    cfg["tracking"]["hand"] = "left"
    x0, y0, x1, y1 = cfg["mapping"]["box"]
    cfg["mapping"]["box"] = [1 - x1, y0, 1 - x0, y1]    # a left-hander calibrates the mirrored box
    return cfg


@pytest.mark.skipif(not FILES, reason="no recordings yet (run tools/record_landmarks.py)")
@pytest.mark.parametrize("hand", ["right", "left"])
@pytest.mark.parametrize("path", FILES, ids=[p.stem for p in FILES])
def test_recording(path, hand):
    data = json.loads(path.read_text())
    if hand == "left":
        data = mirrored(data)
        got = tally(replay(data, mirror_cfg()))
    else:
        got = tally(replay(data))
    for key, want in data["expect"].items():
        if want == ">0":
            assert got[key] > 0, f"{key}: expected some, got none. All: {dict(got)}"
        else:
            assert got[key] == want, f"{key}: expected {want}, got {got[key]}. All: {dict(got)}"
    if data["forbid_other"]:
        extra = {k: v for k, v in got.items() if k not in data["expect"]
                 and not (k.startswith("up:") and f"down:{k[3:]}" in data["expect"])}
        assert not extra, f"unexpected actions: {extra}"


def test_replay_harness_on_synthetic_recording():
    from tests.synth import pose
    frames, t = [], 0.0
    for name, secs in [("point", 0.5), ("lpinch", 0.2), ("point", 0.5)]:
        for _ in range(int(secs * 30)):
            h = pose(name)
            frames.append({"t": t, "hand": {"img": h.img.tolist(), "world": h.world.tolist(),
                                            "handedness": "Right", "score": 1.0}})
            t += 1 / 30
    got = tally(replay({"frames": frames}))
    assert got == {"down:left": 1, "up:left": 1}
