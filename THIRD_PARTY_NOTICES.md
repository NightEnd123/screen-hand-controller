# Third-party software

Gesture Control is MIT-licensed (see `LICENSE`). The downloadable app bundles the
following, each under its own license:

| Component | License | Source |
|---|---|---|
| MediaPipe (hand tracking) | Apache-2.0 | https://github.com/google-ai-edge/mediapipe |
| MediaPipe Hand Landmarker model (`hand_landmarker.task`) | Apache-2.0 | https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker |
| OpenCV (`opencv-contrib-python`) | Apache-2.0 | https://github.com/opencv/opencv-python |
| NumPy | BSD-3-Clause (and others, see its package) | https://numpy.org |
| pynput | LGPL-3.0 | https://github.com/moses-palmer/pynput |
| pystray | LGPL-3.0 | https://github.com/moses-palmer/pystray |
| Pillow | MIT-CMU | https://python-pillow.org |
| psutil | BSD-3-Clause | https://github.com/giampaolo/psutil |
| absl-py, flatbuffers | Apache-2.0 | https://github.com/abseil/abseil-py, https://github.com/google/flatbuffers |
| matplotlib, sounddevice, six, certifi | PSF-based / MIT / MPL-2.0 (pulled in by MediaPipe) | their PyPI pages |
| Python | PSF License | https://www.python.org |

**LGPL components:** pynput and pystray are included as plain `.py` source files inside the
app folder (`_internal\pynput`, `_internal\pystray`), unmodified. You may replace them with
your own versions. Their source and license texts are at the links above, and this app's
own source code is in this repository.
