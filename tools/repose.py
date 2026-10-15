"""Rebuild the drawing's pose from four measured ratios instead of from twenty hand-picked numbers.

**Why the pose is being changed by arithmetic rather than by taste.** The figure reads stiff, and the check that
found out why was not a drawing judgement: the same four ratios were taken from 860 rigs in the corpus -- shoulder
width, hip width, pelvis height and stance width, each divided by the height from the feet to the head bone -- and the
hand-written pose misses all four, in the same direction. It is 18 per cent too narrow at the shoulder, 44 per cent at
the hip, 28 per cent at the stance, and the pelvis sits 16 per cent too high.

**So the new numbers are computed rather than chosen.** Each ratio fixes one coordinate and the chains between are
interpolated, because the two ends of a limb are pinned by two different ratios and moving one end alone breaks the
limb: the hip ratio wants the thigh at 0.093 and the stance ratio wants the toe at 0.105, so scaling the whole leg by
either factor would over- or undershoot the other end.

    python repose.py            # print the new pose and the ratios it achieves
    python repose.py --write    # and put it into tools/cel_drawing.py
"""
import argparse
import importlib.util
import pathlib
import re
import sys

POSE_FILE = pathlib.Path(r'E:\lineweight\tools\cel_drawing.py')

#: **From `measure_rigs.py` over 860 rigs, with the `Bip001 Xtra*` helper bones excluded from the height.** They sit
#: above the head -- `Bip001 Xtra_eyeblowR1` is the highest bone in every rig -- and including them inflated the
#: height by 21.5 per cent, which moved every ratio divided by it. Measured twice before the mistake was seen.
TARGET = {
    'shoulder_width_over_height': 0.2356,
    'hip_width_over_height': 0.2307,
    'pelvis_y_over_height': 0.5439,
    'stance_width_over_height': 0.2608,
}

#: The joints of a limb chain, in order, so a value can be interpolated along it rather than scaled as a block.
ARM = ('Bip001 L Clavicle', 'Bip001 L UpperArm', 'Bip001 L Forearm', 'Bip001 L Hand')
LEG = ('Bip001 L Thigh', 'Bip001 L Calf', 'Bip001 L Foot', 'Bip001 L Toe0')
SPINE = ('Bip001 Pelvis', 'Bip001 Spine', 'Bip001 Spine1', 'Bip001 Neck', 'Bip001 Head')


def load_pose():
    spec = importlib.util.spec_from_file_location('cd', str(POSE_FILE))
    cd = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(cd)
    except SystemExit:
        pass
    return dict(cd.POS)


def lerp(a, b, t):
    return a + (b - a) * t


def canonical(name):
    """The left-hand name for either side, so one lookup serves both.

    **This is the bug the first version had.** It asked `name.replace(' L ', ' R ') in ARM`, which does nothing to a
    name that contains no `' L '` -- so `Bip001 R UpperArm` did not match and **the right half of the figure was left
    exactly where it was while the left half was scaled**. Every ratio that compares a left joint with a right one
    then came out at about half its target, which is what the first run printed: 0.2147 against 0.2356. Mapping the
    right-hand name back to the left is the direction that works, because it cannot silently fail to match.
    """
    return name.replace(' R ', ' L ')


