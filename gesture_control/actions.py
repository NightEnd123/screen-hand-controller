"""Windows mouse/keyboard output via SendInput, plus foreground-window minimize/maximize."""
import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_VIRTUALDESK = 0x0001, 0x8000, 0x4000
MOUSEEVENTF_WHEEL, MOUSEEVENTF_HWHEEL = 0x0800, 0x1000
BUTTON_FLAGS = {("left", True): 0x0002, ("left", False): 0x0004,
                ("right", True): 0x0008, ("right", False): 0x0010}
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x0001, 0x0002
WHEEL_DELTA = 120


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)

VK = {
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "tab": 0x09, "esc": 0x1B,
    "enter": 0x0D, "space": 0x20, "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
    "volume_mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF,
    "media_next": 0xB0, "media_prev": 0xB1, "media_stop": 0xB2, "play_pause": 0xB3,
}
EXTENDED = {0x5B, 0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28,
            0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3}
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def vk_of(name):
    name = name.strip().lower()
    if name in VK:
        return VK[name]
    if len(name) == 1 and name.isalnum():
        return ord(name.upper())
    raise ValueError(f"unknown key {name!r}")


def virtual_screen():
    """(left, top, width, height) of all monitors, in physical pixels once DPI-aware."""
    g = user32.GetSystemMetrics
    return (g(76), g(77), g(78), g(79))


def foreground_exe():
    """File name of the app in front, e.g. 'chrome.exe' ('' if unknown)."""
    import psutil
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        return psutil.Process(pid.value).name()
    except Exception:
        return ""


def cursor_pos():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


class Actuator:
    """Sends real input. Tracks what it holds so release_all() can always clean up."""

    def __init__(self):
        self.screen = virtual_screen()
        self.held_buttons = set()
        self.held_keys = set()
        self._wheel = [0.0, 0.0]   # fractional notches carried between calls (h, v)

    def _send(self, *inputs):
        arr = (INPUT * len(inputs))(*inputs)
        if user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT)) != len(inputs):
            log.debug("SendInput blocked (err %s) - elevated window in front?", ctypes.get_last_error())

    def _mouse(self, flags, dx=0, dy=0, data=0):
        i = INPUT(type=INPUT_MOUSE)
        i.mi = MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)
        return i

    def _key(self, vk, up):
        i = INPUT(type=INPUT_KEYBOARD)
        flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED else 0)
        i.ki = KEYBDINPUT(vk, user32.MapVirtualKeyW(vk, 0), flags, 0, 0)
        return i

    def move(self, x, y):
        left, top, w, h = self.screen
        nx = round((x - left) * 65535 / max(w - 1, 1))
        ny = round((y - top) * 65535 / max(h - 1, 1))
        self._send(self._mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, nx, ny))

    def button(self, btn, down):
        self._send(self._mouse(BUTTON_FLAGS[(btn, down)]))
        (self.held_buttons.add if down else self.held_buttons.discard)(btn)

    def click(self, btn):
        self._send(self._mouse(BUTTON_FLAGS[(btn, True)]), self._mouse(BUTTON_FLAGS[(btn, False)]))

    def scroll(self, h, v):
        """h, v in wheel notches (fractions allowed; sent as smooth sub-notch deltas)."""
        self._wheel[0] += h * WHEEL_DELTA
        self._wheel[1] += v * WHEEL_DELTA
        out = []
        for axis, flag in ((1, MOUSEEVENTF_WHEEL), (0, MOUSEEVENTF_HWHEEL)):
            amount = int(self._wheel[axis])
            if amount:
                self._wheel[axis] -= amount
                out.append(self._mouse(flag, data=amount))
        if out:
            self._send(*out)

    def keydown(self, name):
        vk = vk_of(name)
        self._send(self._key(vk, False))
        self.held_keys.add(vk)

    def keyup(self, name):
        vk = vk_of(name)
        self._send(self._key(vk, True))
        self.held_keys.discard(vk)

    def keys(self, combo):
        vks = [vk_of(k) for k in combo.split("+")]
        self._send(*[self._key(v, False) for v in vks], *[self._key(v, True) for v in reversed(vks)])

    def window(self, op):
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, buf, 64)
        if buf.value in SHELL_CLASSES:
            return
        user32.ShowWindow(hwnd, {"minimize": 6, "maximize": 3, "restore": 9}[op])

    def release_all(self):
        for btn in list(self.held_buttons):
            self.button(btn, False)
        for vk in list(self.held_keys):
            self._send(self._key(vk, True))
        self.held_keys.clear()
        self._wheel = [0.0, 0.0]


class DryRunActuator(Actuator):
    """Logs what would happen; never touches the real mouse or keyboard."""

    def __init__(self):
        super().__init__()
        self.last_move = None

    def _send(self, *inputs):
        pass

    def move(self, x, y):
        self.last_move = (x, y)

    def button(self, btn, down):
        log.info("[dry-run] %s %s at %s", btn, "down" if down else "up", self._at())
        (self.held_buttons.add if down else self.held_buttons.discard)(btn)

    def click(self, btn):
        log.info("[dry-run] %s click at %s", btn, self._at())

    def scroll(self, h, v):
        log.info("[dry-run] scroll h=%+.2f v=%+.2f notches", h, v)

    def keydown(self, name):
        log.info("[dry-run] key down %s", name)
        self.held_keys.add(vk_of(name))

    def keyup(self, name):
        log.info("[dry-run] key up %s", name)
        self.held_keys.discard(vk_of(name))

    def keys(self, combo):
        log.info("[dry-run] keys %s", combo)

    def window(self, op):
        log.info("[dry-run] window %s", op)

    def release_all(self):
        if self.held_buttons or self.held_keys:
            log.info("[dry-run] release all")
        self.held_buttons.clear()
        self.held_keys.clear()

    def _at(self):
        return tuple(round(v) for v in self.last_move) if self.last_move else "?"
