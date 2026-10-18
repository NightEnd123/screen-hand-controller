# Publishing to the Microsoft Store

The Store version is the same app wrapped as an MSIX package. Microsoft signs it after
review, so Store users never see the "Windows protected your PC" warning.

## One-time setup

1. **Create a developer account** (free for individuals) at <https://storedeveloper.microsoft.com>.
   Sign in with your Microsoft account and finish the identity check.
2. In **Partner Center** → **Apps and games** → **New product** → **MSIX or PWA app**,
   **reserve the name**. "AirCursor" is reserved (October 2026).
3. Open the app → **Product management** → **Product identity**. Copy these three values into
   `packaging/msix/store.json`, along with the reserved name as `display_name`. This is done
   for AirCursor:

   | Partner Center | store.json |
   |---|---|
   | Package/Identity/Name | `identity_name` |
   | Package/Identity/Publisher | `publisher` (starts with `CN=`) |
   | Package/Properties/PublisherDisplayName | `publisher_display_name` |

   Commit and push the change.

## Building the package

GitHub builds it for you: **Actions** tab → **store package** → **Run workflow**. Version tags
(`v0.2.0` …) also build it. When the run finishes, download **store-package** under
**Artifacts** and unzip it. Inside is `AirCursor-<version>.msix`.

To build on your own PC instead, you need the Windows SDK. Then run `build.ps1`, followed by
`packaging\msix\build_msix.ps1 -Version 0.2.0`.

## The submission (Partner Center → your app → Start your submission)

**Pricing and availability**: Free, all markets (or choose).

**Properties**
- Category: **Productivity** (subcategory none), or Utilities & tools.
- Privacy policy URL: `https://github.com/NightEnd123/screen-hand-controller/blob/main/PRIVACY.md`
- Website: `https://github.com/NightEnd123/screen-hand-controller`
- Support contact: `https://github.com/NightEnd123/screen-hand-controller/issues`
- Product declarations: answer them as they apply. The app uses the **webcam**, has no in-app
  purchases or ads, and collects no personal information.

**Age ratings**: complete the questionnaire. There's no user-generated content, chat,
location, purchases or violence, so it should come out as suitable for everyone.

**Packages**: upload the `.msix`. Device family: Desktop.

**Store listing (English)**: paste from below, and upload the screenshots in
`packaging/msix/screenshots/` (1920×1080).

**Submission options → Restricted capabilities**: the package uses `runFullTrust`. Paste
this into the box:

> AirCursor is a desktop accessibility and productivity tool that lets people control
> their computer's mouse and a few keyboard shortcuts with hand gestures seen by the webcam.
> It needs full trust to send mouse and keyboard input to whichever app is in front (Win32
> SendInput), to register its pause hotkey (Ctrl+Alt+G) with a low-level keyboard hook, and
> to show a small always-on-top feedback dot next to the cursor. Hand tracking runs entirely
> on the device. No camera images are stored or transmitted, and the app makes no network
> connections.

Then **Submit to the Store**. Review usually takes a few business days for a first submission.

## Listing text

**Product name**: AirCursor (or your reserved name)

**Short description** (shown in search):
> Control your mouse with hand gestures through your webcam. Point, pinch to click, swipe
> between tabs. Works with either hand, on your device.

**Description**:
> AirCursor turns your webcam into a touch-free mouse.
>
> Point with your index finger to move the cursor. Pinch your thumb and finger to click,
> double-click or drag. Pinch with your middle finger to right-click. Move two fingers
> to scroll, swipe your open hand to change browser tabs, and hold a thumbs-down to pause.
>
> A two-minute setup fits it to you: your hand (left or right), your camera, the area your
> hand moves in, and how big or small your pinches are, so it works for big and tiny hands
> alike.
>
> • Works with any webcam, built-in or USB
> • Left- or right-handed
> • Live camera view so you can see what it tracks
> • Per-app gestures: for example, swipe to change slides in PowerPoint or tracks in Spotify
> • Runs quietly in the system tray; pause any time with Ctrl+Alt+G
> • Private: hand tracking runs entirely on your computer. No camera images are saved or
>   sent anywhere, and there's no account and no internet connection
>
> AirCursor is free and open source (MIT).

**What's new in this version**: Dark neon look, new main window with a live camera view,
first-run setup that adapts to your hand.

**Features** (up to 20, one per line):
> Move the cursor by pointing
> Pinch to click, double-click and drag
> Right-click with a middle-finger pinch
> Two-finger scrolling
> Swipe to switch browser tabs, minimize and maximize
> Window switcher (Alt+Tab) with three fingers
> Play/pause and volume with a V-sign
> Left- or right-handed
> Setup that adapts to small or big pinches
> Live camera view with tracking points
> Per-app gestures (PowerPoint, Spotify…)
> Starts with Windows (optional)
> All processing on your device

**Search terms** (up to 7): `webcam mouse`, `touchless`, `accessibility`, `hands-free`,
`hand gestures`, `touch-free mouse`, `mouse alternative`

Keywords must not be other apps' names (Store policy 10.1.3). "air mouse" was rejected for that, and
"camera mouse" is another app's name too. In Partner Center's keyword box, wait a second
before pressing Enter or the keyword is dropped.

## Updates

1. Bump `__version__` in `gesture_control/__init__.py`. The Store needs a higher version each time.
2. Commit, then push a tag: `git tag v0.3.0 && git push origin v0.3.0`. This builds the GitHub
   release zip and the Store package.
3. Partner Center → your app → **Update** (new submission) → **Packages**: upload the new
   `.msix` and submit. After review, Store users get the update automatically.
