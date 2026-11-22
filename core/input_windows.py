import sys
import time
from typing import List, Tuple

IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002

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

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class _INPUTunion(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", _INPUTunion)]


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

    extra = ctypes.c_ulong(0)
    inputs = []
    for vk in vk_codes:
        ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=ctypes.pointer(extra))
        inputs.append(INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=ki)))
    for vk in reversed(vk_codes):
        ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=ctypes.pointer(extra))
        inputs.append(INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=ki)))

    arr = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    time.sleep(0.02)
    if sent != len(inputs):
        return False, "Windows SendInput failed (target app may be running as Administrator)."
    return True, f"Sent {'+'.join(normalized)}"
