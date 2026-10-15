"""Guided landmark recorder. Saves ONLY hand-point coordinates (numbers), never images.

Run:  .venv\\Scripts\\python.exe tools\\record_landmarks.py          (all segments)
      .venv\\Scripts\\python.exe tools\\record_landmarks.py drag rest (just these)

In the window: SPACE = record the shown segment, S = skip it, Q = quit.
Each segment is saved to recordings/<name>.json and replayed by tests/test_replay.py.
"""
import json
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gesture_control.config import MODEL_PATH, load  # noqa: E402
from gesture_control.main import set_dpi_aware  # noqa: E402
from gesture_control.tracker import CONNECTIONS, Tracker  # noqa: E402

OUT = ROOT / "recordings"

# name, instructions, seconds, expected action counts (int = exact, ">0" = at least one), forbid other actions
SEGMENTS = [
    ("point_move", "Point (index up) and move around the box slowly, then quickly", 10, {}, True),
    ("left_click", "Point, then do 5 separate quick thumb+index pinches", 12, {"down:left": 5, "up:left": 5}, True),
    ("tiny_click", "Point, then do 5 TINY left-click pinches, as small as you'd really use them", 12,
     {"down:left": 5, "up:left": 5}, True),
    ("double_click","Do 3 double-pinches (two quick pinches each)", 10, {"down:left": 6, "up:left": 6}, True),
    ("drag", "3 times: pinch, hold, move your hand a few cm, release", 14, {"down:left": 3, "up:left": 3}, True),
    ("right_click", "Point, then do 5 separate thumb+MIDDLE pinches", 12, {"click:right": 5}, True),
    ("scroll", "Two fingers together: move hand up & hold 1 s, back, then down & hold 1 s", 10,
     {"scroll_up": ">0", "scroll_down": ">0"}, True),
    ("swipe_right", "Open palm: 3 quick swipes to the RIGHT (close your hand while bringing it back)", 10,
     {"keys:ctrl+tab": 3}, True),
    ("swipe_left", "Open palm: 3 quick swipes to the LEFT (close your hand while bringing it back)", 10,
     {"keys:ctrl+shift+tab": 3}, True),
    ("swipe_down", "Open palm: 2 quick swipes DOWN (close your hand while bringing it back)", 8,
     {"window:minimize": 2}, True),
    ("swipe_up", "Open palm: 2 quick swipes UP (close your hand while bringing it back)", 8,
     {"window:maximize": 2}, True),
    ("switcher", "Three fingers up, slide right 2-3 cm, then make a fist", 8,
     {"keydown:alt": 1, "keyup:alt": 1}, False),
    ("victory_hold", "V-sign (index + middle spread apart): hold still ~1 s, then relax. Do it 2 times", 10,
     {"keys:play_pause": 2}, True),
    ("volume", "V-sign, hold a moment, move your hand UP and hold 1 s, back, then DOWN and hold 1 s", 10,
     {"keys:volume_up": ">0", "keys:volume_down": ">0"}, True),
    ("call", "Call-me sign (thumb + pinky out, others curled): hold ~1 s, then relax. Do it 2 times", 10,
     {"keys:win+h": 2}, True),
    ("thumbs", "Thumbs-DOWN and hold 1 s, relax, then thumbs-UP and hold 1 s", 8,
     {"pause:True": 1, "pause:False": 1}, True),
    ("rest", "Act normally: type, rest your hands, scratch your face, reach for a drink (no gestures)", 20,
     {}, True),
]


def draw(frame, hand, lines, color=(255, 255, 255)):
    h, w = frame.shape[:2]
    if hand is not None:
        pts = [(int(p[0] * w), int(p[1] * h)) for p in hand.img]
        for a, b in CONNECTIONS:
            cv2.line(frame, pts[a], pts[b], (80, 200, 80), 2)
    for i, line in enumerate(lines):
        y = 26 + 24 * i
        cv2.putText(frame, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)
    cv2.imshow("Landmark recorder", frame)
    return cv2.waitKey(1) & 0xFF


def main():
    set_dpi_aware()
    cfg = load()
    wanted = set(sys.argv[1:])
    segments = [s for s in SEGMENTS if not wanted or s[0] in wanted]
    OUT.mkdir(exist_ok=True)
    cap = cv2.VideoCapture(cfg["camera"]["index"], cv2.CAP_MSMF)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["camera"]["width"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["camera"]["height"])
    tracker = Tracker(cfg["tracking"], MODEL_PATH)
    t0 = time.perf_counter()
    try:
        for i, (name, text, secs, expect, forbid) in enumerate(segments):
            # wait for SPACE
            while True:
                ok, frame = cap.read()
                if not ok:
                    continue
                hand, mirrored = tracker.detect(frame, time.perf_counter() - t0)
                k = draw(mirrored, hand, [f"[{i + 1}/{len(segments)}] {name}", text,
                                          "SPACE = record   S = skip   Q = quit"], (0, 255, 255))
                if k == ord("q"):
                    return
                if k == ord("s"):
                    break
                if k == ord(" "):
                    frames = []
                    start = time.perf_counter()
                    while time.perf_counter() - start < secs + 3:
                        ok, frame = cap.read()
                        if not ok:
                            continue
                        now = time.perf_counter()
                        hand, mirrored = tracker.detect(frame, now - t0)
                        left = start + 3 - now
                        if left > 0:
                            draw(mirrored, hand, [f"Get ready... {left:.0f}", text], (0, 255, 255))
                            continue
                        frames.append({"t": round(now - start - 3, 4), "hand": None if hand is None else {
                            "img": hand.img.round(5).tolist(), "world": hand.world.round(5).tolist(),
                            "handedness": hand.handedness, "score": round(hand.score, 3)}})
                        draw(mirrored, hand, [f"RECORDING {name}: {secs + 3 - (now - start):.0f} s", text],
                             (0, 0, 255))
                    (OUT / f"{name}.json").write_text(json.dumps({
                        "segment": name, "instructions": text, "aspect": mirrored.shape[1] / mirrored.shape[0],
                        "expect": expect, "forbid_other": forbid, "frames": frames}))
                    print(f"saved {name}: {len(frames)} frames, hand in {sum(f['hand'] is not None for f in frames)}")
                    break
    finally:
        cap.release()
        tracker.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
