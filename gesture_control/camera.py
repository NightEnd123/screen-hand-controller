"""Camera on its own thread. Grabs every frame but only decodes one when the engine asks."""
import logging
import threading
import time

import cv2

log = logging.getLogger(__name__)

BACKENDS = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}


class Camera(threading.Thread):
    def __init__(self, cfg_cam):
        super().__init__(daemon=True, name="camera")
        self.cfg = cfg_cam
        self.cap = None
        self.want_open = False
        self.running = True
        self.status = "off"          # off | opening | ok | error
        self._want_frame = threading.Event()
        self._have_frame = threading.Event()
        self._frame = None
        self._frame_id = 0
        self._read_id = 0
        # continuous: decode every frame so read() returns immediately (used while tracking a hand,
        # ~1-2% CPU). Otherwise only decode on request (saves CPU when idle/paused).
        self.continuous = False

    def set_open(self, on):
        self.want_open = on

    def stop(self):
        self.running = False

    def read(self, timeout=1.0):
        """Return a frame newer than the last one returned (BGR), or None."""
        if self.continuous and self._frame_id != self._read_id:
            self._read_id = self._frame_id          # a new frame is already waiting
            return self._frame
        self._have_frame.clear()
        self._want_frame.set()
        if self._have_frame.wait(timeout):
            self._read_id = self._frame_id
            return self._frame
        return None

    def _open(self):
        self.status = "opening"
        backend = BACKENDS.get(self.cfg["backend"], cv2.CAP_ANY)
        cap = cv2.VideoCapture(self.cfg["index"], backend)
        if not cap.isOpened() and backend != cv2.CAP_DSHOW:
            cap = cv2.VideoCapture(self.cfg["index"], cv2.CAP_DSHOW)
        if not cap.isOpened():
            self.status = "error"
            log.warning("could not open camera %s (privacy setting off, or another app has it?)", self.cfg["index"])
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg["width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg["height"])
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        log.info("camera open: %dx%d", cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.status = "ok"
        return cap

    def _close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            log.info("camera released")
        self.status = "off"

    def run(self):
        fails = 0
        try:
            while self.running:
                if not self.want_open:
                    self._close()
                    time.sleep(0.1)
                    continue
                if self.cap is None:
                    self.cap = self._open()
                    if self.cap is None:
                        time.sleep(3)
                        continue
                g0 = time.perf_counter()
                if not self.cap.grab():
                    fails += 1
                    if fails > 30:
                        log.warning("camera stopped delivering frames; reopening")
                        self._close()
                        self.status = "error"
                        fails = 0
                        time.sleep(1)
                    continue
                fails = 0
                if time.perf_counter() - g0 < 0.002:
                    time.sleep(0.004)   # some backends (DirectShow) don't block in grab(); don't spin
                if self.continuous or self._want_frame.is_set():
                    ok, frame = self.cap.retrieve()
                    if ok:
                        self._frame = frame
                        self._frame_id += 1
                        self._want_frame.clear()
                        self._have_frame.set()
        finally:
            self._close()
