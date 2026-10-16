"""Add a detail layer -- hair strands and cloth folds -- and see what the criterion does.

**Why a separate layer rather than an edit to the drawing tool.** The main tool decides the figure; detail is
something added on top of it, and keeping it separate means it can be turned off, measured on its own, or replaced
without touching the thing that draws the body. It also means the criterion can be read for the figure and for the
figure plus detail, which is the comparison that says whether detail is what the number was asking for.

**Where the strands come from, and why not from a list.** The criterion says the drawing has too few separate pieces:
`blobs / sqrt(ink area)` is 0.0066 against a linework median of 0.2202, and the figure is **one** connected blob. So
detail has to be many small marks rather than a few large ones -- and a hand-written list of forty strand coordinates
would be forty more invented numbers in a project whose every hand-written number has cost something.

They are derived instead. The head's position is known from the pose, its size was measured off the rendered fill
(32 by 22 pixels), and a strand is an arc leaving that ellipse at a given angle. The count and the arc's curvature are
parameters rather than data, so changing them is one number and not forty.

    python add_detail.py --strands 40 --folds 12
    python add_detail.py --strands 0          # the figure alone, for comparison
"""
import argparse
import json
import math
import pathlib
import subprocess
import sys

sys.path.insert(0, r'E:\lineweight')
from lineweight import core, project as project_mod, ref

TMP = pathlib.Path(r'E:\DaShaoHuo\cache\tmp')
SOURCE = pathlib.Path(r'E:\DaShaoHuo\cache\cel-drawing.json')


def load():
    return project_mod.load_project(str(SOURCE))


def head_ellipse(proj):
    """The head's centre and radii, read off the fill the renderer actually produced.

    **Measured, not assumed from the bone.** The bone's width is a table value in figure units; what the picture shows
    is that value through the scale, the thinner factor and the round cap, and it is the picture the strands have to
    leave from. 32 by 22 pixels is what the fill came out as.
    """
    for m in proj.marks:
        if m.kind != 'fill':
            continue
        note = m.provenance.get('note') or ''
        # **The lit fill, not the shadow.** Both exist and the shadow is the narrower of the two -- 18 pixels across
        # against the lit shape's 32 -- so taking whichever came first measured the shadow band and would have hung
        # every strand on a head five pixels too small. Two fills carry the same bone's name and only one of them is
        # the head.
        if 'Head' not in note or 'lit' not in note:
            continue
        pts = m.geometry.get('points') or []
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
        return cx, cy, (max(xs) - min(xs)) / 2.0, (max(ys) - min(ys)) / 2.0
    return None


def add_strands(proj, count, cx, cy, rx, ry):
    """Arcs leaving the top of the head, spread across it.

    **One control point per strand, placed on a rule rather than on a list.** The angle walks from just past the left
    of the head to just past the right, the root sits on the ellipse at that angle, and the tip is pushed out and
    down. A strand bends outward by a fixed fraction of the head's size, so a bigger head gets longer hair without
    anybody choosing that.
    """
    made = 0
    for i in range(count):
        t = (i + 0.5) / count
        # **From the left of the head to the right, over the top**, which in screen coordinates is the upper half
        theta = math.pi * (0.08 + 0.84 * t)
        root = (cx + rx * math.cos(theta), cy - ry * math.sin(theta))
        reach = 1.0 + 0.55 + 0.35 * abs(math.cos(theta))
        tip = (cx + rx * reach * math.cos(theta), cy - ry * reach * math.sin(theta) + ry * 0.55)
        # the bow of the strand, pushed away from the head so it reads as hair rather than as a spike
        mid = ((root[0] + tip[0]) / 2.0 + rx * 0.18 * math.cos(theta),
               (root[1] + tip[1]) / 2.0 - ry * 0.18)
        pts = [root, mid, tip]
        width = [1.9, 2.6, 1.1]
        profile = [width[min(2, int(j * 3 / 33))] for j in range(33)]
        rec = core.stroke_record(pts, 'fine', seed=abs(hash(('strand', i))) % 9973, resolution=16,
                                 width_profile=profile)
        proj.add_stroke(rec, stage='line', layer='head', note='strand %d' % i)
        made += 1
    return made


