"""MediaPipe Hand Landmarker wrapper."""
import os

os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import cv2  # noqa: E402
import mediapipe as mp  # noqa: E402
import numpy as np  # noqa: E402
from mediapipe.tasks.python import BaseOptions, vision  # noqa: E402

from .features import Hand  # noqa: E402

CONNECTIONS = [(c.start, c.end) for c in vision.HandLandmarksConnections.HAND_CONNECTIONS]


class Tracker:
    def __init__(self, cfg_tracking, model_path):
        opts = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,   # with 1, the palm detector only runs when no hand is being tracked
            min_hand_detection_confidence=cfg_tracking["min_detection_confidence"],
            min_hand_presence_confidence=cfg_tracking["min_presence_confidence"],
            min_tracking_confidence=cfg_tracking["min_tracking_confidence"],
        )
        self.lm = vision.HandLandmarker.create_from_options(opts)
        self.swap = cfg_tracking.get("swap_handedness", True)
        self.last_ms = -1

    def detect(self, frame_bgr, t):
        """Returns (Hand or None, mirrored BGR frame)."""
        mirrored = cv2.flip(frame_bgr, 1)
        rgb = cv2.cvtColor(mirrored, cv2.COLOR_BGR2RGB)
        ms = max(int(t * 1000), self.last_ms + 1)
        self.last_ms = ms
        r = self.lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ms)
        if not r.hand_landmarks:
            return None, mirrored
        img = np.array([[p.x, p.y, p.z] for p in r.hand_landmarks[0]])
        world = np.array([[p.x, p.y, p.z] for p in r.hand_world_landmarks[0]])
        cat = r.handedness[0][0]
        label = cat.category_name
        if self.swap:   # MediaPipe's label comes out reversed for our mirrored frames
            label = {"Left": "Right", "Right": "Left"}.get(label, label)
        h, w = mirrored.shape[:2]
        return Hand(img=img, world=world, handedness=label, score=cat.score, aspect=w / h), mirrored

    def close(self):
        self.lm.close()
