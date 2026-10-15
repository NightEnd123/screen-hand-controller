"""Turn 21 hand landmarks into hand-shape features.

Landmark indices (MediaPipe): 0 wrist; thumb 1-4; index 5-8; middle 9-12; ring 13-16; pinky 17-20
(each finger: knuckle/MCP, PIP, DIP, tip).

Shape tests use the 3D "world" landmarks (metres, independent of where the hand is in the
frame) divided by hand size, so thresholds work near or far. Positions use the image landmarks.
"""
from dataclasses import dataclass

import numpy as np

WRIST, THUMB_IP, THUMB_TIP = 0, 3, 4
THUMB_MCP = 2
INDEX = (5, 6, 7, 8)
MIDDLE = (9, 10, 11, 12)
RING = (13, 14, 15, 16)
PINKY = (17, 18, 19, 20)
FINGERS = (INDEX, MIDDLE, RING, PINKY)


@dataclass
class Hand:
    img: np.ndarray          # (21, 3) normalized image coords of the mirrored frame (x right, y down)
    world: np.ndarray        # (21, 3) metres
    handedness: str = "Right"
    score: float = 1.0
    aspect: float = 4 / 3    # frame width / height


@dataclass
class Features:
    pose: str                # point | ok | two | victory | three | palm | call | fist | thumbs_up | thumbs_down | other
    ext: tuple               # extended flags: thumb, index, middle, ring, pinky
    ratio_l: float           # thumb-index tip gap / hand size (image space)
    ratio_r: float           # thumb-middle tip gap / hand size (image space)
    index_folded: bool
    middle_folded: bool
    raw_fist: bool           # no finger extended this frame
    palm: tuple              # palm centre in frame-height units (aspect corrected), for motion
    palm_norm: tuple         # palm centre in normalized coords, for the zone check
    size: float              # wrist->middle knuckle in frame-height units
    index_tip: tuple         # normalized
    index_knuckle: tuple     # normalized


def _d(a, b):
    return float(np.linalg.norm(a - b))


def _cos(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def finger_state(w, finger):
    """(extended, folded) for one finger from world landmarks.

    folded = curled deep into the palm (tip nearer the wrist than the knuckle), as in a fist.
    A finger bent to meet the thumb in a pinch is neither extended nor folded.
    """
    mcp, pip, dip, tip = (w[i] for i in finger)
    tip_far = _d(w[WRIST], tip)
    straight = _cos(pip - mcp, tip - pip)
    extended = straight > 0.5 and tip_far > _d(w[WRIST], pip) * 1.1
    folded = tip_far < _d(w[WRIST], mcp)
    return extended, folded


def compute(hand: Hand, cfg_g) -> Features:
    w = np.asarray(hand.world, dtype=float)
    img = np.asarray(hand.img, dtype=float)
    pts = img[:, :2] * np.array([hand.aspect, 1.0])   # aspect-corrected, frame-height units

    size_w = _d(w[WRIST], w[MIDDLE[0]]) or 1e-6
    size_i = _d(pts[WRIST], pts[MIDDLE[0]])

    states = [finger_state(w, f) for f in FINGERS]
    ext_f = [s[0] for s in states]
    thumb_ext = (_d(w[THUMB_TIP], w[MIDDLE[0]]) / size_w > cfg_g["thumb_ext"]
                 and _d(w[WRIST], w[THUMB_TIP]) > _d(w[WRIST], w[THUMB_IP]))
    ext = (thumb_ext, *ext_f)

    # Pinch gaps are measured in the flat camera image: the 3D estimate is poor at fingertip depth
    # with the palm facing the camera, and missed most real pinches in the recordings.
    ratio_l = _d(pts[THUMB_TIP], pts[INDEX[3]]) / (size_i or 1e-6)
    ratio_r = _d(pts[THUMB_TIP], pts[MIDDLE[3]]) / (size_i or 1e-6)

    pose = classify(ext, pts, _d(w[INDEX[3]], w[MIDDLE[3]]) / size_w, cfg_g, ratio_l)

    palm_idx = [WRIST, INDEX[0], MIDDLE[0], RING[0], PINKY[0]]
    palm = pts[palm_idx].mean(axis=0)
    palm_n = img[palm_idx, :2].mean(axis=0)
    return Features(
        pose=pose, ext=ext, ratio_l=ratio_l, ratio_r=ratio_r,
        index_folded=states[0][1], middle_folded=states[1][1], raw_fist=not any(ext_f),
        palm=(float(palm[0]), float(palm[1])), palm_norm=(float(palm_n[0]), float(palm_n[1])),
        size=size_i,
        index_tip=(float(img[INDEX[3], 0]), float(img[INDEX[3], 1])),
        index_knuckle=(float(img[INDEX[0], 0]), float(img[INDEX[0], 1])),
    )


def classify(ext, pts, two_gap, cfg_g, ratio_l=1.0):
    thumb, index, middle, ring, pinky = ext
    if thumb and not (index or middle or ring or pinky):
        v = pts[THUMB_TIP] - pts[THUMB_MCP]
        ys = pts[:, 1]
        if -v[1] > 1.2 * abs(v[0]) and pts[THUMB_TIP, 1] <= ys.min() + 1e-9:
            return "thumbs_up"
        if v[1] > 1.2 * abs(v[0]) and pts[THUMB_TIP, 1] >= ys.max() - 1e-9:
            return "thumbs_down"
    if thumb and pinky and not (index or middle or ring):
        return "call"        # 🤙
    if middle and ring and pinky and ratio_l < cfg_g["ok_gap"]:
        return "ok"          # 👌: thumb and index tips close, other three up -- a pointing pose
    if index and middle and ring and pinky:
        return "palm"
    if index and middle and ring and not pinky:
        return "three"
    if index and middle and not ring and not pinky:
        if two_gap < cfg_g["two_finger_together"]:
            return "two"         # fingers together: scroll
        if two_gap >= cfg_g["victory_gap"]:
            return "victory"     # V-sign, fingers spread: play/pause, volume
        return "other"
    if index and not middle and not ring and not pinky:
        return "point"
    if not (index or middle or ring or pinky):
        return "fist"
    return "other"
