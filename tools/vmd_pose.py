"""One bone's angle across a motion, drawn: the shape of "the moment before the action".

**What this is for.** A VMD gives a rotation per bone per keyframe. The angle a bone has turned from its rest pose is
`2 acos(|w|)`, which loses the axis but keeps the magnitude -- and the magnitude is what a drawing has to show: an arm
that has travelled 120 degrees looks different from one that has travelled 20, whatever plane it travelled in.

**And the moment a drawing wants is on this curve, not at its end.** A pose at the extreme of the curve is finished; the
pose that predicts the movement is the one just after the curve starts to climb -- the body is already committed and
nothing has arrived yet. So this prints the curve, the steepest step, and the frame at which the climb passes a quarter,
a half and three quarters of its own span.

    python tools/vmd_pose.py --src "G:\\KKS\\[VMD]\\Motion.vmd" --bone 左腕
"""
import argparse
import math

from vmd_look import parse


def steps(values):
    return [abs(values[i] - values[i - 1]) for i in range(1, len(values))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--bone', default='左腕')
    ap.add_argument('--bars', type=int, default=56)
    ap.add_argument('--window', type=int, default=0, help='only frames 0..window; 0 means the whole motion')
    args = ap.parse_args()

    _version, _model, bones, span = parse(args.src)
    recs = bones.get(args.bone)
    if not recs:
        near = [b for b in bones if args.bone and args.bone[:2] in b]
        print('  no bone %r; similar names: %s' % (args.bone, near[:12]))
        return 1
    recs.sort()
    if args.window:
        recs = [r for r in recs if r[0] <= args.window] or recs

    frames = [r[0] for r in recs]
    angles = [math.degrees(r[1]) for r in recs]
    lo, hi = min(angles), max(angles)
    print('  %s   bone %r   %d keyframes   frames %d..%d'
          % (args.src.split('\\')[-1], args.bone, len(recs), frames[0], frames[-1]))
    print('  angle runs %.1f to %.1f degrees' % (lo, hi))
    print()

    # The curve, as bars: horizontal is time, vertical is the angle. A ramp, a hold and a return are visibly different
    # shapes, and which one it is decides what a drawing can claim about the next moment.
    span_f = max(1, frames[-1] - frames[0])
    for row in range(8, -1, -1):
        line = []
        for col in range(args.bars):
            target = frames[0] + span_f * col / float(args.bars - 1)
            near = min(recs, key=lambda r: abs(r[0] - target))
            level = (math.degrees(near[1]) - lo) / ((hi - lo) or 1.0)
            # **The bottom row is drawn strictly**, because `level >= 0` is true for every column and the baseline
            # would print as a full bar of ink that means nothing.
            lit = level > row / 8.0 or (row == 0 and level > 0.0)
            line.append('#' if lit else ' ')
        print('  %5.2f |%s' % (row / 8.0, ''.join(line)))
    print('        +%s' % ('-' * args.bars))
    print('         frame %d%s%d' % (frames[0], ' ' * (args.bars - 14), frames[-1]))

    st = steps(angles)
    if st:
        worst = st.index(max(st))
        print()
        print('  steepest step: %.1f degrees between frame %d and %d'
              % (max(st), frames[worst], frames[worst + 1]))
        for frac in (0.25, 0.5, 0.75):
            target = lo + (hi - lo) * frac
            hit = next((frames[i] for i in range(len(angles)) if angles[i] >= target), frames[-1])
            print('  the climb passes %.2f of its span at frame %d' % (frac, hit))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
