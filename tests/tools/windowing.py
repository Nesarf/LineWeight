"""Take a screenshot of an application window and measure the ink inside a fixed rectangle.

Extracted because three tools needed it and each had grown its own copy, along with its own escaping bugs. The part
worth sharing is not the screenshot -- it is the **calibration**: the stage rectangle is established once from a
document known to be empty and then never recomputed, because a region that is found by looking for brightness shrinks
as the drawing fills it, and an instrument that adjusts itself to the thing being measured reports whatever it likes.
Two "the shape does not draw" conclusions in this project were artefacts of exactly that.

Requires PowerShell and .NET drawing, which is what Windows has. Nothing here is imported by the library itself.
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lineweight.ref import decode_png                    # noqa: E402

SHOT_PS = r'''
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;using System.Runtime.InteropServices;
public class Cap {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out R r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  [StructLayout(LayoutKind.Sequential)] public struct R { public int L,T,Rt,B; }
}
"@
$p = Get-Process -Id ([int]$env:DSH_CAP_PID) -ErrorAction SilentlyContinue
if (-not $p) { exit 1 }
$h = $p.MainWindowHandle
if ($h -eq 0) { exit 2 }
$r = New-Object Cap+R
[Cap]::GetWindowRect($h, [ref]$r) | Out-Null
$w = $r.Rt - $r.L; $ht = $r.B - $r.T
if ($w -lt 200) { exit 3 }
$b = New-Object System.Drawing.Bitmap $w, $ht
$g = [System.Drawing.Graphics]::FromImage($b)
$dc = $g.GetHdc()
[Cap]::PrintWindow($h, $dc, 2) | Out-Null
$g.ReleaseHdc($dc)
$b.Save($env:DSH_CAP_OUT, [System.Drawing.Imaging.ImageFormat]::Png)
'''

_SCRIPT = None


def _script_path() -> str:
    global _SCRIPT
    if _SCRIPT is None:
        path = os.path.join(os.environ.get('TEMP', '.'), 'dsh_capture.ps1')
        with open(path, 'w', encoding='ascii', newline='\r\n') as handle:
            handle.write(SHOT_PS)
        _SCRIPT = path
    return _SCRIPT


def window_title(process_name: str) -> str:
    got = subprocess.run(['powershell', '-NoProfile', '-Command',
                          "(Get-Process %s -ErrorAction SilentlyContinue | Where-Object "
                          "{ $_.MainWindowHandle -ne 0 } | Select-Object -First 1).MainWindowTitle" % process_name],
                         capture_output=True, text=True, errors='replace')
    return (got.stdout or '').strip()


def process_id(process_name: str) -> int:
    got = subprocess.run(['powershell', '-NoProfile', '-Command',
                          "(Get-Process %s -ErrorAction SilentlyContinue | Where-Object "
                          "{ $_.MainWindowHandle -ne 0 } | Select-Object -First 1).Id" % process_name],
                         capture_output=True, text=True, errors='replace')
    try:
        return int((got.stdout or '0').strip() or 0)
    except ValueError:
        return 0


def capture(process_name: str, png: str) -> bool:
    """Screenshot the main window of a running process. The path goes through the environment, not through quoting."""
    pid = process_id(process_name)
    if not pid:
        return False
    env = dict(os.environ, DSH_CAP_PID=str(pid), DSH_CAP_OUT=png)
    subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', _script_path()],
                   capture_output=True, text=True, env=env)
    return os.path.exists(png)


def stage_rect(png: str) -> tuple[int, int, int, int] | None:
    """The document rectangle, from a screenshot of a document known to be empty."""
    image = decode_png(png)
    rows = [y for y in range(0, image.height, 2)
            if sum(1 for x in range(0, image.width, 8) if image.pixels[y * image.width + x] > 235) > 40]
    if not rows:
        return None
    y0, y1 = min(rows) + 6, max(rows) - 6
    mid = (y0 + y1) // 2
    xs = [x for x in range(image.width) if image.pixels[mid * image.width + x] > 235]
    if not xs:
        return None
    return min(xs) + 6, y0, max(xs) - 6, y1


def ink_fraction(png: str, rect: tuple[int, int, int, int], threshold: int = 190) -> float:
    """The share of a fixed rectangle that is dark. The rectangle never moves, which is the whole point."""
    image = decode_png(png)
    x0, y0, x1, y1 = rect
    x1 = min(x1, image.width)
    y1 = min(y1, image.height)
    dark = total = 0
    for y in range(y0, y1, 2):
        base = y * image.width
        for x in range(x0, x1, 2):
            total += 1
            if image.pixels[base + x] < threshold:
                dark += 1
    return round(dark / total, 4) if total else -1.0
