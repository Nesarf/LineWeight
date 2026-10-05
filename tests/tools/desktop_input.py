"""An input source that does not move the operator's cursor and does not fight the operator's mouse.

Two mechanisms, chosen by what is available rather than by preference:

**A private desktop.** Windows has one cursor per desktop, so a program running on its own desktop receives input from
its own queue. `SendInput` called with that thread's desktop attached moves *that* desktop's cursor, and the operator's
session is untouched. This is the mechanism the system provides for the problem, and it works without a driver; the cost
is that the window is not visible on the normal desktop while it runs there, though it can still be captured.

**Direct injection**, for when the target is on the normal desktop. `SendInput` there moves the visible pointer, so it is
only used when the private desktop is not in play, and it says so.

Both are wrapped so a caller asks for "click at this point in that window" and does not have to know which is in use.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class RECT(ctypes.Structure):
    _fields_ = [('left', wintypes.LONG), ('top', wintypes.LONG),
                ('right', wintypes.LONG), ('bottom', wintypes.LONG)]


def windows_on(desktop_name: str) -> list[tuple[int, str, str]]:
    """Top-level windows of a desktop, by name: (handle, class, title).

    **`EnumDesktopWindows`, not `EnumWindows`.** `EnumWindows` enumerates the calling thread's desktop only, which is
    why a process started on a private desktop appeared to have no windows at all -- the absence was real from where it
    was being looked from, and the search was in the wrong place rather than the process being broken.
    """
    handle = user32.OpenDesktopW(desktop_name, 0, False, 0x0100)   # DESKTOP_SWITCHDESKTOP
    if not handle:
        return []
    found: list[tuple[int, str, str]] = []
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def visit(window, _param):
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(window, title, 512)
        class_name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(window, class_name, 256)
        if title.value or class_name.value != 'IME':
            found.append((window, class_name.value, title.value))
        return True

    user32.EnumDesktopWindows(handle, enum_proc(visit), 0)
    user32.CloseDesktop(handle)
    return found


def window_rect(handle: int) -> tuple[int, int, int, int]:
    rect = RECT()
    user32.GetWindowRect(wintypes.HWND(handle), ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def set_thread_desktop(desktop_name: str, handle: int = 0) -> int:
    """Attach the calling thread to a desktop. Every input call it makes afterwards belongs to that desktop.

    A thread is attached to a desktop for its lifetime, so this is not something to call and undo casually; it is
    exposed so a worker thread can be pinned to the private desktop and leave the main thread alone.
    """
    desktop = user32.OpenDesktopW(desktop_name, 0, False, 0x0100 | 0x0040 | 0x0001)
    if not desktop:
        return 0
    if not user32.SetThreadDesktop(wintypes.HDESK(desktop)):
        return 0
    return desktop
