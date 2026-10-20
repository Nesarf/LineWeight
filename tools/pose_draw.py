"""Draw one frame of a motion as a skeleton on the canvas.

**What this is the first of.** Everything before it measured a picture that already existed. This one takes a motion
that was performed on another model, composes the joints (see `pose_frame.py`) and lays them down as strokes -- so the
lines come from a body that moved, rather than from a table of proportions.

**The projection is orthographic, and that is stated rather than hidden.** A drawing this project makes has no camera;
`x` and `y` of the joint are the page, and `z` is dropped. A perspective camera would be a different picture and is not
what is being answered here -- the question is what pose a movement passes through.

    python tools/pose_draw.py --pmx "E:\\ANMS\\...\\RINDO_Full.pmx" --vmd "G:\\KKS\\[VMD]\\...\\Motion.vmd" --frame 2736
"""
import argparse
import pathlib
import sys

sys.path.insert(0, r'E:\lineweight')
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from lineweight import core, project

from pmx_bones import parse as parse_pmx
from pose_frame import pose
from vmd_look import parse as parse_vmd

#: The chains a skeleton is drawn from, each one a line a hand would draw in one movement. **Ordered root to tip**,
#: because the width tapers along that direction.
CHAINS = [
    ('spine', ['センター', '上半身', '上半身2', '首', '頭']),
    ('arm_l', ['左肩', '左腕', '左ひじ', '左手首']),
    ('arm_r', ['右肩', '右腕', '右ひじ', '右手首']),
    ('leg_l', ['左足', '左ひざ', '左足首']),
    ('leg_r', ['右足', '右ひざ', '右足首']),
]

#: Bone width at each end of a chain, in page pixels. **Trunk thick, limb tip thin** -- the same relation the corpus
#: measured, written here as the only two numbers a skeleton needs.
WIDTH = {'spine': (26.0, 12.0), 'arm_l': (11.0, 5.0), 'arm_r': (11.0, 5.0),
         'leg_l': (16.0, 6.0), 'leg_r': (16.0, 6.0)}

CANVAS_W, CANVAS_H = 800.0, 600.0
MARGIN = 40.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pmx', required=True)
    ap.add_argument('--vmd', required=True)
    ap.add_argument('--frame', type=int, default=2736)
    ap.add_argument('--out', default=r'E:\DaShaoHuo\cache\pose.json')
    ap.add_argument('--png', default=r'E:\DaShaoHuo\cache\pose.png')
    ap.add_argument('--render', action='store_true')
    args = ap.parse_args()

    _pv, _pname, bones, _r = parse_pmx(args.pmx)
    _vv, _vname, anim, span = parse_vmd(args.vmd)
    pos, _rot = pose(bones, anim, args.frame)
    index = {b['name']: i for i, b in enumerate(bones)}

    chains = []
    for label, names in CHAINS:
        pts = [pos[index[n]] for n in names if n in index]
        if len(pts) >= 2:
            chains.append((label, names, pts))
    if not chains:
        print('  none of the chain names exist in this model')
        return 1

    xs = [p[0] for _l, _n, pts in chains for p in pts]
    ys = [p[1] for _l, _n, pts in chains for p in pts]
    lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)
    scale = min((CANVAS_H - 2 * MARGIN) / ((hi_y - lo_y) or 1.0),
                (CANVAS_W - 2 * MARGIN) / ((hi_x - lo_x) or 1.0))
    cx = (lo_x + hi_x) / 2.0
    cy = (lo_y + hi_y) / 2.0

    def place(p):
        return (CANVAS_W / 2 + (p[0] - cx) * scale, CANVAS_H / 2 - (p[1] - cy) * scale)

    proj = project.Project(width=int(CANVAS_W), height=int(CANVAS_H),
                           title='frame %d' % args.frame)
    marks = 0
    for label, names, pts in chains:
        page = [place(p) for p in pts]
        head_w, tail_w = WIDTH[label]
        n = 16 * (len(page) - 1) + 1
        profile = [head_w + (tail_w - head_w) * i / (n - 1) for i in range(n)]
        rec = core.stroke_record(page, 'ink', seed=11 + marks, resolution=16, width_profile=profile)
        proj.add_stroke(rec, stage='line', layer=label, note='frame %d' % args.frame)
        marks += 1

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    project.save_project(proj, str(out))
    print('  frame %d  chains %d  joints %d  scale %.2f px per unit'
          % (args.frame, len(chains), sum(len(p) for _l, _n, p in chains), scale))
    print('  written to %s' % out)

    if args.render:
        import subprocess
        subprocess.run([sys.executable, '-m', 'lineweight', '--render', str(out), '--out', args.png],
                       capture_output=True, text=True, cwd=r'E:\lineweight')
        print('  rendered to %s' % args.png)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
