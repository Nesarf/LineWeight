"""Score a trace against its reference: how much of the ink is in the wrong place.

**The measure, stated before it is used.** Both pictures are read as "where is there ink" -- dark enough to be a mark --
and compared pixel for pixel:

    difference = pixels where exactly one of the two has ink, divided by the reference's ink pixels

**Symmetric difference over the reference's own count**, so a trace that draws too much and one that draws too little are
both penalised, and neither is rewarded for the part of the page it got right by leaving blank. A threshold of one per
cent means the two ink masks differ on one pixel in a hundred.

**Both sides are read with the same rule.** The reference's pencil line is grey and the rendering's is near black, but
both are below the same threshold, and the paper on both is above it -- so the comparison is of positions, not of tones.

    python tools/copy_score.py --reference "F:\\素材\\图\\16+\\Cache_7cef975685e2f0c2.png" --render run1/final.png
"""
import argparse
import pathlib

import numpy as np
from PIL import Image

#: Ink is anything darker than this, out of 255. **The same number for both pictures**, because the question is where
#: the marks are and not how dark they are.
INK = 205


def ink_mask(path, size, dilate=0, line_only=False):
    """Where the marks are, **binarised before scaling and not after**.

    **The order is the whole reason the first numbers were nonsense.** Scaling a greyscale drawing down with any
    resampling spreads each line into a grey halo, and a threshold applied afterwards counts the halo as ink -- one
    reference went from 1.9 per cent ink to 34 per cent that way. Binarise at the original size, then take the mask down
    with nearest neighbour, and the amount of ink is preserved instead of smeared.

    `line_only` keeps the thin marks and drops the filled patches, which is what a comparison against a traced line
    layer needs: the reference's dark clothing is a filled area, and the trace draws lines, so comparing them as they
    are compares two different things and reports the difference as an error.
    """
    from scipy import ndimage
    img = Image.open(path).convert('L')
    arr = np.asarray(img, dtype=np.uint8)
    mask = arr < INK
    if line_only:
        from copy_linework import ink_weight, FILL_HALF
        weight = ink_weight(mask.astype(np.uint8))
        mask = mask & (weight <= FILL_HALF)
    if size and img.size != size:
        scaled = Image.fromarray((mask * 255).astype(np.uint8)).resize(size, Image.NEAREST)
        mask = np.asarray(scaled) > 127
    if dilate:
        mask = ndimage.binary_dilation(mask, iterations=dilate)
    return mask


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reference', required=True)
    ap.add_argument('--render', required=True)
    ap.add_argument('--ink', type=int, default=INK)
    ap.add_argument('--tolerance', type=int, default=0,
                    help='pixels of slack allowed between the two masks, in render pixels')
    ap.add_argument('--line-only', action='store_true',
                    help='compare lines against lines: drop the reference\'s filled patches')
    ap.add_argument('--limit', type=float, default=0.01)
    args = ap.parse_args()

    ref_img = Image.open(args.reference)
    size = ref_img.size
    ref = ink_mask(args.reference, size, line_only=args.line_only)
    drawn = ink_mask(args.render, size)
    if args.tolerance:
        from scipy import ndimage
        structure = np.ones((3, 3), dtype=bool)
        ref_t = ndimage.binary_dilation(ref, structure=structure, iterations=args.tolerance)
        drawn_t = ndimage.binary_dilation(drawn, structure=structure, iterations=args.tolerance)
        # **Slack in both directions**, so a line drawn one pixel to the side of the reference's is not counted twice.
        only_ref = ref & ~drawn_t
        only_drawn = drawn & ~ref_t
    else:
        only_ref = ref & ~drawn
        only_drawn = drawn & ~ref

    ref_count = int(ref.sum())
    drawn_count = int(drawn.sum())
    missed = int(only_ref.sum())
    extra = int(only_drawn.sum())
    if not ref_count:
        print('  the reference has no ink at this threshold')
        return 1
    wrong = missed + extra
    share = wrong / float(ref_count)
    print('  reference ink %d px, rendered ink %d px  (render is %.1f%% of the reference\'s amount)'
          % (ref_count, drawn_count, 100.0 * drawn_count / ref_count))
    print('  missing %d px, extra %d px, wrong place total %d px' % (missed, extra, wrong))
    print('  difference %.4f of the reference ink   limit %.4f' % (share, args.limit))
    if share <= args.limit:
        print('  within the limit: the two ink masks agree on ninety-nine pixels in a hundred or more')
        return 0
    print('  over the limit by %.4f' % (share - args.limit))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
