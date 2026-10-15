# Gesture Control

Use your mouse with one hand in front of your webcam, on Windows 10 and 11.
Point to move the cursor, pinch to click, swipe to change tabs. Works with your left or right hand.

Everything runs on your computer. The camera picture is never saved or sent anywhere.

## Install

1. Go to **[Releases](../../releases/latest)** and download `GestureControl-…-windows.zip`.
2. Unzip it anywhere you like (for example your Documents folder). Keep the folder together.
3. Double-click **`GestureControl.exe`**.
   - Windows may say *"Windows protected your PC"*. The app isn't code-signed (that costs money).
     Click **More info → Run anyway**.
4. A short **setup** opens, about 2 minutes:
   1. Pick the hand you'll use.
   2. Hold it up so the app can check it sees the right hand.
   3. Point at two corners to choose the area your hand moves in.
   4. Do a few pinches so the clicks fit how *you* pinch.

After that, the app runs in the background with a hand icon in the system tray (check the `^` arrow
by the clock). You can re-run setup any time: tray icon → **Run setup again**.

No Python or anything else is needed. To remove the app, see [Uninstall](#uninstall).

## Gestures

Hold your hand up with the palm toward the screen. These work the same with either hand.

| Do this | Get this |
|---|---|
| ☝️ Point (index finger up) and move | The cursor follows your fingertip |
| 🤏 Pinch thumb + index, let go | Left click. Two quick pinches = double-click |
| Pinch thumb + index, **hold and move** | Drag. Let go to drop |
| Pinch thumb + **middle** finger | Right click |
| 👌 Thumb and index close, other three fingers up | Also moves the cursor. Touch thumb to index to click |
| Index + middle finger up **together**, move up/down | Scroll (like a joystick: further = faster) |
| 🖐️ Open palm, quick swipe right / left | Next / previous browser tab |
| 🖐️ Open palm, quick swipe down / up | Minimize / maximize the window |
| Three fingers up (index, middle, ring), slide sideways | Switch windows (Alt+Tab). Make a fist to pick |
| ✌️ V-sign (fingers spread), hold still ~1 s | Play / pause media |
| ✌️ V-sign, then move up / down | Volume up / down |
| 🤙 Call-me sign (thumb + pinky out), hold ~1 s | Windows voice typing |
| 👎 Thumbs-down, hold ~1 s | **Pause**: gestures stop doing anything |
| 👍 Thumbs-up, hold ~1 s | **Resume** |
| **Ctrl+Alt+G** | Pause / resume from the keyboard |

Tips:
- After a swipe, **close your hand while bringing it back**, or the return trip can count as a swipe the other way.
- A fist, a relaxed hand, and your other hand do nothing. Raising your hand into view or dropping it away doesn't count as a swipe.
- Typing on the keyboard turns gestures off for a second, so typing doesn't cause clicks.
- **The dot next to the cursor** shows what the app sees: green = pointing, red = click/drag, orange = right click, yellow = scroll, purple = window switcher, cyan = open palm, blue = V-sign. A ring fills while you hold a gesture. You can turn it off in Settings.

## Tray icon

Right-click the tray icon for the menu: Pause, Camera off, Settings…, Calibrate control box,
Run setup again, Start with Windows, Quit.

Colours: 🟢 active · 🟡 paused (watching for a thumbs-up) · ⚪ camera off · 🔴 camera problem · 🔵 setting up.

- **Pause** keeps the camera on (slowly) so a thumbs-up can resume.
- **Camera off** releases the camera completely (its light goes off). Turn it back on with Ctrl+Alt+G or the tray.

## Settings

Tray → **Settings…** has sliders for the common things: cursor steadiness, precision mode,
pinch sensitivity, scroll and volume speed, swipe size, and on-screen feedback.

Everything else is in a settings file: tray → **Edit settings file**, save, then tray → **Reload settings**.
The file lives at `%APPDATA%\GestureControl\config.toml` and every option has a comment.
You can also give **individual apps their own gestures**: for example, PowerPoint swipes change
slides and Spotify swipes skip tracks (both set up as examples).

**Precision mode** (on by default): moving slowly moves the cursor less than your hand, for small
targets. Moving fast is 1:1.

## Troubleshooting

| Problem | Try |
|---|---|
| Tray icon is red / setup shows no picture | Close other apps using the camera (Teams, Zoom, Camera). Windows Settings → Privacy & security → Camera: turn on *Camera access* and *Let desktop apps access your camera*. In setup, try **Use another camera**. |
| Nothing happens when I point | Make sure it's the hand you chose in setup and your palm faces the screen. Get some light on your hand. Run setup again. |
| Clicks don't register | Run setup again and do the pinches the way you naturally would. Or Settings → *Pinch sensitivity* toward "tinier pinches". |
| Accidental clicks | Settings → *Pinch sensitivity* toward "fewer accidental clicks". |
| Cursor shaky when still | Settings → *Steadiness when still* lower. |
| Cursor can't reach the screen edges | Tray → **Calibrate control box** and pick a slightly smaller area. |
| Swipes trigger too easily / not at all | Settings → *Swipe size needed*. |
| It can't click in Task Manager, installers or admin prompts | Windows blocks normal apps from controlling admin windows. Use the real mouse there. |

## Privacy

- Hand tracking (Google's MediaPipe) runs entirely on your computer. There's no account, no internet connection, no analytics.
- The camera picture is shown to you during setup and in the optional debug view. It's never saved.
- Settings and a small log file are stored in `%APPDATA%\GestureControl\`.

## Reporting a problem

The most useful thing you can send is a short recording of hand-point numbers (no pictures):

1. Quit the app from the tray.
2. Open a Command Prompt in the app folder and run `GestureControl.exe --record`.
3. Use it normally, especially whatever misbehaves, then Quit from the tray.
4. Attach the file from `%APPDATA%\GestureControl\recordings\sessions\` to a new
   [issue](../../issues/new/choose), and describe what you did and what went wrong.

## Uninstall

Tray → untick **Start with Windows**, then **Quit**. Delete the app folder and `%APPDATA%\GestureControl`.

## For developers

Needs Windows and Python 3.12.

```powershell
.\setup.ps1                                   # venv, packages, hand model
.\run.bat                                     # run with the debug view (camera, landmarks, FPS)
.\run.bat --dry-run                           # log actions instead of moving the mouse
.\.venv\Scripts\python.exe -m pytest          # tests
.\build.ps1 -Version 0.1.0                    # build dist\GestureControl-0.1.0-windows.zip
```

Useful flags: `--setup` (open setup), `--fake-camera` (blank test picture), `--record`, `--paused`,
`--no-tray`. From source, settings are in `config.toml` in the project folder (created from
`gesture_control/default_config.toml` on first run). `GESTURE_CONTROL_HOME` overrides where settings go.

Code (`gesture_control/`):
- `gestures.py`: the gesture state machine (pure logic, no camera or OS calls)
- `features.py`: hand-shape detection from MediaPipe's 21 hand points
- `setup_wizard.py` / `setup_window.py`: first-run setup logic / window
- `filters.py`: One Euro smoothing · `output.py`: 120 Hz cursor glide · `actions.py`: Windows SendInput

Tests: `tests/test_hands.py` runs every gesture across 13 synthetic hands (sizes, distances,
finger lengths, palm widths, tilts, left and right). `tests/test_replay.py` replays real recorded
hand movements in `recordings/`, both as recorded and mirrored as a left hand.
Recordings come from `tools/record_landmarks.py` (hand-point numbers only, no images).
**More recordings from different hands are very welcome** as pull requests.

Releases are built by GitHub Actions when a `v*` tag is pushed (`.github/workflows/release.yml`).

## License

MIT (see `LICENSE`). Bundled third-party components are listed in `THIRD_PARTY_NOTICES.md`.
