# Gesture Control

Control your Windows mouse (and a few shortcuts) with your right hand through the webcam.
Runs in the background with a tray icon. Hand tracking: MediaPipe Hand Landmarker, all on-device. No images are stored or sent anywhere.

## Start / stop
- **Background:** double-click `run_hidden.vbs`. A hand icon appears in the tray (check the `^` overflow area).
- **With the debug view** (camera image, landmarks, mode, FPS, CPU): double-click `run.bat`.
- **Safe test mode:** `run.bat --dry-run` logs what it *would* do to `logs/gesture-control.log` without touching the mouse.
- **Quit:** tray icon → Quit.
- **Start automatically at login:** tray icon → Start with Windows.

## Gestures (right hand, palm toward the screen)
| Do this | Get this |
|---|---|
| ☝️ Point (index finger up) and move | Cursor follows your fingertip |
| 👌 Thumb and index close (not touching), other three fingers up, and move | Also moves the cursor. Touch thumb to index to click. |
| 🤏 Thumb + index pinch, release | Left click (two quick pinches = double-click) |
| Thumb + index pinch, **hold and move** | Drag, released when you open the pinch |
| Thumb + **middle** pinch | Right click |
| ✌️ Index + middle up, held together, then move up/down | Scroll. Works like a joystick: the further from where you started, the faster. |
| 🖐️ Open palm, quick swipe right / left | Next / previous browser tab (Ctrl+Tab / Ctrl+Shift+Tab) |
| 🖐️ Open palm, quick swipe down / up | Minimize / maximize the current window |
| Three fingers up (index, middle, ring) | Window switcher (Alt+Tab). Slide left/right to choose, drop the pose (e.g. make a fist) to pick. |
| ✌️ V-sign (index + middle spread apart), hold still ~1 s | Play / pause media |
| ✌️ V-sign, then move your hand up / down | Volume up / down (like a joystick) |
| 🤙 Call-me sign (thumb + pinky out), hold ~1 s | Windows voice typing (Win+H) |
| 👎 Thumbs-down, hold ~1 s | **Pause**: gestures stop doing anything |
| 👍 Thumbs-up, hold ~1 s | **Resume** |
| **Ctrl+Alt+G** | Pause / resume from the keyboard (also turns the camera back on) |

Tips:
- After a swipe, **close your hand while bringing it back**. Otherwise the return trip can count as a swipe the other way.
- Fist, relaxed hands, and the left hand do nothing.
- Pressing a real key ignores gestures for 1 second, so typing doesn't trigger clicks.

**The dot next to the cursor** shows what the app sees: green = pointing, red = left click/drag, orange = right click, yellow = scroll, purple = window switcher, cyan = open palm, blue = V-sign. A ring fills while you hold a gesture, and a short label confirms shortcuts ("Next tab", "Play / pause"…). Turn it off in Settings.

**Precision mode** (on by default): moving slowly moves the cursor less than your hand, for small targets; moving fast is 1:1.

**Per-app gestures**: in `config.toml`, an `[apps."PROGRAM.EXE"]` section replaces swipes/holds while that program is in front. PowerPoint (swipes change slides) and Spotify (swipes skip tracks) are set up as examples.

Tray colors: 🟢 active · 🟡 paused (watching for thumbs-up) · ⚪ camera off · 🔴 camera problem · 🔵 calibrating.

**Pause vs. Camera off:**
- **Pause** keeps the camera on at 5 fps so a thumbs-up can resume.
- **Camera off** releases the camera (its light goes off, near-zero CPU). Resume with Ctrl+Alt+G or the tray.

## Control box
Only a box in the middle of the camera view maps to your whole screen, so small hand movements reach every corner.
To fit it to where your hand is comfortable: tray → **Calibrate control box**, then hold your fingertip still at the top-left of the area and then at the bottom-right. The box is shown in the debug view.

## Windows permissions
- **Camera:** Settings → Privacy & security → Camera. Turn on *Camera access*, *Let apps access your camera* and *Let desktop apps access your camera*.
- **Mouse/keyboard control** needs no permission on Windows.
- **Limitation:** Windows blocks normal apps from clicking in admin windows (Task Manager, installers, UAC prompts). Use the real mouse there.
- If Teams/Zoom/the Camera app is using the camera, the tray turns red and the app keeps retrying.

## Tuning
Tray → **Settings…** has sliders for the common ones (cursor steadiness, precision, pinch sensitivity, scroll/volume speed, swipe size, feedback). Everything else is in `config.toml` (tray → Edit settings file, then Reload settings). Common tweaks:
- Cursor shaky when still → lower `min_cutoff` (e.g. 0.3).
- Cursor laggy on fast moves → raise `beta` (e.g. 0.02).
- Pinches not registering → lower `pinch_dip` (e.g. 0.05) or raise `pinch_max_left`. Accidental clicks → the opposite.
- Clicks drift → `cursor_point = "index_knuckle"`.
- Scroll too fast/slow → `scroll_gain`.

## Recording a real session (for fixing problems)
Double-click `record_session.bat`, use the app normally (especially whatever misbehaves), then Quit from the tray.
It saves hand-point numbers plus every action the app took to `recordings/sessions/` (no images), which can be replayed to see exactly what went wrong.

## Recording gestures for tuning
`.venv\Scripts\python.exe tools\record_landmarks.py` walks through each gesture and saves only the 21 hand-point coordinates per frame to `recordings/` (no images).
`tests/test_replay.py` then checks that each recording produces exactly the expected actions.

## Development
- `setup.ps1`: one-time setup (venv, packages, model download).
- `.venv\Scripts\python.exe -m pytest`: run the tests.
- Code is in `gesture_control/`:
  - `gestures.py`: the gesture state machine (pure logic)
  - `features.py`: hand-shape detection
  - `filters.py`: One Euro smoothing
  - `output.py`: 120 Hz cursor glide
  - `actions.py`: Windows SendInput
