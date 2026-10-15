"""Gesture Control entry point: wires camera -> tracker -> gesture engine -> output, plus tray + hotkey."""
import argparse
import ctypes
import logging
import logging.handlers
import os
import queue
import subprocess
import sys
import threading
import time
import winsound
from pathlib import Path

if sys.stdout is None:          # pythonw.exe has no console
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

log = logging.getLogger("gesture_control")

STARTUP_FILE = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup/GestureControl.vbs"


def set_dpi_aware():
    """Without this, Windows reports a scaled-down screen (1504x1003 instead of 2256x1504 at 150%)."""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()


def single_instance():
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\GestureControlSingleton")
    if ctypes.windll.kernel32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
        ctypes.windll.user32.MessageBoxW(None, "Gesture Control is already running (see the tray).", "Gesture Control", 0x40)
        sys.exit(0)
    return handle


def setup_logging(log_dir, console):
    log_dir.mkdir(exist_ok=True)
    handlers = [logging.handlers.RotatingFileHandler(log_dir / "gesture-control.log", maxBytes=1_000_000,
                                                     backupCount=3, encoding="utf-8")]
    if console:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class App:
    def __init__(self, args):
        from . import config
        from .actions import Actuator, DryRunActuator, virtual_screen
        from .camera import Camera
        from .gestures import GestureEngine
        from .output import OutputThread
        from .preview import Preview
        from .tracker import Tracker

        self.config = config
        self.args = args
        self.cfg = config.load()
        if args.fake_camera:
            self.cfg["camera"]["backend"] = "fake"
        self.screen = virtual_screen()
        log.info("screen %s, dry_run=%s", self.screen, args.dry_run)
        self.act = DryRunActuator() if args.dry_run else Actuator()
        self.output = OutputThread(self.act, self.cfg["smoothing"]["glide_ms"], resolver=self.resolve_gesture)
        self.ui = None
        self.camera = Camera(self.cfg["camera"])
        self.tracker = Tracker(self.cfg["tracking"], config.MODEL_PATH)
        self.engine = GestureEngine(self.cfg, self.screen)
        self._GestureEngine = GestureEngine
        self.preview_win = Preview()
        self.preview = args.preview
        self.camera_off = False
        self.calibrator = None
        self.wizard = None
        self.cmds = queue.Queue()
        self.running = True
        self.typing_until = 0.0
        self.tray = None
        self.session = None
        if args.record:   # landmark numbers + what the app did, for replaying problems (no images)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            self.session_path = config.SESSIONS_DIR / f"session-{stamp}.json"
            self.session_path.parent.mkdir(parents=True, exist_ok=True)
            self.session = []
            self.session_saved = time.perf_counter()
        self.keys = None
        if args.paused:
            self.engine.set_paused(True)

    # ---- called from other threads (tray / hotkey): queue work for the engine thread ----------
    def is_paused(self):
        return self.engine.paused or self.camera_off

    def toggle_pause(self, source):
        def cmd():
            if self.camera_off:
                self.camera_off = False
                self._set_paused(False, source)
            else:
                self._set_paused(not self.engine.paused, source)
        self.cmds.put(cmd)

    def set_camera_off(self, off):
        def cmd():
            self.camera_off = off
            self._set_paused(off, "camera")
        self.cmds.put(cmd)

    def toggle_preview(self):
        self.preview = not self.preview

    def start_calibration(self):
        from .calibrate import Calibrator

        def cmd():
            w, h = self.cfg["camera"]["width"], self.cfg["camera"]["height"]
            self.output.submit(None, self.engine.set_paused(self.engine.paused))
            self.camera_off = False
            self.calibrator = Calibrator(self.screen[2] / self.screen[3], w / h)
            self.preview = True
            self._notify("Calibration: in the debug window, hold your fingertip at the top-left, then bottom-right.")
        self.cmds.put(cmd)

    def start_wizard(self):
        from .setup_wizard import SetupWizard

        def cmd():
            w, h = self.cfg["camera"]["width"], self.cfg["camera"]["height"]
            self.output.submit(None, self.engine.set_paused(self.engine.paused))
            self.camera_off = False
            self.calibrator = None
            self.wizard = SetupWizard(self.cfg, self.screen[2] / self.screen[3], w / h, self.tracker.swap)
            if self.ui:
                self.ui.open_setup()
        self.cmds.put(cmd)

    def wizard_cmd(self, name, arg=None):
        """Buttons in the setup window (called from the Tk thread)."""
        def cmd():
            wz = self.wizard
            if wz is None:
                return
            if name == "hand":
                wz.choose_hand(arg)
            elif name == "skip":
                wz.skip_step()
            elif name == "camera_next":
                self.camera.cfg["index"] = (self.camera.cfg["index"] + 1) % 4
                self.camera.reopen()
                log.info("setup: trying camera %d", self.camera.cfg["index"])
            elif name in ("finish", "skip_all"):
                updates = (wz.finish(camera_index=self.camera.cfg["index"]) if name == "finish"
                           else {("profile", "setup_done"): True})
                log.info("setup saved: %s", updates)
                self.config.set_values(updates)
                self._end_wizard()
                self._apply_settings(self.config.load())
                self._notify("Setup saved. Gestures are on." if name == "finish"
                             else "Setup skipped. Run it any time from the tray icon.")
            elif name == "cancel":
                self._end_wizard()
                if self.camera.cfg["index"] != self.cfg["camera"]["index"]:
                    self.camera.cfg["index"] = self.cfg["camera"]["index"]
                    self.camera.reopen()
        self.cmds.put(cmd)

    def _end_wizard(self):
        self.wizard = None
        if self.ui:
            self.ui.close_setup()

    def edit_settings(self):
        subprocess.Popen(["notepad.exe", str(self.config.CONFIG_PATH)])

    def reload_settings(self):
        def cmd():
            try:
                cfg = self.config.load()
            except Exception as e:
                self._notify(f"Settings not loaded: {e}")
                log.exception("bad config")
                return
            self._apply_settings(cfg)
            self._notify("Settings reloaded (hotkey changes need a restart).")
        self.cmds.put(cmd)

    def _apply_settings(self, cfg):
        paused = self.engine.paused
        self.output.submit(None, self.engine.set_paused(True))
        self.cfg = cfg
        self.engine = self._GestureEngine(cfg, self.screen)
        self.engine.set_paused(paused)
        self.output.tau = max(cfg["smoothing"]["glide_ms"], 1) / 1000
        self.tracker.swap = cfg["tracking"]["swap_handedness"]
        reopen = cfg["camera"]["index"] != self.camera.cfg["index"]
        self.camera.cfg = cfg["camera"]
        if reopen:
            self.camera.reopen()

    def open_settings(self):
        if self.ui:
            self.ui.open_settings()

    def resolve_gesture(self, name):
        """Per-app override for a named gesture (e.g. swipe_right in PowerPoint), else None."""
        apps = self.cfg.get("apps") or {}
        if not apps:
            return None
        from .actions import foreground_exe
        from .gestures import shortcut_action
        exe = foreground_exe().lower()
        for app_name, mapping in apps.items():
            if app_name.lower() == exe and name in mapping:
                return shortcut_action(mapping[name], name)
        return None

    def startup_enabled(self):
        return STARTUP_FILE.exists()

    def toggle_startup(self):
        if STARTUP_FILE.exists():
            STARTUP_FILE.unlink()
            return
        if self.config.FROZEN:
            exe = Path(sys.executable)
            folder, command = exe.parent, f'"""{exe}"""'
        else:
            folder = self.config.ROOT
            command = f'"""{folder / ".venv" / "Scripts" / "pythonw.exe"}"" -m gesture_control"'
        STARTUP_FILE.write_text(
            'Set sh = CreateObject("WScript.Shell")\r\n'
            f'sh.CurrentDirectory = "{folder}"\r\n'
            f'sh.Run {command}, 0, False\r\n',
            encoding="utf-8")

    def on_typing(self):
        self.typing_until = time.perf_counter() + self.cfg["gestures"]["typing_guard_s"]

    def quit(self):
        self.running = False
        if self.tray:
            self.tray.stop()

    # ---- engine thread -------------------------------------------------------------------------
    def _notify(self, msg):
        log.info(msg)
        if self.tray and self.cfg["feedback"]["notifications"]:
            threading.Thread(target=self.tray.notify, args=(msg,), daemon=True).start()

    def _sound(self, paused):
        if self.cfg["feedback"]["sounds"]:
            alias = "SystemExclamation" if paused else "SystemAsterisk"
            winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)

    def _set_paused(self, paused, source):
        self.output.submit(None, self.engine.set_paused(paused))
        self._announce(paused, source)

    def _announce(self, paused, source):
        self._sound(paused)
        if self.camera_off:
            self._notify("Camera off. Ctrl+Alt+G or the tray icon turns it back on.")
        elif paused:
            self._notify("Gestures paused. Thumbs-up (hold) or Ctrl+Alt+G to resume.")
        else:
            self._notify("Gestures on. Thumbs-down (hold) or Ctrl+Alt+G to pause.")
        log.info("paused=%s camera_off=%s (via %s)", paused, self.camera_off, source)

    def _record(self, t, hand, out):
        self.session.append({
            "t": round(t, 4),
            "hand": None if hand is None else {
                "img": hand.img.round(5).tolist(), "world": hand.world.round(5).tolist(),
                "handedness": hand.handedness, "score": round(hand.score, 3)},
            "mode": out.mode, "pose": out.info.get("pose"),
            "actions": [list(a) for a in out.actions]})
        if t - self.session_saved > 15:
            self.save_session()

    def save_session(self):
        import json
        if self.session:
            t0 = self.session[0]["t"]
            frames = [{**f, "t": round(f["t"] - t0, 4)} for f in self.session]
            self.session_path.write_text(json.dumps({
                "segment": "session", "aspect": self.cfg["camera"]["width"] / self.cfg["camera"]["height"],
                "expect": {}, "forbid_other": False, "frames": frames}))
        self.session_saved = time.perf_counter()

    def _tray_state(self):
        if self.camera.status == "error":
            return "error"
        if self.calibrator is not None or self.wizard is not None:
            return "calibrating"
        if self.camera_off:
            return "off"
        return "paused" if self.engine.paused else "active"

    def engine_loop(self):
        import psutil
        proc = psutil.Process()
        proc.cpu_percent()
        ncpu = psutil.cpu_count() or 1
        cpu, cpu_t = 0.0, time.perf_counter()
        fps_n, fps, fps_t = 0, 0.0, time.perf_counter()
        last_hand = 0.0
        stats_t = time.perf_counter()
        while self.running:
            try:
                while not self.cmds.empty():
                    self.cmds.get_nowait()()
                if self.tray:
                    self.tray.set_state(self._tray_state())

                if self.camera_off:
                    self.camera.set_open(False)
                    if self.preview_win.open:
                        self.preview_win.close()
                    time.sleep(0.1)
                    continue
                self.camera.set_open(True)

                start = time.perf_counter()
                frame = self.camera.read(timeout=1.0)
                if frame is None:
                    if self.wizard is not None and self.ui:
                        self.ui.setup_feed(self.wizard.camera_problem(self.camera.cfg["index"]), None)
                    continue
                t = time.perf_counter()
                hand, mirrored = self.tracker.detect(frame, t)
                if hand is not None:
                    last_hand = t

                banner, progress, out = None, None, None
                if self.wizard is not None:
                    view = self.wizard.update(t, hand)
                    if self.ui:
                        self.ui.setup_feed(view, self._setup_image(mirrored, hand, view))
                    mode = "calibrating"
                elif self.calibrator is not None:
                    banner, result = self.calibrator.update(t, hand)
                    progress = self.calibrator.progress
                    if result == "timeout":
                        self.calibrator = None
                        self._notify("Calibration timed out; box unchanged.")
                    elif result is not None:
                        self.config.save_box(result)
                        self.cfg["mapping"]["box"] = result
                        self.engine.set_box(result)
                        self.calibrator = None
                        self._notify("Control box saved.")
                    mode = "calibrating"
                    if self.ui:
                        self.ui.feed("calibrating", None, [])
                else:
                    out = self.engine.update(t, hand, suppress=t < self.typing_until)
                    self.output.submit(out.cursor, out.actions)
                    if self.ui:
                        self.ui.feed(out.mode, out.info.get("hold"), out.actions,
                                     self.resolve_gesture if self.cfg.get("apps") else None)
                    shown = [a for a in out.actions if a[0] != "scroll"]
                    if shown:
                        log.info("%s (mode %s, pose %s)", shown, out.mode, out.info.get("pose"))
                    if self.session is not None:
                        self._record(t, hand, out)
                    for a in out.actions:
                        if a[0] == "pause":
                            self._announce(a[1], "gesture")
                    mode = out.mode

                # stats
                fps_n += 1
                if t - fps_t >= 1.0:
                    fps, fps_n, fps_t = fps_n / (t - fps_t), 0, t
                if t - cpu_t >= 1.0:
                    cpu, cpu_t = proc.cpu_percent() / ncpu, t
                if t - stats_t >= 30:
                    stats_t = t
                    log.info("stats: %.1f fps, %.1f%% CPU, state %s", fps, cpu, self._tray_state())

                if self.preview:
                    lines = [f"mode: {mode}   state: {self._tray_state()}   {'DRY RUN' if self.args.dry_run else ''}",
                             f"fps: {fps:4.1f}   cpu: {cpu:4.1f}% of machine"]
                    if out is not None and out.info:
                        i = out.info
                        lines.append(f"pose: {i.get('pose')} (raw {i.get('raw_pose')})  hand: "
                                     f"{hand.handedness if hand else '-'}  in box: {i.get('in_zone')}")
                        lines.append(f"pinch gap L {i.get('ratio_l', 0):.2f}  R {i.get('ratio_r', 0):.2f}  "
                                     f"(click below {self.cfg['gestures']['pinch_max_left']:.2f})")
                        if "hold" in i:
                            progress = i["hold"]
                    if out is not None and out.cursor is not None:
                        lines.append(f"cursor -> {round(out.cursor[0])}, {round(out.cursor[1])}")
                    if not self.preview_win.show(mirrored, hand, self.engine.mapper.box, lines,
                                                 mode, progress, banner):
                        self.preview = False
                        self.preview_win.close()
                        if self.args.preview:   # started with the debug view (run.bat): closing it ends the session
                            log.info("debug view closed; quitting")
                            self.quit()
                elif self.preview_win.open:
                    self.preview_win.close()

                # adaptive frame rate
                c = self.cfg["camera"]
                setting_up = self.calibrator is not None or self.wizard is not None
                if self.engine.paused and not setting_up:
                    target = c["paused_fps"]
                elif t - last_hand > c["idle_after_s"] and not setting_up:
                    target = c["idle_fps"]
                else:
                    target = c["active_fps"]
                # While tracking a hand, decode every camera frame so the next one is ready the
                # moment we finish this one (otherwise we wait for a new frame and run at ~half rate).
                self.camera.continuous = target == c["active_fps"]
                wait = 1 / target - (time.perf_counter() - start)
                if wait > 0:
                    time.sleep(wait)
            except Exception:
                log.exception("engine loop error")
                self.act.release_all()
                time.sleep(1)
        self.preview_win.close()

    def _setup_image(self, mirrored, hand, view):
        """Camera picture for the setup window (shown live, never saved), as RGB."""
        import cv2
        from .preview import annotate
        img = annotate(mirrored, hand, None, (80, 200, 80))
        h, w = img.shape[:2]
        for x, y in view.points:
            cv2.circle(img, (int(x * w), int(y * h)), 9, (0, 200, 255), 3)
        img = cv2.resize(img, (512, round(512 * h / w)), interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # ---- lifecycle -----------------------------------------------------------------------------
    def _install_ctrl_c(self):
        """Ctrl+C / closing the console quits cleanly (the tray's message loop would otherwise swallow it)."""
        handler_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

        def on_ctrl(_event):
            self.quit()
            return 1
        self._ctrl_handler = handler_type(on_ctrl)   # keep a reference so it isn't garbage-collected
        ctypes.windll.kernel32.SetConsoleCtrlHandler(self._ctrl_handler, True)

    def _maybe_setup(self):
        if self.args.setup or not self.cfg["profile"]["setup_done"]:
            self.start_wizard()
            return True
        return False

    def run(self):
        from .hotkey import KeyWatcher
        from .tray import Tray
        from .ui import UI

        self.ui = UI(self)
        self.ui.start()
        self.output.start()
        self.camera.start()
        self.keys = KeyWatcher(self.cfg["hotkey"]["toggle"],
                               on_hotkey=lambda: self.toggle_pause("hotkey"), on_typing=self.on_typing)
        self.keys.start()
        engine_thread = threading.Thread(target=self.engine_loop, daemon=True, name="engine")
        self._install_ctrl_c()
        try:
            if self.args.no_tray:
                engine_thread.start()
                self._maybe_setup()
                log.info("running without tray; Ctrl+C to quit")
                end = time.time() + (self.args.seconds or 1e12)
                while self.running and time.time() < end:
                    time.sleep(0.2)
            else:
                self.tray = Tray(self)

                def setup(icon):
                    icon.visible = True
                    engine_thread.start()
                    if not self._maybe_setup():
                        self._announce(self.engine.paused, "start")
                    if self.args.seconds:
                        timer = threading.Timer(self.args.seconds, self.quit)
                        timer.daemon = True
                        timer.start()

                self.tray.run(setup)
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            if engine_thread.is_alive():
                engine_thread.join(timeout=3)
            self.keys.stop()
            self.ui.stop()
            self.output.stop()
            self.output.join(timeout=2)
            self.act.release_all()
            self.camera.stop()
            self.camera.join(timeout=3)
            self.tracker.close()
            if self.session is not None:
                self.save_session()
                log.info("session saved to %s", self.session_path)
            log.info("stopped")


def main(argv=None):
    p = argparse.ArgumentParser(prog="gesture_control", description="Control the mouse with hand gestures.")
    p.add_argument("--dry-run", action="store_true", help="log actions instead of moving the mouse / pressing keys")
    p.add_argument("--preview", action="store_true", help="open the debug view at start")
    p.add_argument("--paused", action="store_true", help="start paused")
    p.add_argument("--no-tray", action="store_true", help="run in the console without a tray icon")
    p.add_argument("--seconds", type=float, help="quit after this many seconds (testing)")
    p.add_argument("--setup", action="store_true", help="open the setup wizard even if setup was done")
    p.add_argument("--fake-camera", action="store_true", help="use a blank test picture instead of a camera")
    p.add_argument("--record", action="store_true",
                   help="save hand-point numbers + actions to recordings/sessions/ (no images)")
    args = p.parse_args(argv)

    set_dpi_aware()
    _mutex = single_instance()  # noqa: F841  (kept alive for the process lifetime)
    from . import config
    config.ensure_config()
    setup_logging(config.LOG_DIR, console=sys.stdout is not None and sys.stdout.isatty())
    log.info("settings: %s", config.CONFIG_PATH)
    if not config.MODEL_PATH.exists():
        ctypes.windll.user32.MessageBoxW(
            None, f"Model file missing:\n{config.MODEL_PATH}\nRe-download the app (or run setup.ps1 from source).",
            "Gesture Control", 0x10)
        return 1
    try:
        App(args).run()
    except Exception as e:
        log.exception("could not start")
        ctypes.windll.user32.MessageBoxW(
            None, f"Gesture Control could not start:\n{e}\n\nDetails are in {config.LOG_DIR / 'gesture-control.log'}",
            "Gesture Control", 0x10)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
