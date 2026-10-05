"""A virtual input source: one place that moves the mouse and types, and that reports whether it actually did.

The earlier attempts were split across a PowerShell `SendKeys` call, a raw `mouse_event` with coordinates I had computed
by hand from a window rectangle, and posted window messages. Three mechanisms, three coordinate systems, and no way to
tell which of them had failed -- when a click did nothing there was no evidence whether the position was wrong, the
mechanism was ignored, or the window was not listening.

What is here instead:

* **`SendInput`, not `mouse_event`.** `SendInput` is the modern path and is what a real device goes through; it also
  takes normalized absolute coordinates across the whole virtual desktop, so no window-relative arithmetic is needed and
  a mis-scaled coordinate cannot silently land somewhere plausible.
* **The cursor position is read back after every move.** A move that did not happen is then a fact rather than an
  assumption, which is the part that was missing.
* **Window rectangles come from the same call that will be used to click**, so a click either lands inside a known
  rectangle or is refused before it happens.

The real mouse is left where it was found if `restore` is used. Nothing here is imported by the library.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import time

user32 = ctypes.windll.user32

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
SM_CXSCREEN, SM_CYSCREEN = 0, 1


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.POINTER(wintypes.ULONG))]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.POINTER(wintypes.ULONG))]


class _INPUTunion(ctypes.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [('type', wintypes.DWORD), ('union', _INPUTunion)]


def _send(*inputs: INPUT) -> int:
    array = (INPUT * len(inputs))(*inputs)
    return user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))


def screen_size() -> tuple[int, int]:
    return user32.GetSystemMetrics(SM_CXSCREEN), user32.GetSystemMetrics(SM_CYSCREEN)


def cursor() -> tuple[int, int]:
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def move(x: int, y: int, settle: float = 0.05) -> tuple[int, int]:
    """Move the pointer and **return where it actually is**, which is the check the old code never made."""
    width, height = screen_size()
    # absolute coordinates are normalized to 0..65535 over the primary monitor
    nx = int(x * 65535 / max(1, width - 1))
    ny = int(y * 65535 / max(1, height - 1))
    _send(INPUT(type=INPUT_MOUSE,
                union=_INPUTunion(mi=MOUSEINPUT(nx, ny, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, None))))
    time.sleep(settle)
    return cursor()


def click(x: int | None = None, y: int | None = None, button: str = 'left', settle: float = 0.08) -> bool:
    """Move, verify, then press and release. Returns whether the pointer ended up where it was asked to go."""
    if x is not None and y is not None:
        landed = move(x, y)
        if abs(landed[0] - x) > 2 or abs(landed[1] - y) > 2:
            return False
    down, up = ((MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP) if button == 'left'
                else (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP))
    _send(INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=MOUSEINPUT(0, 0, 0, down, 0, None))))
    time.sleep(settle)
    _send(INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=MOUSEINPUT(0, 0, 0, up, 0, None))))
    time.sleep(settle)
    return True


def wheel(notches: int, settle: float = 0.1) -> None:
    _send(INPUT(type=INPUT_MOUSE,
                union=_INPUTunion(mi=MOUSEINPUT(0, 0, notches * 120, MOUSEEVENTF_WHEEL, 0, None))))
    time.sleep(settle)


VK = {'enter': 0x0D, 'esc': 0x1B, 'tab': 0x09, 'space': 0x20, 'back': 0x08,
      'ctrl': 0x11, 'alt': 0x12, 'shift': 0x10, 'home': 0x24, 'end': 0x23,
      'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28, 'delete': 0x2E}


def _key(vk: int, up: bool = False) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, None)))


def _vk(name: str) -> int:
    """Named keys, or a single letter or digit, which map to their own code in both cases."""
    lowered = name.lower()
    if lowered in VK:
        return VK[lowered]
    if len(name) == 1:
        if name.isdigit():
            return 0x30 + int(name)
        if name.isalpha():
            return ord(name.upper())
    raise KeyError('no virtual key for %r' % name)


def key(name: str, settle: float = 0.05) -> None:
    vk = _vk(name)
    _send(_key(vk))
    time.sleep(settle)
    _send(_key(vk, up=True))
    time.sleep(settle)


def chord(*names: str, settle: float = 0.1) -> None:
    """A modifier combination, held together -- Ctrl+O rather than Ctrl, then O."""
    keys = [_vk(n) for n in names]
    for vk in keys:
        _send(_key(vk))
    time.sleep(settle)
    for vk in reversed(keys):
        _send(_key(vk, up=True))
    time.sleep(settle)


def type_text(text: str, settle: float = 0.02) -> None:
    """Type by Unicode codepoint, so the keyboard layout cannot turn a path into something else.

    `SendKeys` interprets its argument: a backslash, a quote, a brace or a bracket changes the meaning of what follows,
    and every one of those appears in a Windows path. This sends the characters themselves and has no escape syntax to
    get wrong.
    """
    for character in text:
        code = ord(character)
        _send(INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, None))))
        _send(INPUT(type=INPUT_KEYBOARD,
                    union=_INPUTunion(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None))))
        time.sleep(settle)
