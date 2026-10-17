"""Draw the strokes a hand practises before it draws anything, and measure them.

**Why this before more content.** The drawing has been built from shapes outward: a bone gives a shape, and the line is
what that shape's boundary turns out to be. **A line drawing goes the other way** -- a line is drawn, and the shape is
what the line encloses. So the pen itself has never been practised, only inherited from geometry. This draws the five
marks a hand does on the first page -- a straight line, a circle, an S, a taper, and a line that changes direction --
and measures each one against what the reference library knows about real lines.

**What is measured, and why each one is a fault when it goes wrong:**

* **the width along the stroke** -- a line that is the same width everywhere is a computer line; a drawn one thins at
  its ends and swells where the hand pressed.
* **the wander off the intended path** -- a hand wobbles; a wobble that is too tidy reads as a machine, and one that is
  too large reads as a mistake. The reference's own roughness is the scale.
* **the gap at the ends** -- whether a stroke starts and stops where it was asked to, since every seam in the drawing
  is such an end.
* **the ink per unit length against the nominal width** -- if those disagree, the width being asked for is not the
  width being laid down, and every width measurement on this drawing is measuring something else.

    python line_practice.py
    python line_practice.py --out E:/DaShaoHuo/cache/tmp/practice.png
"""
import argparse
import json
import math
import pathlib
import statistics
import subprocess
import sys

sys.path.insert(0, r'E:\lineweight')
import numpy as np
from PIL import Image
from scipy import ndimage

from lineweight import core, project as project_mod

TMP = pathlib.Path(r'E:\DaShaoHuo\cache\tmp')


def sag(points, amplitude, count):
    """Points along a straight run, pushed sideways by a sine -- the smallest description of a hand's wobble."""
    out = []
    for i in range(count):
        t = i / float(count - 1)
        for k in range(len(points) - 1):
            if t <= (k + 1) / float(len(points) - 1) + 1e-9:
                a, b = points[k], points[k + 1]
                u = (t - k / float(len(points) - 1)) * (len(points) - 1)
                x = a[0] + (b[0] - a[0]) * u
                y = a[1] + (b[1] - a[1]) * u
                dx, dy = b[0] - a[0], b[1] - a[1]
                L = math.hypot(dx, dy) or 1.0
                w = amplitude * math.sin(math.pi * t)
                out.append((x - dy / L * w, y + dx / L * w))
                break
    return out


def circle(cx, cy, r, count=97):
    return [(cx + r * math.cos(i / (count - 1.0) * 2 * math.pi),
             cy + r * math.sin(i / (count - 1.0) * 2 * math.pi)) for i in range(count)]


def s_curve(cx, cy, r, count=97):
    return [(cx + r * 0.7 * math.sin(i / (count - 1.0) * 2 * math.pi),
             cy - r * math.cos(i / (count - 1.0) * 2 * math.pi)) for i in range(count)]


def measure_stroke(lum, centre, threshold=200):
    """Width across the stroke at each sample, and how far the ink wanders from the centreline."""
    widths, offsets = [], []
    for i in range(1, len(centre) - 1):
        x0, y0 = centre[i - 1]
        x1, y1 = centre[i + 1]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        total, lo, hi = 0, 0, 0
        for direction in (1, -1):
            for step in range(1, 60):
                x = int(round(centre[i][0] + nx * step * direction))
                y = int(round(centre[i][1] + ny * step * direction))
                if not (0 <= x < lum.shape[1] and 0 <= y < lum.shape[0]):
                    break
                if lum[y, x] >= threshold:
                    break
                total += 1
                if direction > 0:
                    hi = step
                else:
                    lo = step
        widths.append(total + 1)
        if lo + hi:
            offsets.append(abs(hi - lo) / 2.0)
    return widths, offsets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(TMP / 'practice.png'))
    args = ap.parse_args()

    proj = project_mod.Project(width=800, height=600, title='line practice')

    marks = []
    #: **A straight run, with the wobble a hand has.** `sag` pushes the line sideways by a sine whose size is the
    #: amplitude, so the wobble can be turned up and down as one number instead of by editing points.
    marks.append(('straight', sag([(120, 120), (520, 120)], 2.5, 81), [3.0] * 81))
    #: **A circle**, closed back on itself, which is the mark that shows whether a pen can join its own start.
    marks.append(('circle', circle(300, 320, 110), [3.0] * 97))
    #: **An S**, the mark that shows whether a pen can change direction without a corner.
    marks.append(('s-curve', s_curve(620, 320, 100), [3.0] * 97))
    #: **A taper**: a straight run whose width goes from nothing to wide to nothing, which is what a real stroke does.
    marks.append(('taper', sag([(120, 500), (520, 500)], 2.0, 81),
                  [0.4 + 5.6 * math.sin(math.pi * i / 80.0) for i in range(81)]))
    #: **A corner**: two runs meeting at a right angle, to see whether the join is a join or a notch.
    marks.append(('corner', sag([(620, 480), (720, 480), (720, 580)], 1.5, 81), [3.0] * 81))

    for name, pts, prof in marks:
        if len(prof) != 16 * (len(pts) - 1) + 1:
            prof = [prof[min(len(prof) - 1, int(i * len(prof) / (16.0 * (len(pts) - 1) + 1)))]
                    for i in range(16 * (len(pts) - 1) + 1)]
        rec = core.stroke_record(pts, 'ink', seed=abs(hash(name)) % 9973, resolution=16, width_profile=prof)
        proj.add_stroke(rec, stage='line', layer='practice', note=name)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    project_mod.save_project(proj, str(out.with_suffix('.json')))
    subprocess.run([sys.executable, '-m', 'lineweight', '--render', str(out.with_suffix('.json')),
                    '--out', str(out)], capture_output=True, text=True, cwd=r'E:\lineweight')

    lum = np.array(Image.open(out).convert('L'))
    print('  drew %d practice strokes to %s' % (len(marks), out))
    print()
    print('  %-10s %8s %8s %8s %10s %10s' % ('stroke', 'w min', 'w med', 'w max', 'spread', 'laid/want'))
    for name, pts, prof in marks:
        widths, offsets = measure_stroke(lum, pts)
        if not widths:
            continue
        # **The profile as the renderer received it, which is the expanded one and not the short list above it.**
        # The first version averaged the short list against a laid width that had already been expanded, and the
        # mismatch was caught by `want` not equalling `len(prof)` -- the guard was there and it reported a zero rather
        # than the number, which is the quieter kind of failure.
        want = 16 * (len(pts) - 1) + 1
        expanded = prof if len(prof) == want else [
            prof[min(len(prof) - 1, int(i * len(prof) / float(want)))] for i in range(want)]
        nominal = statistics.mean(expanded)
        laid = statistics.mean(widths)
        print('  %-10s %8d %8d %8d %10d %10.2f' % (
            name, min(widths), int(statistics.median(widths)), max(widths),
            max(widths) - min(widths), laid / max(1e-9, nominal)))
    print()
    print('  ** `spread` is max minus min, and it is the number that matters for a pen**: a stroke whose widest point')
    print('     is many times its narrowest is either a taper on purpose or a fault, and only the profile says which.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
