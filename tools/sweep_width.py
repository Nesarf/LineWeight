"""How the taper ratio and the ink fraction respond to line width, swept rather than guessed.

**The two targets may pull against each other, and that is what this measures.** Against the pale band of the linework
reference, the drawing is **25 per cent low on taper** (0.3426 against 0.4543) and **69 per cent high on ink** (0.0588
against 0.0348). Taper low means the thin fifth of the runs is too thin against their mean; ink high means too much of
the page is covered. **Thinning every line lowers the ink and, on the evidence already gathered, also lowers the
taper** -- an earlier run at a 0.55 scale gave a taper of 0.2814 against 0.3426 at full width, so the two move
together and no single scale can satisfy both.

So the scale is swept and both quantities are reported at each point, which turns "adjust the line widths" into a
curve with a visible trade rather than a value to guess at.

    python sweep_width.py
"""
import importlib.util
import pathlib
import subprocess
import sys

sys.path.insert(0, r'E:\lineweight')
from lineweight import ref

REPO = pathlib.Path(r'E:\lineweight')
TOOL = REPO / 'tools' / 'cel_drawing.py'
TMP = pathlib.Path(r'E:\DaShaoHuo\cache\tmp')
PROJECT = TMP / 'sweep-drawing.json'

#: The pale band of the reference, which is what a line drawing is compared against. Both figures come from
#: `linework_bands` in `tests/data/linework_summary.json`.
TARGET_TAPER = 0.4543
TARGET_INK = 0.0348


def run_at(scale):
    """Render the drawing at one width scale and measure it."""
    text = TOOL.read_text(encoding='utf-8')
    import re
    text = re.sub(r'^THINNER = [0-9.]+', 'THINNER = %s' % scale, text, flags=re.M)
    TOOL.write_text(text, encoding='utf-8')
    subprocess.run([sys.executable, str(TOOL), str(PROJECT)], capture_output=True, text=True, cwd=str(REPO))
    out = TMP / ('sweep-%s.png' % str(scale).replace('.', '_'))
    subprocess.run([sys.executable, '-m', 'lineweight', '--render', str(PROJECT), '--out', str(out)],
                   capture_output=True, text=True, cwd=str(REPO))
    if not out.exists():
        return None
    m = ref.measure(str(out))
    return m


def main():
    original = TOOL.read_text(encoding='utf-8')
    print('  %-8s %10s %10s %10s %10s %12s' % ('scale', 'ink', 'taper', 'p90/med', 'wmed', 'runs in win'))
    print('  %-8s %10.4f %10.4f %10.3f' % ('target', TARGET_INK, TARGET_TAPER, 3.0))
    rows = []
    try:
        for scale in (0.6, 0.8, 1.0, 1.2, 1.5, 2.0):
            m = run_at(scale)
            if m is None:
                print('  %-8s failed' % scale)
                continue
            kept = 100.0 * m.line_runs / m.runs if m.runs else 0.0
            rows.append((scale, m))
            print('  %-8.1f %10.4f %10.4f %10.3f %10.1f %11.1f%%'
                  % (scale, m.ink_ratio, m.taper_ratio,
                     m.width_p90 / m.width_median if m.width_median else 0, m.width_median, kept))
    finally:
        TOOL.write_text(original, encoding='utf-8')
        print()
        print('  the tool is restored to the width it had')

    if not rows:
        return 1
    print()
    # **Which point is best is not a judgement this can make**, because the two targets disagree about direction. What
    # it can do is say which point is closest to both at once on a scale-free measure, and by how much each misses.
    best = None
    for scale, m in rows:
        d_taper = abs(m.taper_ratio - TARGET_TAPER) / TARGET_TAPER
        d_ink = abs(m.ink_ratio - TARGET_INK) / TARGET_INK
        score = max(d_taper, d_ink)
        if best is None or score < best[0]:
            best = (score, scale, m, d_taper, d_ink)
    score, scale, m, d_taper, d_ink = best
    print('  closest to both targets at once: scale %.1f' % scale)
    print('    taper %.4f against %.4f -> %.1f%% off' % (m.taper_ratio, TARGET_TAPER, 100 * d_taper))
    print('    ink   %.4f against %.4f -> %.1f%% off' % (m.ink_ratio, TARGET_INK, 100 * d_ink))
    print()
    print('  ** and the sweep shows whether they can be met together. If every row misses one of them badly, then')
    print('     line width is not the variable that fixes this drawing, and something else about it is wrong. **')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
