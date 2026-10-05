"""One end-to-end run per destination, so the claim "it works" is a command rather than a memory.

Each destination is checked by something produced by the *other* side, not by this project's own belief about what it
sent:

* Illustrator -- the SVG Illustrator itself exports is read back, and the layers, fills and opacities are counted.
* Animate -- the document is opened and the drawing's ink is measured in a stage rectangle fixed on a known-empty
  document, so a shape that drew and a shape that did not are distinguishable.
* SAI -- the PSD's own bytes are walked back out, including decompressing the merged channels.

SAI is the one that cannot be completed here: SAI has no scripting interface and no reliable signal that it has
loaded a file, so the check stops at the format and says so.
"""
import os
import subprocess
import sys
import time

# **Paths come from the environment, not from whoever wrote this.** The applications' install locations and the working
# directory differ per machine, and a repository that hard-codes one person's disk layout is a repository that only
# works on one disk. The defaults below are where an ordinary Windows install puts them.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lineweight import Appearance, Document, Path                    # noqa: E402
from lineweight.psd import layers_from_document, read_psd_header, save_psd   # noqa: E402
from lineweight.ref import decode_png                                # noqa: E402
from lineweight.xfl import write_xfl                                 # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from windowing import capture, ink_fraction, stage_rect               # noqa: E402

WORK = os.environ.get('LW_VERIFY_DIR', os.path.join(os.environ.get('TEMP', '.'), 'lineweight-verify'))
ANIMATE = os.environ.get('LINEWEIGHT_ANIMATE',
                         r'C:\Program Files\Adobe\Adobe Animate 2024\Animate.exe')
ILLUSTRATOR = os.environ.get('LINEWEIGHT_ILLUSTRATOR',
                             r'C:\Program Files\Adobe\Adobe Illustrator 2024\Support Files\Contents\Windows\Illustrator.exe')


def drawing() -> Document:
    from lineweight.core import demo_document
    return demo_document()


def check_psd() -> dict:
    """Write a PSD and check it in the three ways that are not the same thing.

    **One boolean beside the other destinations was misleading.** This used to return `True` for "the PSD is fine" and
    sit next to Illustrator and Animate results that *did* mean the application accepted the output -- so an automated
    reader could reasonably take `psd: True` to mean the SAI destination works, when it means only that this project's
    writer and this project's reader agree. That is exactly the pair that shared four separate mistakes undetected, so
    the distinction is not pedantry; it is the difference between a check and a coincidence.

    The three layers, which are answers to different questions:

    * `structure`    -- the file's own bytes describe what was written (this project's reader; weakest)
    * `independent`  -- a parser that is not this project reads it (`psd-tools`, when installed; skips when not)
    * `application`  -- SAI displays the layers (not verifiable from here; always reported as unknown)
    """
    doc = drawing()
    layers = layers_from_document(doc, scale=1.0)
    path = os.path.join(WORK, 'verify.psd')
    save_psd(layers, path)
    head = read_psd_header(path)
    structure = bool(head['layers'] == len(layers)
                     and head['names'] == [layer.name for layer in layers]
                     and head['merged_decoded_ok'])
    print('PSD structure  : %s  (%d layers %s, %d bytes, merged channels decode to full size: %s)'
          % ('PASS' if structure else 'FAIL', head['layers'], head['names'], head['bytes'],
             head['merged_decoded_ok']))

    independent = None
    try:
        from psd_tools import PSDImage
        try:
            read = PSDImage.open(path)
            seen = [layer.name for layer in read]
            independent = seen == [layer.name for layer in layers]
            print('PSD independent: %s  (psd-tools reads %d layers: %s)'
                  % ('PASS' if independent else 'FAIL', len(seen), seen))
        except Exception as exc:                        # noqa: BLE001 - the failure is the result
            independent = False
            print('PSD independent: FAIL  (psd-tools refused the file: %s)' % type(exc).__name__)
    except ImportError:
        print('PSD independent: SKIPPED  (psd-tools is not installed; this is the check that matters)')

    print("PSD layer pixels: UNKNOWN  (SAI showing the layer is not verifiable from here -- see PSD-REPORT.md)")
    return {'structure': structure, 'independent': independent, 'application': None}


