"""Find the frames a movement passes through hardest, which is where a drawing of it lives.

**The claim being tested.** A drawn figure should show the moment the movement is committed and not finished -- Hampton
writes it as 「the moment before the action starts」 and every book in the library says the same thing from a different
side. **A motion file makes that phrase measurable**: sum the absolute change in every major joint's angle from frame to
frame, and the result is a speed. A drawing wants the frame just before a peak, where the speed is already high and the
pose has not yet arrived.

**Why the peak itself is the wrong frame.** At the peak the limb is moving fastest *through* the pose -- the pose there
is a pose, but it is the middle of a swing, held for one frame. Just before it, the body is committed and the shape is
still closing; just after it, the shape is opening out again. The three are different pictures of the same movement and
only the second carries the prediction.

    python tools/action_scan.py --vmd "G:\\KKS\\[VMD]\\...\\Motion.vmd"
"""
import argparse
import math

from vmd_look import parse as parse_vmd

#: The joints whose movement is a movement. Fingers and hair ride along and would only add noise.
MOVERS = ['センター', '上半身', '上半身2', '首', '頭',
          '左腕', '左ひじ', '左手首', '右腕', '右ひじ', '右手首',
          '左足', '左ひざ', '左足首', '右足', '右ひざ', '右足首']


def angle_at(recs, frame):
    """One bone's angle at a frame, **interpolated between the keys that bracket it**.

    Holding the previous key was the first version and it made the speed curve alternate between zero and 566 degrees:
    a held value does not change, so every sample that did not cross a key reported no motion, and the one that did
    reported the whole key's worth at once. **A speed that is zero five frames out of six is a sampling artefact, not a
    gesture.** The file also carries interpolation curves this does not read, so a straight line between keys is an
    approximation -- but it is an approximation of the same shape, which the hold was not.
    """
    if frame <= recs[0][0]:
        return recs[0][1]
    if frame >= recs[-1][0]:
        return recs[-1][1]
    for i in range(len(recs) - 1):
        a, b = recs[i], recs[i + 1]
        if a[0] <= frame <= b[0]:
            span = b[0] - a[0]
            t = (frame - a[0]) / float(span) if span else 0.0
            return a[1] + (b[1] - a[1]) * t
    return recs[-1][1]


def angle_series(anim, names, frames):
    """Each named bone's angle at every frame in `frames`, interpolated between keys."""
    out = []
    for name in names:
        recs = anim.get(name)
        if not recs:
            continue
        recs = sorted(recs, key=lambda r: r[0])
        out.append((name, [angle_at(recs, f) for f in frames]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vmd', required=True)
    ap.add_argument('--step', type=int, default=2, help='frames between samples of the speed curve')
    ap.add_argument('--peaks', type=int, default=6)
    args = ap.parse_args()

    _v, _model, anim, span = parse_vmd(args.vmd)
    frames = list(range(span[0], span[1] + 1, args.step))
    series = angle_series(anim, MOVERS, frames)
    if not series:
        print('  none of the mover joints exist in this motion')
        return 1

    speed = []
    for i in range(len(frames)):
        if i == 0:
            speed.append(0.0)
            continue
        # Angles are radians here, so the sum is converted once rather than per joint.
        speed.append(math.degrees(sum(abs(vals[i] - vals[i - 1]) for _n, vals in series)))

    total = sum(speed) or 1.0
    print('  %s   model %r   frames %d..%d   %d joints'
          % (args.vmd.split('\\')[-1], _model, span[0], span[1], len(series)))
    print('  mean speed %.1f degrees per sample, peak %.1f' % (total / len(speed), max(speed)))

    # **Local maxima only, and separated**, so the same swing is not counted twice.
    order = sorted(range(1, len(speed) - 1), key=lambda i: -speed[i])
    chosen = []
    for i in order:
        if speed[i] < speed[i - 1] or speed[i] < speed[i + 1]:
            continue
        if all(abs(frames[i] - frames[j]) > 30 for j in chosen):
            chosen.append(i)
        if len(chosen) >= args.peaks:
            break

    print()
    print('    %-8s %8s %8s  %s' % ('peak', 'speed', 'before', 'the frame before it is the one to draw'))
    for i in chosen:
        print('    %-8d %8.1f %8d  frame %d'
              % (frames[i], speed[i], speed[i - 1], frames[i] - args.step * 2))

    # A short profile of the strongest one, so the shape of the event is visible and not only its position.
    if chosen:
        i = chosen[0]
        lo, hi = max(0, i - 12), min(len(speed), i + 13)
        print()
        print('  around the strongest peak (frame %d):' % frames[i])
        top = max(speed[lo:hi]) or 1.0
        for k in range(lo, hi):
            bar = '#' * int(40 * speed[k] / top)
            mark = ' <' if k == i else ''
            print('    frame %5d  %6.1f  %s%s' % (frames[k], speed[k], bar, mark))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
