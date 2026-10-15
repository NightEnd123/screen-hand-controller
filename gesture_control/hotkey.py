"""Global hotkey + "you're typing" detection from one low-level keyboard hook (pynput).

Keys our own app sends (SendInput) are flagged as injected by Windows and ignored here.
"""
import ctypes
import logging

from pynput import keyboard

from .actions import vk_of

log = logging.getLogger(__name__)
user32 = ctypes.WinDLL("user32")

WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
LLKHF_INJECTED = 0x10
MODS = {"ctrl": (0x11,), "alt": (0x12,), "shift": (0x10,), "win": (0x5B, 0x5C)}
MODIFIER_VKS = {0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}


def _down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


class KeyWatcher:
    def __init__(self, combo, on_hotkey, on_typing):
        parts = [p.strip().lower() for p in combo.split("+")]
        self.mods = {p for p in parts if p in MODS}
        keys = [p for p in parts if p not in MODS]
        if len(keys) != 1:
            raise ValueError(f"hotkey needs exactly one non-modifier key: {combo!r}")
        self.vk = vk_of(keys[0])
        self.on_hotkey, self.on_typing = on_hotkey, on_typing
        self.listener = keyboard.Listener(win32_event_filter=self._filter)

    def start(self):
        self.listener.start()

    def stop(self):
        self.listener.stop()

    def _filter(self, msg, data):
        if data.flags & LLKHF_INJECTED or msg not in (WM_KEYDOWN, WM_SYSKEYDOWN):
            return False
        vk = data.vkCode
        if vk == self.vk and all(any(_down(v) for v in MODS[m]) for m in self.mods) \
                and not any(any(_down(v) for v in MODS[m]) for m in set(MODS) - self.mods):
            self.listener.suppress_event()   # don't also type the key into the focused app
            try:
                self.on_hotkey()
            except Exception:
                log.exception("hotkey handler failed")
        elif vk not in MODIFIER_VKS:
            self.on_typing()
        return False
