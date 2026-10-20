"""Compose one frame of a motion onto a bone hierarchy, and print where the joints land.

**The join between two files that were never meant to be read together.** A VMD holds a local rotation per bone per
keyframe; a PMX holds each bone's rest position and parent. Neither is a pose. Composing them is what a pose is:

    world_rot[b]  = world_rot[parent] * local_rot[b]
    world_pos[b]  = world_pos[parent] + world_rot[parent] * (rest[b] - rest[parent] + anim_pos[b])

**No interpolation and no IK are applied, and both are named rather than left implicit.** The keyframes are taken as the
last one at or before the frame asked for, which is what a step holds; and a leg driven by an IK bone is placed by the
IK, so its own child joints read somewhere other than where the foot would be. What this answers is *where the spine,
the head and the limb roots are*, which is the structure a drawing is laid out on.

    python tools/pose_frame.py --pmx "E:\\ANMS\\...\\RINDO_Full.pmx" --vmd "G:\\KKS\\[VMD]\\...\\Motion.vmd" --frame 2736
"""
import argparse

from pmx_bones import parse as parse_pmx
from vmd_look import parse as parse_vmd

import numpy as np

#: The joints a figure's layout is built from, in the order a drawing lays them down.
MAJOR = ['センター', '上半身', '上半身2', '首', '頭',
         '左腕', '左ひじ', '左手首', '右腕', '右ひじ', '右手首',
         '左足', '左ひざ', '左足首', '右足', '右ひざ', '右足首']


def quat_to_matrix(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def last_at_or_before(recs, frame):
    """The keyframe a step holds. **A motion is a step function between keys**, so this is the honest read."""
    best = None
    for r in recs:
        if r[0] <= frame and (best is None or r[0] > best[0]):
            best = r
    return best if best is not None else recs[0]


def pose(bones, anim, frame):
    """World position and rotation of every bone. **Parents come before children**, which PMX guarantees."""
    n = len(bones)
    pos = [None] * n
    rot = [None] * n
    for i, b in enumerate(bones):
        recs = anim.get(b['name'])
        local_r = quat_to_matrix(recs and last_at_or_before(recs, frame)[3] or (0.0, 0.0, 0.0, 1.0))
        local_p = np.array(recs and last_at_or_before(recs, frame)[2] or (0.0, 0.0, 0.0))
        if b['parent'] < 0 or pos[b['parent']] is None:
            pos[i] = np.array(b['pos']) + local_p
            rot[i] = local_r
        else:
            j = b['parent']
            offset = np.array(b['pos']) - np.array(bones[j]['pos']) + local_p
            pos[i] = pos[j] + rot[j] @ offset
            rot[i] = rot[j] @ local_r
    return pos, rot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pmx', required=True)
    ap.add_argument('--vmd', required=True)
    ap.add_argument('--frame', type=int, required=True)
    ap.add_argument('--ascii', action='store_true', help='draw the joints in the frame')
    args = ap.parse_args()

    _v, _name, bones, _r = parse_pmx(args.pmx)
    _vv, _vm, anim, span = parse_vmd(args.vmd)
    pos, _rot = pose(bones, anim, args.frame)
    index = {b['name']: i for i, b in enumerate(bones)}

    print('  model %r, %d bones;  motion frames %d..%d;  frame asked for %d'
          % (_name, len(bones), span[0], span[1], args.frame))
    print()
    print('    %-12s %8s %8s %8s' % ('joint', 'x', 'y', 'z'))
    placed = {}
    for name in MAJOR:
        i = index.get(name)
        if i is None:
            continue
        placed[name] = pos[i]
        print('    %-12s %8.2f %8.2f %8.2f' % (name, pos[i][0], pos[i][1], pos[i][2]))

    if not placed:
        print('  none of the major joint names exist in this model')
        return 1

    # **What the figure's layout actually asks: how far the joints are from the vertical through the feet.** A figure
    # on its way somewhere leans; a figure at rest does not.
    if 'センター' in placed:
        centre = placed['センター']
        print()
        for name in ('頭', '左腕', '左手首', '右足首'):
            if name in placed:
                dx = placed[name][0] - centre[0]
                print('  %-8s is %6.2f units from the centre line horizontally' % (name, dx))

    if args.ascii:
        ys = [p[1] for p in placed.values()]
        lo, hi = min(ys), max(ys)
        span_y = (hi - lo) or 1.0
        xs = [p[0] for p in placed.values()]
        lo_x, hi_x = min(xs), max(xs)
        span_x = (hi_x - lo_x) or 1.0
        rows, cols = 24, 44
        grid = [[' '] * cols for _ in range(rows)]
        for name, p in placed.items():
            col = int((p[0] - lo_x) / span_x * (cols - 1))
            row = int((hi - p[1]) / span_y * (rows - 1))
            grid[row][col] = 'O'
        print()
        for r in grid:
            print('    ' + ''.join(r))
        print('    the joints: %s' % ', '.join(sorted(placed)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
