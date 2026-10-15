"""Synthetic right-hand landmarks for tests (palm facing the camera, fingers up, mirrored view)."""
import math

import numpy as np

from gesture_control.features import Hand

# finger: (mcp x, mcp y, segment lengths)
_FINGERS = {
    "index": (-0.030, -0.085, (0.040, 0.025, 0.020)),
    "middle": (-0.010, -0.090, (0.043, 0.027, 0.021)),
    "ring": (0.010, -0.085, (0.040, 0.025, 0.020)),
    "pinky": (0.028, -0.075, (0.032, 0.020, 0.018)),
}
_CURL = {"ext": (0, 0, 0), "curl": (80, 180, 240), "bent": (35, 75, 95)}


def _finger(name, state, spread=0.0):
    x, y, segs = _FINGERS[name]
    pts = [np.array([x, y, 0.0])]
    for seg, ang in zip(segs, _CURL[state]):
        a = math.radians(ang)
        d = np.array([spread * math.cos(a), -math.cos(a), -math.sin(a)])
        pts.append(pts[-1] + seg * d / np.linalg.norm(d))
    return pts


def make_hand(index="ext", middle="ext", ring="ext", pinky="ext", thumb="out",
              center=(0.5, 0.35), scale=2.0, rotate180=False, aspect=4 / 3,
              pinch=None, spread=None, handedness="Right", pinch_gap=0.004):
    """Build a Hand. thumb: out | folded | up. pinch: None | 'index' | 'middle' (thumb tip meets that tip)."""
    w = np.zeros((21, 3))
    w[0] = (0, 0, 0)
    spread = spread or {}
    for i, (name, st) in enumerate(zip(_FINGERS, (index, middle, ring, pinky))):
        w[5 + 4 * i: 9 + 4 * i] = _finger(name, st, spread.get(name, 0.0))
    cmc = np.array([-0.025, -0.025, 0.0])
    if thumb == "out":
        d = np.array([-0.6, -0.8, 0.0])
    elif thumb == "up":
        d = np.array([-0.15, -0.99, 0.0])
        cmc = np.array([-0.025, -0.03, -0.02])
    else:
        d = None
    if d is not None:
        d = d / np.linalg.norm(d)
        w[1] = cmc
        w[2] = cmc + 0.04 * d
        w[3] = w[2] + 0.035 * d
        w[4] = w[3] + (0.045 if thumb == "up" else 0.03) * d
    else:  # folded across the curled fingers
        w[1] = cmc
        w[2] = (-0.040, -0.045, -0.015)
        w[3] = (-0.030, -0.060, -0.035)
        w[4] = (-0.005, -0.070, -0.040)
    if pinch:
        tip = w[8] if pinch == "index" else w[12]
        w[4] = tip + np.array([-pinch_gap, 0.003, 0.0])
        w[3] = (w[2] + w[4]) / 2 + np.array([-0.012, 0.0, 0.0])
    if rotate180:
        w[:, 0] *= -1
        w[:, 1] *= -1
    img = np.zeros((21, 3))
    img[:, 0] = (center[0] * aspect + w[:, 0] * scale) / aspect
    img[:, 1] = center[1] + w[:, 1] * scale + 0.09 * scale
    img[:, 2] = w[:, 2]
    return Hand(img=img, world=w, handedness=handedness, aspect=aspect)


POSES = {
    "point": dict(index="ext", middle="curl", ring="curl", pinky="curl", thumb="out"),
    "two": dict(index="ext", middle="ext", ring="curl", pinky="curl", thumb="folded"),
    "victory": dict(index="ext", middle="ext", ring="curl", pinky="curl", thumb="folded",
                    spread={"index": -0.5, "middle": 0.5}),
    "three": dict(index="ext", middle="ext", ring="ext", pinky="curl", thumb="folded"),
    "palm": dict(),
    "fist": dict(index="curl", middle="curl", ring="curl", pinky="curl", thumb="folded"),
    "thumbs_up": dict(index="curl", middle="curl", ring="curl", pinky="curl", thumb="up"),
    "thumbs_down": dict(index="curl", middle="curl", ring="curl", pinky="curl", thumb="up", rotate180=True),
    "call": dict(index="curl", middle="curl", ring="curl", pinky="ext", thumb="out"),
    "ok": dict(index="bent", middle="ext", ring="ext", pinky="ext", pinch="index", pinch_gap=0.028),
    "ok_closed": dict(index="bent", middle="ext", ring="ext", pinky="ext", pinch="index", pinch_gap=0.004),
    "lpinch": dict(index="bent", middle="curl", ring="curl", pinky="curl", pinch="index"),
    "rpinch": dict(index="ext", middle="bent", ring="curl", pinky="curl", pinch="middle"),
}


def pose(name, **kw):
    return make_hand(**{**POSES[name], **kw})
