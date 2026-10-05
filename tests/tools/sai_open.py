"""Open a PSD in SAI and capture its layer panel.

SAI has no scripting interface and its window title does not change when a document loads, so the only evidence
available is what is on screen. The layer panel sits on the left below the navigator; the canvas fills the rest. A file
with layers shows entries there, and a file SAI reads as flat shows an empty grey box -- which is exactly the difference
this is here to settle.

**The crop region is fixed rather than searched for.** A region located by looking for a large light area moves as the
panel fills, so it would find what it expects; two wrong conclusions in this project came from an instrument that
adjusted itself to the thing it was measuring.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from windowing import capture, window_title                       # noqa: E402

SAI = os.environ.get('LINEWEIGHT_SAI', r'E:\Apps\SAI-en\sai.exe')
# **The process name is not derivable from the executable's.** SAI 2 runs as `sai2`, SAI 1 as `sai`, and
# this machine's install changed from one to the other; the name is a parameter for the same reason the
# path is.
PROCESS = os.environ.get('LINEWEIGHT_SAI_PROCESS', 'sai')


def window_rect(process: str) -> tuple[int, int, int, int] | None:
    got = subprocess.run(['powershell', '-NoProfile', '-Command',
                          "$p = Get-Process %s -ErrorAction SilentlyContinue | Where-Object "
                          "{ $_.MainWindowHandle -ne 0 } | Select-Object -First 1; if ($p) { "
                          "Add-Type -AssemblyName System.Windows.Forms; "
                          "$r = [System.Windows.Forms.Screen]::FromHandle($p.MainWindowHandle).Bounds; "
                          "'{0},{1}' -f $r.Width, $r.Height }" % process],
                         capture_output=True, text=True, errors='replace')
    text = (got.stdout or '').strip()
    if not text or ',' not in text:
        return None
    width, height = (int(v) for v in text.split(','))
    return 0, 0, width, height


def main() -> int:
    psd = sys.argv[1] if len(sys.argv) > 1 else r'E:\DaShaoHuo\downloads\lineweight-test.psd'
    if not os.path.exists(psd):
        print('no such file: %s' % psd)
        return 2

    for line in subprocess.run(['tasklist', '/FI', 'IMAGENAME eq %s.exe' % PROCESS, '/FO', 'CSV', '/NH'],
                               capture_output=True, text=True, errors='replace').stdout.splitlines():
        if PROCESS in line.lower():
            pid = line.split(',')[1].strip('"')
            subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
    import time
    time.sleep(3)

    print('opening %s' % psd)
    subprocess.run(['cmd', '/c', 'start', '', SAI, psd], capture_output=True)
    time.sleep(35)

    print('window title: %r' % window_title(PROCESS))
    shot = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sai-shot.png')
    if not capture(PROCESS, shot):
        print('could not capture the SAI window (is it still starting?)')
        return 1
    print('captured %s' % shot)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
