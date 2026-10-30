"""What width does a drawing's ink actually occupy, in units of the figure rather than of the page?

**Why not pixels.** A width in pixels says nothing about a drawing: the same artist's line at 2000 pixels tall and at
4000 is the same line, and the number doubles. The only scale-free quote is against something in the picture, and the
figure's own height is the obvious one -- the corpus already uses head heights for proportion.

**Why the figure's height and not the page's.** A page is a rectangle the artist chose for layout; a figure is what the
drawing is of. The bounding box of the ink is the figure's extent, so `figure height` is read off the ink itself and needs
no other input.

**The measurement is a distance transform, not a stroke model.** Every skeleton pixel is half a width from the nearest
background, so twice the transform is the line's width there, and the median over a whole drawing's skeleton is the
drawing's typical width. That is a property of the ink and nothing else -- no brush, no spacing, no pressure model.

    python tools/line_width_library.py --glob "E:\\DaShaoHuo\\downloads\\pixiv-senga\\*.jpg" --limit 12
"""
import argparse
import json
import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, r'E:\lineweight')
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import copy_linework as cl
from scipy import ndimage

#: Ink is anything darker than this, as 0..255. A line drawing on paper has pale paper and a scanned pencil around 120 to
#: 180, so the threshold sits well above both and below the paper.
INK = 205

#: The head-to-height ratio the corpus uses, so a width can be quoted in head heights as well as in figure heights.
#: **It is an assumption, not a measurement for any particular picture.**
HEADS = 6.5


def ink_mask(gray):
    """The ink, with the page around it removed.

    **The paper is not always white.** A scanned drawing has a grey cast and a photographed one has a shadow, so the
    threshold is relative to the page's own brightness rather than absolute.
    """
    page = float(np.percentile(gray, 90))
    limit = min(INK, page - 25.0)
    return gray < limit


def figure_box(mask):
    """The figure's extent, taken from **the largest connected mass of ink** rather than from all of it.

    **The bounding box of every ink pixel is not the figure.** A drawing with a decorative border, a dense background or a
    stray mark in a corner has ink at every edge of the page, so its box is the page -- and every width divided by that box
    comes out too small. A corpus gathered by a search tag contains many such drawings: the one that exposed this had a
    small character in a white oval surrounded by cross-and-dot ornament, and its "figure height" came out as the whole
    image, which is why a survey of forty drawings reported a spread of nearly four times.

    **The largest single mass is the figure** in a character drawing, because head, body and hair are one connected shape
    while ornament is separate. It fails when the character is drawn as disconnected pieces and the background is one
    connected field, so the returned box is a guess with a reason, not a fact.
    """
    labelled, count = ndimage.label(mask)
    if count == 0:
        return None
    sizes = np.bincount(labelled.ravel())
    sizes[0] = 0
    biggest = int(sizes.argmax())
    mass = labelled == biggest
    rows = np.flatnonzero(mass.any(axis=1))
    cols = np.flatnonzero(mass.any(axis=0))
    if rows.size == 0 or cols.size == 0:
        return None
    return int(rows[0]), int(rows[-1]), int(cols[0]), int(cols[-1])


def widths_of(path, long_side=1600, subpixel=True, regions=None):
    image = Image.open(path).convert('L')
    scale = min(1.0, long_side / float(max(image.size)))
    if scale < 1.0:
        image = image.resize((max(1, int(image.size[0] * scale)), max(1, int(image.size[1] * scale))), Image.LANCZOS)
    gray = np.asarray(image, dtype=np.float32)
    mask = ink_mask(gray)
    box = figure_box(mask)
    if box is None:
        return None
    height = box[1] - box[0] + 1

    # **The skeleton, so the width is sampled on the line rather than in the ink's interior.** Sampled anywhere in the
    # mask, a thick patch would contribute its middle and a hairline its own -- the two would not be comparable.
    skeleton = cl.thin(mask.astype(np.uint8)).astype(bool)
    ys, xs = np.nonzero(skeleton)
    if subpixel:
        widths = subpixel_widths(gray, mask, skeleton)
    else:
        distance = ndimage.distance_transform_edt(mask)
        widths = 2.0 * distance[skeleton]
    keep = widths > 0
    ys, xs, widths = ys[keep], xs[keep], widths[keep]
    if widths.size < 20:
        return None
    result = {
        'name': pathlib.Path(path).name,
        'size': image.size,
        'figure_height': height,
        'skeleton_px': int(widths.size),
        'median': float(np.median(widths)) / height,
        'p10': float(np.percentile(widths, 10)) / height,
        'p90': float(np.percentile(widths, 90)) / height,
    }
    if regions:
        result['by_part'] = {part: assign(ys, xs, widths, spans, image.size) for part, spans in regions.items()}
    return result