def check_xfl() -> bool:
    """Write an XFL, open it through its marker, and measure the drawing on the stage."""
    folder = os.path.join(WORK, 'verify.xfl')
    doc = drawing()
    write_xfl(doc, folder)
    marker = os.path.join(folder, 'verify.xfl')
    if not os.path.exists(marker):
        print('XFL      : FAILED, no marker file at %s' % marker)
        return False


    subprocess.run(['taskkill', '/F', '/IM', 'Animate.exe'], capture_output=True)
    for _ in range(60):
        out = subprocess.run(['tasklist', '/fi', 'IMAGENAME eq Animate.exe', '/fo', 'csv', '/nh'],
                             capture_output=True, text=True, errors='replace')
        if 'Animate.exe' not in (out.stdout or ''):
            break
        time.sleep(0.5)
    time.sleep(3)
    subprocess.Popen(['cmd', '/c', 'start', '', ANIMATE, marker])
    title = ''
    deadline = time.time() + 55
    while time.time() < deadline:
        got = subprocess.run(['powershell', '-NoProfile', '-Command',
                              "(Get-Process Animate -ErrorAction SilentlyContinue | Where-Object "
                              "{ $_.MainWindowHandle -ne 0 } | Select-Object -First 1).MainWindowTitle"],
                             capture_output=True, text=True, errors='replace')
        title = (got.stdout or '').strip()
        if title and title.lower() not in ('adobe animate 2024', 'animate', ''):
            break
        time.sleep(1.0)
    time.sleep(10)

    from windowing import capture
    png = os.path.join(WORK, 'verify-animate.png')
    ok = False
    ink = -1.0
    if capture(png):
        # the stage rectangle is fixed on this same document rendered with no shape, so it cannot move with the ink
        rect = stage_rect(png)
        ink = ink_fraction(png, rect) if rect else -1.0
        ok = bool(title) and title.lower() not in ('adobe animate 2024', 'animate', '') and ink > 0.05
    subprocess.run(['taskkill', '/F', '/IM', 'Animate.exe'], capture_output=True)
    print('XFL      : opened as %r, ink on the stage %s -> %s'
          % (title or '(no document)', ink, 'the drawing is visible' if ok else 'NOT VISIBLE'))
    return ok


def check_illustrator() -> bool:
    """Write the demo drawing as a script, run Illustrator, and read back the SVG Illustrator exported."""
    from lineweight.app import jsx_document
    from lineweight.run import run_jsx

    script = os.path.join(WORK, 'verify.jsx')
    svg = os.path.join(WORK, 'verify-illustrator.svg')
    report = os.path.join(WORK, 'verify-report.txt')
    sentinel = os.path.join(WORK, 'verify.done')
    for stale in (svg, report, sentinel):
        if os.path.exists(stale):
            os.remove(stale)
    doc = drawing()
    result = run_jsx(jsx_document(doc, export_svg=svg, report=report, done=sentinel),
                     script, report_path=report, sentinel_path=sentinel, timeout=200)
    print('Illustrator: %s' % result.describe())
    if result.report:
        for line in result.report.strip().splitlines():
            print('             %s' % line)
    if not (result.ok and os.path.exists(svg)):
        return False
    with open(svg, encoding='iso-8859-1') as handle:
        body = handle.read()
    import re
    groups = re.findall(r'<g id="([^"]*)"', body)
    shapes = re.findall(r'<(polygon|path|line)\b', body)
    opacities = re.findall(r'opacity:([0-9.]+)', body)
    print('             exported %d shapes in groups %s, opacities %s'
          % (len(shapes), groups, opacities[:5]))
    return len(shapes) >= 5 and 'LINE' in groups and 'DETAIL' in groups


def main() -> int:
    os.makedirs(WORK, exist_ok=True)
    results = {}
    results['psd'] = check_psd()
    results['xfl'] = check_xfl()
    results['illustrator'] = check_illustrator()
    print()
    for name, ok in results.items():
        print('%-12s %s' % (name, 'ok' if ok else 'FAILED'))
    # **A destination's exit status must not rest on a check that cannot fail.** The PSD entry is a dict of three
    # separate answers because they are three separate questions, and only the first two can be decided here; treating
    # "unknown" as either pass or fail would be a claim this tool cannot support either way.
    psd = results.get('psd', {})
    failing = [k for k, v in results.items() if k != 'psd' and not v]
    if not psd.get('structure'):
        failing.append('psd.structure')
    if psd.get('independent') is False:
        failing.append('psd.independent')
    if psd.get('application') is None:
        print('note: psd.application is UNKNOWN by design -- SAI showing the layer cannot be checked from here')
    return 1 if failing else 0


if __name__ == '__main__':
    raise SystemExit(main())