def build(pos):
    """The new pose, with every change traceable to one of the four ratios."""
    out = {}
    top = min(p[1] for p in pos.values())
    bot = max(p[1] for p in pos.values())
    h = bot - top

    def x(n):
        return pos[n][0]

    def y(n):
        return pos[n][1]

    # **The height is held fixed**, because it is the denominator of all four ratios and moving the head would move
    # the target with it. So the head stays and the pelvis comes down -- which is what the corpus says a body is:
    # a shorter leg under the same head.
    pelvis_y = bot - TARGET['pelvis_y_over_height'] * h

    thigh_x = TARGET['hip_width_over_height'] * h / 2.0
    toe_x = TARGET['stance_width_over_height'] * h / 2.0
    upperarm_x = TARGET['shoulder_width_over_height'] * h / 2.0
    # the arm chain scaled as a whole, because only its second joint is pinned by a measurement and an arm that
    # changes shape between the shoulder and the hand is not what the ratio is asking for
    arm_scale = upperarm_x / x('Bip001 L UpperArm')

    for name, (px, py) in pos.items():
        side = -1.0 if ' R ' in name else 1.0
        key = canonical(name)
        nx, ny = px, py

        if key in ARM:
            nx = px * arm_scale
        elif key in LEG:
            i = LEG.index(key)
            t = i / (len(LEG) - 1.0)
            nx = lerp(thigh_x, toe_x, t) * side
            # **The leg's y is interpolated too, not just translated.** The pelvis comes down and the foot does not
            # move, so the chain shortens between them: adding an offset would shorten the thigh and leave the calf
            # the same length, which is not a shorter leg but a broken one.
            ny = lerp(pelvis_y, bot, t)
        elif key in SPINE:
            # **The spine is interpolated between the pelvis and the head, and the first version left it alone.**
            # `Bip001 Pelvis` is on this chain, so a `pass` here meant the pelvis never moved and the ratio it was
            # supposed to fix came out identical to before -- visible in the first run, which printed 0.6335 against
            # a target of 0.5439. The head is the anchor at the top because the height must not move with it.
            i = SPINE.index(key)
            t = i / (len(SPINE) - 1.0)
            ny = lerp(pelvis_y, y('Bip001 Head'), t)
        out[name] = (round(nx, 5), round(ny, 5))
    return out, h, pelvis_y


def ratios(pos):
    top = min(p[1] for p in pos.values())
    bot = max(p[1] for p in pos.values())
    h = bot - top

    def x(n):
        return pos[n][0]

    def y(n):
        return pos[n][1]
    return {
        'shoulder_width_over_height': abs(x('Bip001 L UpperArm') - x('Bip001 R UpperArm')) / h,
        'hip_width_over_height': abs(x('Bip001 L Thigh') - x('Bip001 R Thigh')) / h,
        'pelvis_y_over_height': (bot - y('Bip001 Pelvis')) / h,
        'stance_width_over_height': abs(x('Bip001 L Toe0') - x('Bip001 R Toe0')) / h,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args()

    pos = load_pose()
    before = ratios(pos)
    new, h, pelvis_y = build(pos)
    after = ratios(new)

    print('  height held at %.4f, pelvis moved from %.4f to %.4f' % (h, pos['Bip001 Pelvis'][1], pelvis_y))
    print()
    print('  %-30s %10s %10s %10s' % ('ratio', 'before', 'after', 'target'))
    for k in TARGET:
        print('  %-30s %10.4f %10.4f %10.4f' % (k, before[k], after[k], TARGET[k]))
    print()
    print('  the joints that moved most:')
    moves = sorted(((abs(new[n][0] - pos[n][0]) + abs(new[n][1] - pos[n][1]), n) for n in pos), reverse=True)
    for d, n in moves[:8]:
        print('    %-26s (%7.4f, %7.4f) -> (%7.4f, %7.4f)' % (n, pos[n][0], pos[n][1], new[n][0], new[n][1]))

    if not args.write:
        print()
        print('  not written; pass --write to put it into %s' % POSE_FILE.name)
        return 0

    text = POSE_FILE.read_text(encoding='utf-8')
    block = ['POS = {']
    for name in sorted(new):
        block.append("    %-22s (%s, %s)," % ("'%s':" % name, new[name][0], new[name][1]))
    block.append('}')
    # replace the POS literal, from `POS = {` to the matching close
    start = text.index('POS = {')
    depth, i = 0, start
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                break
        i += 1
    text = text[:start] + '\n'.join(block) + text[i + 1:]
    POSE_FILE.write_text(text, encoding='utf-8')
    print()
    print('  written to %s' % POSE_FILE)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
