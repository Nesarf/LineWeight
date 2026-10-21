"""Build `model/`: the geometry a drawing is laid out on, exported from the sources that have it.

**Two libraries, two jobs, and this is the second one.** `learn/` holds what can be counted -- how many parts a body
has, which folds exist, what a line's width encodes. **`model/` holds what has a position**: a skeleton's rest
positions and parents, and the joint positions of frames taken from performed motion. One says how to draw, the other
says what is being drawn and where it is.

**Everything here is generated, never hand written**, so a bad export is fixed by fixing the exporter. The sources are
outside the repository and are large; what lands in `model/` is a few hundred kilobytes of coordinates, which is the
same rule `corpus/manifest.jsonl` follows -- record the facts, not the assets.

**The frames are chosen, not sampled.** For each motion the joint-speed curve is computed, the strongest peaks are
taken, and for each peak three frames are saved: the one before it, the peak, and the one after. That is what makes a
pose in this directory a pose rather than a moment, and the three are the same movement read three ways.

    python tools/build_model_library.py --pmx "E:\\ANMS\\...\\RINDO_Full.pmx" --motion "G:\\KKS\\[VMD]\\...\\Motion.vmd"

The command is recorded in `model/README.md` so the directory can be rebuilt.
"""
import argparse
import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from action_scan import MOVERS, angle_series
from pmx_bones import parse as parse_pmx
from pose_frame import pose
from vmd_look import parse as parse_vmd

#: The joints a pose is stored for. **A skeleton has 279 bones and a drawing is laid out on about twenty** -- the rest
#: are fingers, accessories and the chains a physics solver drives, and carrying them made `poses.json` 709 KB for
#: thirty-six frames. What is kept is the spine from the hips to the head, and both limbs with the joint that bends
#: in the middle of each.
POSE_BONES = ('センター', '下半身', '上半身', '上半身2', '首', '頭',
              '左肩', '左腕', '左ひじ', '左手首', '右肩', '右腕', '右ひじ', '右手首',
              '左足', '左ひざ', '左足首', '右足', '右ひざ', '右足首')


def speed_curve(anim, frames):
    """Sum of every mover joint's angle change per sample, in degrees."""
    series = angle_series(anim, MOVERS, frames)
    out = []
    for i in range(len(frames)):
        if i == 0:
            out.append(0.0)
            continue
        out.append(math.degrees(sum(abs(v[i] - v[i - 1]) for _n, v in series)))
    return out


def peaks(frames, speed, count, gap):
    """Local maxima, separated by at least `gap` frames so one swing is not counted twice."""
    order = sorted(range(1, len(speed) - 1), key=lambda i: -speed[i])
    chosen = []
    for i in order:
        if speed[i] < speed[i - 1] or speed[i] < speed[i + 1]:
            continue
        if all(abs(frames[i] - frames[j]) > gap for j in chosen):
            chosen.append(i)
        if len(chosen) >= count:
            break
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pmx', required=True, help='where the rest positions and the parents come from')
    ap.add_argument('--motion', action='append', default=[], help='a vmd; repeat for more than one')
    ap.add_argument('--out', default='model')
    ap.add_argument('--peaks', type=int, default=3)
    ap.add_argument('--gap', type=int, default=240, help='frames between two peaks')
    ap.add_argument('--step', type=int, default=2)
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    _version, model_name, bones, _r = parse_pmx(args.pmx)
    skeleton = {
        'model': model_name,
        'source': args.pmx,
        'bones': [{'name': b['name'],
                   'parent': bones[b['parent']]['name'] if 0 <= b['parent'] < len(bones) else None,
                   'pos': [round(v, 4) for v in b['pos']]} for b in bones],
    }
    (out / 'skeleton.json').write_text(json.dumps(skeleton, ensure_ascii=False, indent=1), encoding='utf-8')
    print('  skeleton.json   %d bones from %r' % (len(bones), model_name))

    poses = []
    motions = []
    for path in args.motion:
        _v, vmd_model, anim, span = parse_vmd(path)
        frames = list(range(span[0], span[1] + 1, args.step))
        speed = speed_curve(anim, frames)
        chosen = peaks(frames, speed, args.peaks, args.gap)
        joinable = sum(1 for b in bones if b['name'] in anim)
        motions.append({
            'path': path,
            'model': vmd_model,
            'bones_in_motion': len(anim),
            'bones_this_skeleton_shares': joinable,
            'frames': list(span),
            'mean_speed': round(sum(speed) / len(speed), 2) if speed else 0.0,
            'peak_speed': round(max(speed), 2) if speed else 0.0,
            'peak_frames': [frames[i] for i in chosen],
        })
        for i in chosen:
            for offset, why in ((-args.step * 2, 'before'), (0, 'peak'), (args.step * 2, 'after')):
                frame = frames[i] + offset
                if frame < span[0] or frame > span[1]:
                    continue
                pos, _rot = pose(bones, anim, frame)
                poses.append({
                    'motion': path,
                    'frame': frame,
                    'role': why,
                    'speed': round(speed[i], 2),
                    'joints': {b['name']: [round(float(p[0]), 3), round(float(p[1]), 3), round(float(p[2]), 3)]
                               for b, p in zip(bones, pos) if p is not None and b['name'] in POSE_BONES},
                })
        print('  %-14s frames %d..%d, %d shared bones, peak frames %s'
              % (path.split('\\')[-1], span[0], span[1], joinable, [frames[i] for i in chosen]))

    (out / 'poses.json').write_text(json.dumps({
        'source': {'pmx': args.pmx, 'skeleton': 'skeleton.json'},
        'note': 'joint world positions per frame; y is up; the units are the model\'s own',
        'poses': poses,
    }, ensure_ascii=False, indent=1), encoding='utf-8')
    (out / 'motions.json').write_text(json.dumps(motions, ensure_ascii=False, indent=1), encoding='utf-8')
    print('  poses.json      %d frames' % len(poses))
    print('  motions.json    %d motions' % len(motions))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
