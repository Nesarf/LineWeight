"""How wide is the ink, as a share of the picture's own height?

**Why this is not `line_width_library.py`.** That tool builds its figure box from the largest connected mass of ink, which
is right for a corpus of character drawings where head, body and hair touch. Fed this pipeline's own output it refuses
twice: the largest mass is 5 per cent of the ink, and it spans 9 per cent of the height, because the picture is drawn
from more than a thousand separate strokes. Turning those gates off would keep the box wrong, so the comparison needs one
definition of "the picture's height" that both sides can satisfy. It is the bounding box of all the ink: for a line
drawing on white paper that is the figure, and for a line layer that is the area the drawing occupies.

**Why a share and not pixels.** A width in pixels says nothing on its own: the same line at 1000 pixels tall and at 3000
is the same line, and the number triples. Dividing by the ink's own height makes the two comparable without asking
anyone where the figure starts.

**Why the distance transform.** Every skeleton pixel is half a width from the nearest background, so twice the transform
is the line's width there. That is a property of the ink and nothing else -- no brush, no pressure model.

    python tools/width_share.py --glob "E:\\DaShaoHuo\\downloads\\pixiv-senga\\*.jpg" --limit 16
    python tools/width_share.py --glob "cache/paint17/lines.png" --gate none
"""
import argparse
import glob
import os
import statistics as st
import sys

import numpy as np
from scipy import ndimage

sys.path.insert(0, r'E:\lineweight')
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))

import copy_linework as cl


def measure(path, long_side):
    """The ink's width distribution and the height it is quoted against, or None when there is no ink."""
    blob, width, height = cl.load_ink(path, long_side, cl.INK)
    if blob.sum() < 1000:
        return None
    skel = cl.thin(blob)
    if skel.sum() < 100:
        return None
    distance = ndimage.distance_transform_edt(blob)
    widths = 2.0 * distance[skel.astype(bool)]
    ys = np.nonzero(blob)[0]
    span = int(ys.max() - ys.min() + 1)
    if span < 16:
        return None
    median = float(np.median(widths))
    return {
        'width': int(width),
        'height': int(height),
        'skel': int(skel.sum()),
        'median_px': median,
        'p10_px': float(np.percentile(widths, 10)),
        'p90_px': float(np.percentile(widths, 90)),
        'span': span,
        'share': median / span * 100.0,
        'ratio': float(np.percentile(widths, 90)) / max(median, 1e-9),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--glob', required=True)
    ap.add_argument('--limit', type=int, default=0, help='0 means every match')
    ap.add_argument('--long-side', type=int, default=2880,
                    help='the page rule the rest of the tools use, so a width here can be compared with a width there')
    ap.add_argument('--max-share', type=float, default=3.0,
                    help='a share above this is a filled shape rather than a line: report it and leave it out of the summary')
    ap.add_argument('--gate', choices=['on', 'none'], default='on',
                    help='"none" reports every drawing, including the ones the filled-shape gate would drop')
    ap.add_argument('--exclude', default='',
                    help='comma-separated name fragments to leave out, for a folder that mixes line art with colour')
    args = ap.parse_args(argv)

    paths = sorted(glob.glob(args.glob))
    if args.exclude:
        drop = [s.strip() for s in args.exclude.split(',') if s.strip()]
        paths = [p for p in paths if not any(d in os.path.basename(p) for d in drop)]
    if args.limit:
        paths = paths[:args.limit]
    if not paths:
        raise SystemExit('no files match %r' % args.glob)

    rows, skipped = [], []
    print('  %-22s %10s %10s %10s %8s %8s' % ('file', 'median %', 'p10 %', 'p90 %', 'p90/med', 'span'))
    for path in paths:
        r = measure(path, args.long_side)
        name = os.path.basename(path)
        if r is None:
            print('  %-22s no ink, or ink too small to have a width' % name)
            continue
        r['name'] = name
        if args.gate == 'on' and r['share'] > args.max_share:
            skipped.append(r)
            print('  %-22s %9.4f%%  skipped: this is a filled shape, not a line' % (name, r['share']))
            continue
        rows.append(r)
        print('  %-22s %9.4f%% %9.4f%% %9.4f%% %8.2f %8d'
              % (name, r['share'], r['p10_px'] / r['span'] * 100.0, r['p90_px'] / r['span'] * 100.0,
                 r['ratio'], r['span']))

    if not rows:
        raise SystemExit('nothing measured')
    shares = sorted(r['share'] for r in rows)
    ratios = sorted(r['ratio'] for r in rows)
    print()
    print('  %d drawings' % len(rows))
    print('  width / ink height    median %.4f%%   range %.4f%% .. %.4f%%   spread %.2fx'
          % (st.median(shares), shares[0], shares[-1], shares[-1] / max(shares[0], 1e-9)))
    print('  p90 / median          median %.2f     range %.2f .. %.2f'
          % (st.median(ratios), ratios[0], ratios[-1]))
    if skipped:
        print('  skipped %d, all above %.1f%%' % (len(skipped), args.max_share))
    return 0


if __name__ == '__main__':
    sys.exit(main())
