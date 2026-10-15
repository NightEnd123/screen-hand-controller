"""Settings: built-in defaults, overridden by config.toml."""
import copy
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.toml"
MODEL_PATH = ROOT / "models" / "hand_landmarker.task"
LOG_DIR = ROOT / "logs"

DEFAULTS = {
    "profile": {"setup_done": False},
    "camera": {
        "index": 0, "backend": "msmf", "width": 640, "height": 480,
        "active_fps": 30, "idle_fps": 10, "paused_fps": 5, "idle_after_s": 2.0,
    },
    "tracking": {
        "hand": "right", "swap_handedness": True, "min_detection_confidence": 0.6, "min_presence_confidence": 0.5,
        "min_tracking_confidence": 0.5, "min_hand_size": 0.05, "zone_margin": 0.15,
    },
    "mapping": {"box": [], "cursor_point": "index_tip"},
    "smoothing": {
        "min_cutoff": 0.5, "beta": 0.01, "d_cutoff": 1.0, "glide_ms": 15, "offset_decay_px": 400,
        "precision": True, "precision_gain": 0.4, "precision_slow": 100, "precision_fast": 800,
    },
    "gestures": {
        "pose_frames": 3, "pinch_frames": 2, "release_frames": 2, "scroll_hold_ms": 150, "pinch_max_left": 0.22, "pinch_max_right": 0.30, "pinch_dip": 0.05, "ok_gap": 0.5,
        "pinch_window_ms": 600, "release_frac": 0.5, "pinch_off": 0.45,
        "drag_threshold_px": 30, "release_freeze_ms": 180, "snap_lookback_ms": 300,
        "hand_lost_grace_ms": 200, "two_finger_together": 0.45, "victory_gap": 0.6,
        "gesture_hold_s": 0.7, "volume_arm_s": 0.25, "volume_deadzone": 0.3, "volume_gain": 12.0,
        "volume_max": 15.0,
        "scroll_deadzone": 0.15, "scroll_gain": 20.0, "scroll_max": 40.0,
        "swipe_min_hands": 0.75, "size_ref_halflife_s": 3.0, "swipe_settle_ms": 300, "swipe_facing": 0.7, "swipe_window_ms": 300, "swipe_axis_ratio": 2.0,
        "swipe_cooldown_ms": 800, "switcher_step": 0.5, "switcher_exit_frames": 6, "switcher_hold_ms": 300, "after_click_lockout_ms": 500,
        "switcher_timeout_s": 5.0, "thumb_hold_s": 0.8, "thumb_ext": 0.55,
        "typing_guard_s": 1.0,
    },
    "shortcuts": {
        "swipe_right": "ctrl+tab", "swipe_left": "ctrl+shift+tab",
        "swipe_up": "window:maximize", "swipe_down": "window:minimize",
        "victory_hold": "play_pause", "call_hold": "win+h",
    },
    "hotkey": {"toggle": "ctrl+alt+g"},
    "feedback": {"sounds": True, "notifications": True, "overlay": True},
    "apps": {},
}


def _merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load(path=CONFIG_PATH):
    cfg = copy.deepcopy(DEFAULTS)
    if Path(path).exists():
        with open(path, "rb") as f:
            _merge(cfg, tomllib.load(f))
    return cfg


def _toml(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{round(v, 4)}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(f"{x:.3f}" if isinstance(x, float) else _toml(x) for x in v) + "]"
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return str(v)


def set_values(updates, path=CONFIG_PATH):
    """Write {(section, key): value} into config.toml, keeping every comment and the layout."""
    path = Path(path)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    for (section, key), value in updates.items():
        header = re.search(rf"^\[{re.escape(section)}\][ \t]*$", text, flags=re.M)
        if header is None:
            text = text.rstrip("\n") + f"\n\n[{section}]\n{key} = {_toml(value)}\n"
            continue
        start = header.end()
        nxt = re.search(r"^\[", text[start:], flags=re.M)
        end = start + nxt.start() if nxt else len(text)
        block = text[start:end]
        pat = re.compile(rf"^({re.escape(key)}[ \t]*=[ \t]*)([^#\n]*?)([ \t]*#.*)?$", flags=re.M)
        if pat.search(block):
            block = pat.sub(lambda m: m.group(1) + _toml(value) + (m.group(3) or ""), block, count=1)
        else:
            block = f"\n{key} = {_toml(value)}" + block
        text = text[:start] + block + text[end:]
    path.write_text(text, encoding="utf-8")


def save_box(box, path=CONFIG_PATH):
    """Rewrite only the `box = [...]` line so the comments in config.toml survive."""
    set_values({("mapping", "box"): list(box)}, path)