def assign(ys, xs, widths, spans, size):
    """The widths of the skeleton points that fall inside one part's boxes.

    **A box, not a traced part.** Labelling which stroke is an eyelash would need a human or a model per stroke; a box
    says "this region of the picture is the eye" and lets every skeleton point inside answer for it. It is coarser than the
    convention's vocabulary and precise enough for the only question being asked -- whether two parts have different
    typical widths.
    """
    width_px, height_px = size
    inside = np.zeros(ys.shape, dtype=bool)
    for box in spans:
        x0, y0, x1, y1 = box
        inside |= ((xs >= x0 * width_px) & (xs <= x1 * width_px)
                   & (ys >= y0 * height_px) & (ys <= y1 * height_px))
    chosen = widths[inside]
    if chosen.size == 0:
        return None
    return {'count': int(chosen.size),
            'median': float(np.median(chosen)),
            'p10': float(np.percentile(chosen, 10)),
            'p90': float(np.percentile(chosen, 90))}


def subpixel_widths(gray, mask, skeleton, half=7):
    """The width at each skeleton pixel, **measured in ink rather than in whole pixels**.

    **Why the distance transform could not answer this.** On a two-pixel line it can only report a half pixel, so the
    measured widths of a drawing's strokes take a handful of values and `p90/median` comes out as 1.00 or 2.00 rather than
    as a number that could be compared with anything. The anti-aliased edge is where the information that was thrown away
    lives: a column that is forty per cent covered is four tenths of a pixel, and JPEG's soft edge carries exactly that.

    **Two directions, and the smaller one wins.** A stroke's true width is what a line drawn across it measures; measuring
    along a stroke instead gives its length. Taking the smaller of the row and column integrals is the cheap way to always
    land on the crossing direction without computing a normal -- wrong only at a junction, where both directions run along
    ink, and a junction is a small share of any drawing's skeleton.
    """
    page = float(np.percentile(gray, 90))
    ink_level = float(np.percentile(gray[mask], 10)) if mask.any() else 0.0
    span = max(page - ink_level, 1.0)
    coverage = np.clip((page - gray) / span, 0.0, 1.0)

    rows = np.cumsum(coverage, axis=0)
    rows = np.vstack([np.zeros((1, coverage.shape[1]), dtype=np.float64), rows])
    cols = np.cumsum(coverage, axis=1)
    cols = np.hstack([np.zeros((coverage.shape[0], 1), dtype=np.float64), cols])

    ys, xs = np.nonzero(skeleton)
    y0 = np.clip(ys - half, 0, coverage.shape[0])
    y1 = np.clip(ys + half + 1, 0, coverage.shape[0])
    x0 = np.clip(xs - half, 0, coverage.shape[1])
    x1 = np.clip(xs + half + 1, 0, coverage.shape[1])
    vertical = rows[y1, xs] - rows[y0, xs]
    horizontal = cols[ys, x1] - cols[ys, x0]
    return np.minimum(vertical, horizontal)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glob', required=True)
    ap.add_argument('--limit', type=int, default=12)
    ap.add_argument('--long-side', type=int, default=1600)
    ap.add_argument('--max-median', type=float, default=0.005,
                    help='reject a drawing whose typical width is this much of the figure height; half a per cent of a '
                         'figure is two hundred pixels of a two-thousand-pixel drawing, which is a filled area and not a '
                         'line. Needed because the corpus is a search result, not a curated set')
    ap.add_argument('--max-ratio', type=float, default=6.0,
                    help='reject a drawing whose p90 is this many times its median; a line drawing stays inside the '
                         'range the corpus measured, while a dark garment fills a whole region')
    ap.add_argument('--regions', default='',
                    help='a JSON file of {part: [[x0,y0,x1,y1], ...]} with the boxes as fractions of the image, so the '
                         'widths can be reported by part of the body rather than as one pooled number')
    args = ap.parse_args()

    regions = None
    if args.regions:
        regions = json.loads(pathlib.Path(args.regions).read_text(encoding='utf-8'))
        print('  parts: %s' % ', '.join(sorted(regions)))

    folder = pathlib.Path(args.glob).parent
    files = sorted(folder.glob(pathlib.Path(args.glob).name))[:args.limit]
    print('  %-26s %9s %9s %9s %9s' % ('file', 'median', 'p10', 'p90', 'p90/median'))
    rows = []
    rejected = []
    for path in files:
        try:
            result = widths_of(path, args.long_side, regions=regions)
        except Exception as problem:  # a corrupt or unusual file must not stop the survey
            print('  %-26s %s' % (path.name[:26], problem))
            continue
        if result is None:
            print('  %-26s (too little ink)' % path.name[:26])
            continue
        ratio = result['p90'] / max(result['median'], 1e-9)
        if result['median'] > args.max_median or ratio > args.max_ratio:
            rejected.append((path.name, result['median'], ratio))
            continue
        rows.append(result)
        print('  %-26s %8.4f%% %8.4f%% %8.4f%% %9.2f'
              % (path.name[:26], 100 * result['median'], 100 * result['p10'],
                 100 * result['p90'], ratio))

    if rejected:
        print()
        print('  rejected %d of %d as not line art:' % (len(rejected), len(rejected) + len(rows)))
        for name, median, ratio in rejected[:8]:
            print('    %-26s median %6.3f%%  p90/median %5.2f' % (name[:26], 100 * median, ratio))

    if len(rows) >= 2:
        medians = np.array([r['median'] for r in rows])
        ratios = np.array([r['p90'] / max(r['median'], 1e-9) for r in rows])
        print()
        print('  %d drawings' % len(rows))
        print('  median width / figure height: median of medians %.4f%%   range %.4f%% .. %.4f%%   spread %.2fx'
              % (100 * np.median(medians), 100 * medians.min(), 100 * medians.max(),
                 medians.max() / max(medians.min(), 1e-9)))
        print('  p90/median within one drawing: median %.2f   range %.2f .. %.2f'
              % (np.median(ratios), ratios.min(), ratios.max()))
        print('  in head heights (assuming %s heads): typical line is %.3f%% of a head'
              % (HEADS, 100 * np.median(medians) * HEADS))

        if regions:
            # **The only question this table has to answer.** If two parts of a body do not have different typical widths,
            # then "what line for what part" is not a table at all and the whole exercise is a way of writing down a
            # number that carries no information. The threshold is a ratio of medians, so it does not depend on how large
            # the drawings are or on the units.
            pooled = {}
            for row in rows:
                for part, stats in (row.get('by_part') or {}).items():
                    if stats:
                        pooled.setdefault(part, []).append(stats['median'])
            print()
            print('  %-16s %5s %12s %12s' % ('part', 'n', 'median', 'as head %'))
            summary = {}
            for part in sorted(pooled):
                values = np.array(pooled[part])
                summary[part] = float(np.median(values))
                print('  %-16s %5d %11.4f%% %11.3f%%'
                      % (part, values.size, 100 * np.median(values),
                         100 * np.median(values) * HEADS / np.median(medians) if np.median(medians) else 0))
            if len(summary) >= 2:
                low = min(summary.values())
                high = max(summary.values())
                print()
                print('  widest part is %.2f x the narrowest (%s over %s)'
                      % (high / max(low, 1e-9),
                         ', '.join(p for p, v in summary.items() if v == high),
                         ', '.join(p for p, v in summary.items() if v == low)))
                print('  %s the 1.5x threshold that would make a part table worth having'
                      % ('PASSES' if high / max(low, 1e-9) >= 1.5 else 'FAILS'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
