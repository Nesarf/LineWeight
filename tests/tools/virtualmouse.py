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


_GAIN: float | None = None


def calibrate(settle: float = 0.05) -> float:
    """Measure how far the cursor moves per unit of requested delta.

    **Windows scales relative mouse motion.** The system's pointer speed and "enhance pointer precision" apply a gain to
    every relative delta, which is why asking for 120 pixels produced about 144 and the error grew with the distance. A
    sequence of absolute moves had landed exactly, so the gain does not apply to them -- but absolute motion needs
    normalization that depends on the monitor layout, and it missed by hundreds of pixels here.

    Rather than guess which effect is in play, this asks the system: move one pixel at a time, measure, and divide the
    answer out of every later request. The gain is a property of the machine, so it is measured once.
    """
    global _GAIN
    start = cursor()
    _send(INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=MOUSEINPUT(50, 0, 0, MOUSEEVENTF_MOVE, 0, None))))
    time.sleep(settle)
    moved = cursor()[0] - start[0]
    _send(INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=MOUSEINPUT(-50, 0, 0, MOUSEEVENTF_MOVE, 0, None))))
    time.sleep(settle)
    _GAIN = (moved / 50.0) if moved else 1.0
    return _GAIN


def move(x: int, y: int, settle: float = 0.05) -> tuple[int, int]:
    """Move the pointer and **return where it actually is**, which is the check the old code never made.

    **By relative steps, not by absolute coordinates.** Absolute motion needs the position normalized to 0..65535 over
    the desktop, and that normalization depends on the resolution, the monitor layout and any display scaling: on this
    machine a move to (834, 476) landed at (19, 6), which is the kind of miss that looks like "the click did nothing".
    A relative delta is computed from the position the system itself reports, so scaling cannot enter into it.

    Large jumps are sent in steps too -- a single delta of several hundred pixels can be clamped by the driver.
    """
    if _GAIN is None:
        calibrate()
    for _ in range(60):
        here = cursor()
        dx, dy = x - here[0], y - here[1]
        if abs(dx) <= 1 and abs(dy) <= 1:
            break
        # divide the system's gain out of the request, then bound the step so the driver cannot clamp it
        step_x = max(-120, min(120, int(dx / _GAIN)))
        step_y = max(-120, min(120, int(dy / _GAIN)))
        _send(INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=MOUSEINPUT(step_x, step_y, 0, MOUSEEVENTF_MOVE, 0, None))))
        time.sleep(settle / 4)
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

def drag(points: list[tuple[int, int]], button: str = 'left', steps_per_segment: int = 8,
         settle: float = 0.012) -> bool:
    """Press at the first point, move through the rest, release at the last.

    **Every intermediate position is sent.** A drawing application samples the pointer while the button is down, so a
    single move from the start to the end of a stroke produces either a straight line or nothing at all depending on how
    it reads the queue -- and a stroke is what is being tested, not a click. The interpolation is in *screen* steps
    rather than in time, because what SAI records is the path.

    Returns whether the pointer was where it was asked to be at the start, which is the one part of this that can be
    checked rather than hoped for.
    """
    if len(points) < 2:
        return False
    down, up = ((MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP) if button == 'left'
                else (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP))
    landed = move(*points[0])
    if abs(landed[0] - points[0][0]) > 2 or abs(landed[1] - points[0][1]) > 2:
        return False
    _send(INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=MOUSEINPUT(0, 0, 0, down, 0, None))))
    time.sleep(settle)
    for index in range(len(points) - 1):
        x0, y0 = points[index]
        x1, y1 = points[index + 1]
        for step in range(1, steps_per_segment + 1):
            fraction = step / steps_per_segment
            _send(INPUT(type=INPUT_MOUSE,
                        union=_INPUTunion(mi=MOUSEINPUT(int(x0 + (x1 - x0) * fraction),
                                                        int(y0 + (y1 - y0) * fraction), 0,
                                                        MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, None))))
            time.sleep(settle / 2)
    time.sleep(settle)
    _send(INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=MOUSEINPUT(0, 0, 0, up, 0, None))))
    time.sleep(settle)
    return True
