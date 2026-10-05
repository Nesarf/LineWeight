"""Run an application on its own Windows desktop, so input sent to it cannot reach the operator's session.

The problem this solves: `SendInput` injects into the *session's* input queue, so a virtual pointer built on it moves
the real cursor and fights the real mouse. Windows has one cursor per desktop, and a second desktop is therefore the
mechanism the system already provides for exactly this -- programs running there get their own input queue, their own
cursor and their own foreground window, and the default desktop is untouched.

What this does not give: the application is not visible on the operator's screen. Windows can be captured from another
desktop (the capture functions work on a handle, not on what is displayed), so it stays observable, but it is not
interactive from the default desktop while it runs there.

`CreateDesktop` needs `GENERIC_ALL` on the new desktop, and processes started on it must go through
`CreateProcess` with `STARTUPINFO.lpDesktop` -- the shell cannot be asked to do it.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

DESKTOP_CREATEWINDOW = 0x0002
DESKTOP_ENUMERATE = 0x0040
DESKTOP_WRITEOBJECTS = 0x0080
DESKTOP_READOBJECTS = 0x0001
DESKTOP_SWITCHDESKTOP = 0x0100
DESKTOP_CREATEMENU = 0x0004
DESKTOP_HOOKCONTROL = 0x0008
DESKTOP_JOURNALRECORD = 0x0010
DESKTOP_JOURNALPLAYBACK = 0x0020
GENERIC_ALL = 0x10000000
STARTF_USESHOWWINDOW = 0x0001


class STARTUPINFO(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('lpReserved', wintypes.LPWSTR), ('lpDesktop', wintypes.LPWSTR),
                ('lpTitle', wintypes.LPWSTR), ('dwX', wintypes.DWORD), ('dwY', wintypes.DWORD),
                ('dwXSize', wintypes.DWORD), ('dwYSize', wintypes.DWORD), ('dwXCountChars', wintypes.DWORD),
                ('dwYCountChars', wintypes.DWORD), ('dwFillAttribute', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD), ('wShowWindow', wintypes.WORD), ('cbReserved2', wintypes.WORD),
                ('lpReserved2', ctypes.POINTER(ctypes.c_byte)), ('hStdInput', wintypes.HANDLE),
                ('hStdOutput', wintypes.HANDLE), ('hStdError', wintypes.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [('hProcess', wintypes.HANDLE), ('hThread', wintypes.HANDLE),
                ('dwProcessId', wintypes.DWORD), ('dwThreadId', wintypes.DWORD)]


def create(name: str = 'lineweight-input'):
    """Make a desktop, or return a handle to it if it already exists."""
    handle = user32.CreateDesktopW(name, None, None, 0, GENERIC_ALL, None)
    if not handle:
        handle = user32.OpenDesktopW(name, 0, False, GENERIC_ALL)
    return handle


def launch(desktop: str, executable: str, arguments: str = '') -> int:
    """Start a program on that desktop and return its process id, or 0.

    **`CreateProcess`, not `ShellExecute` or `start`.** The desktop a process runs on is fixed at creation and is named
    in `STARTUPINFO`; there is no way to move a running process between desktops, so the shell helpers -- which always
    create on the interactive desktop -- cannot be used.
    """
    startup = STARTUPINFO()
    startup.cb = ctypes.sizeof(STARTUPINFO)
    startup.lpDesktop = desktop
    startup.dwFlags = STARTF_USESHOWWINDOW
    startup.wShowWindow = 1                                     # SW_SHOWNORMAL
    info = PROCESS_INFORMATION()
    command = '"%s"' % executable if not arguments else '"%s" %s' % (executable, arguments)
    created = kernel32.CreateProcessW(None, ctypes.c_wchar_p(command), None, None, False,
                                      0x00000008 | 0x00000400,  # CREATE_NEW_CONSOLE | CREATE_UNICODE_ENVIRONMENT
                                      None, None, ctypes.byref(startup), ctypes.byref(info))
    if not created:
        return 0
    kernel32.CloseHandle(info.hThread)
    kernel32.CloseHandle(info.hProcess)
    return info.dwProcessId


def switch(handle: int) -> bool:
    """Bring a desktop to the front. This **does** change what the operator sees**, so it is opt-in."""
    return bool(user32.SwitchDesktop(wintypes.HDESK(handle)))


def current_name() -> str:
    """The name of the desktop the calling thread is attached to."""
    handle = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
    return name_of(handle)


def name_of(handle: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    needed = wintypes.DWORD()
    user32.GetUserObjectInformationW(wintypes.HANDLE(handle), 2, buffer, 512, ctypes.byref(needed))
    return buffer.value


def input_desktop() -> str:
    handle = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if not handle:
        return ''
    name = name_of(handle)
    user32.CloseDesktop(handle)
    return name
