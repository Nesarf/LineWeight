"""The trunk as a shape rather than as a thickened spine.

**What was wrong with the trunk.** It was drawn by stroking the pelvis, spine and chest bones with a width each, so it
was a capsule that widened and narrowed -- a board with four numbers. A torso is not a capsule: it is a shape whose
outline is what the eye reads, and **the outline is exactly what the measured body profiles hold**: a width at every
height, from four character meshes, agreeing with each other.

**So the shape is built from the measurement, not from the bones.** For each band between the hip and the neck the
left and right edge sit at half the measured width, taken as the mean of however many profiles are given. The outline
that comes out is a waist narrower than both the hips and the chest -- which the capsule could state as numbers and
could not show as a curve.

    python tools/torso_shape.py --profile model/shape/Zome-body.json --profile model/shape/Cian_VRM-body.json
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, r'E:\lineweight')
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from lineweight import core, project

def region_of(points):
    """A `Region` from a polygon that is already closed -- points and a path, which is all a fill mark needs.

    **`add_fill` takes a Region, not a list**, and handing it one raised `'list' object has no attribute 'points'`.
    """
    d = 'M ' + ' L '.join('%.2f %.2f' % (x, y) for x, y in points) + ' Z'
    return core.Region(points=[tuple(p) for p in points], d=d)


#: The trunk's own span, as a fraction of the figure's height above the feet. **Taken from the joint table, not from
#: the profile**: the profile does not know where a hip ends and a thigh begins, and the table does.
#:
#: **The top is 0.706 and not 0.775, because the arms arrive first.** The measured width jumps from 0.115 at 0.690 to
#: 0.581 at 0.732 -- that is not shoulders, that is an arm held out at some height between the two, and a trunk that
#: claims it would come out half again as wide as the body. The shoulders are the clavicle's job in the drawing; this
#: shape stops where the body does.
TRUNK_BOTTOM = 0.433
TRUNK_TOP = 0.690


def smooth(samples, window=7):
    """A moving average over the sampled widths.

    **Without it the outline is the profile's own noise.** Band widths run 0.091, 0.115, 0.099, 0.108 as the bands
    cross the waist and the chest, and a shape drawn straight from them has a notch at every band -- the eye reads it as
    a garment seam, not as a body. A torso is smooth at this scale, so the measurement is smoothed to that scale rather
    than the shape being invented.
    """
    out = []
    n = len(samples)
    for i in range(n):
        lo = max(0, i - window // 2)
        hi = min(n, i + window // 2 + 1)
        chunk = samples[lo:hi]
        out.append((sum(s[0] for s in chunk) / len(chunk), sum(s[1] for s in chunk) / len(chunk)))
    return out

CANVAS_W, CANVAS_H = 600.0, 800.0
MARGIN = 40.0


def average_profile(paths):
    """Width at each height, averaged over the given profiles. **Averaged because one model is not a rule.**"""
    grids = []
    for path in paths:
        data = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
        rows = [(r['y'], r['w']) for r in data['rows']]
        grids.append(rows)
    samples = []
    steps = 48
    for i in range(steps + 1):
        y = TRUNK_BOTTOM + (TRUNK_TOP - TRUNK_BOTTOM) * i / float(steps)
        widths = []
        for rows in grids:
            near = min(rows, key=lambda r: abs(r[0] - y))
            widths.append(near[1])
        samples.append((y, sum(widths) / float(len(widths))))
    return smooth(samples)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', action='append', required=True)
    ap.add_argument('--out', default=r'E:\DaShaoHuo\cache\torso.json')
    ap.add_argument('--png', default=r'E:\DaShaoHuo\cache\torso.png')
    ap.add_argument('--render', action='store_true')
    args = ap.parse_args()

    samples = average_profile(args.profile)
    print('  %d profiles, trunk %.3f..%.3f of the height' % (len(args.profile), TRUNK_BOTTOM, TRUNK_TOP))
    for i, (y, w) in enumerate(samples):
        if i % 6 == 0:
            print('    y %.3f   width %.3f' % (y, w))

    scale = (CANVAS_H - 2 * MARGIN) / 1.0
    cx = CANVAS_W / 2

    def place(y, w):
        # y is height above the feet; the page is measured down from the top, and the whole figure is one unit tall.
        return (cx + w * scale / 2.0, CANVAS_H - MARGIN - y * scale)

    left = [place(y, -w) for y, w in samples]
    right = [place(y, w) for y, w in samples]
    shape = left + right[::-1]
    shape.append(shape[0])

    proj = project.Project(width=int(CANVAS_W), height=int(CANVAS_H), title='trunk from the profile')
    shape_pts = [(p[0], p[1]) for p in shape]
    proj.add_fill(region_of(shape_pts), stage='colour', colour='#d6baa8',
                  note='trunk from the measured profile')
    outline = core.stroke_record(shape_pts, 'fine', seed=8, resolution=8,
                                 width_profile=[2.4] * (8 * (len(shape_pts) - 1) + 1))
    proj.add_stroke(outline, stage='line', layer='torso', note='trunk outline')
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    project.save_project(proj, str(out))
    print('  written to %s' % out)
    if args.render:
        import subprocess
        subprocess.run([sys.executable, '-m', 'lineweight', '--render', str(out), '--out', args.png],
                       capture_output=True, text=True, cwd=r'E:\lineweight')
        print('  rendered to %s' % args.png)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
