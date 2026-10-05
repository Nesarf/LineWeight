"""Send keystrokes to a window that will not come to the foreground on its own.

`AppActivate` and `SetForegroundWindow` both declined: the foreground window stayed on whatever was there before, so
every keystroke this session sent went to the wrong application and the tool reported failure for the wrong reason. The
culprit is the foreground lock -- a process that is not already the foreground owner cannot take it, and being an
administrator does not exempt it from that rule.

The way through is `AttachThreadInput`: attach the calling thread's input queue to the thread that owns the foreground
window, which makes the two share a foreground state, then set the foreground and detach. The window keeps the focus
after the detach, because the lock is checked at the moment of the call rather than continuously.

Written as a module rather than inline PowerShell because the quoting had begun to cost more than the automation.
"""
import ctypes
import ctypes.wintypes as wintypes
import subprocess
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def _title(handle: int) -> str:
    buffer = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(wintypes.HWND(handle), buffer, 512)
    return buffer.value


def _class_name(handle: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(wintypes.HWND(handle), buffer, 256)
    return buffer.value


def windows_of(process_name: str) -> list[tuple[int, str, str, bool]]:
    """Every top-level window owned by a process: (handle, class, title, visible)."""
    got = subprocess.run(['powershell', '-NoProfile', '-Command',
                          "(Get-Process %s -ErrorAction SilentlyContinue | Select-Object -First 1).Id" % process_name],
                         capture_output=True, text=True, errors='replace')
    try:
        pid = int((got.stdout or '0').strip())
    except ValueError:
        return []
    if not pid:
        return []
    found: list[tuple[int, str, str, bool]] = []
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def visit(handle, _param):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        if owner.value == pid:
            found.append((handle, _class_name(handle), _title(handle), bool(user32.IsWindowVisible(handle))))
        return True

    user32.EnumWindows(enum_proc(visit), 0)
    return found


def foreground_title() -> str:
    return _title(user32.GetForegroundWindow())


def force_foreground(handle: int) -> bool:
    """Take the foreground lock by attaching to whoever holds it, set the target, then detach."""
    target_thread = user32.GetWindowThreadProcessId(wintypes.HWND(handle), None)
    current_thread = kernel32.GetCurrentThreadId()
    foreground = user32.GetForegroundWindow()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0

    attached = []
    for thread in (foreground_thread, target_thread):
        if thread and thread != current_thread and thread not in attached:
            if user32.AttachThreadInput(current_thread, thread, True):
                attached.append(thread)
    try:
        user32.ShowWindow(wintypes.HWND(handle), 9)          # SW_RESTORE
        user32.BringWindowToTop(wintypes.HWND(handle))
        user32.SetForegroundWindow(wintypes.HWND(handle))
        user32.SetFocus(wintypes.HWND(handle))
    finally:
        for thread in attached:
            user32.AttachThreadInput(current_thread, thread, False)

    time.sleep(0.6)
    return user32.GetForegroundWindow() == handle


def send(keys: str, wait: float = 1.2) -> None:
    """SendKeys into whatever currently has the focus. The caller is responsible for the focus being right."""
    escaped = keys.replace("'", "''")
    subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "[System.Windows.Forms.SendKeys]::SendWait('%s')" % escaped],
                   capture_output=True, text=True)
    time.sleep(wait)


def type_into(handle: int, keys: str, wait: float = 1.2) -> bool:
    """Bring a window to the front and type into it **while the input queues are still attached**.

    The earlier version set the foreground, detached, and then sent the keys -- and the window had lost the foreground
    by the time they arrived, so the keystrokes went to whatever else was in front and the tool blamed the
    application. Holding the attachment open across the whole operation is the difference: with the queues joined, the
    focus cannot move out from under the keys between the two steps.
    """
    target_thread = user32.GetWindowThreadProcessId(wintypes.HWND(handle), None)
    current_thread = kernel32.GetCurrentThreadId()
    foreground = user32.GetForegroundWindow()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0

    attached = []
    for thread in (foreground_thread, target_thread):
        if thread and thread != current_thread and thread not in attached:
            if user32.AttachThreadInput(current_thread, thread, True):
                attached.append(thread)
    try:
        user32.ShowWindow(wintypes.HWND(handle), 9)
        user32.BringWindowToTop(wintypes.HWND(handle))
        user32.SetForegroundWindow(wintypes.HWND(handle))
        user32.SetFocus(wintypes.HWND(handle))
        time.sleep(0.4)
        ok = user32.GetForegroundWindow() == handle
        if ok:
            send(keys, wait)
    finally:
        time.sleep(0.3)
        for thread in attached:
            user32.AttachThreadInput(current_thread, thread, False)
    return ok


def post_key(handle: int, virtual_key: int, extended: bool = False) -> None:
    """A message straight to the window, for when the focus cannot be had at all.

    Less faithful than typing -- an application that reads the keyboard through its own message loop rather than the
    queue may ignore it -- but it does not depend on the foreground lock.
    """
    WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
    scan = user32.MapVirtualKeyW(virtual_key, 0)
    flags = 1 if extended else 0
    user32.PostMessageW(wintypes.HWND(handle), WM_KEYDOWN, virtual_key, (scan << 16) | flags)
    user32.PostMessageW(wintypes.HWND(handle), WM_KEYUP, virtual_key, (scan << 16) | flags | (1 << 30) | (1 << 31))
