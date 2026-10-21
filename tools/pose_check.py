"""Check the drawing's own joint table against a model's rest pose, joint by joint.

**The table in `cel_drawing.py` came from eleven Unity rigs; the model library can measure the same joints directly.**
When two sources disagree on where the hand is by a fifth of a body, the disagreement is worth a tool rather than an
argument -- and the number to read is each joint's height, counted from the same end.

**Both are converted to "how far below the top of the figure", as a fraction**, because that is the form the table is
written in. A model's own height here is the span of its *bones*, not of its vertices: the top of a skull is a bone,
the tip of a horn is not.

    python tools/pose_check.py --pmx "E:\\ANMS\\...\\RINDO_Full.pmx"
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
sys.path.insert(0, r'E:\lineweight')

from pmx_bones import parse as parse_pmx

#: The table's name for a joint, and the model's. **The left side is the drawing's**; where a model names a joint
#: differently the mapping says so rather than being guessed at by substring.
PAIRS = [
    ('Bip001 Pelvis', '下半身'),
    ('Bip001 Spine', '上半身'),
    ('Bip001 Spine1', '上半身2'),
    ('Bip001 Neck', '首'),
    ('Bip001 Head', '頭'),
    ('Bip001 L UpperArm', '左腕'),
    ('Bip001 L Forearm', '左ひじ'),
    ('Bip001 L Hand', '左手首'),
    ('Bip001 L Thigh', '左足'),
    ('Bip001 L Calf', '左ひざ'),
    ('Bip001 L Foot', '左足首'),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pmx', required=True)
    args = ap.parse_args()

    import cel_drawing

    _v, model_name, bones, _r = parse_pmx(args.pmx)
    by_name = {b['name']: b for b in bones}
    # **The height is the head bone to the ankle bone, not the span of every bone.** A model carries bones for
    # weapons, wings and empty parents, and one of them sat at y=21 on a figure 14 units tall -- which made every
    # value below it a fraction of the wrong whole. The leg joints still looked right under that divisor, by accident,
    # which is exactly how a scale fault survives a review.
    head = by_name.get('頭')
    ankle = by_name.get('左足首')
    if head and ankle:
        hi, lo = head['pos'][1], ankle['pos'][1]
    else:
        ys = [b['pos'][1] for b in bones]
        hi, lo = max(ys), min(ys)
    span = (hi - lo) or 1.0

    print('  %s   %d bones   height proxy %.3f..%.3f (head bone to ankle bone)' % (model_name, len(bones), lo, hi))
    print('  the model column is "how far below the top of the bone span", as the table writes it')
    print()
    print('    %-20s %-14s %8s %8s %8s' % ('table joint', 'model bone', 'table', 'model', 'difference'))
    worst = None
    for table_name, model_name_jp in PAIRS:
        if table_name not in cel_drawing.POS:
            continue
        bone = by_name.get(model_name_jp)
        if bone is None:
            print('    %-20s %-14s %8s %8s  %s' % (table_name, model_name_jp, '%.3f' % cel_drawing.POS[table_name][1],
                                                   '-', 'not in this model'))
            continue
        model_from_top = (hi - bone['pos'][1]) / span
        table_from_top = cel_drawing.POS[table_name][1]
        diff = table_from_top - model_from_top
        if worst is None or abs(diff) > abs(worst[2]):
            worst = (table_name, model_from_top, diff)
        print('    %-20s %-14s %8.3f %8.3f %+8.3f' % (table_name, model_name_jp, table_from_top,
                                                      model_from_top, diff))
    if worst:
        print()
        print('  the largest disagreement is %s: the table puts it %+.3f of a body below where the model does'
              % (worst[0], worst[2]))
        print('  a positive number means the table has the joint lower than the model')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
