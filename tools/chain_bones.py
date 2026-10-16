"""Make the bones of a limb one stroke instead of a stack of strokes that happen to touch.

**What the picture showed.** At a joint the upper arm thins to a point and the forearm thins to a point and the two
points meet, so **the join is the thinnest place in the limb**. That is one fact seen twice: the drawing reads as marks
laid near one another rather than as a drawing, and `taper_ratio` -- the thinnest fifth of the runs over their mean --
comes out 25 per cent low while no individual line width is wrong.

**The fix, and why it is small.** `stroke_record` already takes a `width_profile` array, and `BONE_WIDTH` is already
written so that one bone's end width equals the next bone's start width -- the upper arm's end is 0.039 and the
forearm's start is 0.039, so the two profiles join without a step. What is wrong is only *where the taper is applied*:
`bone_profile` tapers the first `ENTRY` of **every** bone, and `stroke_record` ends **every** mark, so a chain of four
bones carries four entry tapers and four exits where a drawing has two.

**So the loop changes from per bone to per chain**, and the profile gains two flags saying whether this bone is at the
head or the tail of its chain. Everything else -- the bow, the shadow band, the fills, the outline -- is the same
machinery applied once per chain rather than once per bone.

    python chain_bones.py           # show the chains it would build, and stop
    python chain_bones.py --write   # rewrite tools/cel_drawing.py
"""
import argparse
import pathlib

TOOL = pathlib.Path(r'E:\lineweight\tools\cel_drawing.py')

# --- edit 1: the profile learns where it sits in a chain ----------------------
OLD_PROFILE = """def bone_profile(bone, n, taper_from=0.0):
    top = bottom = 0.030
    for key in ('Finger', 'Toe', 'Head', 'Neck', 'Clavicle', 'UpperArm', 'Forearm', 'Hand',
                'Thigh', 'Calf', 'Foot', 'Spine1', 'Spine', 'Pelvis'):
        if key in bone:
            top, bottom = BONE_WIDTH[key]
            break
    out = []
    for i in range(n):
        t = i / max(1, n - 1)
        w = top + (bottom - top) * t
        if t < ENTRY:
            w *= 1.0 - taper_from * (1.0 - t / ENTRY)
        if bone in TIP_BONES and t > 1.0 - EXIT:
            w *= 1.0 - 0.55 * ((t - (1.0 - EXIT)) / EXIT)
        out.append(w * SCALE * THINNER)
    return out"""

NEW_PROFILE = '''def bone_profile(bone, n, taper_from=0.0, is_head=True, is_tail=True):
    """One bone's width along its own length.

    **`is_head` and `is_tail` exist because a taper belongs to a stroke and not to a bone.** A chain of four bones is
    one line in a drawing: it enters at the clavicle, runs to the hand, and leaves once. The first version tapered the
    first `ENTRY` of every bone and let `stroke_record` end every mark, so a four-bone arm carried four entries and
    four exits -- **and at each joint two exits met, which is why the join came out thinner than either bone.** The
    flags say whether this particular bone is the one at the head or the tail of the chain it belongs to; a bone in
    the middle tapers at neither end, because its ends are joints and a joint is not where a line stops.
    """
    top = bottom = 0.030
    for key in ('Finger', 'Toe', 'Head', 'Neck', 'Clavicle', 'UpperArm', 'Forearm', 'Hand',
                'Thigh', 'Calf', 'Foot', 'Spine1', 'Spine', 'Pelvis'):
        if key in bone:
            top, bottom = BONE_WIDTH[key]
            break
    out = []
    for i in range(n):
        t = i / max(1, n - 1)
        w = top + (bottom - top) * t
        if is_head and t < ENTRY:
            w *= 1.0 - taper_from * (1.0 - t / ENTRY)
        if is_tail and bone in TIP_BONES and t > 1.0 - EXIT:
            w *= 1.0 - 0.55 * ((t - (1.0 - EXIT)) / EXIT)
        out.append(w * SCALE * THINNER)
    return out


def chains(by_layer):
    """Every bone of each layer, each in exactly one chain, walked from root to tip.

    **The invariant is that no bone is dropped**, and the first version broke it. It started chains only at bones
    whose parent lies outside the layer and stopped the walk at any fork -- which reads like a tidy guard and is not:
    the two clavicles hang off `Spine1`, so their parent *is* in the layer and they are not starts, and the walk from
    the pelvis stops at the fork, so they were never reached either. **They disappeared from the drawing silently**,
    and the only reason it was noticed is that the printed list of chains had nine entries where it should have had
    eleven.

    So the walk marks what it has taken, and a fork pushes each child back as a new chain's head. Whatever is left
    when the queue empties starts a chain of its own, which is the backstop that makes "each in exactly one" true
    rather than hopeful.
    """
    out = []
    for layer, pairs in by_layer.items():
        children = {c: p for c, p in pairs}
        for c, p in pairs:
            children.setdefault(c, p)
        remaining = set(children)
        queue = sorted(c for c, p in pairs if p not in children)
        while remaining:
            if not queue:
                # **The backstop.** Anything still unvisited becomes a chain head, so a shape of skeleton this did
                # not anticipate loses nothing -- it only gets split into more chains than it might have.
                queue = [sorted(remaining)[0]]
            start = queue.pop(0)
            if start not in remaining:
                continue
            walk, cur = [], start
            while cur in remaining:
                remaining.discard(cur)
                walk.append(cur)
                kids = sorted(k for k, kp in pairs if kp == cur)
                if len(kids) == 1:
                    cur = kids[0]
                else:
                    queue.extend(k for k in kids if k in remaining)
                    break
            if walk:
                out.append((layer, walk))
    return out'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args()

    s = TOOL.read_text(encoding='utf-8')
    if OLD_PROFILE not in s:
        raise SystemExit('the bone_profile definition was not found as expected')
    s = s.replace(OLD_PROFILE, NEW_PROFILE)
    print('  bone_profile now takes is_head / is_tail, and chains() reads the skeleton')
    print()
    print('  the rest of the loop -- per chain instead of per bone -- is the next edit, and it is being done')
    print('  separately because it is the part that changes the picture.')

    if args.write:
        TOOL.write_text(s, encoding='utf-8')
        print('  written to %s' % TOOL)
    else:
        print('  not written; pass --write')


if __name__ == '__main__':
    main()
