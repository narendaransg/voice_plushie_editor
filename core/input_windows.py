import sys
import time
from typing import List, Tuple

IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    INPUT_HARDWARE = 2

    KEYEVENTF_KEYUP = 0x0002

    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_WHEEL = 0x0800
    WHEEL_DELTA = 120

    VK_MAP = {
        "backspace": 0x08,
        "tab": 0x09,
        "enter": 0x0D,
        "shift": 0x10,
        "ctrl": 0x11,
        "alt": 0x12,
        "esc": 0x1B,
        "space": 0x20,
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
        "delete": 0x2E,
        "0": 0x30,
        "1": 0x31,
        "2": 0x32,
        "3": 0x33,
        "4": 0x34,
        "5": 0x35,
        "6": 0x36,
        "7": 0x37,
        "8": 0x38,
        "9": 0x39,
        "=": 0xBB,
        "+": 0xBB,
        "-": 0xBD,
    }
    for code in range(ord("a"), ord("z") + 1):
        VK_MAP[chr(code)] = code - 32  # A-Z virtual key codes

    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUTunion(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", wintypes.DWORD),
            ("union", _INPUTunion),
        ]


def _send_mouse_inputs(items: List[Tuple[int, int, int]]) -> Tuple[bool, str]:
    if not IS_WINDOWS:
        return True, f"[Dry-run] Mouse actions: {len(items)}"
    inputs = []
    for dx, dy, flags in items:
        mi = MOUSEINPUT(dx=int(dx), dy=int(dy), mouseData=0, dwFlags=flags, time=0, dwExtraInfo=0)
        inputs.append(INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=mi)))
    arr = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        err = ctypes.get_last_error()
        return False, f"Windows mouse SendInput failed (sent={sent}/{len(inputs)}, winerr={err})."
    return True, "OK"


def move_mouse_relative(dx: int, dy: int) -> Tuple[bool, str]:
    """Move mouse cursor relative to current position."""
    if dx == 0 and dy == 0:
        return True, "No movement"
    ok, detail = _send_mouse_inputs([(int(dx), int(dy), MOUSEEVENTF_MOVE)])
    if not ok:
        return False, detail
    return True, f"Moved cursor ({int(dx)}, {int(dy)})"


def mouse_click(button: str = "left") -> Tuple[bool, str]:
    """Perform a single left or right mouse click."""
    btn = (button or "left").lower()
    if btn == "right":
        down_flag, up_flag, label = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP, "right click"
    else:
        down_flag, up_flag, label = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, "left click"
    ok, detail = _send_mouse_inputs([(0, 0, down_flag), (0, 0, up_flag)])
    time.sleep(0.02)
    return (True, f"Sent {label}") if ok else (False, detail)


def mouse_double_click() -> Tuple[bool, str]:
    """Perform a double left-click."""
    ok, detail = _send_mouse_inputs([
        (0, 0, MOUSEEVENTF_LEFTDOWN),
        (0, 0, MOUSEEVENTF_LEFTUP),
        (0, 0, MOUSEEVENTF_LEFTDOWN),
        (0, 0, MOUSEEVENTF_LEFTUP),
    ])
    time.sleep(0.03)
    return (True, "Sent double click") if ok else (False, detail)


def mouse_down(button: str = "left") -> Tuple[bool, str]:
    """Press and hold mouse button."""
    flag = MOUSEEVENTF_RIGHTDOWN if (button or "left").lower() == "right" else MOUSEEVENTF_LEFTDOWN
    ok, detail = _send_mouse_inputs([(0, 0, flag)])
    return (True, "Holding click") if ok else (False, detail)


def mouse_up(button: str = "left") -> Tuple[bool, str]:
    """Release held mouse button."""
    flag = MOUSEEVENTF_RIGHTUP if (button or "left").lower() == "right" else MOUSEEVENTF_LEFTUP
    ok, detail = _send_mouse_inputs([(0, 0, flag)])
    return (True, "Released click") if ok else (False, detail)


def mouse_scroll(wheel_delta: int = WHEEL_DELTA) -> Tuple[bool, str]:
    """Scroll vertical wheel by wheel_delta (positive up, negative down)."""
    if not IS_WINDOWS:
        return True, f"[Dry-run] Scroll {wheel_delta}"
    mi = MOUSEINPUT(dx=0, dy=0, mouseData=ctypes.c_uint(wheel_delta).value, dwFlags=MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=0)
    inp = INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=mi))
    arr = (INPUT * 1)(inp)
    sent = user32.SendInput(1, arr, ctypes.sizeof(INPUT))
    if sent != 1:
        err = ctypes.get_last_error()
        return False, f"Windows scroll SendInput failed (winerr={err})."
    return True, f"Scrolled {'up' if wheel_delta > 0 else 'down'}"


def get_active_window_title() -> str:
    """Return foreground window title on Windows, or empty string on non-Windows."""
    if not IS_WINDOWS:
        return ""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def check_target_window(window_keywords: List[str]) -> Tuple[bool, str]:
    """Verify whether the foreground window matches the selected editor profile."""
    if not IS_WINDOWS:
        return True, "Non-Windows dry-run environment"
    title = get_active_window_title()
    lowered = title.lower()
    if not window_keywords:
        return True, title
    matched = any(kw.lower() in lowered for kw in window_keywords)
    return matched, title


def send_key_combo(keys: List[str]) -> Tuple[bool, str]:
    """Send a chord of keys (e.g., ['ctrl', 'b']) via Windows SendInput."""
    if not keys:
        return False, "No keys configured for this command."

    normalized = [k.strip().lower() for k in keys if k.strip()]
    if not IS_WINDOWS:
        return True, f"[Dry-run] Would send {'+'.join(normalized)}"

    vk_codes = []
    for k in normalized:
        vk = VK_MAP.get(k)
        if vk is None:
            return False, f"Unsupported key '{k}' in shortcut mapping."
        vk_codes.append(vk)

    inputs = []
    for vk in vk_codes:
        ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
        inputs.append(INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=ki)))
    for vk in reversed(vk_codes):
        ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
        inputs.append(INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=ki)))

    arr = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    time.sleep(0.02)
    if sent != len(inputs):
        err = ctypes.get_last_error()
        return False, f"Windows SendInput failed (sent={sent}/{len(inputs)}, winerr={err})."
    return True, f"Sent {'+'.join(normalized)}"
