"""Have SAI create a document and save it, so there is a reference file this project did not write.

Everything learned about the PSD container so far came from diffing against one file SAI wrote -- and that found a real
defect in one step after several rounds of reasoning had not. The same file cannot answer what a *layered* SAI document
looks like when SAI itself composes it, so this drives SAI to make one.

**SAI takes over a minute to become ready on this machine**, and every earlier attempt failed for that reason rather than
for any fault in the file: the screenshot was taken while the splash was still on screen and read as "the document did
not open". The wait here is therefore generous and the readiness test is a window title, not a sleep.

Nothing is killed with `taskkill`. SAI was left in a state where it would not open anything after being force-killed
repeatedly, and getting out of that state required reinstalling it.

**In SAI 1 a shortcut is usually the start of a sequence, not the whole of one.** Ctrl+N opens a canvas dialog that
still wants its size confirmed, Ctrl+S opens a save dialog that then wants a format, and a driver that sends one
keystroke and reads the result concludes the command failed. `sequence()` exists for that: it sends keys and waits
between them, and it is the shape the rest of this tool is built from.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SAI = os.environ.get('LINEWEIGHT_SAI', r'E:\Apps\SAI-en\sai.exe')
PROCESS = os.environ.get('LINEWEIGHT_SAI_PROCESS', 'sai')


def powershell(script: str) -> str:
    got = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script],
                         capture_output=True, text=True, errors='replace')
    return (got.stdout or '') + (got.stderr or '')


def send_keys(keys: str, wait: float = 1.5) -> None:
    powershell("Add-Type -AssemblyName System.Windows.Forms; "
               "[System.Windows.Forms.SendKeys]::SendWait('%s')" % keys.replace("'", "''"))
    time.sleep(wait)


def sequence(*steps: tuple[str, float]) -> None:
    """A shortcut and whatever the dialog it opened still wants, as one unit.

    Passing a single string of keys would run them together, and SAI 1 would receive the confirmation before it had
    drawn the dialog asking for it. Each step is (keys, seconds to wait afterwards) and the wait is the point.
    """
    for keys, wait in steps:
        send_keys(keys, wait)


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else r'E:\DaShaoHuo\cache\tmp\sai-reference.psd'
    if os.path.exists(target):
        os.remove(target)

    print('starting SAI (it takes about a minute to become ready here)')
    subprocess.run(['cmd', '/c', 'start', '', SAI], capture_output=True)

    ready = False
    for i in range(30):
        time.sleep(5)
        title = powershell("(Get-Process %s -ErrorAction SilentlyContinue | Where-Object "
                           "{ $_.MainWindowHandle -ne 0 } | Select-Object -First 1).MainWindowTitle" % PROCESS).strip()
        if title:
            print('  %3ds  window: %r' % ((i + 1) * 5, title[:60]))
            ready = True
            break
    if not ready:
        print('SAI never showed a window')
        return 1
    time.sleep(20)                                  # let the interface finish settling before it is driven

    print('creating a canvas: Ctrl+N, then Enter for the default size')
    powershell("(New-Object -ComObject WScript.Shell).AppActivate('%s')" % PROCESS)
    time.sleep(1)
    sequence(('^n', 8), ('~', 10))          # the canvas dialog, then confirm its default size

    print('saving: Ctrl+S')
    sequence(('^s', 8))                     # the save dialog needs its path before it will accept anything
    # the save dialog takes a path; type it, then accept
    powershell("Add-Type -AssemblyName System.Windows.Forms; "
               "[System.Windows.Forms.SendKeys]::SendWait('%s')" % target.replace('\\', '\\'))
    time.sleep(2)
    send_keys('~', 10)

    if os.path.exists(target):
        print('SAI wrote %s (%d bytes)' % (target, os.path.getsize(target)))
        return 0
    print('no file was written; SAI may be showing a dialog. Left open for inspection.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