def add_folds(proj, count):
    """Short arcs across the joints, where cloth gathers.

    **The joints are not chosen, they are read off the strokes that already exist.** Every chain's first and last
    point is a joint by construction, so a fold is a short arc placed there and turned across the limb -- which means
    the folds follow the pose without anybody saying where the pose put them.
    """
    chains = [m for m in proj.marks if m.kind == 'stroke' and (m.provenance.get('note') or '').startswith('chain')]
    made = 0
    for idx, chain in enumerate(chains):
        pts = [tuple(p) for p in chain.geometry['centre']]
        if len(pts) < 6 or made >= count:
            continue
        for frac in (0.30, 0.62):
            i = int(frac * (len(pts) - 1))
            x0, y0 = pts[i]
            x1, y1 = pts[min(i + 2, len(pts) - 1)]
            dx, dy = x1 - x0, y1 - y0
            L = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / L, dx / L
            half = 6.0 + 3.0 * math.sin(idx)
            fold = [(x0 - nx * half, y0 - ny * half),
                    (x0 + nx * half + dx * 2.0, y0 + ny * half + dy * 2.0)]
            rec = core.stroke_record(fold, 'fine', seed=abs(hash(('fold', idx, frac))) % 9973, resolution=16,
                                     width_profile=[1.4, 2.2])
            proj.add_stroke(rec, stage='line', layer='torso', note='fold %d.%d' % (idx, int(frac * 100)))
            made += 1
            if made >= count:
                break
    return made


def measure(path):
    m = ref.measure(str(path))
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    with Image.open(path) as im:
        g = np.array(im.convert('L'))
    ink = g < 200
    lab, n = ndimage.label(ink, structure=np.ones((3, 3), dtype=int))
    sizes = ndimage.sum(ink, lab, range(1, n + 1)) if n else []
    keep = int((sizes >= 8).sum()) if n else 0
    area = int(ink.sum())
    return m, keep, area, keep / math.sqrt(max(1, area))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--strands', type=int, default=40)
    ap.add_argument('--folds', type=int, default=12)
    args = ap.parse_args()

    proj = load()
    before = len([m for m in proj.marks if m.kind == 'stroke'])
    ell = head_ellipse(proj)
    if not ell:
        print('  no head fill in the project; nothing to hang strands on')
        return 1
    print('  the head fill measures %.1f by %.1f px at (%.1f, %.1f)' % (2 * ell[2], 2 * ell[3], ell[0], ell[1]))
    s = add_strands(proj, args.strands, *ell)
    f = add_folds(proj, args.folds)
    after = len([m for m in proj.marks if m.kind == 'stroke'])
    print('  added %d strands and %d folds; strokes %d -> %d' % (s, f, before, after))

    out = TMP / 'detailed.json'
    project_mod.save_project(proj, str(out))
    img = TMP / 'detailed.png'
    subprocess.run([sys.executable, '-m', 'lineweight', '--render', str(out), '--out', str(img)],
                   capture_output=True, text=True, cwd=r'E:\lineweight')

    rows = []
    for label, path in (('figure alone', r'E:\DaShaoHuo\cache\chained.png'), ('with detail', str(img))):
        try:
            m, keep, area, ratio = measure(path)
            rows.append((label, keep, area, ratio))
        except Exception as exc:
            print('  %-14s %s' % (label, str(exc)[:50]))
    print()
    print('  %-14s %8s %10s %14s %10s %10s' % ('', 'blobs', 'ink px', 'blobs/sqrt(ink)', 'ink', 'taper'))
    for label, keep, area, ratio in rows:
        m = ref.measure(str(img if label == 'with detail' else r'E:\DaShaoHuo\cache\chained.png'))
        print('  %-14s %8d %10d %14.4f %10.4f %10.4f' % (label, keep, area, ratio, m.ink_ratio, m.taper_ratio))
    print('  %-14s %8s %10s %14.4f %10s %10s' % ('linework', '', '', 0.2202, '', ''))
    print()
    print('  ** the criterion is the fourth column. The linework median is 0.2202 and the figure alone is 0.0066,')
    print('     so what this asks is whether adding small marks moves it, and by how much per mark added. **')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
