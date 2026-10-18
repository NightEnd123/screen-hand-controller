# Privacy policy: AirCursor

*Last updated: October 18, 2026*

AirCursor lets you control your Windows mouse with hand gestures through your webcam.
This policy covers the app from GitHub and from the Microsoft Store.

## The short version

AirCursor doesn't collect, store, send or share any personal information. Everything
happens on your own computer.

## Camera

- The app uses your webcam to see your hand. Each camera picture is processed in memory on
  your computer by Google's MediaPipe hand-tracking model (which ships inside the app) and then
  thrown away.
- Camera pictures are **never saved** to disk and **never sent** anywhere.
- You only see the picture when you choose to, in the setup window and the optional camera
  view. It isn't recorded there either.
- You can turn the camera off at any time from the app window, the tray icon or Ctrl+Alt+G.

## What's stored on your computer

- **Settings** (for example which hand you use, your control area, pinch sensitivity).
- **A small log file** of what the app did (for example "left click", "paused"), used for
  troubleshooting. It contains no pictures.
- **Session recordings, only if you start one yourself** with `--record`. These contain the
  21 hand-point coordinates per frame (numbers, not pictures), so you can send them along
  with a bug report if you choose to.

These files stay on your computer, in the app's own data folder. Uninstalling the Store app
removes them. For the GitHub version, delete `%APPDATA%\AirCursor`.

## What we don't do

- No accounts, no sign-in.
- No internet connection is made by the app: no analytics, telemetry, ads or tracking.
- No data is sold or shared with anyone.

## Keyboard and mouse

The app moves the mouse pointer and presses keys (for example Ctrl+Tab) when you make the
matching gesture. It watches for one keyboard shortcut (Ctrl+Alt+G, to pause and resume)
and notices when you're typing, so gestures briefly stop while you type. It does not record
what you type.

## Children

The app collects no personal information from anyone, including children.

## Changes and contact

Changes to this policy will be posted here, with a new date at the top.
Questions: open an issue at https://github.com/NightEnd123/screen-hand-controller/issues
