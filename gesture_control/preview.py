"""Optional debug window: landmarks, control box, mode, FPS, CPU."""
import cv2

from .tracker import CONNECTIONS

WINDOW = "Gesture Control - debug view"
MODE_COLORS = {
    "point": (80, 200, 80), "lpinch": (60, 60, 230), "drag": (60, 60, 230), "rpinch": (230, 120, 40),
    "scroll": (200, 200, 40), "switcher": (200, 80, 200), "palm": (40, 200, 230),
    "paused": (0, 190, 230), "typing": (150, 150, 150),
}


class Preview:
    def __init__(self):
        self.open = False

    def show(self, frame, hand, box, lines, mode="", progress=None, banner=None):
        img = frame.copy()
        h, w = img.shape[:2]
        x0, y0, x1, y1 = box
        cv2.rectangle(img, (int(x0 * w), int(y0 * h)), (int(x1 * w), int(y1 * h)), (255, 255, 255), 1)
        color = MODE_COLORS.get(mode, (200, 200, 200))
        if hand is not None:
            pts = [(int(p[0] * w), int(p[1] * h)) for p in hand.img]
            for a, b in CONNECTIONS:
                cv2.line(img, pts[a], pts[b], color, 2)
            for i, p in enumerate(pts):
                cv2.circle(img, p, 5 if i in (4, 8, 12) else 3, (255, 255, 255), -1)
        y = 22
        for line in lines:
            cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
            y += 20
        if progress is not None:
            cv2.rectangle(img, (10, h - 24), (10 + int((w - 20) * progress), h - 10), (0, 200, 255), -1)
        if banner:
            cv2.rectangle(img, (0, h // 2 - 22), (w, h // 2 + 14), (0, 0, 0), -1)
            cv2.putText(img, banner, (12, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1, cv2.LINE_AA)
        cv2.imshow(WINDOW, img)
        if not self.open:
            cv2.setWindowProperty(WINDOW, cv2.WND_PROP_TOPMOST, 1)
            self.open = True
        cv2.waitKey(1)
        # user closed the window with the X button?
        return cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) >= 1

    def close(self):
        if self.open:
            self.open = False
            try:   # already gone if the user closed it with the X button
                cv2.destroyWindow(WINDOW)
                cv2.waitKey(1)
            except cv2.error:
                pass
